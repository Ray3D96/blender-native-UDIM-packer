# SPDX-License-Identifier: GPL-3.0-or-later
"""UDIM grid packing pipeline: one global uniform scale + native placement.

Strategy (v4, validated against Blender 5.2):

All objects are treated as one shared texture set.  Their islands are
pooled and a single layout is solved for the whole pool, so no two
islands ever overlap - even when they belong to different objects.

1. Detect UV islands with :mod:`native_udim_packer.islands` (seam-aware)
   on read-only object-mode bmeshes, and snapshot each face's original UV
   coordinates once.  No outline extraction: shape handling is delegated
   to the packer below.
2. With "normalize" enabled, compute each island's equalizing scale
   ``norm_scale = sqrt((total_uv / total_3d) * 3d_area_i / uv_area_i)`` -
   but do NOT pre-apply it; it only feeds the reference sizes and the
   final writeback.
3. Solve the layout (:mod:`native_udim_packer.layout`): islands are
   assigned to tiles with sequential first-fit-decreasing (tile 1001 is
   filled before 1002 opens, and so on), and a shrinking search finds the
   largest global scale ``S*`` for which every tile's content fits.  Each
   search round *is* a real placement: every used tile is packed with
   Blender's built-in ``bpy.ops.uv.pack_islands`` (C speed, shape-aware,
   no overlaps by construction), and the measured post-pack extent of each
   tile is the feasibility oracle.  The final round leaves the finished
   layout in place - there is no separate writeback pass.
    4. Re-center + grow: every used tile's content is re-centered on its
       tile center, then all tiles are scaled by one uniform factor limited
       by the tightest tile/axis (``layout.final_growth_factor``), so the
       finished layout maxes out the bottleneck UDIM while keeping texel
       density equal across tiles.  One similarity transform per tile, so
       no new overlaps are possible.

Consequences:

* Relative sizes between islands are preserved exactly.  With normalize
  on, every island ends up with the same texel density across all objects
  - the same guarantee as Blender's built-in "Average Islands Scale".
  With normalize off, any scale equalization the user performed
  beforehand is left untouched (one uniform factor is applied to
  everything).
* ``S*`` is the largest uniform scale for which the native packer
  confirms every tile fits by measurement.  Used tiles are filled as
  densely as the packer allows, sequentially from 1001 upward; when total
  content exceeds grid capacity everything shrinks uniformly and
  proportions stay intact.  The reported ``global_scale`` is the effective
  scale actually written: ``S*`` times the final re-center/growth factor
  (reported separately as ``stretch_factor``).
* "90 degree rotation" ON lets the native packer rotate individual
  islands by 90 degrees (cardinal directions) when that saves space; OFF
  keeps every island in its current orientation.

Each used tile is packed in a single multi-object edit session that covers
every object contributing islands to that tile, with exactly one
``uv.pack_islands`` call per tile: the native packer then places all of
the tile's islands - from all objects - together, which is what makes
cross-object overlap impossible.  The original selection and active object
are restored afterwards.  Objects hidden from the view layer are
temporarily exposed for the duration of their edit session (the built-in
packer refuses to run on invisible objects) and their visibility state is
restored afterwards.  Only bpy/bmesh and built-in operators are used; no
external processes.
"""
from __future__ import annotations

import math

import bpy
import bmesh

from .islands import (
    Island,
    detect_islands,
    selected_island_faces,
)
from .layout import Item as _LayoutItem
from .layout import PackRefusedError as _PackRefusedError
from .layout import final_growth_factor as _final_growth_factor
from .layout import tile_islands_overlap as _tile_islands_overlap
from .layout import solve as _layout_solve
from .layout import tile_order as _tile_order


def udim_number(tile_u: int, tile_v: int) -> int:
    """UDIM id for a tile using the standard UDIM convention.

    (0,0)=1001, (1,0)=1002 ... (9,0)=1010 across a row, and each higher row
    adds 10: (0,1)=1011, (0,2)=1021.  A UDIM row is therefore 10 tiles wide,
    so the grid X dimension must stay <= 10 (enforced by the operator).
    """
    return 1001 + tile_u + tile_v * 10


def normalize_scales(islands: list[Island]) -> float | None:
    """Set ``island.norm_scale`` so texel density is equalized.

    Every island is scaled about its centroid by
    ``sqrt( (total_uv / total_3d) * 3d_area_i / uv_area_i )``, which makes
    ``uv_area / 3d_area`` identical for all islands while preserving the
    overall UV footprint.  Degenerate islands are left untouched (scale 1).

    Returns the number of islands actually rescaled, or None when no
    island has a usable area pair.
    """
    total_uv = sum(i.uv_area for i in islands)
    total_3d = sum(i.world_area for i in islands)
    if total_uv <= 1e-12 or total_3d <= 1e-12:
        return None
    changed = 0
    for i in islands:
        if i.uv_area > 1e-12 and i.world_area > 1e-12:
            i.norm_scale = math.sqrt((total_uv / total_3d)
                                     * (i.world_area / i.uv_area))
            changed += 1
    return changed


