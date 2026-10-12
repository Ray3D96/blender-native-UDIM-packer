# Probe 9: does the CANCEL pattern follow face INDEX (construction order)
# or GEOMETRY (side vs top/bottom)? Test standalone cubes built three ways.
import bmesh
import bpy

MARGIN = 0.008


def clear():
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def smart(ob):
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')


def test_face(tag, ob, face_idx):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    x0, y0, w, h = 0.0, 0.0, 0.797, 0.797
    for f in tuple(bm.faces):
        if f.index == face_idx:
            coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
            for l, c in zip(tuple(f.loops), coords):
                l[uvl].uv = c
        f.select = (f.index == face_idx)
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=MARGIN, scale=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE9 {tag} face{face_idx} -> {r}", flush=True)


# --- variant A: default cube, straight -------------------------------------
clear()
bpy.ops.mesh.primitive_cube_add(size=2)
a = bpy.context.active_object
a.name = "cubeA"
smart(a)
for i in range(6):
    test_face("A-default", a, i)

# --- variant B: cube rotated 90 deg about X before smart_project ------------
clear()
bpy.ops.mesh.primitive_cube_add(size=2)
b = bpy.context.active_object
b.name = "cubeB"
b.rotation_euler = (1.5707963, 0.0, 0.0)
bpy.ops.object.transform_apply(rotation=True)
smart(b)
for i in range(6):
    test_face("B-rotX90", b, i)

# --- variant C: cube built via bmesh (different construction) ---------------
clear()
me = bpy.data.meshes.new("cubeC")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=2.0)
bm.to_mesh(me)
bm.free()
c = bpy.data.objects.new("cubeC", me)
bpy.context.scene.collection.objects.link(c)
bpy.context.view_layer.objects.active = c
smart(c)
for i in range(6):
    test_face("C-bmesh", c, i)

print("PROBE9 DONE", flush=True)
