# SPDX-License-Identifier: GPL-2.0-or-later
"""UDIM grid packing pipeline built on Blender's native ``uv.pack_islands``.

Strategy (validated against Blender 5.2):

Multiple objects are treated as one shared texture set: their islands are
pooled and balanced together, so no two islands ever overlap — even when they
belong to different objects.  Each object is edited in its own isolated edit
session; the original selection is restored afterwards.

1. Detect UV islands with :mod:`native_udim_packer.islands` (seam-aware).
2. Optionally pre-scale islands to equalize texel density ("normalize").
3. Balance the pooled islands across the U x Y tile grid (LPT scheduling:
   largest island first, always into the currently emptiest tile).
4. For every non-empty tile, in order:
     a. select exactly that tile's faces;
     b. translate them so their UV bounding-box minimum sits at the origin
        (deterministic starting position for the native packer);
     c. run ``bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', ...)`` which
        packs the selection into a single 1x1 tile region;
     d. measure where the packer actually put them and shift by the integer
        delta to the assigned tile.  The measured re-offset makes the result
        correct no matter which UDIM tile the native packer chose as its
        target (it depends on editor context), and keeps every island inside
        ``[tu, tu+1] x [tv, tv+1]``.
   If the native operator fails for a tile, a pure-Python shelf packer places
   that tile's islands manually (with 90-degree rotation when enabled).
5. With "normalize" on, every single-owner tile is measured afterwards and,
   if needed, uniformly shrunk back to the equalized texel density: the
   native packer with ``scale=True`` scales small selections UP to fill the
   tile, which would otherwise leave each tile at a different density.

Only bpy/bmesh and built-in operators are used; no external processes.
"""
from __future__ import annotations

import math

import bpy
import bmesh

