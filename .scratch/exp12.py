import bpy, bmesh

def bounds(bm, uvl, idx=None):
    pts = [l[uvl].uv for f in tuple(bm.faces) if (idx is None or f.index in idx) for l in tuple(f.loops)]
    return (round(min(p.x for p in pts),4), round(max(p.x for p in pts),4),
            round(min(p.y for p in pts),4), round(max(p.y for p in pts),4))

bpy.ops.mesh.primitive_cube_add(size=2)
c = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)

bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
# select all via bmesh + translate min to origin (already ~0)
for f in tuple(bm.faces):
    f.select_set(True)
bmesh.update_edit_mesh(c.data)
print("same-bm before pack:", bounds(bm, uvl))

with bpy.context.temp_override(object=c, active_object=c):
    bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='CARDINAL', scale=True, margin_method='FRACTION', margin=0.01)

print("same-bm after pack: ", bounds(bm, uvl))
bm.free()
bm2 = bmesh.from_edit_mesh(c.data)
uvl2 = bm2.loops.layers.uv.active
print("fresh-bm after pack:", bounds(bm2, uvl2))
bm2.free()
bpy.ops.object.mode_set(mode='OBJECT')