# --------------------------------------------------------------------------
# edit-session helpers
# --------------------------------------------------------------------------

def _expose_in_view_layer(ob) -> list:
    """Temporarily make ``ob`` visible in the current view layer.

    The built-in ``uv.pack_islands`` operator refuses to run on objects
    that are not visible in the view layer (it returns CANCELLED).  This
    clears every visibility blocker - the object's own viewport flags and
    any excluded or hidden collection it lives in - and returns a list of
    restore callables.  The caller must run them (in reverse order) once
    the object's edit session is over, so the user's visibility state is
    left exactly as found.
    """
    undo: list = []
    if ob.hide_viewport:
        ob.hide_viewport = False
        undo.append(lambda o=ob: setattr(o, "hide_viewport", True))
    try:
        if ob.hide_get():
            ob.hide_set(False)
            undo.append(lambda o=ob: o.hide_set(True))
    except RuntimeError:
        pass  # not in the view layer at all; _enter_edit will report it

    targets = {c.name for c in ob.users_collection}

    def walk(lc, path):
        path = path + [lc]
        if lc.collection.name in targets:
            for node in path:
                if node.exclude:
                    node.exclude = False
                    undo.append(lambda n=node: setattr(n, "exclude", True))
                if node.hide_viewport:
                    node.hide_viewport = False
                    undo.append(
                        lambda n=node: setattr(n, "hide_viewport", True))
                if node.collection.hide_viewport:
                    node.collection.hide_viewport = False
                    undo.append(lambda c=node.collection:
                                setattr(c, "hide_viewport", True))
        for ch in lc.children:
            walk(ch, path)

    walk(bpy.context.view_layer.layer_collection, [])
    return undo


def _enter_edit(ob) -> bool:
    """Enter edit mode on ``ob``.  Returns True when this call entered it.

    If some other object is currently being edited, that session is
    exited first (its UV state is already committed to the mesh data);
    the caller restores the original edit state afterwards.
    """
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    return True


def _enter_multi_edit(obs: list) -> None:
    """Enter a multi-object edit session on every object in ``obs``.

    Committing any open session first works the same way as for a single
    object: the UV state of the previous session is already in the mesh
    data when it is exited.
    """
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode='EDIT')
    # The built-in packer's selection gate only honors face selection in
    # FACE select mode, and headless sessions do not guarantee that the
    # session starts in it (a non-FACE default makes uv.pack_islands
    # cancel silently).  Set it explicitly; the state is session-scoped.
    bpy.ops.mesh.select_mode(type="FACE")


def _exit_edit() -> None:
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _finish(started_in_edit: bool, saved_selection: list, original_active,
            toolsettings: dict | None = None,
            uv_selection: dict | None = None) -> None:
    """Restore the selection (and edit mode) as found before packing.

    ``uv_selection`` maps object name to the face indices that carried the
    UV-editor selection flag when packing started; the per-tile pack
    sessions clobber face/UV selection, so the original UV selection is
    re-applied once we are back in (multi-)edit mode.  Face indices are
    stable because packing never changes topology.
    """
    bpy.ops.object.select_all(action='DESELECT')
    for name in saved_selection:
        ob = bpy.data.objects.get(name)
        if ob is not None:
            try:
                ob.select_set(True)
            except RuntimeError:
                pass
    if original_active is not None and original_active.name in bpy.data.objects:
        bpy.context.view_layer.objects.active = original_active
    if started_in_edit:
        if (bpy.context.object is not None
                and bpy.context.object.mode != 'EDIT'):
            try:
                bpy.ops.object.mode_set(mode='EDIT')
            except RuntimeError:
                pass
        if uv_selection:
            for name, want in uv_selection.items():
                ob = bpy.data.objects.get(name)
                if ob is None or ob.mode != 'EDIT':
                    continue
                try:
                    bm = bmesh.from_edit_mesh(ob.data)
                except RuntimeError:
                    continue
                try:
                    want_set = set(want)
                    for f in tuple(bm.faces):
                        f.uv_select = (f.index in want_set)
                    bmesh.update_edit_mesh(ob.data)
                finally:
                    bm.free()
    if toolsettings is not None:
        ts = bpy.context.scene.tool_settings
        for key, val in toolsettings.items():
            setattr(ts, key, val)


# --------------------------------------------------------------------------
# island bookkeeping
# --------------------------------------------------------------------------

