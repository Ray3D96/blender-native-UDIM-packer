"""Bisect: which Wire faces (or global state) make pack_islands cancel."""
import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

ob = bpy.data.objects["Wire"]
me = ob.data
N = len(me.polygons)


def pack_face_set(idxs, tag):
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table()
    for f in tuple(bm.faces):
        f.select = (f.index in idxs)
    bmesh.update_edit_mesh(me)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ok = r == {'FINISHED'}
    print(f"W6 {tag}: n={len(idxs)} -> {'OK' if ok else 'CANCELLED'}")
    return ok


# 1: all faces EXCEPT face 0
pack_face_set(set(range(1, N)), "all except face0")
# 2: face 0 alone (re-confirm)
pack_face_set({0}, "face0 alone")
# 3: a middle face alone
pack_face_set({N // 2}, "middle face alone")

# 4: if both 1 and 3 behave differently, bisect the failing half.
all_ok = pack_face_set(set(range(N)), "ALL faces (re-confirm)")
if not all_ok:
    # find a minimal-ish failing subset by halving
    cur = list(range(N))
    for _ in range(12):
        if len(cur) <= 8:
            break
        half = len(cur) // 2
        lo = set(cur[:half])
        hi = set(cur[half:])
        if not pack_face_set(lo, f"bisect-lo n={len(lo)}"):
            cur = list(lo)
        else:
            # lo is fine -> culprit in hi (or interaction); keep hi
            cur = list(hi)
    print(f"W6 minimal failing subset: {cur}")

print("W6DONE")
