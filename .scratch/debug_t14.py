# SPDX-License-Identifier: GPL-2.0-or-later
"""Trace T14 (test object, 2x2) through LPT + rebalance + final pack."""
import math
import sys

import bpy
import bmesh

_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:  # noqa: BLE001
        pass
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
import native_udim_packer as _A  # noqa: E402
_A.register()
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer.islands import (  # noqa: E402
    detect_islands, island_bounds, island_outline)
from native_udim_packer.layout import (  # noqa: E402
    Item, _lpt_assign, _pack_tile_rect, _rect_proxy, pack_tile)
import native_udim_packer.layout as L  # noqa: E402


def make_t14(name):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    b = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8,
                                          location=(-6, 0, 0))
    c = bpy.context.active_object
    a.select_set(True); b.select_set(True); c.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def build_items(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    islands = detect_islands(bm, uvl)
    items = []
    for n, isl in enumerate(islands):
        minx, miny, maxx, maxy = island_bounds(bm, uvl, isl.face_indices)
        w, h = maxx - minx, maxy - miny
        outers, holes = island_outline(bm, uvl, isl.face_indices)
        nverts = sum(len(lp) for lp in outers + holes)
        o_loops, h_loops = [], []
        if outers and nverts >= 6 and math.hypot(w, h) >= 0.02:
            minxo = min(p[0] for lp in outers + holes for p in lp)
            minyo = min(p[1] for lp in outers + holes for p in lp)

            def _local(lp, ox=minxo, oy=minyo):
                return tuple((x - ox, y - oy) for x, y in lp)

            o_loops = [_local(lp) for lp in outers]
            h_loops = [_local(lp) for lp in holes]
        items.append(Item(n, w, h, outers=tuple(o_loops),
                          holes=tuple(h_loops)))
    bm.free()
    return items


ob = make_t14("t14")
shaped = build_items(ob)
print(f"islands: {len(shaped)}")
for it in shaped:
    tag = "SHAPE" if it.outers else "rect "
    print(f"  {it.index}: {tag} w={it.w:.4f} h={it.h:.4f} "
          f"area={it.w * it.h:.4f}")

gx, gy = 2, 2
keys = [
    ("area", lambda it: (-(it.w * it.h), -max(it.w, it.h), it.index)),
    ("maxdim", lambda it: (-max(it.w, it.h), -(it.w * it.h), it.index)),
    ("perim", lambda it: (-(it.w + it.h), -(it.w * it.h), it.index)),
]
for name, key in keys:
    assign = _lpt_assign(shaped, gx * gy, key)
    proxy = {t: _pack_tile_rect(_rect_proxy(assign[t]), True, 0.01)[0]
             for t in range(gx * gy) if assign[t]}
    actual = {t: pack_tile(assign[t], True, 0.01)[0]
              for t in range(gx * gy) if assign[t]}
    print(f"LPT {name}: " + " ".join(
        f"t{t}:[{[i.index for i in assign[t]]}]P={proxy.get(t, 0):.3f}"
        f"/A={actual.get(t, 0):.3f}" for t in range(gx * gy)))

# what does the OLD v2-style all-rectangle LPT give? (v2 compared actuals)
rect_items = [Item(it.index, it.w, it.h) for it in shaped]
for name, key in keys:
    assign = _lpt_assign(rect_items, gx * gy, key)
    actual = {t: pack_tile(assign[t], True, 0.01)[0]
              for t in range(gx * gy) if assign[t]}
    print(f"v2rect {name}: " + " ".join(
        f"t{t}:[{[i.index for i in assign[t]]}]A={actual.get(t, 0):.3f}"
        for t in range(gx * gy)))

S, placements = L.solve(shaped, gx, gy, 0.01, True)
print(f"\nS* = {S}")
per_tile = {}
for p in placements:
    it = shaped[p.item]
    per_tile.setdefault((p.tile_u, p.tile_v), []).append(
        (it.index, it.w * it.h))
for t in sorted(per_tile):
    idxs = [i for i, _ in per_tile[t]]
    area = sum(a for _, a in per_tile[t])
    print(f"  tile {t}: items={idxs} bbox_area_sum={area:.4f}")
print("DEBUG DONE")