def _detect_object(ob):
    """Detect islands on ``ob`` (object mode).  None when no UV layer."""
    me = ob.data
    if me.uv_layers is None or len(me.uv_layers) == 0:
        return None
    bm = bmesh.new()
    bm.from_mesh(me)
    try:
        uvl = bm.loops.layers.uv.active
        islands = detect_islands(bm, uvl)
        return islands or None
    finally:
        bm.free()


def _capture_edit_selection(ob):
    """(selected-island face set, UV-selected face indices) from a live edit.

    Blender 5.x keeps UV-editor selection in per-face ``uv_select`` flags on
    the edit bmesh - they are discarded when the session is exited - so this
    must run while ``ob`` is still in an edit session (callers check
    ``ob.mode == 'EDIT'`` first; otherwise ``bmesh.from_edit_mesh`` raises
    RuntimeError).  The first value expands the selection to whole islands
    (the packing granularity); the second keeps the raw selected faces so
    the exact pre-pack selection can be restored.  Returns ``(None, None)``
    when the object has no UV layer.
    """
    me = ob.data
    if me.uv_layers is None or len(me.uv_layers) == 0:
        return None, None
    bm = bmesh.from_edit_mesh(me)
    try:
        uvl = bm.loops.layers.uv.active
        if uvl is None:
            return None, None
        faces = selected_island_faces(bm, uvl)
        raw = [f.index for f in tuple(bm.faces) if f.uv_select]
        return faces, raw
    finally:
        bm.free()


def _snapshot_uv(me) -> dict[int, list]:
    """Original UVs per face: ``{face_index: [(x, y), ...]}`` in loop order.

    Topology never changes during packing (move/scale/rotate only), so
    polygon indices and their loop layout are stable across edit
    sessions - plain data is enough to restore or re-place any island.
    """
    uvl = me.uv_layers.active.data
    out: dict[int, list] = {}
    for p in me.polygons:
        out[p.index] = [tuple(uvl[p.loop_start + j].uv)
                        for j in range(p.loop_total)]
    return out


# --------------------------------------------------------------------------
# one search round: place everything at scale S with the native packer
# --------------------------------------------------------------------------

