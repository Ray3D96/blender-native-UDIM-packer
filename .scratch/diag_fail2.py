# SPDX-License-Identifier: GPL-3.0-or-later
"""Stress the scale search and report why rounds are refused."""
import sys
import traceback

import bpy

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
from native_udim_packer import layout as L
from native_udim_packer import packer

_real_solve = L.solve


def logging_solve(items, grid_x, grid_y, margin, oracle, max_rounds=48, etas=(0.92, 0.85, 0.75, 0.65, 0.5)):
    stats = {"calls": 0, "refuse": 0, "extent": 0, "fit": 0}
    last_s = [None]

    def wrapped(assign, S):
        stats["calls"] += 1
        last_s[0] = S
        ntiles = len(set(assign.values()))
        try:
            ext = oracle(assign, S)
        except L.PackRefusedError as exc:
            stats["refuse"] += 1
            if stats["refuse"] <= 4 or stats["refuse"] % 25 == 0:
                print(f"    refuse #{stats['refuse']} S={S:.5f} tiles={ntiles} {exc}",
                      flush=True)
            raise
        stats["extent"] += 1
        used = [e for e in ext if e is not None]
        worst = 0.0
        for e in used:
            worst = max(worst, e[2], e[3], e[2] - e[0], e[3] - e[1])
        print(f"    measured S={S:.5f} tiles={ntiles} worst={worst:.4f} n={len(used)}",
              flush=True)
        return ext

    try:
        out = _real_solve(items, grid_x, grid_y, margin, wrapped, max_rounds, etas)
        print(f"  SOLVED S={out[0]:.5f} rounds={out[2]} calls={stats}", flush=True)
        return out
    except RuntimeError as exc:
        print(f"  FAILED {exc} calls={stats} lastS={last_s[0]}", flush=True)
        raise


L.solve = logging_solve
packer._layout_solve = logging_solve


def clear():
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


def run(name, obs, **kw):
    print(f"\n=== {name} polys={sum(len(o.data.polygons) for o in obs)} ===", flush=True)
    try:
        res = packer.pack_objects(obs, **kw)
        print("  result error:", res.get("error"),
              "islands", res.get("packed_islands"),
              "tiles", res.get("tiles_used_total"),
              flush=True)
    except Exception:
        traceback.print_exc()


print("\n##### UV SPHERE #####", flush=True)
clear()
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
ob = bpy.context.active_object
smart([ob])
run("sphere-2x2", [ob], grid_x=2, grid_y=2, margin=0.005, rotate_90=True)
clear()
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
ob = bpy.context.active_object
smart([ob])
run("sphere-1x1", [ob], grid_x=1, grid_y=1, margin=0.005, rotate_90=False)

print("\n##### TORUS #####", flush=True)
clear()
bpy.ops.mesh.primitive_torus_add(major_segments=48, minor_segments=16,
                                 major_radius=1.0, minor_radius=0.25)
ob = bpy.context.active_object
smart([ob])
run("torus-2x2", [ob], grid_x=2, grid_y=2, margin=0.01, rotate_90=True)

print("\n##### 4 MONKEYS #####", flush=True)
clear()
obs = []
for i in range(4):
    bpy.ops.mesh.primitive_monkey_add(size=1.5, location=(i * 3, 0, 0))
    obs.append(bpy.context.active_object)
smart(obs)
run("4monkeys-2x2", obs, grid_x=2, grid_y=2, margin=0.005, rotate_90=True)

print("\n##### QA BLEND #####", flush=True)
bpy.ops.wm.open_mainfile(filepath=ROOT + "/QA_Test_Files/P_BLENDER_01.5.blend")
meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]
print("  objects:", [(o.name, len(o.data.polygons)) for o in meshes], flush=True)
# Pack each mesh alone on 2x2, skip anything huge.
for o in meshes:
    if len(o.data.polygons) > 8000:
        print(f"  skip {o.name} polys={len(o.data.polygons)}", flush=True)
        continue
    # ensure visible / selectable
    o.hide_set(False)
    o.hide_viewport = False
    run(f"qa:{o.name}", [o], grid_x=2, grid_y=2, margin=0.005, rotate_90=True)

print("\nDONE", flush=True)
