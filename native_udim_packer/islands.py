# SPDX-License-Identifier: GPL-2.0-or-later
"""Pure-bmesh UV island utilities for Blender 5.x.

Blender 5.x removed ``bmesh.from_object``; edit-mode geometry is accessed with
``bmesh.from_edit_mesh(mesh)`` and written back with ``bmesh.update_edit_mesh``.
BMesh element sequences are not directly iterable in 5.x: iterate with
``tuple(seq)`` and only index after ``ensure_lookup_table()``.

Everything here works on a live bmesh + its active UV layer, so the same code
serves the packer (edit mode) and tests (headless edit mode).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Two loops sharing an edge are "connected" (same island) when their UV
# coordinates match within this tolerance; otherwise the edge is a UV seam.
UV_SEAM_EPS = 1e-6


@dataclass(eq=False)
class Island:
    """One connected group of faces in UV space (seam-aware)."""

    face_indices: set          # int, bmesh face indices (valid while bm alive)
    uv_area: float = 0.0       # total signed-magnitude area in UV space
    world_area: float = 0.0    # total mesh area in object/local space
    centroid: tuple = (0.0, 0.0)   # UV-space center used for transforms
    min_uv: tuple = (0.0, 0.0)
    max_uv: tuple = (0.0, 0.0)
    norm_scale: float | None = 1.0  # optional pre-scale applied by the packer


def detect_islands(bm, uvl) -> list[Island]:
    """Detect UV islands via seam-aware union-find over bmesh faces.

    Connectivity rules (the standard definition of a UV island):
      * all loops of one face belong to the same island;
      * two faces across a shared edge are connected only when BOTH shared
        vertices have (nearly) identical UV coordinates in the two faces,
        i.e. the edge is NOT a UV seam.  A boundary edge connects nothing.

    Corner matching must compare explicit per-vertex positions: for a
    consistently wound manifold the two ``edge.link_loops`` start at
    *opposite* ends of the shared edge, so comparing their UVs directly
    tests mismatched corners and never merges across an edge (every face
    would become its own island).

    Returns one :class:`Island` per connected group with measured stats.
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    bm.faces.ensure_lookup_table()
    faces = tuple(bm.faces)

    # Per-face map of vertex index -> UV corner position.
    face_uv: dict[int, dict[int, tuple[float, float]]] = {}
    for f in faces:
        corners: dict[int, tuple[float, float]] = {}
        for l in tuple(f.loops):
            u = l[uvl].uv
            corners[l.vert.index] = (u.x, u.y)
        face_uv[f.index] = corners

    # Across edges: connect the two faces only when both shared corners match.
    bm.edges.ensure_lookup_table()
    for e in tuple(bm.edges):
        fl = tuple(e.link_faces)
        if len(fl) != 2:
            continue
        c1 = face_uv[fl[0].index]
        c2 = face_uv[fl[1].index]
        connected = True
        for v in e.verts:
            a = c1.get(v.index)
            b = c2.get(v.index)
            if (a is None or b is None
                    or abs(a[0] - b[0]) >= UV_SEAM_EPS
                    or abs(a[1] - b[1]) >= UV_SEAM_EPS):
                connected = False
                break
        if connected:
            union(fl[0].index, fl[1].index)

    # Group faces by root.
    groups: dict[int, set[int]] = {}
    for f in faces:
        groups.setdefault(find(f.index), set()).add(f.index)

    islands: list[Island] = []
    for fidx_set in groups.values():
        isl_faces = [f for f in faces if f.index in fidx_set]
        uv_area = 0.0
        world_area = 0.0
        minx = miny = math.inf
        maxx = maxy = -math.inf
        cu = cv = 0.0          # area-weighted centroid accumulator
        for f in isl_faces:
            loops = tuple(f.loops)
            n = len(loops)
            # Shoelace area of the face's UV polygon (magnitude).
            a2 = 0.0
            for i in range(n):
                u1 = loops[i][uvl].uv
                u2 = loops[(i + 1) % n][uvl].uv
                a2 += u1.x * u2.y - u2.x * u1.y
            fa = abs(a2) * 0.5
            wfa = f.calc_area()      # local-space face area
            uv_area += fa
            world_area += wfa
            for l in loops:
                u = l[uvl].uv
                if u.x < minx:
                    minx = u.x
                if u.x > maxx:
                    maxx = u.x
                if u.y < miny:
                    miny = u.y
                if u.y > maxy:
                    maxy = u.y
            # Per-face UV centroid (loop average) weighted by UV area.
            fu = sum(l[uvl].uv.x for l in loops) / n
            fv = sum(l[uvl].uv.y for l in loops) / n
            w = fa if fa > 1e-12 else 1e-9
            cu += fu * w
            cv += fv * w
        tw = uv_area if uv_area > 1e-12 else 1.0
        islands.append(Island(
            face_indices=fidx_set,
            uv_area=uv_area,
            world_area=world_area,
            centroid=(cu / tw, cv / tw),
            min_uv=(minx, miny) if math.isfinite(minx) else (0.0, 0.0),
            max_uv=(maxx, maxy) if math.isfinite(maxx) else (0.0, 0.0),
        ))
    return islands


def selected_island_faces(bm, uvl) -> set[int]:
    """Face indices of every island that has at least one UV-selected face.

    Blender 5.x stores UV-editor selection as a per-face ``uv_select`` flag
    on the edit bmesh (the pre-5 loop-level select flags are gone), so an
    island counts as selected when ANY of its faces carries it: clicking in
    ISLANDS mode selects all of an island's faces, and a partial (box/face)
    selection still selects the whole island, because islands are atomic
    packing units - they can never be split across tiles.  Must run on a
    live edit bmesh; selection flags do not exist in object mode.
    """
    islands = detect_islands(bm, uvl)
    face_by_index = {f.index: f for f in tuple(bm.faces)}
    sel: set[int] = set()
    for isl in islands:
        for fi in isl.face_indices:
            if face_by_index[fi].uv_select:
                sel |= isl.face_indices
                break
    return sel