def _execute_round(state: list, assign: dict, positions: list, S: float,
                   rotate_90: bool, margin: float,
                   static_polys: list | None = None) -> list:
    """Place every island at global scale ``S`` (native per-tile packing).

    Each used tile is packed with exactly one ``uv.pack_islands`` call,
    inside a multi-object edit session covering every object that
    contributes islands to the tile; the native packer therefore places
    all of a tile's islands - from all objects - together, so cross-
    object overlap in shared tiles is impossible.

    ``static_polys`` (selected-islands mode) is a list of the untouched
    islands, each a list of its face polygons in global UV space: they
    never move, but packed content must not land on top of them, so each
    tile's exact overlap check also verifies against them (shifted into
    that tile's local 0..1 space).

    Returns measured post-pack extents per used tile as a list indexed by
    row-major tile position (``None`` for unused tiles), in 0..1 UV space
    before the integer tile offset.  Raises PackRefusedError when a tile
    pack is cancelled or produces overlapping islands (the scale search
    then retries at a smaller scale); other failures raise RuntimeError
    and abort the whole pack, with the caller restoring the original UVs
    from the snapshots.
    """
    n_tiles = len(positions)
    extents: list = [None] * n_tiles

    # Per-tile membership: which objects contribute islands to each tile.
    # Every face belongs to exactly one island, hence to exactly one tile,
    # so running one session per used tile covers every face of every
    # object in this round.
    members_by_tile: dict[int, list] = {}
    for s in state:
        for t in {assign[i._item_index] for i in s["islands"]}:
            members_by_tile.setdefault(t, []).append(s)

    for t in sorted(members_by_tile):
        members = members_by_tile[t]
        obs = [s["ob"] for s in members]
        undo_vis: list = []
        for ob in obs:
            undo_vis.extend(_expose_in_view_layer(ob))
        try:
            # One multi-object edit session per tile: every involved object
            # is edited together, so the single pack_islands call below sees
            # all of the tile's islands at once and places them with mutual
            # avoidance - content from different objects in a shared tile
            # can never overlap.
            _enter_multi_edit(obs)

            # Write this round's scaled UVs and select exactly each object's
            # tile-t faces; commit every mesh before the operator runs.
            fsets: dict[str, set] = {}
            for s in members:
                ob, snap = s["ob"], s["snapshot"]
                face_map: dict[int, list] = {}
                for i in s["islands"]:
                    if assign[i._item_index] != t:
                        continue
                    k = i._s_norm * S
                    minx0, miny0 = i.min_uv[0], i.min_uv[1]
                    for fi in i.face_indices:
                        face_map[fi] = [((x - minx0) * k, (y - miny0) * k)
                                        for (x, y) in snap[fi]]
                fset = set(face_map)
                fsets[ob.name] = fset
                me = ob.data
                bm = bmesh.from_edit_mesh(me)
                try:
                    uvl = bm.loops.layers.uv.active
                    for f in tuple(bm.faces):
                        uv_list = face_map.get(f.index)
                        if uv_list is not None:
                            for l, (x, y) in zip(tuple(f.loops), uv_list):
                                l[uvl].uv = (x, y)
                        f.select = (f.index in fset)
                    bmesh.update_edit_mesh(me)
                finally:
                    bm.free()

            r = bpy.ops.uv.pack_islands(
                rotate=rotate_90, rotate_method="CARDINAL",
                margin=margin, scale=False)
            if r != {'FINISHED'}:
                # The native operator cancels silently (no report) when its
                # toolsettings-dependent selection gate finds nothing to
                # pack.  Refuse the round so the scale search can retry;
                # visibility is the usual remaining cause.
                raise _PackRefusedError(
                    f"uv.pack_islands returned {r} while packing tile "
                    f"{udim_number(*positions[t])}; every involved object "
                    f"({', '.join(o.name for o in obs)}) must be visible "
                    f"in the view layer with an active UV map")

            # Fresh handles after the operator (it may rebuild the edit
            # bmesh): read every member's tile-t faces in 0..1 space
            # (pre-offset), measure the union extent, and keep each face's
            # polygon for the exact overlap check below.
            tu, tv = positions[t]
            minx = miny = math.inf
            maxx = maxy = -math.inf
            face_polys: dict[str, dict[int, list]] = {}
            for s in members:
                ob = s["ob"]
                me = ob.data
                fset = fsets[ob.name]
                bm = bmesh.from_edit_mesh(me)
                try:
                    uvl = bm.loops.layers.uv.active
                    polys: dict[int, list] = {}
                    for f in tuple(bm.faces):
                        if f.index not in fset:
                            continue
                        poly = [(l[uvl].uv.x, l[uvl].uv.y)
                                for l in tuple(f.loops)]
                        polys[f.index] = poly
                        for (x, y) in poly:
                            if x < minx:
                                minx = x
                            if x > maxx:
                                maxx = x
                            if y < miny:
                                miny = y
                            if y > maxy:
                                maxy = y
                    face_polys[ob.name] = polys
                finally:
                    bm.free()

            # Exact non-overlap verification.  The native packer is allowed
            # to place islands overlapping each other when the content does
            # not fit at scale=False (it still reports FINISHED and may even
            # keep everything inside [0, 1-margin]), so a clean extent is no
            # proof of a clean layout.  Boundary contact is fine; anything
            # with positive-area intersection refuses the round.
            tile_polys: list[list] = []
            for s in members:
                ob = s["ob"]
                fp = face_polys[ob.name]
                for i in s["islands"]:
                    if assign[i._item_index] != t:
                        continue
                    tile_polys.append([fp[fi] for fi in i.face_indices])
            static_flags: list[bool] | None = None
            if static_polys:
                # Untouched islands are fixed obstacles.  Their polygons sit
                # in global UV space, so shift them into this tile's local
                # 0..1 space and verify the packed content against them as
                # well (the grid-hash check ignores far-away cells).  Each
                # static island is one entry, flagged static, so its own
                # adjacent faces are never compared against each other and
                # pre-existing static-vs-static overlaps cannot make this
                # round infeasible.
                tu_s, tv_s = positions[t]
                static_flags = [False] * len(tile_polys)
                for isl_polys in static_polys:
                    tile_polys.append(
                        [[(x - tu_s, y - tv_s) for (x, y) in poly]
                         for poly in isl_polys])
                    static_flags.append(True)
            if _tile_islands_overlap(tile_polys, static_flags):
                raise _PackRefusedError(
                    f"uv.pack_islands produced overlapping islands in tile "
                    f"{udim_number(*positions[t])} at this scale; the "
                    f"content is too large for the free space")

            if tu != 0 or tv != 0:
                for s in members:
                    ob = s["ob"]
                    me = ob.data
                    fset = fsets[ob.name]
                    bm = bmesh.from_edit_mesh(me)
                    try:
                        uvl = bm.loops.layers.uv.active
                        for f in tuple(bm.faces):
                            if f.index not in fset:
                                continue
                            for l in tuple(f.loops):
                                u = l[uvl].uv
                                u.x += tu
                                u.y += tv
                        bmesh.update_edit_mesh(me)
                    finally:
                        bm.free()

            extents[t] = [minx, miny, maxx, maxy]
        finally:
            _exit_edit()
            for fn in reversed(undo_vis):
                fn()

    return extents


