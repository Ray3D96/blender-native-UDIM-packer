from mathutils import Vector
import mathutils.geometry as g
# CCW unit square triangles
A = [Vector((0,0,0)), Vector((1,0,0)), Vector((1,1,0)), Vector((0,1,0))]
B = [Vector((0.5,0.5,0)), Vector((1.5,0.5,0)), Vector((1.5,1.5,0)), Vector((0.5,1.5,0))]
C = [Vector((2,0,0)), Vector((3,0,0)), Vector((2,1,0))]
ta = g.tessellate_polygon([A]); tb = g.tessellate_polygon([B]); tc = g.tessellate_polygon([C])
t1 = tuple(A[i] for i in ta[0]); t2 = tuple(B[i] for i in tb[0]); t3 = tuple(C[i] for i in tc[0])
print("overlap  :", g.intersect_tri_tri_2d(*t1, *t2))
print("disjoint :", g.intersect_tri_tri_2d(*t1, *t3))
# flip winding of triangle 1 (CW)
t1c = t1[::-1]
print("overlap CW:", g.intersect_tri_tri_2d(*t1c, *t2))
print("disjoint CW:", g.intersect_tri_tri_2d(*t1c, *t3))
# flip both
print("overlap CWCW:", g.intersect_tri_tri_2d(*t1c, *t2[::-1]))
