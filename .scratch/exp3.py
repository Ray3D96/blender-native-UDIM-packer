import bpy, bmesh

def get_uv_snapshot(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    snap = {}
    for f in tuple(bm.faces):
        us = tuple((round(l[uvl].uv.x, 6), round(l[uvl].uv.y, 6)) for l in tuple(f.loops))
        snap[f.index] = (us, f.select)
    bm.free()
    return snap

bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,0))
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(5,0,0))
b = bpy.context.active_object
a.select_set(True); b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
c = bpy.context.active_object; c.name = "cubeC"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)

bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
for f in tuple(bm.faces):
    xs = [l[uvl].uv.x for l in tuple(f.loops)]
    f.select = min(xs) < 0.5
bmesh.update_edit_mesh(c.data)
bm.free()

before = get_uv_snapshot(c)
n_sel = sum(1 for us, sel in before.values() if sel)
print(f"selected faces: {n_sel}/{len(before)}")

with bpy.context.temp_override(object=c, active_object=c):
    r = bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='CARDINAL', scale=True, margin_method='FRACTION', margin=0.01)
print("pack result:", r)

after = get_uv_snapshot(c)
moved_unsel = [i for i in before if not before[i][1] and before[i][0] != after[i][0]]
moved_sel   = [i for i in before if before[i][1] and before[i][0] != after[i][0]]
print(f"unselected faces moved: {len(moved_unsel)}")
print(f"selected faces moved:   {len(moved_sel)}")
if not moved_unsel:
    print("PASS: unselected islands untouched")
else:
    i = moved_unsel[0]
    print("FAIL example:", before[i][0][:2], "->", after[i][0][:2])
bpy.ops.object.mode_set(mode='OBJECT')