def _stretch_final_layout(state: list, assign_final: dict, positions: list,
                          margin: float, static_polys: list | None = None) -> float:
    """Re-center each used tile's content and grow it by one global factor.

    Every tile is re-centered on its tile center, and - when any headroom
    remains - all tiles are scaled together by one uniform factor until the
    tightest tile/axis reaches its margin boundary (see
    :func:`native_udim_packer.layout.final_growth_factor`); a single global
    factor keeps texel density equal across UDIMs.  Per tile this is one
    similarity transform - re-centering plus scaling about the content's
    bbox center - which preserves all relative geometry inside the tile and
    therefore cannot create any new overlap among the packed islands.

    When ``static_polys`` (selected-islands mode) are present, growing a
    tile can push its packed content into the fixed, untouched islands that
    share the tile; those collisions grow monotonically with the factor, so
    candidate factors are verified against the static polygons and the
    largest clean one is kept (bisection), with one exact final gate before
    anything is written.  If even the pure re-centering translation collides,
    no transform is applied at all - the pre-stretch layout was already
    verified clean in the final search round.

    Note that ``uv.pack_islands`` treats its margin as island-to-island
    spacing, not as a boundary offset: a dense packing can legitimately span
    slightly wider than the [m, 1-m] box (it always stays inside the tile).
    When no tile/axis has headroom the factor is 1.0 and only the pure
    re-centering translation is applied.

    Runs in object mode on the finished layout (the final round has left
    the meshes written).  Returns the applied factor (>= 1.0; 1.0 when
    nothing can grow - the re-centering still happens).
    """
    # Face -> tile membership for every packed object (each face belongs to
    # exactly one island, hence to exactly one tile).
    face_tile: dict[str, dict[int, int]] = {}
    for s in state:
        m: dict[int, int] = {}
        for i in s["islands"]:
            t = assign_final[i._item_index]
            for fi in i.face_indices:
                m[fi] = t
        face_tile[s["ob"].name] = m

    # Measure each used tile's content bbox in global UV space.
    bboxes: dict[int, list] = {}
    for s in state:
        ob = s["ob"]
        fmap = face_tile[ob.name]
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        try:
            uvl = bm.loops.layers.uv.active
            for f in tuple(bm.faces):
                t = fmap.get(f.index)
                if t is None:
                    continue
                bb = bboxes.setdefault(
                    t, [math.inf, math.inf, -math.inf, -math.inf])
                for l in tuple(f.loops):
                    x, y = l[uvl].uv.x, l[uvl].uv.y
                    if x < bb[0]:
                        bb[0] = x
                    if x > bb[2]:
                        bb[2] = x
                    if y < bb[1]:
                        bb[1] = y
                    if y > bb[3]:
                        bb[3] = y
        finally:
            bm.free()

    local_extents = {t: [bb[0] - positions[t][0], bb[1] - positions[t][1],
                         bb[2] - positions[t][0], bb[3] - positions[t][1]]
                     for t, bb in bboxes.items()}
    K_max = _final_growth_factor(local_extents, margin)

    centers = {t: [(bb[0] + bb[2]) * 0.5, (bb[1] + bb[3]) * 0.5]
               for t, bb in bboxes.items()}

    if static_polys:
        # Packed-vs-packed stays clean under the per-tile similarity
        # transform; only packed-vs-static collisions can appear, and they
        # grow monotonically with the factor.  Read every packed face's UVs
        # once (linked-duplicate mesh data is read a single time - counting
        # it twice would make identical polygons "overlap" themselves),
        # then verify candidate factors against the fixed content.
        face_uvs: dict[str, dict[int, list]] = {}
        seen_data = set()
        for s in state:
            ob = s["ob"]
            did = id(ob.data)
            if did in seen_data:
                continue
            seen_data.add(did)
            fmap = face_tile[ob.name]
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            try:
                uvl = bm.loops.layers.uv.active
                fuvs: dict[int, list] = {}
                for f in tuple(bm.faces):
                    if fmap.get(f.index) is None:
                        continue
                    fuvs[f.index] = [(l[uvl].uv.x, l[uvl].uv.y)
                                     for l in tuple(f.loops)]
                face_uvs[ob.name] = fuvs
            finally:
                bm.free()

        def candidate_ok(Kc: float) -> bool:
            for t in bboxes:
                tu, tv = positions[t]
                cx, cy = centers[t]
                px, py = tu + 0.5, tv + 0.5
                polys: list[list] = []
                for s in state:
                    fuvs = face_uvs.get(s["ob"].name)
                    if not fuvs:
                        continue
                    fmap = face_tile[s["ob"].name]
                    # One entry per packed island (all of its faces share a
                    # tile) so adjacent faces are never self-compared.
                    for i in s["islands"]:
                        fis = [fi for fi in i.face_indices if fi in fuvs]
                        if not fis or fmap[fis[0]] != t:
                            continue
                        polys.append(
                            [[(px + (x - cx) * Kc,
                               py + (y - cy) * Kc)
                              for (x, y) in fuvs[fi]]
                             for fi in fis])
                static_flags: list[bool] | None = None
                if static_polys:
                    static_flags = [False] * len(polys)
                    for isl_polys in static_polys:
                        polys.append(
                            [[(x - tu, y - tv) for (x, y) in poly]
                             for poly in isl_polys])
                        static_flags.append(True)
                if _tile_islands_overlap(polys, static_flags):
                    return False
            return True

        if not candidate_ok(1.0):
            # Even the pure re-centering translation collides with fixed
            # content: leave the verified pre-stretch layout untouched.
            return 1.0
        lo, hi = 1.0, K_max
        for _ in range(24):
            if hi - lo <= 1e-5:
                break
            mid = (lo + hi) * 0.5
            if candidate_ok(mid):
                lo = mid
            else:
                hi = mid
        K = lo if candidate_ok(lo) else 1.0
    else:
        K = K_max

    # Apply one similarity transform per used tile: content center -> tile
    # center, scaled by K.  uv' = tile_center + (uv - content_center) * K
    # With K == 1.0 this is the pure re-centering translation; it is always
    # applied so every used tile carries balanced margins around its
    # content, even when no growth is possible.
    written_meshes = set()
    for s in state:
        ob = s["ob"]
        if id(ob.data) in written_meshes:
            # Linked-duplicate mesh data: the first owner already wrote the
            # transform; re-applying it would scale twice.
            continue
        written_meshes.add(id(ob.data))
        fmap = face_tile[ob.name]
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        try:
            uvl = bm.loops.layers.uv.active
            for f in tuple(bm.faces):
                t = fmap.get(f.index)
                if t is None:
                    continue
                tu, tv = positions[t]
                cx, cy = centers[t]
                px, py = tu + 0.5, tv + 0.5
                for l in tuple(f.loops):
                    u = l[uvl].uv
                    u.x = px + (u.x - cx) * K
                    u.y = py + (u.y - cy) * K
            bm.to_mesh(ob.data)
        finally:
            bm.free()
    return K


