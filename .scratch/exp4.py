import bpy, bmesh

def snap(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    s = tuple((f.index, round(l[uvl].uv.x,5), round(l[uvl].uv.y,5)) for f in tuple(bm.faces) for l in tuple(f.loops))
    bm.free()
    return s

bpy.ops.mesh.primitive_cube_add(size=2)
c = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
S0 = snap(c)

# does ed.undo_push exist?
print("has undo_push:", hasattr(bpy.ops.ed, 'undo_push'))
try:
    bpy.ops.ed.undo_push(message="batch test")
    print("undo_push OK")
except Exception as e:
    print("undo_push FAIL:", e)

# change 1: direct bmesh UV shift
bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
for f in tuple(bm.faces):
    for l in tuple(f.loops):
        l[uvl].uv.x += 0.25
bmesh.update_edit_mesh(c.data)
bm.free()

# change 2: pack_islands (separate operator call)
with bpy.context.temp_override(object=c, active_object=c):
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=False, scale=True, margin_method='FRACTION', margin=0.01)

S1 = snap(c)
print("changes applied:", S1 != S0)

# single undo -> should revert BOTH if batching works
try:
    bpy.ops.ed.undo()
    print("undo OK")
except Exception as e:
    print("undo FAIL:", e)
S2 = snap(c)
print("single undo reverted both changes:", S2 == S0)

# second undo (if batching failed, this reverts the other change)
try:
    bpy.ops.ed.undo()
    print("second undo OK")
except Exception as e:
    print("second undo FAIL:", e)
S3 = snap(c)
print("after 2nd undo == S0:", S3 == S0)
bpy.ops.object.mode_set(mode='OBJECT')
