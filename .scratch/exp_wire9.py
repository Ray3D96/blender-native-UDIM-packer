"""Object-state facts for Wire + ob.copy() (shared data) pack test."""
import bpy

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)

# 1: which objects are in edit mode right after load?
edit_objs = [o.name for o in bpy.data.objects if o.mode == 'EDIT']
print(f"W9 edit-mode objects after load: {edit_objs}")
print(f"W9 context.object after load: "
      f"{bpy.context.object.name if bpy.context.object else None} "
      f"mode={bpy.context.object.mode if bpy.context.object else None}")

ob = bpy.data.objects["Wire"]
print(f"W9 Wire is_edit_mode={ob.mode == 'EDIT'} mode={ob.mode}")
print(f"W9 Wire hide_viewport={ob.hide_viewport} hide_select={ob.hide_select} "
      f"visible={ob.visible_get()} instance_type={ob.instance_type}")
print(f"W9 Wire data.users={ob.data.users} collection(s)="
      f"{[c.name for c in ob.users_collection]}")

if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    r = bpy.ops.object.mode_set(mode='OBJECT')
    print(f"W9 commit edit -> {r}")
print(f"W9 Wire mode after commit: {ob.mode} "
      f"edit_objs={[o.name for o in bpy.data.objects if o.mode == 'EDIT']}")


def pack_obj(o, tag):
    r0 = None
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        r0 = bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    r1 = bpy.ops.object.mode_set(mode="EDIT")
    print(f"W9 {tag}: mode_set(EDIT)->{r1} ctx_mode={bpy.context.object.mode if bpy.context.object else None} "
          f"is_edit={o.mode == 'EDIT'}")
    import bmesh
    bm = bmesh.from_edit_mesh(o.data)
    for f in tuple(bm.faces):
        f.select = True
    bmesh.update_edit_mesh(o.data)
    bm.free()
    r2 = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                 margin=0.0, scale=False)
    print(f"W9 {tag}: pack -> {r2}")
    if o.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    return r2 == {'FINISHED'}


# 2: Wire now (clean state)
pack_obj(ob, "Wire original")

# 3: ob.copy() shares the SAME mesh data, new object
o_c = ob.copy()  # does NOT copy data by default? -> copy() copies object only, shares data
o_c.name = "w9_wirecopy"
bpy.context.scene.collection.objects.link(o_c)
print(f"W9 copy shares data: {o_c.data is ob.data} "
      f"modifiers={[m.type for m in o_c.modifiers]}")
pack_obj(o_c, "Wire ob.copy() (shared data)")

# 4: if copy worked and original didn't -> strip object-level differences.
#    Try: move Wire into the same collection as the copy / clear custom props?
#    First just retest original once more after all that state churn.
pack_obj(ob, "Wire original (retest)")
print("W9DONE")
