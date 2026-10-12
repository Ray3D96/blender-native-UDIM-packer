"""Validate multi-object edit-mode semantics for the per-tile rewrite.

Test 1: two objects, overlapping UVs, multi-edit both, select all faces,
        ONE uv.pack_islands call -> do cross-object islands avoid each
        other and land inside [0,1]?
Test 2: third object in the same multi-edit with UNSELECTED faces inside
        [0,1] -> do they act as obstacles for the packer?
Test 3: per-object bmesh.from_edit_mesh in a multi-edit session: does
        face.index match the mesh polygon index (write-path validity)?
"""
import bpy
import bmesh


def make_cube(name, loc):
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    return ob


def smart(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select = True
    bmesh.update_edit_mesh(ob.data)
    r = bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    assert r == {'FINISHED'}, r
    bpy.ops.object.mode_set(mode='OBJECT')


def shift_all(ob, dx, dy):
    uvl = ob.data.uv_layers.active.data
    for p in ob.data.polygons:
        for j in range(p.loop_total):
            u = uvl[p.loop_start + j].uv
            u.x += dx
            u.y += dy


def bboxes(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    out = []
    for f in bm.faces:
        xs = [l[uvl].uv.x for l in f.loops]
        ys = [l[uvl].uv.y for l in f.loops]
        out.append((min(xs), min(ys), max(xs), max(ys)))
    bm.free()
    return out


def overlap_area(ba, bb):
    w = min(ba[2], bb[2]) - max(ba[0], bb[0])
    h = min(ba[3], bb[3]) - max(ba[1], bb[1])
    return max(0.0, w) * max(0.0, h)


bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------------------------------------------------------- Test 1
a = make_cube("A", (0, 0, 0))
b = make_cube("B", (6, 0, 0))
smart(a)
smart(b)
shift_all(a, 0.45, 0.45)   # A islands now in [0.45, ~1.4]
shift_all(b, -0.45, -0.45)  # B islands now in [-0.45, ~0.6]

bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
b.select_set(True)
bpy.context.view_layer.objects.active = a
r = bpy.ops.object.mode_set(mode='EDIT')
print(f"T1 enter multi-edit: {r} modes="
      f"{(a.mode, b.mode)} active={bpy.context.object.name}")

for ob in (a, b):
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select = True
    bmesh.update_edit_mesh(ob.data)

r = bpy.ops.uv.pack_islands(rotate=False, rotate_method="CARDINAL",
                            margin=0.02, scale=False)
print(f"T1 pack result: {r}")
bpy.ops.object.mode_set(mode='OBJECT')

ba = bboxes(a)
bb = bboxes(b)
allin = all(0 <= x0 and y0 >= 0 and x1 <= 1 and y1 <= 1
            for (x0, y0, x1, y1) in ba + bb)
tot_ov = sum(overlap_area(x, y) for x in ba for y in bb)
print(f"T1 all_in_[0,1]={allin} cross_overlap_bbox={tot_ov:.4f}")
print(f"T1 A bboxes: {[tuple(round(v, 3) for v in t) for t in ba]}")
print(f"T1 B bboxes: {[tuple(round(v, 3) for v in t) for t in bb]}")

# ---------------------------------------------------------------- Test 2
bpy.data.objects.remove(a)
bpy.data.objects.remove(b)
a = make_cube("A", (0, 0, 0))
b = make_cube("B", (6, 0, 0))
c = make_cube("C", (12, 0, 0))
smart(a)
smart(b)
smart(c)
# C: all faces coincide on one big square [0.3, 0.7]^2 in the middle
CORNERS = [(0.3, 0.3), (0.7, 0.3), (0.7, 0.7), (0.3, 0.7)]
uvl = c.data.uv_layers.active.data
for p in c.data.polygons:
    for j in range(p.loop_total):
        uvl[p.loop_start + j].uv = CORNERS[j % 4]
# A and B overlapping again
shift_all(a, 0.3, 0.3)
shift_all(b, -0.3, -0.3)

bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
b.select_set(True)
c.select_set(True)          # C is edited but its faces stay unselected
bpy.context.view_layer.objects.active = a
bpy.ops.object.mode_set(mode='EDIT')
for ob in (a, b):
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select = True
    bmesh.update_edit_mesh(ob.data)
bm = bmesh.from_edit_mesh(c.data)
for f in bm.faces:
    f.select = False
bmesh.update_edit_mesh(c.data)

r = bpy.ops.uv.pack_islands(rotate=False, rotate_method="CARDINAL",
                            margin=0.02, scale=False)
print(f"T2 pack result (C unselected): {r}")
bpy.ops.object.mode_set(mode='OBJECT')

ba = bboxes(a)
bb = bboxes(b)
hit = sum(overlap_area(x, (0.3, 0.3, 0.7, 0.7)) for x in ba + bb)
print(f"T2 A/B bbox overlap with C square [0.3,0.7]^2: {hit:.4f}")
print(f"T2 A bboxes: {[tuple(round(v, 3) for v in t) for t in ba]}")

# ---------------------------------------------------------------- Test 3
bpy.data.objects.remove(a)
bpy.data.objects.remove(b)
bpy.data.objects.remove(c)
a = make_cube("A", (0, 0, 0))
b = make_cube("B", (6, 0, 0))
smart(a)
smart(b)
bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.mode_set(mode='EDIT')

# write a distinct UV per face via bmesh, keyed by f.index
ok = True
for ob in (a, b):
    bm = bmesh.from_edit_mesh(ob.data)
    uvl2 = bm.loops.layers.uv.active
    for f in bm.faces:
        v = (f.index * 0.13 % 1.0, (f.index * 0.71) % 1.0)
        for l in f.loops:
            l[uvl2].uv = v
    bmesh.update_edit_mesh(ob.data)
bpy.ops.object.mode_set(mode='OBJECT')
for ob in (a, b):
    uvl3 = ob.data.uv_layers.active.data
    for p in ob.data.polygons:
        got = uvl3[p.loop_start].uv
        want = (p.index * 0.13 % 1.0, (p.index * 0.71) % 1.0)
        if abs(got.x - want[0]) > 1e-6 or abs(got.y - want[1]) > 1e-6:
            ok = False
            print(f"T3 MISMATCH {ob.name} poly {p.index}: "
                  f"got ({got.x:.4f},{got.y:.4f}) want {want}")
print(f"T3 face.index == polygon.index in multi-edit: {ok}")
print("EXP-MULTIEDIT DONE")
