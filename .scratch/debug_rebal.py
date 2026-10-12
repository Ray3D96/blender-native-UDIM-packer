# SPDX-License-Identifier: GPL-2.0-or-later
"""Instrument _rebalance on the monkey 3x1 case with full precision."""
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
from native_udim_packer.layout import (  # noqa: E402
    Item, _lpt_assign, _pack_tile_rect, _rect_proxy)
import native_udim_packer.layout as L  # noqa: E402

bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(mon.data)
uvl = bm.loops.layers.uv.active
islands = P.detect_islands(bm, uvl)
items = []
for n, isl in enumerate(islands):
    minx, miny, maxx, maxy = P.island_bounds(bm, uvl, isl.face_indices)
    items.append(Item(n, maxx - minx, maxy - miny))
bm.free()

print("items (full precision):")
for it in items:
    print(f"  {it.index}: w={it.w!r} h={it.h!r}")

# logging wrapper around the proxy pack
orig_pack = L._pack_tile_rect


def log_pack(lst, rotate_90, g):
    E, out = orig_pack(lst, rotate_90, g)
    print(f"  PACK {[i.index for i in lst]} -> E={E!r}")
    return E, out


L._pack_tile_rect = log_pack

assign = _lpt_assign(items, 3, lambda it: (-(it.w * it.h),
                                           -max(it.w, it.h), it.index))
print("LPT:", {t: [i.index for i in v] for t, v in assign.items()})
res = L._rebalance(assign, 3, 1, True, 0.01)
print("AFTER:", {t: [i.index for i in v] for t, v in res.items()})
print("DEBUG DONE")
