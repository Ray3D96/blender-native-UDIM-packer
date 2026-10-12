# SPDX-License-Identifier: GPL-2.0-or-later
"""Smoke test for the v2 engine (global uniform scale + rigid placement)."""
import math
import sys

import bpy
import bmesh

# Force the SOURCE code (not the installed addon loaded at startup).
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
print(f"loaded source addon version {_A.bl_info['version']}")


def make_t1(name):
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


def clean():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        if m.users == 0:
            bpy.data.meshes.remove(m)


def measure(ob, gx, gy):
    """Per-tile fill + distortion (area ratio spread)."""
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    me = ob.data
    bm = bmesh.from_edit_mesh(me)
    uvl = bm.loops.layers.uv.active
    islands = P.detect_islands(bm, uvl)
    before = [i.uv_area for i in islands]
    res = P.verify_packing(ob, gx, gy)
    per = {}
    for p in res["per_island"]:
        if p["tile"] is None:
            continue
        tu, tv = p["tile"]
        w = p["bounds"][2] - p["bounds"][0]
        h = p["bounds"][3] - p["bounds"][1]
        per.setdefault((tu, tv), 0.0)
        per[(tu, tv)] += w * h
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    fills = {t: v / ((1 - 0.02) ** 2) for t, v in per.items()}
    return res, fills


def areas(ob):
    """uv_area/world_area per island in object mode."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    isl = P.detect_islands(bm, uvl)
    out = [(i.uv_area, i.world_area) for i in isl]
    bm.free()
    return out


print("=== SMOKE v2: T1 2x2 normalize OFF ===")
clean()
ob = make_t1("smoke_off")
pre = areas(ob)
r = P.pack_objects([ob], 2, 2, False, True, 0.01)
print("result:", {k: v for k, v in r.items() if k != "objects"},
      "obj:", r["objects"].get("smoke_off"))
res, fills = measure(ob, 2, 2)
post = areas(ob)
ratios = [a / b for (a, _), (_, b) in zip(post, pre) if b > 1e-9]
# note: island ORDER may differ between detections; compare as multisets via
# sorted lists of final/pre area ratios is invalid - instead check uniformity
# of final density with normalize ON below. Report spread of raw ratios.
rs = sorted(ratios)
print(f"islands={res['islands']} all_inside={res['all_inside']}")
print("fills:", {t: round(v, 3) for t, v in fills.items()})
print(f"ratio spread (order-sensitive, informational): "
      f"{rs[0]:.3f} .. {rs[-1]:.3f}")

print()
print("=== SMOKE v2: T1 2x2 normalize ON ===")
clean()
ob = make_t1("smoke_on")
r = P.pack_objects([ob], 2, 2, True, True, 0.01)
res, fills = measure(ob, 2, 2)
dens = [u / w for u, w in areas(ob) if w > 1e-9]
spread = max(dens) / min(dens)
print(f"islands={res['islands']} all_inside={res['all_inside']}")
print("fills:", {t: round(v, 3) for t, v in fills.items()})
print(f"texel density spread (on): {spread:.6f}  "
      f"(1.0 = perfectly uniform)")

print()
print("=== SMOKE v2: multi-object 2x2 (T5-like) ===")
clean()
o1 = make_t1("sm_m1")
bpy.ops.mesh.primitive_cube_add(size=1.5, location=(0, 10, 0))
o2 = bpy.context.active_object
o2.name = "sm_m2"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
r = P.pack_objects([o1, o2], 2, 2, False, True, 0.01)
print("result:", {k: v for k, v in r.items() if k != "objects"},
      "obj:", r["objects"])
ok1 = ok2 = False
for ob_, tag in ((o1, "a"), (o2, "b")):
    res, fills = measure(ob_, 2, 2)
    ok = res["all_inside"]
    print(f"{tag}: islands={res['islands']} all_inside={ok} "
          f"fills={{t: round(v,3) for t,v in fills.items()}}")
    ok1 = ok1 or (tag == "a" and ok)
    ok2 = ok2 or (tag == "b" and ok)

print()
print("SMOKE DONE")
