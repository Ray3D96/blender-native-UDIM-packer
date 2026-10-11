import bpy, bmesh

def bounds_of(ob, face_indices=None):
    idx = set(face_indices) if face_indices is not None else None
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    pts = [l[uvl].uv for f in tuple(bm.faces) if (idx is None or f.index in idx) for l in tuple(f.loops)]
    r = (round(min(p.x for p in pts),4), round(max(p.x for p in pts),4),
         round(min(p.y for p in pts),4), round(max(p.y for p in pts),4))
    bm.free()
    return r

# --- Hypothesis test: island fully inside tile (1,0), pack without moving ---
bpy.ops.mesh.primitive_cube_add(size=2)
c = bpy.context.active_object; c.name = "hypo"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
# move all UVs +1 in x -> now inside tile (1,0): [1.0..2.0]x[0..1]
bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
for f in tuple(bm.faces):
    for l in tuple(f.loops):
        l[uvl].uv.x += 1.0
bmesh.update_edit_mesh(c.data)
bm.free()
print("before (in tile 1,0):", bounds_of(c))
with bpy.context.temp_override(object=c, active_object=c):
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=False, scale=True, margin_method='FRACTION', margin=0.01)
print("after pack (no move):", bounds_of(c), " <- if in [1,2]x[0,1]: closest=min-corner tile")
bpy.ops.object.mode_set(mode='OBJECT')

# --- Robustness: multi-island group, min=(0,0), extent up to 2.5 -> must all fit [0,1]^2 ---
bpy.ops.mesh.primitive_cube_add(size=2)
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(5,0,0))
b = bpy.context.active_object
a.select_set(True); b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
c = bpy.context.active_object; c.name = "robust"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
# scale everything 2.5x (min stays ~0), then pack
bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
for f in tuple(bm.faces):
    for l in tuple(f.loops):
        l[uvl].uv *= 2.5
bmesh.update_edit_mesh(c.data)
bm.free()
print("before (2.5x, min~0):", bounds_of(c))
with bpy.context.temp_override(object=c, active_object=c):
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='CARDINAL', scale=True, margin_method='FRACTION', margin=0.01)
print("after pack:", bounds_of(c), " <- must be within [0,1]x[0,1]")
bpy.ops.object.mode_set(mode='OBJECT')
