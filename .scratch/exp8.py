import bpy, bmesh

def get_island_groups(ob):
    """Group faces into islands via UV edge connectivity. Returns list of face-index sets."""
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    parent = {}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    bm.faces.ensure_lookup_table()
    faces = tuple(bm.faces)
    for f in faces:
        for l in tuple(f.loops):
            vi = l.vert.index
            parent.setdefault(vi, vi)
    for f in faces:
        loops = tuple(f.loops)
        for i in range(len(loops)):
            a = loops[i].vert.index
            b = loops[(i+1) % len(loops)].vert.index
            union(a, b)
    groups = {}
    for f in faces:
        root = find(tuple(f.loops)[0].vert.index)
        groups.setdefault(root, []).append(f.index)
    bm.free()
    return list(groups.values())

def transform_group(ob, face_indices, target_aabb):
    """Scale+translate island group so its UV AABB == target_aabb ((minx,miny,maxx,maxy))."""
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    idx = set(face_indices)
    # collect uv coords of the group
    pts = []
    for f in tuple(bm.faces):
        if f.index in idx:
            for l in tuple(f.loops):
                pts.append(l[uvl].uv.copy())
    minx = min(p.x for p in pts); maxx = max(p.x for p in pts)
    miny = min(p.y for p in pts); maxy = max(p.y for p in pts)
    w = maxx - minx or 1e-6; h = maxy - miny or 1e-6
    tx0, ty0, tx1, ty1 = target_aabb
    sx = (tx1 - tx0) / w; sy = (ty1 - ty0) / h
    s = min(sx, sy)  # uniform scale to fit
    # recompute centered placement
    cx = (minx + maxx) / 2; cy = (miny + maxy) / 2
    tcx = (tx0 + tx1) / 2; tcy = (ty0 + ty1) / 2
    for f in tuple(bm.faces):
        if f.index in idx:
            for l in tuple(f.loops):
                u = l[uvl].uv
                u.x = tcx + s * (u.x - cx)
                u.y = tcy + s * (u.y - cy)
    bmesh.update_edit_mesh(ob.data)
    bm.free()

def bounds_of(ob, face_indices):
    idx = set(face_indices)
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    pts = [l[uvl].uv for f in tuple(bm.faces) if f.index in idx for l in tuple(f.loops)]
    r = (round(min(p.x for p in pts),4), round(max(p.x for p in pts),4),
         round(min(p.y for p in pts),4), round(max(p.y for p in pts),4))
    bm.free()
    return r

# joined two cubes -> 12 islands (6 each)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0,0,0))
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(5,0,0))
b = bpy.context.active_object
a.select_set(True); b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
c = bpy.context.active_object; c.name = "twoCubes"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)

groups = get_island_groups(c)
print(f"islands: {len(groups)}")
# pick two groups: one for tile 0, one for tile 1 (make them BIG by joining? just use as-is)
g0 = max(groups, key=len)
rest = [g for g in groups if g != g0]
g1 = max(rest, key=len)

# Place g0 in tile 0 region [0.05..0.95]^2, g1 straddling: [0.85..1.75] x [0.05..0.95], centroid at 1.3 (tile 1)
transform_group(c, g0, (0.05, 0.05, 0.95, 0.95))
transform_group(c, g1, (0.85, 0.05, 1.75, 0.95))
print("g0 placed:", bounds_of(c, g0))
print("g1 placed (straddles boundary):", bounds_of(c, g1))

# single pack call on ALL faces
with bpy.context.temp_override(object=c, active_object=c):
    r = bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='CARDINAL', scale=True, margin_method='FRACTION', margin=0.01)
print("pack:", r)
print("g0 after:", bounds_of(c, g0), "  (must be within [0,1]x[0,1])")
print("g1 after:", bounds_of(c, g1), "  (must be within [1,2]x[0,1])")

# check ALL islands stayed in their own tile: group by centroid tile
bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
groups2 = get_island_groups(c)
for g in groups2:
    pts = [l[uvl].uv for f in tuple(bm.faces) if f.index in set(g) for l in tuple(f.loops)]
    cx = sum(p.x for p in pts)/len(pts); cy = sum(p.y for p in pts)/len(pts)
    tile = (int(cx), int(cy))
    minx = min(p.x for p in pts); maxx = max(p.x for p in pts)
    miny = min(p.y for p in pts); maxy = max(p.y for p in pts)
    inside = (minx >= -1e-4 and maxx <= tile[0]+1+1e-4 and miny >= -1e-4 and maxy <= tile[1]+1+1e-4)
    print(f"  island n={len(g)} centroid=({cx:.2f},{cy:.2f}) tile={tile} bounds=[{minx:.3f},{maxx:.3f}]x[{miny:.3f},{maxy:.3f}] inside={inside}")
bm.free()
bpy.ops.object.mode_set(mode='OBJECT')
