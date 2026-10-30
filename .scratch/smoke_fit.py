# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke the measured-fit + rebalance path."""
import sys
import time
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
from native_udim_packer import layout, packer

FAIL = 0

def check(name, cond, detail=""):
    global FAIL
    print(("  ok  " if cond else " FAIL ") + name + ("" if cond else "  " + str(detail)),
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

def overlaps(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    try:
        uvl = bm.loops.layers.uv.active
        islands = packer.detect_islands(bm, uvl)
        polys = []
        for isl in islands:
            faces = []
            for f in tuple(bm.faces):
                if f.index in isl.face_indices:
                    faces.append([(l[uvl].uv.x, l[uvl].uv.y) for l in tuple(f.loops)])
            if faces:
                polys.append(faces)
    finally:
        bm.free()
    return layout.tile_islands_overlap(polys)

def run(name, obs, **kw):
    print(f"\n=== {name} ===", flush=True)
    t0 = time.perf_counter()
    try:
        res = packer.pack_objects(obs, **kw)
    except Exception:
        traceback.print_exc()
        check(name, False, "raised")
        return
    dt = time.perf_counter() - t0
    err = res.get("error")
    check(name + " packed", not err, err)
    if err:
        return
    print(f"  {dt:.2f}s scale={res.get('global_scale'):.4f} "
          f"stretch={res.get('stretch_factor'):.4f} "
          f"moves={res.get('rebalance_moves')} tiles={res.get('tiles_used_total')}",
          flush=True)
    gx, gy = kw.get("grid_x", 2), kw.get("grid_y", 2)
    for ob in obs:
        v = packer.verify_packing(ob, gx, gy)
        check(f"{name} {ob.name} inside", v["all_inside"])
        check(f"{name} {ob.name} no overlap", not overlaps(ob))

clear()
bpy.ops.mesh.primitive_cube_add(size=2)
cube = bpy.context.active_object
smart([cube])
run("cube-2x2", [cube], grid_x=2, grid_y=2, margin=0.005, rotate_90=True)

clear()
bpy.ops.mesh.primitive_monkey_add(size=2)
mon = bpy.context.active_object
smart([mon])
run("monkey-2x2", [mon], grid_x=2, grid_y=2, margin=0.005, rotate_90=True)

clear()
bpy.ops.mesh.primitive_monkey_add(size=1)
mon = bpy.context.active_object
run("suzanne-native-3x1", [mon], grid_x=3, grid_y=1, margin=0.01, rotate_90=True)

print(f"\nSMOKE FAIL={FAIL}", flush=True)
sys.exit(1 if FAIL else 0)
