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

# initialize undo system (as our addon will do via ed.undo_push)
bpy.ops.ed.undo_push(message="NativeUDIM: Pack to UDIM Grid")
print("S0 (baseline):         ", bounds(c))

# change 1: direct bmesh shift
bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
for f in tuple(bm.faces):
    for l in tuple(f.loops):
        l[uvl].uv.x += 0.25
bmesh.update_edit_mesh(c.data)
bm.free()
print("S1 (after bmesh shift):", bounds(c))

# change 2: pack_islands operator
with bpy.context.temp_override(object=c, active_object=c):
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=False, scale=True, margin_method='FRACTION', margin=0.01)
print("S2 (after pack):       ", bounds(c))

bpy.ops.ed.undo()
print("U1 (undo #1):          ", bounds(c))
bpy.ops.ed.undo()
print("U2 (undo #2):          ", bounds(c))
bpy.ops.object.mode_set(mode='OBJECT')
