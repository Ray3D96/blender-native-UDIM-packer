"""Diagnose why uv.pack_islands CANCELLED on the QA 'Wire' object.

v2: commit any saved edit-mode state first (the QA blend is stored with an
object in EDIT mode), then probe pack_islands behavior on Wire alone.
"""
import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    print("WIRE saved-in-edit:", bpy.context.object.name,
          "-> committing to OBJECT")
    bpy.ops.object.mode_set(mode='OBJECT')

ob = bpy.data.objects.get("Wire")
me = ob.data
print("WIRE mesh:", me.name, "users:", me.users, "polys:", len(me.polygons))
print("WIRE uv_layers:", [l.name for l in me.uv_layers],
      "active:", me.uv_layers.active.name if me.uv_layers.active else None)
print("WIRE shape_keys:", me.shape_keys is not None,
      "modifiers:", [m.type for m in ob.modifiers])

bpy.ops.object.select_all(action="DESELECT")
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode="EDIT")


def sel_count():
    bm = bmesh.from_edit_mesh(me)
    n = sum(1 for f in tuple(bm.faces) if f.select)
    total = len(bm.faces)
    idx0 = None
    bm.faces.ensure_lookup_table()
    fs = sorted(f.index for f in tuple(bm.faces))
    bm.free()
    return n, total, fs[0], fs[-1]


# A: select ALL faces (via bmesh), pack
bm = bmesh.from_edit_mesh(me)
for f in tuple(bm.faces):
    f.select = True
bmesh.update_edit_mesh(me)
bm.free()
print("WIRE A pre-pack selected:", sel_count())
r1 = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                             margin=0.0, scale=False)
print("WIRE A all-faces pack:", r1)

# B: single face (lowest index), pack
lo = sel_count()[2]
bm = bmesh.from_edit_mesh(me)
bm.faces.ensure_lookup_table()
for f in tuple(bm.faces):
    f.select = (f.index == lo)
bmesh.update_edit_mesh(me)
bm.free()
print("WIRE B pre-pack selected:", sel_count())
r2 = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                             margin=0.0, scale=False)
print("WIRE B one-face pack:", r2)

# C: single face, rotate off
bm = bmesh.from_edit_mesh(me)
bm.faces.ensure_lookup_table()
for f in tuple(bm.faces):
    f.select = (f.index == lo)
bmesh.update_edit_mesh(me)
bm.free()
r3 = bpy.ops.uv.pack_islands(rotate=False, rotate_method="CARDINAL",
                             margin=0.0, scale=False)
print("WIRE C one-face no-rot:", r3)

# D: index sanity - edit bmesh face indices vs me.polygons order
bm = bmesh.from_edit_mesh(me)
bm.faces.ensure_lookup_table()
edit_idx = [f.index for f in tuple(bm.faces)]
bm.free()
poly_idx = list(range(len(me.polygons)))
same = sorted(edit_idx) == poly_idx
print("WIRE D edit-face-indexes == 0..n-1:", same,
      "min/max:", min(edit_idx), max(edit_idx))

# E: does another cable object behave the same? (cross-check)
for cand in ("cable", "cable.001"):
    o2 = bpy.data.objects.get(cand)
    if o2 is None or o2.type != 'MESH':
        continue
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    o2.select_set(True)
    bpy.context.view_layer.objects.active = o2
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(o2.data)
    for f in tuple(bm.faces):
        f.select = True
    bmesh.update_edit_mesh(o2.data)
    bm.free()
    r4 = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                 margin=0.0, scale=False)
    print(f"WIRE E {cand} all-faces pack:", r4)
    bpy.ops.object.mode_set(mode="OBJECT")

bpy.ops.object.mode_set(mode="OBJECT")
print("WIREDONE")
