import bpy, bmesh, sys
from mathutils import Vector
import mathutils.geometry as geom

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(size=2)
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(6,0,0))
b = bpy.context.active_object
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8, location=(-6,0,0))
c = bpy.context.active_object
a.select_set(True); b.select_set(True); c.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
ob = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)

from native_udim_packer import packer as P
bm = bmesh.from_edit_mesh(ob.data)
uvl = bm.loops.layers.uv.active
islands = P.detect_islands(bm, uvl)
print("islands:", len(islands))
P._manual_shelf_pack(bm, uvl, islands, 0.01)
bmesh.update_edit_mesh(ob.data)

# re-detect and find intersecting pairs with details
isl2 = P.detect_islands(bm, uvl)
print("re-detected islands:", len(isl2))
tris = []
for i in isl2:
    tlist = []
    for f in tuple(bm.faces):
        if f.index in i.face_indices:
            pts = [Vector((l[uvl].uv.x, l[uvl].uv.y, 0.0)) for l in tuple(f.loops)]
            for t in geom.tessellate_polygon([pts]):
                tlist.append(tuple(pts[k] for k in t))
    tris.append(tlist)
bm.free()
bpy.ops.object.mode_set(mode='OBJECT')

n = 0
for x in range(len(tris)):
    for y in range(x+1, len(tris)):
        for ta in tris[x]:
            for tb in tris[y]:
                if geom.intersect_tri_tri_2d(*ta, *tb):
                    n += 1
                    print(f"PAIR {x}-{y}: A={[ (round(v.x,4), round(v.y,4)) for v in ta ]} B={[ (round(v.x,4), round(v.y,4)) for v in tb ]}")
                    if n >= 8: sys.exit(0)
print("total intersecting pairs:", n)
