from mathutils import Vector
import mathutils.geometry as g
A = [Vector((0,0,0)), Vector((1,0,0)), Vector((1,1,0)), Vector((0,1,0))]
B = [Vector((0.5,0.5,0)), Vector((1.5,0.5,0)), Vector((1.5,1.5,0)), Vector((0.5,1.5,0))]
C = [Vector((2,0,0)), Vector((3,0,0)), Vector((2,1,0))]
D = [Vector((1,0,0)), Vector((2,0,0)), Vector((1,1,0))]
ta = g.tessellate_polygon([A]); tb = g.tessellate_polygon([B])
tc = g.tessellate_polygon([C]); td = g.tessellate_polygon([D])
def tri(P, t):  # resolve index triple to 3 Vectors (x,y only)
    return [P[i] for i in t]
t1 = tri(A, ta[0]); t2 = tri(B, tb[0])
r1 = g.intersect_tri_tri_2d(*t1, *t2)
print("overlap:", repr(r1))
t3 = tri(C, tc[0])
r2 = g.intersect_tri_tri_2d(*t1, *t3)
print("disjoint:", repr(r2))
t4 = tri(D, td[0])
r3 = g.intersect_tri_tri_2d(*t1, *t4)
print("touching:", repr(r3))
