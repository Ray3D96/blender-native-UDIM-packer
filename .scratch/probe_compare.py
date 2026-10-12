# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact before/after probe: pack QA scene with the engine given on argv."""
import math
import sys

import bpy
import bmesh

ADDON_PATH = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else \
    "/mnt/fusion/ai-projects/blender-uv-packer"

_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:  # noqa: BLE001
        pass
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, ADDON_PATH)
import native_udim_packer as A  # noqa: E402
A.register()
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer.islands import (  # noqa: E402
    detect_islands, island_bounds)

print(f"engine at {ADDON_PATH} version {A.bl_info['version']}")


def uv_area(bm, uvl, face_indices):
    total = 0.0
    for f in tuple(bm.faces):
        if f.index in face_indices:
            ls = tuple(f.loops)
            n = len(ls)
            a2 = 0.0
            for i in range(n):
                u1 = ls[i][uvl].uv
                u2 = ls[(i + 1) % n][uvl].uv
                a2 += u1.x * u2.y - u2.x * u1.y
            total += abs(a2) * 0.5
    return total


path = "/mnt/fusion/ai-projects/blender-uv-packer/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=path)
targets = [o for o in bpy.data.objects
           if o.type == 'MESH' and o.data.uv_layers
           and o.data.uv_layers.active]
print(f"scene: {len(targets)} target objects")

res = P.pack_objects(targets, 3, 1, True, True, 0.0)
S = res.get("global_scale")
print(f"S* = {S!r}  tiles_used_total = {res.get('tiles_used_total')}")

bm_all = {}
n_isl = 0
tot_area = 0.0
for o in targets:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    uvl = bm.loops.layers.uv.active
    for isl in detect_islands(bm, uvl):
        minx, miny, maxx, maxy = island_bounds(bm, uvl, isl.face_indices)
        t = (int(math.floor(minx + 1e-4)), int(math.floor(miny + 1e-4)))
        a = uv_area(bm, uvl, isl.face_indices)
        n_isl += 1
        tot_area += a
        d = bm_all.setdefault(
            t, [0.0, math.inf, math.inf, -math.inf, -math.inf])
        d[0] += a
        d[1] = min(d[1], minx)
        d[2] = min(d[2], miny)
        d[3] = max(d[3], maxx)
        d[4] = max(d[4], maxy)
    bm.free()

print(f"islands_post={n_isl} total_final_area={tot_area!r}")
for t in sorted(bm_all):
    a, mnx, mny, mxx, myy = bm_all[t]
    w = mxx - mnx
    h = myy - mny
    print(f"tile {t}: area_fill={a!r} content_bbox={w!r}x{h!r}")
print("COMPARE DONE")