from .islands import (
    Island,
    detect_islands,
    island_bounds,
    place_island_into,
    scale_faces_about,
    translate_faces,
)


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

    Returns the target density ratio ``total_uv / total_3d`` (or ``None``
    when no island has usable areas); callers can use it to restore the
    equalized density after packing.
    """
    good = [i for i in islands if i.uv_area > 1e-9 and i.world_area > 1e-9]
    tot_uv = sum(i.uv_area for i in good)
    tot_w = sum(i.world_area for i in good)
    if tot_uv <= 0.0 or tot_w <= 0.0:
        for i in islands:
            i.norm_scale = None
        return None
    ratio = tot_uv / tot_w
    for i in islands:
        if i.uv_area > 1e-9 and i.world_area > 1e-9:
            i.norm_scale = math.sqrt(ratio * i.world_area / i.uv_area)
        else:
            i.norm_scale = None
    return ratio


def assign_tiles(islands: list[Island], grid_x: int, grid_y: int,
                 area_of=None) -> dict[tuple[int, int], list[Island]]:
    """Balance islands across the tile grid (LPT / longest processing time).

    Islands are sorted by area (largest first) and each goes into the tile
    with the lowest current load; ties break to the first tile in row-major
    order, so results are deterministic.  ``area_of`` may override the area
    used for balancing (e.g. post-normalization areas).
    """
    if area_of is None:
        area_of = lambda i: i.uv_area  # noqa: E731
    tiles = [(i, j) for i in range(grid_x) for j in range(grid_y)]
    load = {t: 0.0 for t in tiles}
    assignment: dict[tuple[int, int], list[Island]] = {t: [] for t in tiles}
    for isl in sorted(islands, key=area_of, reverse=True):
        t = min(tiles, key=lambda t: load[t])
        assignment[t].append(isl)
        load[t] += area_of(isl)
    return assignment


def _select_only(bm, face_indices: set[int]) -> None:
    for f in tuple(bm.faces):
        f.select_set(f.index in face_indices)


def _selection_bounds(bm, uvl, face_indices: set[int]):
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
    return (minx, miny, maxx, maxy)


def _faces_uv_area(bm, uvl, face_indices: set[int]) -> float:
    """Shoelace UV area of the given faces (same convention as detect_islands)."""
    total = 0.0
    for f in tuple(bm.faces):
        if f.index in face_indices:
            loops = tuple(f.loops)
            n = len(loops)
            a2 = 0.0
            for i in range(n):
                u1 = loops[i][uvl].uv
                u2 = loops[(i + 1) % n][uvl].uv
                a2 += u1.x * u2.y - u2.x * u1.y
            total += abs(a2) * 0.5
    return total


def _shelf_layout(items: list, m: float, g: float):
    """Virtual shelf packing (no bmesh writes).

    ``items`` is a list of ``(island, w, h)`` at unit scale; ``g`` is the
    global scale factor.  Returns ``(slots, used)`` where each slot is
    ``(island, u0, v_top, fw, fh, sf, rot)`` (final width/height, total scale
    factor for this island, rotation steps) and ``used`` is the total shelf
    height consumed from the top of the interior.
    """
    W = 1.0 - 2.0 * m
    shelves: list[list[float]] = []   # [u_cursor, v_top, height]
    slots: list[tuple] = []
    for isl, w, h in items:
        rot = 0
        bw, bh = w * g, h * g
        if bw > W and bh <= W:        # rotate once to fit the width
            bw, bh, rot = bh, bw, 1
        sf = g * min(1.0, W / bw) * (1.0 - 1e-6)   # total scale for this island
        fw = h * sf if rot else w * sf             # final footprint after rotation
        fh = w * sf if rot else h * sf

        slot = None
        for si in range(len(shelves)):
            uc, vt, ht = shelves[si]
            if fh <= ht + 1e-9 and uc + fw <= W + 1e-9:
                slot = (si, uc, vt)
                break
        if slot is None:
            used = sum(sh[2] for sh in shelves)
            vt = (1.0 - m) - used
            # record the shelf height *including* a trailing gap, so the next
            # shelf starts m below this one's bottom edge
            shelves.append([m, vt, fh + m])
            slot = (len(shelves) - 1, m, vt)

        si, uc, vt = slot
        slots.append((isl, uc, vt, fw, fh, sf, rot))
        shelves[si][0] = uc + fw + m   # gap between items
    return slots, sum(sh[2] for sh in shelves)


def _shelf_slots(items: list, m: float) -> list:
    """Two-phase virtual shelf layout with global shrink-to-fit.

    ``items`` is a list of ``(island, w, h)`` at *current* UV scale.  Returns
    the final slot list from :func:`_shelf_layout`, globally shrunk (a few
    iterations at most) until the shelf stack fits the tile interior.
    """
    cap_h = 1.0 - 2.0 * m
    items = sorted(items, key=lambda t: t[1] * t[2], reverse=True)
    g = 1.0
    slots: list[tuple] = []
    for _ in range(4):
        slots, used = _shelf_layout(items, m, g)
        if used <= cap_h + 1e-9:
            break
        # shrink everything geometrically; shelf waste shrinks too, so this
        # converges quickly (one extra pass is almost always enough)
        g *= max(math.sqrt(cap_h / used) * 0.98, 0.05)
    return slots


def _manual_shelf_pack(bm, uvl, isl_list: list[Island], margin: float,
                       offset: tuple = (0, 0)) -> None:
    """Pure-Python fallback: shelf-pack a tile's islands into one UDIM tile.

    Each island is scaled about its center, optionally rotated 90 degrees,
    and translated into its slot inside the tile at integer offset ``(tu, tv)``.
    Containment is guaranteed even for over-capacity tiles (see
    :func:`_shelf_slots`); no overlap is produced.
    """
    m = max(float(margin), 1e-4)
    items = []
    for i in isl_list:
        minx, miny, maxx, maxy = island_bounds(bm, uvl, i.face_indices)
        items.append((i, max(maxx - minx, 1e-6), max(maxy - miny, 1e-6)))

    ox, oy = float(offset[0]), float(offset[1])
    for isl, u0, vt, fw, fh, sf, rot in _shelf_slots(items, m):
        place_island_into(bm, uvl, isl.face_indices,
                          (u0 + ox, vt - fh + oy, u0 + fw + ox, vt + oy),
                          scale=sf, rotate_steps=rot)


def _island_size(i: Island) -> tuple[float, float]:
    """Current (post-normalization) bounding-box size of an island."""
    w = max(i.max_uv[0] - i.min_uv[0], 1e-6)
    h = max(i.max_uv[1] - i.min_uv[1], 1e-6)
    s = i.norm_scale or 1.0
    return w * s, h * s


def _native_pack_tile(bm, uvl, ob, me, isl_list: list[Island], tu: int, tv: int,
                      rotate_90: bool, margin: float) -> str:
    """Native per-tile pack of one object's island group.

    Selects exactly the tile's faces, translates their bounding-box minimum
    to the origin, runs ``uv.pack_islands`` (which packs the selection into a
    single 1x1 region), measures where it actually landed and shifts by the
    integer delta to the assigned tile.  Returns "" on success or a reason
    string; the caller falls back to :func:`_manual_shelf_pack` then.
    """
    face_idx: set[int] = set()
    for i in isl_list:
        face_idx |= i.face_indices

    _select_only(bm, face_idx)
    # deterministic start: bounding-box minimum at the origin
    minx, miny, _, _ = _selection_bounds(bm, uvl, face_idx)
    translate_faces(bm, uvl, face_idx, -minx, -miny)
    bmesh.update_edit_mesh(me)

    reason = ""
    try:
        with bpy.context.temp_override(object=ob, active_object=ob):
            res = bpy.ops.uv.pack_islands(
                udim_source='CLOSEST_UDIM',
                rotate=bool(rotate_90),
                rotate_method='CARDINAL' if rotate_90 else 'ANY',
                scale=True,
                merge_overlap=False,
                margin_method='FRACTION',
                margin=float(margin),
            )
        if res != {'FINISHED'}:
            reason = f"native returned {res}"
    except (RuntimeError, AttributeError, TypeError) as exc:
        reason = f"native raised: {exc}"

    if not reason:
        # measure the tile the native packer actually used and shift by the
        # integer delta to our assigned tile.
        minx, miny, maxx, maxy = _selection_bounds(bm, uvl, face_idx)
        landed_u = int(round(minx))
        landed_v = int(round(miny))
        if (maxx - minx > 1.0 + 1e-4) or (maxy - miny > 1.0 + 1e-4):
            # the selection was not packed into a single tile region; fall
            # back to the deterministic manual shelf packer.
            reason = "native spread selection across tiles"
        else:
            du = tu - landed_u
            dv = tv - landed_v
            if du or dv:
                translate_faces(bm, uvl, face_idx, du, dv)

    bmesh.update_edit_mesh(me)
    return reason


def _enter_edit(ob) -> None:
    """Enter single-object edit mode for ``ob`` (isolated object selection)."""
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    if bpy.context.mode != 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='EDIT')


def _exit_edit() -> None:
    if bpy.context.mode == 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='OBJECT')


def _restore_selection(saved: set) -> None:
    _exit_edit()
    for o in tuple(bpy.context.selected_objects):
        o.select_set(False)
    for o in saved:
        if o.name in bpy.data.objects:
            o.select_set(True)


def _finish(started_in_edit: bool, saved: set, original_active) -> None:
    """Restore the object selection and, when packing started from (multi-)
    edit mode, return to it — so packing never yanks the user out of their
    workflow."""
    _restore_selection(saved)
    if started_in_edit and original_active is not None \
            and original_active.name in bpy.data.objects:
        original_active.select_set(True)
        bpy.context.view_layer.objects.active = original_active
        try:
            bpy.ops.object.mode_set(mode='EDIT')
        except RuntimeError:
            pass


def pack_objects(objs, grid_x: int, grid_y: int, normalize: bool,
                 rotate_90: bool, margin: float) -> dict:
    """Pack the UV islands of several objects into one *shared* UDIM grid.

    All objects are treated as a single texture set: their islands are
    balanced across the whole grid together and never overlap, even when they
    belong to different objects.  Tiles whose islands all come from one
    object use the native packer; tiles shared by several objects are laid
    out with the built-in shelf packer (the native operator can only see one
    object at a time).

    Mode and selection state are managed internally: each object is edited in
    its own isolated edit session, and the original object selection is
    restored.  When packing starts from (multi-)edit mode, the user is
    returned to it afterwards with the same objects being edited.  Returns
    ``{"objects": {name: stats}, "fallback_tiles": n, "fallback_reasons":
    [...], "shared_tiles": n}`` plus an optional ``"errors": {name: msg}``
    for objects that could not be processed, or ``{"error": msg}`` when
    nothing could be done.
    """
    saved_selection = set(bpy.context.selected_objects)
    original_active = bpy.context.active_object
    started_in_edit = bpy.context.mode == 'EDIT_MESH'
    if started_in_edit:
        # Leave (multi-)edit mode first so the per-object isolated edit
        # sessions below start from a clean state.
        bpy.ops.object.mode_set(mode='OBJECT')

    # ---- phase 1: detect islands on every object --------------------------
    state: list[dict] = []   # {"ob", "me", "islands"}
    errors: dict[str, str] = {}
    for ob in objs:
        me = ob.data
        if not me.uv_layers or me.uv_layers.active is None:
            errors[ob.name] = "no active UV map"
            continue
        try:
            _enter_edit(ob)
            bm = bmesh.from_edit_mesh(me)
            uvl = bm.loops.layers.uv.active
            islands = detect_islands(bm, uvl) if uvl is not None else []
            bm.free()
            _exit_edit()
        except RuntimeError as exc:
            _exit_edit()
            errors[ob.name] = str(exc)
            continue
        if uvl is None:
            errors[ob.name] = "active UV layer not found in bmesh"
            continue
        if not islands:
            errors[ob.name] = "no UV islands found"
            continue
        for i in islands:
            i.owner = ob
        state.append({"ob": ob, "me": me, "islands": islands})

    if not state:
        _finish(started_in_edit, saved_selection, original_active)
        return {"error": "; ".join(f"{n}: {m}" for n, m in errors.items())}

    all_islands = [i for s in state for i in s["islands"]]

    # ---- phase 2: optional texel-density equalization ----------------------
    target_ratio: float | None = None
    if normalize:
        target_ratio = normalize_scales(all_islands)

    # ---- phase 3: global tile balancing ------------------------------------
    def _balancing_area(i):
        s = i.norm_scale or 1.0
        return i.uv_area * s * s
    assignment = assign_tiles(all_islands, grid_x, grid_y,
                              area_of=_balancing_area if normalize else None)

    # ---- phase 4: precompute shelf slots for tiles shared by several objects
    m = max(float(margin), 1e-4)
    shared_slots: dict[tuple[int, int], list] = {}
    for (tu, tv), isl_list in assignment.items():
        if len({i.owner for i in isl_list}) > 1:
            items = [(i, *(_island_size(i))) for i in isl_list]
            shared_slots[(tu, tv)] = _shelf_slots(items, m)

    # ---- phase 5: place everything, one isolated edit session per object ---
    fallback_tiles = 0
    fallback_reasons: list[str] = []
    for s in state:
        ob, me = s["ob"], s["me"]
        try:
            _enter_edit(ob)
        except RuntimeError as exc:
            errors[ob.name] = str(exc)
            continue
        bm = None
        try:
            bm = bmesh.from_edit_mesh(me)
            uvl = bm.loops.layers.uv.active

            if normalize:
                for i in s["islands"]:
                    if i.norm_scale and abs(i.norm_scale - 1.0) > 1e-6:
                        scale_faces_about(bm, uvl, i.face_indices,
                                          i.norm_scale, i.centroid)
                bmesh.update_edit_mesh(me)

            for (tu, tv), isl_list in assignment.items():
                mine = [i for i in isl_list if i.owner is ob]
                if not mine:
                    continue
                if (tu, tv) in shared_slots:
                    # tile shared with other objects: use the precomputed
                    # combined layout so islands from different objects
                    # cannot overlap
                    for isl, u0, vt, fw, fh, sf, rot in shared_slots[(tu, tv)]:
                        if isl.owner is not ob:
                            continue
                        place_island_into(bm, uvl, isl.face_indices,
                                          (u0 + tu, vt - fh + tv,
                                           u0 + fw + tu, vt + tv),
                                          scale=sf, rotate_steps=rot)
                else:
                    reason = _native_pack_tile(bm, uvl, ob, me, mine, tu, tv,
                                               rotate_90, margin)
                    if reason:
                        _manual_shelf_pack(bm, uvl, mine, margin,
                                           offset=(tu, tv))
                        fallback_tiles += 1
                        fallback_reasons.append(f"tile ({tu},{tv}): {reason}")
        except RuntimeError as exc:
            errors[ob.name] = str(exc)
        finally:
            if bm is not None:
                # leave a clean selection state for this object
                for f in tuple(bm.faces):
                    f.select_set(False)
                bmesh.update_edit_mesh(me)
                bm.free()
            _exit_edit()

    # ---- phase 6: restore the normalized texel density ---------------------
    # uv.pack_islands(scale=True) scales a small selection UP to fill the
    # tile, which would silently break the texel-density equalization (each
    # tile ends up at a different fill factor).  For every single-owner tile
    # we measure the achieved ratio and uniformly shrink the content back to
    # the target.  We never upscale: that could push islands out of their
    # tile.  Shared tiles only use the shelf packer (scale <= 1), so they are
    # already at or below the target and are skipped.
    if target_ratio is not None:
        for (tu, tv), isl_list in assignment.items():
            owners = {i.owner for i in isl_list}
            if len(owners) != 1:
                continue
            ob = next(iter(owners))
            me = ob.data
            try:
                _enter_edit(ob)
            except RuntimeError as exc:
                errors[ob.name] = str(exc)
                continue
            bm = None
            try:
                bm = bmesh.from_edit_mesh(me)
                uvl = bm.loops.layers.uv.active
                uv_sum = sum(_faces_uv_area(bm, uvl, i.face_indices)
                             for i in isl_list)
                world_sum = sum(i.world_area for i in isl_list)
                if world_sum > 1e-9:
                    r_t = uv_sum / world_sum
                    if r_t > target_ratio * (1.0 + 1e-3):
                        f = math.sqrt(target_ratio / r_t)
                        cx, cy = tu + 0.5, tv + 0.5
                        for i in isl_list:
                            scale_faces_about(bm, uvl, i.face_indices,
                                              f, (cx, cy))
                        bmesh.update_edit_mesh(me)
            except RuntimeError as exc:
                errors[ob.name] = str(exc)
            finally:
                if bm is not None:
                    for ff in tuple(bm.faces):
                        ff.select_set(False)
                    bmesh.update_edit_mesh(me)
                    bm.free()
                _exit_edit()

    _finish(started_in_edit, saved_selection, original_active)

    objects = {}
    for s in state:
        tiles = sorted({t for t, lst in assignment.items()
                        if any(i.owner is s["ob"] for i in lst)})
        objects[s["ob"].name] = {
            "islands": len(s["islands"]),
            "tiles_used": tiles,
            "udims": [udim_number(u, v) for u, v in tiles],
        }

    result = {
        "objects": objects,
        "fallback_tiles": fallback_tiles,
        "fallback_reasons": fallback_reasons,
        "shared_tiles": len(shared_slots),
    }
    if errors:
        result["errors"] = errors
    return result


def pack_object(ob, grid_x: int, grid_y: int, normalize: bool,
                rotate_90: bool, margin: float) -> dict:
    """Pack one object's active UV map into the UDIM grid.

    Thin wrapper around :func:`pack_objects` for a single target; mode and
    selection state are managed internally.  Returns a stats dict:
    ``{"islands": n, "tiles_used": [(u, v), ...], "udims": [int, ...],
    "fallback_tiles": int, "fallback_reasons": [...]}`` or ``{"error": msg}``.
    """
    res = pack_objects([ob], grid_x, grid_y, normalize, rotate_90, margin)
    if "error" in res:
        return {"error": res["error"]}
    errs = res.get("errors", {})
    if ob.name in errs:
        return {"error": f"{ob.name}: {errs[ob.name]}"}
    s = res["objects"][ob.name]
    return {
        "islands": s["islands"],
        "tiles_used": s["tiles_used"],
        "udims": s["udims"],
        "fallback_tiles": res["fallback_tiles"],
        "fallback_reasons": res["fallback_reasons"],
    }


def verify_packing(ob, grid_x: int, grid_y: int) -> dict:
    """Post-pack audit (used by tests): per-island tile + containment check.

    Returns ``{"islands": n, "all_inside": bool, "per_island": [...]}``.
    """
    me = ob.data
    bm = bmesh.from_edit_mesh(me)
    uvl = bm.loops.layers.uv.active
    islands = detect_islands(bm, uvl)
    per = []
    all_inside = True
    eps = 1e-4
    for i in islands:
        minx, miny, maxx, maxy = island_bounds(bm, uvl, i.face_indices)
        # An island sits inside a single unit tile when its bounding box does
        # not cross a tile boundary; the owning tile is floor of the minimum.
        tu = int(math.floor(minx + eps)) if minx >= -eps else None
        tv = int(math.floor(miny + eps)) if miny >= -eps else None
        single_tile = (
            tu is not None and tv is not None
            and math.floor(maxx - eps) == tu and math.floor(maxy - eps) == tv
        )
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
            "bounds": (round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4)),
            "inside": inside,
        })
    bm.free()
    return {"islands": len(islands), "all_inside": all_inside, "per_island": per}
