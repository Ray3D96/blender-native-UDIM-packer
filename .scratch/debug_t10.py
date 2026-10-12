# SPDX-License-Identifier: GPL-2.0-or-later
"""Trace T10 (monkey, 3x1) through LPT + rebalance to find the empty tile."""
import sys

import bpy
import bmesh

_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] old module unregister: {exc}")
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
import native_udim_packer as _A  # noqa: E402
_A.register()
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer.layout import (  # noqa: E402
    Item, _lpt_assign, _pack_tile_rect, _rect_proxy)

bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object

me = mon.data
bm = bmesh.new()
bm.from_mesh(me)
uvl = bm.loops.layers.uv.active
islands = P.detect_islands(bm, uvl)
print(f"islands: {len(islands)}")

items = []
for n, isl in enumerate(islands):
    minx, miny, maxx, maxy = P.island_bounds(bm, uvl, isl.face_indices)
    w, h = maxx - minx, maxy - miny
    outers, holes = isl._outline if hasattr(isl, "_outline") else ([], [])
    nverts = sum(len(lp) for lp in outers + holes)
    print(f"  item {n}: faces={len(isl.face_indices)} "
          f"w={w:.4f} h={h:.4f} area={w * h:.4f} outline_verts={nverts}")
    items.append(Item(n, w, h))
bm.free()

gx, gy = 3, 1
keys = [
    ("area", lambda it: (-(it.w * it.h), -max(it.w, it.h), it.index)),
    ("maxdim", lambda it: (-max(it.w, it.h), -(it.w * it.h), it.index)),
    ("perim", lambda it: (-(it.w + it.h), -(it.w * it.h), it.index)),
]
for name, key in keys:
    assign = _lpt_assign(items, gx * gy, key)
    ext = {t: _pack_tile_rect(_rect_proxy(assign[t]), True, 0.01)[0]
           for t in range(gx * gy) if assign[t]}
    detail = ", ".join(
        f"t{t}:[{[it.index for it in assign[t]]}]E={ext.get(t, 0):.3f}"
        for t in range(gx * gy))
    print(f"LPT {name}: {detail}")

# now the real solve with tracing monkeypatched rebalance
import native_udim_packer.layout as L  # noqa: E402

orig = L._rebalance


def traced(assign, grid_x, grid_y, rotate_90, g, max_passes=4):
    def ext_of(lst):
        return _pack_tile_rect(_rect_proxy(lst), rotate_90, g)[0] \
            if lst else 0.0

    for p in range(max_passes):
        ext = {t: ext_of(assign[t]) for t in range(grid_x * grid_y)
               if assign[t]}
        print(f"  pass {p}: " + " ".join(
            f"t{t}:[{[i.index for i in assign[t]]}]E={ext.get(t, 0):.3f}"
            for t in range(grid_x * grid_y)))
        if len(ext) < 2:
            break
        order = sorted(ext, key=lambda t: (-ext[t], t))
        tb = order[0]
        lo = min(ext.values())
        if ext[tb] <= lo * 1.03 + 1e-9:
            print("  balanced enough, stop")
            break
    return orig(assign, grid_x, grid_y, rotate_90, g)


L._rebalance = traced
S, placements = L.solve(items, gx, gy, 0.01, True)
print(f"\nS* = {S}")
for p in sorted(placements, key=lambda q: (q.tile_u, q.tile_v, q.item)):
    print(f"  item {p.item} -> tile ({p.tile_u},{p.tile_v}) "
          f"pos=({p.x0:.3f},{p.y0:.3f}) size={p.w:.3f}x{p.h:.3f} "
          f"rot={p.rotated}")
print("DEBUG DONE")
