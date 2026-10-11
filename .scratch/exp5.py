import bpy, bmesh

def bounds(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    us = [l[uvl].uv for f in tuple(bm.faces) for l in tuple(f.loops)]
    r = (round(min(u.x for u in us),4), round(max(u.x for u in us),4),
         round(min(u.y for u in us),4), round(max(u.y for u in us),4))
    bm.free()
    return r

bpy.ops.mesh.primitive_cube_add(size=2)
c = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
print("S0 (after smart project):", bounds(c))

# single bmesh-only change, then undo
bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
for f in tuple(bm.faces):
    for l in tuple(f.loops):
        l[uvl].uv.x += 0.25
bmesh.update_edit_mesh(c.data)
bm.free()
print("S1 (after bmesh shift):", bounds(c))
bpy.ops.ed.undo()
print("S2 (after undo #1):    ", bounds(c))

# now: pack_islands only, then undo
with bpy.context.temp_override(object=c, active_object=c):
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=False, scale=True, margin_method='FRACTION', margin=0.01)
print("S3 (after pack):       ", bounds(c))
bpy.ops.ed.undo()
print("S4 (after undo #2):    ", bounds(c))
bpy.ops.object.mode_set(mode='OBJECT')
