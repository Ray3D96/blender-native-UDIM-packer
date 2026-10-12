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


def _pip(pt: tuple, poly: tuple) -> bool:
    """Ray-casting point-in-polygon (pure Python)."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _shoelace(poly: tuple) -> float:
    """Signed area of a polygon loop (positive for CCW winding)."""
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s * 0.5


def island_outline(bm, uvl, face_indices: set[int]) -> tuple[list[tuple], list[tuple]]:
    """Extract the real boundary of one island in UV space.

    Returns ``(outers, holes)``: two lists of loops, each loop a tuple of
    ``(x, y)`` points (absolute UV coordinates).  ``outers`` are the outer
    boundary loops; ``holes`` are interior voids nested inside an outer.

    Method: an edge instance belongs to the island boundary when no other
    face instance of the same geometric edge carries matching UVs at both
    shared corners (the seam-aware rule used by :func:`detect_islands`).
    Boundary half-edges are walked into closed loops; each loop is then
    classified outer vs hole by centroid nesting against larger loops.

    The result feeds the shape-aware layout solver, which can pack into
    concavities and holes instead of treating islands as rectangles.
    """
    faces = [f for f in tuple(bm.faces) if f.index in face_indices]
    groups: dict[frozenset, list[tuple]] = {}
    for f in faces:
        ls = tuple(f.loops)
        n = len(ls)
        for i in range(n):
            a = ls[i].vert.index
            b = ls[(i + 1) % n].vert.index
            ua = (ls[i][uvl].uv.x, ls[i][uvl].uv.y)
            ub = (ls[(i + 1) % n][uvl].uv.x, ls[(i + 1) % n][uvl].uv.y)
            groups.setdefault(frozenset((a, b)), []).append(
                (f.index, i, a, b, ua, ub))

    boundary = []
    for insts in groups.values():
        if len(insts) == 1:
            boundary.append(insts[0])
            continue
        used = [False] * len(insts)
        for i in range(len(insts)):
            if used[i]:
                continue
            f1, _li, a1, b1, ua1, ub1 = insts[i]
            matched = False
            for j in range(i + 1, len(insts)):
                if used[j]:
                    continue
                _f2, _lj, a2, b2, ua2, ub2 = insts[j]
                if ((a2, b2) == (b1, a1)
                        and abs(ua2[0] - ub1[0]) < UV_SEAM_EPS
                        and abs(ua2[1] - ub1[1]) < UV_SEAM_EPS
                        and abs(ub2[0] - ua1[0]) < UV_SEAM_EPS
                        and abs(ub2[1] - ua1[1]) < UV_SEAM_EPS):
                    used[i] = used[j] = True
                    matched = True
                    break
            if not matched:
                boundary.append(insts[i])
                used[i] = True

    # Walk boundary half-edges into closed loops.
    starts: dict[int, list[tuple]] = {}
    for be in boundary:
        starts.setdefault(be[2], []).append(be)
    loops = []
    while any(starts.values()):
        startv = next(v for v, lst in starts.items() if lst)
        cur = starts[startv].pop()
        pts = [cur[4]]
        while True:
            opts = starts.get(cur[3], [])
            if not opts:
                break
            cur = opts.pop(0)
            pts.append(cur[4])
        if len(pts) >= 3:
            loops.append(tuple(pts))

    # Classify outer vs hole by centroid nesting against larger loops.
    info = []
    for lp in loops:
        area = _shoelace(lp)
        cx = sum(p[0] for p in lp) / len(lp)
        cy = sum(p[1] for p in lp) / len(lp)
        info.append((abs(area), (cx, cy), lp))
    info.sort(key=lambda t: -t[0])
    outers: list[tuple] = []
    holes: list[tuple] = []
    for _a, c, lp in info:
        if any(_pip(c, o) for o in outers):
            holes.append(lp)
        else:
            outers.append(lp)
    return outers, holes


def island_bounds(bm, uvl, face_indices: set[int]) -> tuple[float, float, float, float]:
    """Current (minx, miny, maxx, maxy) UV bounds of the given faces."""
    minx = miny = math.inf
    maxx = maxy = -math.inf
    for f in tuple(bm.faces):
        if f.index in face_indices:
            for l in tuple(f.loops):
                u = l[uvl].uv
                if u.x < minx:
                    minx = u.x
                if u.x > maxx:
                    maxx = u.x
                if u.y < miny:
                    miny = u.y
                if u.y > maxy:
                    maxy = u.y
    if not math.isfinite(minx):
        return (0.0, 0.0, 0.0, 0.0)
    return (minx, miny, maxx, maxy)


def translate_faces(bm, uvl, face_indices: set[int], du: float, dv: float) -> None:
    """Shift the UVs of the given faces by (du, dv). Call update_edit_mesh after."""
    for f in tuple(bm.faces):
        if f.index in face_indices:
            for l in tuple(f.loops):
                u = l[uvl].uv
                u.x += du
                u.y += dv


def scale_faces_about(bm, uvl, face_indices: set[int], s: float, center: tuple) -> None:
    """Uniformly scale the UVs of the given faces about ``center`` (u, v)."""
    if abs(s - 1.0) < 1e-9:
        return
    cx, cy = center
    for f in tuple(bm.faces):
        if f.index in face_indices:
            for l in tuple(f.loops):
                u = l[uvl].uv
                u.x = cx + s * (u.x - cx)
                u.y = cy + s * (u.y - cy)


def rotate_faces_90(bm, uvl, face_indices: set[int], steps: int, center: tuple | None = None) -> None:
    """Rotate the UVs of the given faces by ``steps`` x 90 degrees counter-clockwise.

    ``steps`` in {1, 2, 3}. When ``center`` is None the island's own bounds
    center is used. This is the manual fallback for the native CARDINAL
    rotation (used only if ``uv.pack_islands`` cannot run).
    """
    steps %= 4
    if steps == 0:
        return
    if center is None:
        minx, miny, maxx, maxy = island_bounds(bm, uvl, face_indices)
        center = ((minx + maxx) * 0.5, (miny + maxy) * 0.5)
    cx, cy = center
    for f in tuple(bm.faces):
        if f.index in face_indices:
            for l in tuple(f.loops):
                u = l[uvl].uv
                dx, dy = u.x - cx, u.y - cy
                if steps == 1:      # 90 deg CCW
                    nx, ny = -dy, dx
                elif steps == 2:    # 180 deg
                    nx, ny = -dx, -dy
                else:               # 270 deg CCW (= 90 CW)
                    nx, ny = dy, -dx
                u.x = cx + nx
                u.y = cy + ny


def place_island_into(bm, uvl, face_indices: set[int], target_aabb: tuple,
                      scale: float = 1.0, rotate_steps: int = 0) -> None:
    """Scale (and optionally 90-deg rotate) an island about its bounds center,
    then translate it so its UV bounding box equals ``target_aabb``
    ``(minx, miny, maxx, maxy)``. Used by the manual shelf-packing fallback."""
    minx, miny, maxx, maxy = island_bounds(bm, uvl, face_indices)
    cx, cy = (minx + maxx) * 0.5, (miny + maxy) * 0.5
    if abs(scale - 1.0) > 1e-9:
        scale_faces_about(bm, uvl, face_indices, scale, (cx, cy))
    if rotate_steps % 4:
        rotate_faces_90(bm, uvl, face_indices, rotate_steps % 4, (cx, cy))
    minx, miny, maxx, maxy = island_bounds(bm, uvl, face_indices)
    tx0, ty0, tx1, ty1 = target_aabb
    translate_faces(bm, uvl, face_indices, tx0 - minx, ty0 - miny)
