import bpy, bmesh, sys
from mathutils import Vector
import mathutils.geometry as geom

sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
from native_udim_packer import packer as P

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# o1: cube2 + cube1 + icosphere -> 32 islands
bpy.ops.mesh.primitive_cube_add(size=2); a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(6,0,0)); b = bpy.context.active_object
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8, location=(-6,0,0)); c = bpy.context.active_object
a.select_set(True); b.select_set(True); c.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
o1 = bpy.context.active_object; o1.name = "t5a"

# o2: single cube -> 6 islands
bpy.ops.mesh.primitive_cube_add(size=1.0)
o2 = bpy.context.active_object; o2.name = "t5b"

for ob in (o1, o2):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')

for ob in (o1, o2):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    r = P.pack_object(ob, 2, 2, False, True, 0.01)
    print(f"{ob.name}: {r.get('islands')} islands -> tiles {sorted(r.get('tiles_used', []))} "
          f"fallback={r.get('fallback_tiles')} reasons={r.get('fallback_reasons')}")
    bpy.ops.object.mode_set(mode='OBJECT')

def island_tris(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    islands = P.detect_islands(bm, uvl)
    out = []
    for isl in islands:
        minx, miny, maxx, maxy = P.island_bounds(bm, uvl, isl.face_indices)
        tris = []
        for f in tuple(bm.faces):
            if f.index in isl.face_indices:
                pts = [Vector((l[uvl].uv.x, l[uvl].uv.y, 0.0)) for l in tuple(f.loops)]
                for t in geom.tessellate_polygon([pts]):
                    tris.append(tuple(pts[k] for k in t))
        out.append(((minx, miny, maxx, maxy), tris))
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    return out

def fmt(t): return [(round(p.x,3), round(p.y,3)) for p in t]
A = island_tris(o1); B = island_tris(o2)
print(f"t5a: {len(A)} islands, t5b: {len(B)} islands")

for name, L in (("t5a", A), ("t5b", B)):
    for x in range(len(L)):
        for y in range(x+1, len(L)):
            hit = next(((ta, tb) for ta in L[x][1] for tb in L[y][1]
                        if geom.intersect_tri_tri_2d(*ta, *tb)), None)
            if hit:
                print(f"  SELF {name} isl{x} {tuple(round(v,3) for v in L[x][0])} "
                      f"x isl{y} {tuple(round(v,3) for v in L[y][0])} "
                      f"A={fmt(hit[0])} B={fmt(hit[1])}")

n = 0
for i, (ba, ta_list) in enumerate(A):
    for j, (bb, tb_list) in enumerate(B):
        hit = next(((ta, tb) for ta in ta_list for tb in tb_list
                    if geom.intersect_tri_tri_2d(*ta, *tb)), None)
        if hit:
            n += 1
            print(f"  X t5a[{i}] {tuple(round(v,3) for v in ba)} x t5b[{j}] "
                  f"{tuple(round(v,3) for v in bb)} A={fmt(hit[0])} B={fmt(hit[1])}")
print("cross pairs:", n)
