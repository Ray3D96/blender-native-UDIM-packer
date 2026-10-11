# SPDX-License-Identifier: GPL-2.0-or-later
"""Smoke test for the 0.1.1 release zip: install, enable, version, one pack."""
import sys
import bpy

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}  ({detail})")
    if not cond:
        FAILS.append(name)


r = bpy.ops.preferences.addon_install(
    filepath="/mnt/fusion/ai-projects/blender-uv-packer/dist/native_udim_packer-0.1.1.zip")
check("install 0.1.1 from zip", r == {'FINISHED'}, str(r))
bpy.ops.preferences.addon_enable(module="native_udim_packer")
import addon_utils
check("addon enabled", addon_utils.check("native_udim_packer"))

import native_udim_packer as A
check("bl_info version is 0.1.1", tuple(A.bl_info["version"]) == (0, 1, 1),
      str(A.bl_info["version"]))
check("VERSION string", A.VERSION == "0.1.1", A.VERSION)
check("operator registered", hasattr(bpy.ops.native_udim, "pack_to_grid"))

# panel class present and its draw() references the version stamp
ui = __import__("native_udim_packer.ui", fromlist=["ui"])
src = open(ui.__file__).read()
check("panel shows version stamp", f'f"version {{"VERSION"}}"' in src or "version {VERSION}" in src)

# one real pack to prove the engine is intact in this build
bpy.ops.mesh.primitive_cube_add(size=2)
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
b = bpy.context.active_object
a.select_set(True); b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
ob = bpy.context.active_object
ob.name = "smoke"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
r = bpy.ops.native_udim.pack_to_grid(udim_x=2, udim_y=2, normalize_scale=False,
                                     rotate_90=True, margin=0.01)
check("pack FINISHED", r == {'FINISHED'}, str(r))

print()
print(f"SMOKE: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
