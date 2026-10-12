"""Isolate object-level vs data-level cause: copy Wire's mesh, strip suspects."""
import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

ob = bpy.data.objects["Wire"]
me = ob.data


def pack_obj(o, tag):
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    r = bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(o.data)
    for f in tuple(bm.faces):
        f.select = True
    bmesh.update_edit_mesh(o.data)
    bm.free()
    res = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                  margin=0.0, scale=False)
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    print(f"W7 {tag}: -> {res}")
    return res == {'FINISHED'}


# 1: plain copy of the mesh data on a fresh object (no modifiers)
m_copy = me.copy()
o_copy = bpy.data.objects.new("w7_copy", m_copy)
bpy.context.scene.collection.objects.link(o_copy)
pack_obj(o_copy, "mesh copy, no modifier")

# 2: original Wire with SUBSURF disabled
mod = ob.modifiers[0]
print(f"W7 Wire modifier {mod.type} show_viewport={mod.show_viewport}")
mod.show_viewport = False
mod.show_render = False
pack_obj(ob, "Wire with SUBSURF off")
mod.show_viewport = True
mod.show_render = True

# 3: copy + remove loose elements
m2 = me.copy()
bm = bmesh.new()
bm.from_mesh(m2)
loose_v = [v for v in bm.verts if not v.link_faces]
loose_e = [e for e in bm.edges if not e.link_faces]
print(f"W7 loose verts={len(loose_v)} loose edges={len(loose_e)}")
bmesh.ops.delete(bm, geom=loose_v + loose_e, context='VERTS_EDGES')
bm.to_mesh(m2)
bm.free()
o2 = bpy.data.objects.new("w7_noloose", m2)
bpy.context.scene.collection.objects.link(o2)
pack_obj(o2, "copy minus loose elements")

# 4: copy + triangulate all faces (3D topology)
m3 = me.copy()
bm = bmesh.new()
bm.from_mesh(m3)
bmesh.ops.triangulate(bm, faces=list(bm.faces))
bm.to_mesh(m3)
bm.free()
o3 = bpy.data.objects.new("w7_tris", m3)
bpy.context.scene.collection.objects.link(o3)
pack_obj(o3, "copy triangulated")

# 5: copy + drop custom split normals / smooth shading
m4 = me.copy()
try:
    if m4.has_custom_normals():
        m4.clear_custom_normals()
except AttributeError:
    pass
for p in m4.polygons:
    p.use_smooth = False
o4 = bpy.data.objects.new("w7_flat", m4)
bpy.context.scene.collection.objects.link(o4)
pack_obj(o4, "copy flat-shaded, no custom normals")

print("W7DONE")
