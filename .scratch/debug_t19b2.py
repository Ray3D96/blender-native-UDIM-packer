# SPDX-License-Identifier: GPL-2.0-or-later
"""Minimal T19b reproduction with length diagnostics."""
import bmesh
import bpy

# --- force-reload addon from source tree (sys.modules hazard) -------------
import importlib
import sys

for _m in [m for m in list(sys.modules)
           if m.startswith("native_udim_packer")]:
    sys.modules.pop(_m, None)
try:
    import native_udim_packer as _old  # noqa: F401
except ImportError:
    pass
else:
    try:
        _old.unregister()
    except Exception:
        pass
    for _m in [m for m in list(sys.modules)
               if m.startswith("native_udim_packer")]:
        sys.modules.pop(_m, None)

sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
import native_udim_packer as P  # noqa: E402
P.register()


def state(tag):
    me = bpy.context.scene.objects["t18"].data
    print(f"{tag}: layers={[l.name for l in me.uv_layers]} "
          f"active={me.uv_layers.active.name} "
          f"loops={len(me.uv_layers.active.data)}", flush=True)


# --- fixture (same recipe as e2e make_test_object) ------------------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
b = bpy.context.active_object
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8, location=(-6, 0, 0))
c = bpy.context.active_object
bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
b.select_set(True)
c.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
ob = bpy.context.active_object
ob.name = "t18"
me = ob.data
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')

state("pre-T19a")
pre = [(d.uv.x, d.uv.y) for d in me.uv_layers.active.data]

# --- T19b sequence ---------------------------------------------------------
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
state("in-edit")
try:
    bpy.ops.uv.select_all(action='DESELECT')
    print("uv.select_all DESELECT ok", flush=True)
except Exception as exc:  # noqa: BLE001
    print(f"uv.select_all EXC {exc}", flush=True)
state("after-op")
bmz = bmesh.from_edit_mesh(me)
for f in tuple(bmz.faces):
    f.uv_select = False
bmesh.update_edit_mesh(me)
bmz.free()
state("after-clear")

r = P.pack_objects([ob], 2, 2, False, True, 0.01, selected_islands=True)
print(f"pack result: {r.get('error')!r}", flush=True)
state("post-pack")
post = [(d.uv.x, d.uv.y) for d in me.uv_layers.active.data]
print(f"len pre={len(pre)} post={len(post)} eq={pre == post}", flush=True)
if pre != post:
    common = min(len(pre), len(post))
    for k in range(common):
        if pre[k] != post[k]:
            print(f"first-diff {k}: {pre[k]} -> {post[k]}", flush=True)
            break
    else:
        print("common prefix identical; length differs", flush=True)
print("PROBE-DONE", flush=True)