def _restore_snapshots(state: list) -> None:
    """Write the original UVs back for every object (best effort)."""
    for s in state:
        ob = s["ob"]
        snap = s["snapshot"]
        me = ob.data
        try:
            _enter_edit(ob)
            bm = bmesh.from_edit_mesh(me)
            try:
                uvl = bm.loops.layers.uv.active
                bm.faces.ensure_lookup_table()
                for f in tuple(bm.faces):
                    uv_list = snap.get(f.index)
                    if uv_list is None:
                        continue
                    for l, (x, y) in zip(tuple(f.loops), uv_list):
                        l[uvl].uv = (x, y)
                bmesh.update_edit_mesh(me)
            finally:
                bm.free()
        except RuntimeError:
            pass
        finally:
            _exit_edit()


# --------------------------------------------------------------------------
# public pipeline
# --------------------------------------------------------------------------

def pack_objects(objects: list, grid_x: int = 2, grid_y: int = 2,
                 normalize_scale: bool = False, rotate_90: bool = True,
                 margin: float = 0.01, selected_islands: bool = False) -> dict:
    """Pack the UV islands of ``objects`` into a UDIM grid.

    With ``selected_islands=True`` only the islands that are currently
    selected in the UV editor are packed (an island counts as selected when
    at least one of its faces is selected); every other island keeps its
    UVs exactly and acts as an obstacle the packed content must avoid.
    This mode needs a live selection, so it must be started from (multi-)
    edit mode - running it in object mode returns an error.

    Returns a result dict (see operator/README) or ``{"error": ...}``.
    On any failure the original UVs are restored before returning.
    """
    objects = [o for o in objects if o is not None and o.type == 'MESH']
    if not objects:
        return {"error": "no mesh objects to pack", "objects": {},
                "errors": {}}

    # Capture the user's state up front; commit any pending edit-mode
    # changes so detection sees exactly what will be packed.  The state is
    # restored once, on every exit path, by _finish().
    started_in_edit = (bpy.context.object is not None
                       and bpy.context.object.mode == 'EDIT')
    saved_selection = [o.name for o in bpy.context.selected_objects]
    original_active = bpy.context.view_layer.objects.active

    if selected_islands and not started_in_edit:
        # UV selection flags only exist inside a live edit session, so
        # there is nothing to select against in object mode.  No state has
        # been touched yet - just report.
        return {"error": ("pack-selected-islands needs a live UV selection: "
                          "enter the UV editor, select islands, then run "
                          "the operator"),
                "objects": {}, "errors": {}}

    # Selected-islands mode: read the edit-bmesh selection NOW - it is
    # discarded the moment the session is exited below.  Objects that are
    # not part of the current edit session (single-object edit with other
    # targets) simply contribute no selected islands.
    sel_faces_by_obj: dict[str, set] = {}
    uv_selection: dict[str, list] = {}
    if selected_islands and started_in_edit:
        for ob in objects:
            if ob.mode == 'EDIT':
                faces, raw_faces = _capture_edit_selection(ob)
                if faces is not None:
                    sel_faces_by_obj[ob.name] = faces
                    uv_selection[ob.name] = raw_faces

    if started_in_edit:
        bpy.ops.object.mode_set(mode='OBJECT')

    # The built-in packer's selection gate is toolsettings-dependent, and
    # headless sessions do not guarantee a usable default (a non-FACE mesh
    # select mode or sync-off settings make uv.pack_islands cancel
    # silently).  Force a deterministic state for the duration of the pack;
    # _finish() restores it on every exit path.
    ts = bpy.context.scene.tool_settings
    saved_toolsettings = {
        "use_uv_select_sync": ts.use_uv_select_sync,
        "uv_sticky_select_mode": ts.uv_sticky_select_mode,
    }
    ts.use_uv_select_sync = True
    ts.uv_sticky_select_mode = "DISABLED"

    # 1) detect islands + snapshot original UVs (object mode) ----------
    state = []
    errors: dict[str, str] = {}
    for ob in objects:
        islands = _detect_object(ob)
        if islands is None:
            errors[ob.name] = "no UV layer found"
            continue
        for i in islands:
            i.owner = ob
        state.append({"ob": ob, "islands": islands})
    if not state:
        _finish(started_in_edit, saved_selection, original_active,
                toolsettings=saved_toolsettings, uv_selection=uv_selection)
        return {"error": "no UV islands found on any target object",
                "objects": {}, "errors": errors}

    # Selected-islands mode: keep only the islands touched by the UV
    # selection; everything else stays where it is (and becomes an obstacle
    # for the overlap checks below).  With normalize on, texel density is
    # equalized over the packed set only - the untouched islands keep their
    # existing scale.
    static_polys: list | None = None
    if selected_islands:
        packed_total = 0
        for s in state:
            sf = sel_faces_by_obj.get(s["ob"].name, set())
            kept = [i for i in s["islands"] if i.face_indices & sf]
            s["untouched_count"] = len(s["islands"]) - len(kept)
            # Kept for the static-obstacle grouping below: the islands that
            # stay where they are, still whole.
            s["static_islands"] = [i for i in s["islands"]
                                   if not (i.face_indices & sf)]
            s["islands"] = kept
            packed_total += len(kept)
        if packed_total == 0:
            _finish(started_in_edit, saved_selection, original_active,
                    toolsettings=saved_toolsettings,
                    uv_selection=uv_selection)
            return {"error": "no UV islands selected in the UV editor",
                    "objects": {}, "errors": errors}

    all_islands = [i for s in state for i in s["islands"]]
    if normalize_scale:
        normalize_scales(all_islands)

    # 2) reference sizes + items ---------------------------------------
    items = []
    for n, i in enumerate(all_islands):
        i._s_norm = i.norm_scale if i.norm_scale is not None else 1.0
        i._item_index = n
        w = max((i.max_uv[0] - i.min_uv[0]) * i._s_norm, 1e-6)
        h = max((i.max_uv[1] - i.min_uv[1]) * i._s_norm, 1e-6)
        items.append(_LayoutItem(n, w, h))

    for s in state:
        s["snapshot"] = _snapshot_uv(s["ob"].data)

    if selected_islands:
        # Untouched islands never move: their polygons (original UVs) are
        # fixed obstacles for every overlap check below.  Grouped per island
        # (a list of its face polygons, global UV space) so that adjacent
        # faces of one static island are never compared against each other.
        # Mesh data shared by linked duplicates is counted once.
        static_polys = []
        seen_data = set()
        for s in state:
            ob = s["ob"]
            did = id(ob.data)
            if did in seen_data:
                continue
            seen_data.add(did)
            snap = s["snapshot"]
            for isl in s.get("static_islands", []):
                polys = [list(snap[fi]) for fi in isl.face_indices
                         if fi in snap]
                if polys:
                    static_polys.append(polys)

    # 3) scale search with the native-pack oracle ----------------------
    positions = _tile_order(grid_x, grid_y)

    def oracle(assign: dict, S: float) -> list:
        return _execute_round(state, assign, positions, S, rotate_90,
                              margin, static_polys)

    try:
        S_final, assign_final, rounds, feasible = _layout_solve(
            items, grid_x, grid_y, margin, oracle)
    except RuntimeError as exc:
        _restore_snapshots(state)
        _finish(started_in_edit, saved_selection, original_active,
                toolsettings=saved_toolsettings, uv_selection=uv_selection)
        return {"error": str(exc), "objects": {}, "errors": errors}
    if not feasible:
        _restore_snapshots(state)
        _finish(started_in_edit, saved_selection, original_active,
                toolsettings=saved_toolsettings, uv_selection=uv_selection)
        return {"error": "scale search did not converge", "objects": {},
                "errors": errors}

    # 3b) re-center + global growth: the final round always leaves slack in
    #     the tiles; grow every tile by one uniform factor (limited by the
    #     tightest tile/axis) to maximize texel density.  One similarity
    #     transform per tile, so no new overlaps are possible among the
    #     packed islands and the exact verification of the final round stays
    #     valid; in selected-islands mode the growth factor is additionally
    #     verified against the untouched (static) content before writing.
    stretch = _stretch_final_layout(state, assign_final, positions, margin,
                                    static_polys)

    # 4) report ---------------------------------------------------------
    used_set = set(assign_final.values())
    tile_owners: dict[int, set] = {}
    for s in state:
        for i in s["islands"]:
            t = assign_final[i._item_index]
            tile_owners.setdefault(t, set()).add(s["ob"].name)

    results: dict[str, dict] = {}
    for s in state:
        ob = s["ob"]
        tiles_used = sorted({positions[assign_final[i._item_index]]
                             for i in s["islands"]})
        results[ob.name] = {
            "islands": len(s["islands"]),
            "tiles_used": tiles_used,
            "udims": [udim_number(tu, tv) for (tu, tv) in tiles_used],
        }

    # The mesh now holds the final placement; restore the user's state.
    _finish(started_in_edit, saved_selection, original_active,
            toolsettings=saved_toolsettings, uv_selection=uv_selection)

    return {
        "objects": results,
        "fallback_tiles": 0,
        "fallback_reasons": [],
        "shared_tiles": sum(1 for owners in tile_owners.values()
                            if len(owners) > 1),
        # The effective uniform scale actually written to the meshes: the
        # solved scale times the final re-center/growth factor.
        "global_scale": S_final * stretch,
        "stretch_factor": stretch,
        "tiles_used_total": [positions[t] for t in sorted(used_set)],
        "packed_islands": sum(len(s["islands"]) for s in state),
        "untouched_islands": (sum(s.get("untouched_count", 0)
                                  for s in state)
                              if selected_islands else 0),
    }


