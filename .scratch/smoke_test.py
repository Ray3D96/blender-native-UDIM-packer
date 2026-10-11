import sys, bpy, bmesh
R = []
def check(name, cond, detail=""):
    R.append(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))

bpy.ops.preferences.addon_install(filepath="/mnt/fusion/ai-projects/blender-uv-packer/dist/native_udim_packer-1.0.0.zip")
bpy.ops.preferences.addon_enable(module="native_udim_packer")
check("install+enable", hasattr(bpy.ops.native_udim, "pack_to_grid"))
# panel class registered?
from native_udim_packer.ui import NATIVE_UDIM_PT_main
check("panel class registered", bpy.types.Panel is not None and NATIVE_UDIM_PT_main.bl_category == "UDIM")

bpy.ops.mesh.primitive_cube_add(size=2)
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(6,0,0))
b = bpy.context.active_object
a.select_set(True); b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
ob = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')

r = bpy.ops.native_udim.pack_to_grid(udim_x=3, udim_y=2, normalize_scale=True, rotate_90=True, margin=0.008)
check("pack 3x2 FINISHED", r == {'FINISHED'})
from native_udim_packer import packer
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
res = packer.verify_packing(ob, 3, 2)
check("all islands inside 3x2 tiles", res["all_inside"], f"islands={res['islands']}")
tiles = sorted({p['tile'] for p in res['per_island'] if p['tile']})
udims = sorted({p['udim'] for p in res['per_island'] if p['udim']})
check("UDIM ids row-major", udims == [1001 + u + v*3 for (u,v) in tiles], f"udims={udims}")
bpy.ops.object.mode_set(mode='OBJECT')
print("SMOKE:", "ALL PASS" if all(R) else "FAILURES")
sys.exit(0 if all(R) else 1)
