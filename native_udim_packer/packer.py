# SPDX-License-Identifier: GPL-2.0-or-later
"""UDIM grid packing pipeline: one global uniform scale + rigid placement.

Strategy (v2, validated against Blender 5.2):

All objects are treated as one shared texture set.  Their islands are pooled
and a single layout is solved for the whole pool, so no two islands ever
overlap - even when they belong to different objects.

1. Detect UV islands with :mod:`native_udim_packer.islands` (seam-aware) on
   read-only object-mode bmeshes.
2. With "normalize" enabled, compute each island's equalizing scale
   ``norm_scale = sqrt((total_uv / total_3d) * 3d_area_i / uv_area_i)`` -
   but do NOT pre-apply it; it only feeds the layout reference sizes and
   the final writeback.
3. Solve a global rigid layout (:mod:`native_udim_packer.layout`): islands
   are assigned to tiles (LPT load balancing, three deterministic orderings
   tried and the best kept), each tile is greedily packed at reference
   scale, and one uniform scale ``S*`` is derived so that every tile's
   content fits its ``[margin, 1-margin]`` interior.  Nothing is rescaled
   per tile afterwards: every island receives exactly one rigid transform
   (scale ``norm_scale_i * S*``, optional 90-degree rotation, translation).

Consequences:

* Relative sizes between islands are preserved exactly.  With normalize on,
  every island ends up with the same texel density across all objects -
  the same guarantee as Blender's built-in "Average Islands Scale".  With
  normalize off, any scale equalization the user performed beforehand is
  left untouched (one uniform factor is applied to everything).
* ``S*`` is the largest uniform scale this heuristic family can achieve, so
  used tiles are filled as densely as possible.  When total content exceeds
  grid capacity everything shrinks uniformly and proportions stay intact.

Each object is edited in its own isolated edit session; the original
selection is restored afterwards.  Only bpy/bmesh and built-in operators
are used; no external processes.
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
)
from .layout import Item as _LayoutItem
from .layout import solve as _layout_solve


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
    when no island has usable areas).
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


# --------------------------------------------------------------------------
# edit-session round-trip helpers
# --------------------------------------------------------------------------

def _enter_edit(ob):
    """Enter edit mode for ``ob``; returns True when this call entered it."""
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        return False
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    return True


def _exit_edit():
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _finish(started_in_edit: bool, saved, original_active):
    """Restore the pre-call selection state (and edit mode) exactly."""
    for o in bpy.context.selected_objects:
        try:
            o.select_set(False)
        except RuntimeError:
            pass
    if saved is not None:
        for name in saved:
            ob = bpy.data.objects.get(name)
            if ob is not None:
                try:
                    ob.select_set(True)
                except (RuntimeError, TypeError):
                    pass
    if original_active is not None and original_active.name in bpy.data.objects:
        bpy.context.view_layer.objects.active = original_active
    if started_in_edit:
        act = bpy.context.view_layer.objects.active
        if act is not None and act.type == 'MESH':
            try:
                bpy.ops.object.mode_set(mode='EDIT')
            except RuntimeError:
                pass


# --------------------------------------------------------------------------
# island detection / matching
# --------------------------------------------------------------------------

def _island_fingerprint(isl) -> tuple:
    """Content-based identity of an island (independent of bmesh indices).

    Two islands match when they cover the same number of faces with the
    same 3D area, the same UV area, and the same UV bounding-box size
    (all measured by detect_islands).  Remaining ambiguity is limited to
    truly congruent islands, which are interchangeable for packing
    purposes, so first-come matching is safe.
    """
    w = isl.max_uv[0] - isl.min_uv[0]
    h = isl.max_uv[1] - isl.min_uv[1]
    return (len(isl.face_indices), round(isl.world_area, 6),
            round(isl.uv_area, 6), round(w, 4), round(h, 4))


def _match_islands(ref_islands: list[Island],
                   live_islands: list[Island]) -> dict[int, Island]:
    """Map reference islands to fresh live islands by fingerprint.

    Returns ``{id(ref_island): live_island}``.  Raises RuntimeError when an
    island cannot be matched (would mean the geometry changed under us).
    """
    buckets: dict[tuple, list[Island]] = {}
    for li in live_islands:
        buckets.setdefault(li._fingerprint, []).append(li)
    out: dict[int, Island] = {}
    for ri in ref_islands:
        b = buckets.get(ri._fingerprint)
        if not b:
            raise RuntimeError(
                f"island matching failed (fp={ri._fingerprint}); "
                "mesh geometry changed between detect and writeback")
        out[id(ri)] = b.pop(0)
    return out


def _detect_object(ob) -> list[Island] | None:
    """Detect islands on ``ob`` in object mode (read-only bmesh).

    Returns the island list, or None when the object has no usable UVs.
    Islands carry a temporary ``_fingerprint`` used for live matching.
    """
    me = ob.data
    if not getattr(me, "uv_layers", None) or len(me.uv_layers) == 0:
        return None
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        uvl = bm.loops.layers.uv.active
        if uvl is None:
            return None
        islands = detect_islands(bm, uvl)
        for i in islands:
            i._fingerprint = _island_fingerprint(i)
    finally:
        bm.free()
    return islands or None


# --------------------------------------------------------------------------
# main pipeline
# --------------------------------------------------------------------------

def pack_objects(objects: list, grid_x: int = 2, grid_y: int = 2,
                 normalize_scale: bool = False, rotate_90: bool = True,
                 margin: float = 0.01) -> dict:
    """Pack the UV islands of ``objects`` into a UDIM grid (see module doc).

    Returns per-object stats plus global diagnostics; on total failure
    returns ``{"error": ...}``.
    """
    # --- 1) read-only detection in object mode -----------------------------
    state: list[dict] = []
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
        return {"error": "no packable UV islands found",
                "objects": {}, "errors": errors}

    # --- 2) normalize scales (computed, NOT pre-applied) --------------------
    all_islands = [i for s in state for i in s["islands"]]
    if normalize_scale:
        normalize_scales(all_islands)

    # --- 3) global rigid layout at reference scale --------------------------
    items: list[_LayoutItem] = []
    ref_by_index: dict[int, tuple[Island, float]] = {}
    for n, i in enumerate(all_islands):
        minx, miny, maxx, maxy = i.min_uv[0], i.min_uv[1], i.max_uv[0], i.max_uv[1]
        s_norm = i.norm_scale if i.norm_scale is not None else 1.0
        w = max((maxx - minx) * s_norm, 1e-6)
        h = max((maxy - miny) * s_norm, 1e-6)
        items.append(_LayoutItem(n, w, h))
        ref_by_index[n] = (i, s_norm)

    S, placements = _layout_solve(items, grid_x, grid_y, margin, rotate_90)

    # Final UV rect + writeback parameters per island.
    plan: dict[int, dict] = {}
    for p in placements:
        i, s_norm = ref_by_index[p.item]
        x0 = p.tile_u + margin + p.x0 * S
        y0 = p.tile_v + margin + p.y0 * S
        plan[id(i)] = {
            "aabb": (x0, y0, x0 + p.w * S, y0 + p.h * S),
            "scale": s_norm * S,
            "rotated": p.rotated,
            "tile": (p.tile_u, p.tile_v),
        }

    # --- 4) per-object writeback in isolated edit sessions ------------------
    results: dict[str, dict] = {}
    tile_owners: dict[tuple[int, int], set] = {}
    for s in state:
        ob = s["ob"]
        started_in_edit = (bpy.context.object is not None
                           and bpy.context.object.mode == 'EDIT')
        saved = [o.name for o in bpy.context.selected_objects]
        original_active = bpy.context.view_layer.objects.active
        try:
            _enter_edit(ob)
            me = ob.data
            bm = bmesh.from_edit_mesh(me)
            uvl = bm.loops.layers.uv.active
            live = detect_islands(bm, uvl)
            for li in live:
                li._fingerprint = _island_fingerprint(li)
            match = _match_islands(s["islands"], live)
            for i in s["islands"]:
                pi = plan[id(i)]
                li = match[id(i)]
                place_island_into(
                    bm, uvl, li.face_indices, pi["aabb"],
                    scale=pi["scale"],
                    rotate_steps=1 if pi["rotated"] else 0)
            bmesh.update_edit_mesh(me)
        except Exception as exc:  # noqa: BLE001 - per-object isolation
            errors[ob.name] = f"packing failed: {exc}"
        finally:
            try:
                for f in tuple(bm.faces):
                    f.select = False
                bm.free()
            except Exception:  # noqa: BLE001 - bmesh may be gone on error
                pass
            _exit_edit()
        _finish(started_in_edit, saved, original_active)

        if ob.name in errors and "packing failed" in errors[ob.name]:
            continue
        tiles_used = sorted({plan[id(i)]["tile"] for i in s["islands"]})
        results[ob.name] = {
            "islands": len(s["islands"]),
            "tiles_used": tiles_used,
            "udims": [udim_number(u, v) for (u, v) in tiles_used],
        }
        for (tu, tv) in tiles_used:
            tile_owners.setdefault((tu, tv), set()).add(ob.name)

    if not results:
        return {"error": "no packable UV islands found",
                "objects": {}, "errors": errors}

    used_tiles = sorted(tile_owners)
    return {
        "objects": results,
        "fallback_tiles": 0,
        "fallback_reasons": [],
        "shared_tiles": sum(1 for owners in tile_owners.values()
                            if len(owners) > 1),
        "global_scale": S,
        "tiles_used_total": used_tiles,
    }


def pack_object(ob, grid_x: int = 2, grid_y: int = 2,
                normalize_scale: bool = False, rotate_90: bool = True,
                margin: float = 0.01) -> dict:
    """Convenience wrapper for a single object (used by tests/probes)."""
    result = pack_objects([ob], grid_x, grid_y, normalize_scale,
                          rotate_90, margin)
    if "error" in result:
        raise RuntimeError(result["error"])
    entry = result["objects"].get(
        ob.name, {"islands": 0, "tiles_used": [], "udims": []})
    return {**entry, "fallback_tiles": 0, "fallback_reasons": []}


# --------------------------------------------------------------------------
# verification helper (used by tests)
# --------------------------------------------------------------------------

def verify_packing(ob, grid_x: int, grid_y: int) -> dict:
    """Audit the current UV state of ``ob`` against the UDIM grid.

    Must be called while ``ob`` is in edit mode.  Checks that every island
    lies fully inside exactly one tile of the grid and reports per-island
    bounds.  Overlap checking between islands is done by the caller on the
    returned bounds (the packer guarantees it by construction).
    """
    me = ob.data
    bm = bmesh.from_edit_mesh(me)
    uvl = bm.loops.layers.uv.active
    islands = detect_islands(bm, uvl)
    eps = 1e-4
    per = []
    all_inside = True
    for i in islands:
        minx, miny, maxx, maxy = island_bounds(bm, uvl, i.face_indices)
        tu = math.floor(minx + eps) if maxx - minx < 1.0 - 2 * eps else None
        tv = math.floor(miny + eps) if maxy - miny < 1.0 - 2 * eps else None
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
