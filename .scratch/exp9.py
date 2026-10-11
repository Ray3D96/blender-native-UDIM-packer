import bpy, bmesh

EPS = 1e-6

def get_islands(bm, uvl):
    """Seam-aware island detection via loop union-find.
    Returns list of sets of face indices."""
    parent = {}
    def find(x):
        parent.setdefault(x, x)
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
    # 1) within each face, all loops are one island
    for f in faces:
        fl = tuple(f.loops)
        for l in fl[1:]:
            union(fl[0].index, l.index)
    # 2) across edges: connect only if UVs match (no seam)
    bm.edges.ensure_lookup_table()
    for e in tuple(bm.edges):
        ls = tuple(e.link_loops)
        if len(ls) == 2:
            u1, u2 = ls[0][uvl].uv, ls[1][uvl].uv
            if abs(u1.x - u2.x) < EPS and abs(u1.y - u2.y) < EPS:
                union(ls[0].index, ls[1].index)

    # map loop -> face
    loop_to_face = {}
    for f in faces:
        for l in tuple(f.loops):
            loop_to_face[l.index] = f.index
    groups = {}
    for li, fi in loop_to_face.items():
        root = find(li)
        groups.setdefault(root, set()).add(fi)
    return list(groups.values())

def transform_group(ob, face_indices, target_aabb):
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    idx = set(face_indices)
    pts = [l[uvl].uv.copy() for f in tuple(bm.faces) if f.index in idx for l in tuple(f.loops)]
    minx = min(p.x for p in pts); maxx = max(p.x for p in pts)
    miny = min(p.y for p in pts); maxy = max(p.y for p in pts)
    w = maxx - minx or 1e-6; h = maxy - miny or 1e-6
    tx0, ty0, tx1, ty1 = target_aabb
    s = min((tx1-tx0)/w, (ty1-ty0)/h)
    cx = (minx+maxx)/2; cy = (miny+maxy)/2
    tcx = (tx0+tx1)/2; tcy = (ty0+ty1)/2
    for f in tuple(bm.faces):
        if f.index in idx:
            for l in tuple(f.loops):
                u = l[uvl].uv
                u.x = tcx + s*(u.x-cx)
                u.y = tcy + s*(u.y-cy)
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

# joined two cubes -> expect 12 islands (6 per cube) with seam-aware detection
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

bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
groups = get_islands(bm, uvl)
bm.free()
print(f"islands (seam-aware): {len(groups)}")  # expect 12

# assign: biggest group -> tile 0, second -> tile 1, fully contained
gs = sorted(groups, key=len, reverse=True)
g0, g1 = gs[0], gs[1]
transform_group(c, g0, (0.05, 0.05, 0.95, 0.95))     # tile 0 fully
transform_group(c, g1, (1.05, 0.05, 1.95, 0.95))     # tile 1 fully
print("g0 placed:", bounds_of(c, g0), "(tile 0)")
print("g1 placed:", bounds_of(c, g1), "(tile 1)")

with bpy.context.temp_override(object=c, active_object=c):
    r = bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True, rotate_method='CARDINAL', scale=True, margin_method='FRACTION', margin=0.01)
print("pack:", r)
print("g0 after:", bounds_of(c, g0), "  must be within [0,1]x[0,1]")
print("g1 after:", bounds_of(c, g1), "  must be within [1,2]x[0,1]")

# verify every island stays inside the tile of its pre-placement centroid
bm = bmesh.from_edit_mesh(c.data)
uvl = bm.loops.layers.uv.active
groups2 = get_islands(bm, uvl)
ok = True
for g in groups2:
    idx = set(g)
    pts = [l[uvl].uv for f in tuple(bm.faces) if f.index in idx for l in tuple(f.loops)]
    minx=min(p.x for p in pts); maxx=max(p.x for p in pts)
    miny=min(p.y for p in pts); maxy=max(p.y for p in pts)
    cx=(minx+maxx)/2; cy=(miny+maxy)/2
    t=(int(cx), int(cy))
    inside = (minx >= -1e-4 and maxx <= t[0]+1+1e-4 and miny >= -1e-4 and maxy <= t[1]+1+1e-4)
    ok &= inside
    print(f"  island n={len(g):2d} tile={t} bounds=[{minx:.3f},{maxx:.3f}]x[{miny:.3f},{maxy:.3f}] inside={inside}")
print("ALL INSIDE:", ok)
bm.free()
bpy.ops.object.mode_set(mode='OBJECT')