def pack_object(ob, grid_x: int = 2, grid_y: int = 2,
                normalize_scale: bool = False, rotate_90: bool = True,
                margin: float = 0.01, selected_islands: bool = False) -> dict:
    """Convenience wrapper: pack a single object."""
    return pack_objects([ob], grid_x, grid_y, normalize_scale, rotate_90,
                        margin, selected_islands=selected_islands)


def verify_packing(ob, grid_x: int, grid_y: int) -> dict:
    """Check that every island of ``ob`` sits inside exactly one tile."""
    me = ob.data
    if me.uv_layers is None or len(me.uv_layers) == 0:
        return {"islands": 0, "all_inside": False, "per_island": []}
    bm = bmesh.new()
    bm.from_mesh(me)
    try:
        uvl = bm.loops.layers.uv.active
        islands = detect_islands(bm, uvl)
    finally:
        bm.free()
    all_inside = True
    per = []
    eps = 1e-4
    for i in islands:
        minx, miny, maxx, maxy = i.min_uv[0], i.min_uv[1], i.max_uv[0], \
            i.max_uv[1]
        tu = math.floor(minx + eps) if (maxx - minx < 1.0 - 2 * eps
                                        and math.floor(maxx - eps)
                                        == math.floor(minx + eps)) else None
        tv = math.floor(miny + eps) if (maxy - miny < 1.0 - 2 * eps
                                        and math.floor(maxy - eps)
                                        == math.floor(miny + eps)) else None
        single_tile = (tu is not None and tv is not None
                       and math.floor(maxx - eps) == tu
                       and math.floor(maxy - eps) == tv)
        in_grid = (
            minx >= -eps and maxx <= grid_x + eps
            and miny >= -eps and maxy <= grid_y + eps
            and 0 <= tu < grid_x and 0 <= tv < grid_y
        ) if single_tile else False
        inside = single_tile and in_grid
        all_inside = all_inside and inside
        per.append({
            "faces": len(i.face_indices),
            "tile": (tu, tv) if single_tile else None,
            "udim": udim_number(tu, tv) if single_tile else None,
            "bounds": (round(minx, 4), round(miny, 4),
                       round(maxx, 4), round(maxy, 4)),
            "inside": inside,
        })
    return {"islands": len(islands), "all_inside": all_inside,
            "per_island": per}
