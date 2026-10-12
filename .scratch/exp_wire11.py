"""Confirm ob.hide_set(False) alone unblocks pack_islands on Wire."""
import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

ob = bpy.data.objects["Wire"]


def pack_wire(tag):
    if ob.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(ob.data)
    for f in tuple(bm.faces):
        f.select = True
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    if ob.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    print(f"W11 {tag}: hide_get={ob.hide_get()} visible={ob.visible_get()} -> {r}")
    return r == {'FINISHED'}


print(f"W11 start: hide_get={ob.hide_get()} hide_viewport={ob.hide_viewport} "
      f"visible={ob.visible_get()}")
pack_wire("baseline hidden")

ob.hide_set(False)
ok = pack_wire("after hide_set(False)")

ob.hide_set(True)
pack_wire("restored hidden (should fail)")
print(f"W11 RESULT: fix works = {ok}")
print("W11DONE")
