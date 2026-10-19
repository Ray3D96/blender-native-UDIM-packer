# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe: does the T14 fixture at margin=0 leave axis headroom (K > 1)?
Prints stretch_factor and per-tile union bboxes (tile-local) from
verify_packing island bounds."""
import sys
import math
import bpy

for _m in [m for m in list(sys.modules)
           if m == "native_udim_packer" or m.startswith("native_udim_packer.")]:
    _old = sys.modules.pop(_m)
    try:
        _old.unregister()
    except Exception:
        pass
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
import native_udim_packer as A  # noqa: E402
from native_udim_packer import packer as P  # noqa: E402

print(f"PROBE version={A.bl_info['version']}")


def make_test_object(name):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    b = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8,
                                          location=(-6, 0, 0))
    c = bpy.context.active_object
    bpy.ops.object.select_all(action='DESELECT')
    for o in (a, b, c):
        o.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
ob = make_test_object("t16probe")

m = float(sys.argv[-1]) if len(sys.argv) > 3 else 0.0
r = P.pack_objects([ob], 2, 2, False, True, m)
v = P.verify_packing(ob, 2, 2)
print(f"PROBE margin={m} S*={r.get('global_scale')!r} "
      f"K={r.get('stretch_factor')!r} error={r.get('error')} "
      f"all_inside={v['all_inside']}")
union = {}
for isl in v["per_island"]:
    if not isl["inside"] or isl["tile"] is None:
        continue
    tu, tv = isl["tile"]
    bb = union.setdefault((tu, tv), [math.inf, math.inf, -math.inf,
                                     -math.inf])
    x0, y0, x1, y1 = isl["bounds"]
    bb[0] = min(bb[0], x0)
    bb[1] = min(bb[1], y0)
    bb[2] = max(bb[2], x1)
    bb[3] = max(bb[3], y1)
lin = 1.0 - 2.0 * m
for t in sorted(union):
    bb = union[t]
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    cx = (bb[0] + bb[2]) / 2 - t[0]
    cy = (bb[1] + bb[3]) / 2 - t[1]
    print(f"PROBE   tile{t}: w={w:.6f} h={h:.6f} "
          f"frac=({w / lin:.5f},{h / lin:.5f}) center=({cx:.6f},{cy:.6f})")
print("PROBE DONE")
