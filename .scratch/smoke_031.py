# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke the reliability fixes: uneven scales, selected islands, multi-object."""
import sys
import traceback

import bpy
import bmesh

ROOT = "/mnt/fusion/ai-projects/blender-uv-packer"
_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception:
        pass
for n in [n for n in list(sys.modules) if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[n]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import native_udim_packer as A
A.register()
from native_udim_packer import packer

FAIL = 0

def check(name, cond, detail=""):
    global FAIL
    print(("  ok  " if cond else " FAIL ") + name + ("" if cond else "  " + detail),
          flush=True)
    if not cond:
        FAIL += 1

def clear():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

def smart(obs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")

def scale_largest(ob, factor):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    try:
        uvl = bm.loops.layers.uv.active
        islands = A.islands.detect_islands(bm, uvl)
        big = max(islands, key=lambda i: i.uv_area)
        cx = (big.min_uv[0] + big.max_uv[0]) * 0.5
        cy = (big.min_uv[1] + big.max_uv[1]) * 0.5
        for f in tuple(bm.faces):
            if f.index not in big.face_indices:
                continue
            for l in tuple(f.loops):
                u = l[uvl].uv
                u.x = cx + (u.x - cx) * factor
                u.y = cy + (u.y - cy) * factor
        bm.to_mesh(me)
    finally:
        bm.free()

def run(name, obs, **kw):
    print(f"\n=== {name} ===", flush=True)
    try:
        res = packer.pack_objects(obs, **kw)
    except Exception:
        traceback.print_exc()
        check(name + " no exception", False, "raised")
        return None
    err = res.get("error")
    check(name + " packed", not err, str(err))
    if err:
        return res
    gx, gy = kw.get("grid_x", 2), kw.get("grid_y", 2)
    for ob in obs:
        v = packer.verify_packing(ob, gx, gy)
        check(f"{name} {ob.name} inside", v["all_inside"], str(v["per_island"][:3]))
    print(f"  scale={res.get('global_scale'):.4f} stretch={res.get('stretch_factor'):.4f} "
          f"tiles={res.get('tiles_used_total')} islands={res.get('packed_islands')}",
          flush=True)
    return res

clear()
bpy.ops.mesh.primitive_cube_add(size=2)
cube = bpy.context.active_object
smart([cube])
run("cube-2x2", [cube], grid_x=2, grid_y=2, margin=0.005, rotate_90=True)

clear()
bpy.ops.mesh.primitive_monkey_add(size=2)
mon = bpy.context.active_object
smart([mon])
scale_largest(mon, 8.0)
run("monkey-uneven", [mon], grid_x=2, grid_y=2, margin=0.005, rotate_90=True,
    normalize_scale=False)

clear()
bpy.ops.mesh.primitive_monkey_add(size=2)
mon = bpy.context.active_object
smart([mon])
scale_largest(mon, 8.0)
run("monkey-uneven-norm", [mon], grid_x=2, grid_y=2, margin=0.005, rotate_90=True,
    normalize_scale=True)

clear()
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
a = bpy.context.active_object
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8, location=(-3, 0, 0))
b = bpy.context.active_object
smart([a, b])
# Select the largest islands on A only, from edit mode, and pack with the
# option on — B's islands must stay put.
bpy.ops.object.select_all(action="DESELECT")
a.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.mode_set(mode="EDIT")
bm = bmesh.from_edit_mesh(a.data)
uvl = bm.loops.layers.uv.active
islands = packer.detect_islands(bm, uvl)
picked = sorted(islands, key=lambda i: -i.uv_area)[:2]
want = set()
for isl in picked:
    want |= isl.face_indices
for f in tuple(bm.faces):
    f.uv_select = f.index in want
bmesh.update_edit_mesh(a.data)
bm.free()
# snapshot B
pre_b = packer._snapshot_uv(b.data)
res = run("selected-islands", [a, b], grid_x=2, grid_y=2, margin=0.01,
          rotate_90=True, selected_islands=True)
if res and not res.get("error"):
    post_b = packer._snapshot_uv(b.data)
    check("selected-islands leaves the other object untouched", pre_b == post_b,
          f"faces {len(pre_b)}")
    check("selected-islands packed count", res.get("packed_islands") == 2,
          str(res.get("packed_islands")))

print(f"\nSMOKE FAIL={FAIL}", flush=True)
sys.exit(1 if FAIL else 0)
