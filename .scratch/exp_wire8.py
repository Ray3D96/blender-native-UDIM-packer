"""Per-island probe on Wire: which island(s) make pack_islands cancel?"""
import sys

import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

# import the addon's island detector (force-reload pattern)
for m in [k for k in list(sys.modules) if k.startswith("native_udim_packer")]:
    del sys.modules[m]
sys.path.insert(0, ADDON_PATH)
import importlib

mod = importlib.import_module("native_udim_packer.islands")
detect_islands = mod.detect_islands

ob = bpy.data.objects["Wire"]
me = ob.data

bm = bmesh.new()
bm.from_mesh(me)
uvl = bm.loops.layers.uv.active
islands = detect_islands(bm, uvl)
bm.free()
print(f"W8 Wire islands={len(islands)}")
sizes = sorted((len(i.face_indices) for i in islands), reverse=True)
print(f"W8 island face counts (top 12): {sizes[:12]} total={sum(sizes)}")


def pack_face_set(idxs, tag):
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bm2 = bmesh.from_edit_mesh(me)
    bm2.faces.ensure_lookup_table()
    for f in tuple(bm2.faces):
        f.select = (f.index in idxs)
    bmesh.update_edit_mesh(me)
    bm2.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ok = r == {'FINISHED'}
    print(f"W8 {tag}: n={len(idxs)} -> {'OK' if ok else 'CANCELLED'}")
    return ok


# test each island alone (cap output: all islands, but tag big ones)
bad = []
for k, isl in enumerate(islands):
    fi = set(isl.face_indices)
    tag = f"island {k} faces={len(fi)}"
    if not pack_face_set(fi, tag):
        bad.append(k)

print(f"W8 failing islands: {bad}")

# test: all faces EXCEPT the first failing island
if bad:
    skip = set(islands[bad[0]].face_indices)
    rest = set(range(len(me.polygons))) - skip
    pack_face_set(rest, f"all minus failing island {bad[0]}")
print("W8DONE")
