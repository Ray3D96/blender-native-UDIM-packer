from mathutils import Vector
import mathutils.geometry as g
A = [Vector((0,0,0)), Vector((1,0,0)), Vector((1,1,0)), Vector((0,1,0))]
B = [Vector((0.5,0.5,0)), Vector((1.5,0.5,0)), Vector((1.5,1.5,0)), Vector((0.5,1.5,0))]
C = [Vector((2,0,0)), Vector((3,0,0)), Vector((2,1,0))]
ta = g.tessellate_polygon(A); tb = g.tessellate_polygon(B)
print("tess A:", ta, " tess B:", tb)
r1 = g.intersect_tri_tri_2d(ta[0], tb[0])
print("overlap result:", r1, type(r1))
tc = g.tessellate_polygon(C)
r2 = g.intersect_tri_tri_2d(ta[0], tc[0])
print("disjoint result:", r2, type(r2))
# touching edge case
D = [Vector((1,0,0)), Vector((2,0,0)), Vector((1,1,0))]
td = g.tessellate_polygon(D)
r3 = g.intersect_tri_tri_2d(ta[0], td[0])
print("touching result:", r3, type(r3))
