"""Baseline: face counts, current detector count, independent ground truth.

Ground truth = flood fill over faces using explicit per-vertex UV comparison
via e.link_faces (structurally different from the addon's link_loops code).
"""
import bpy
import bmesh
import math

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)

EPS = 1e-6


def ground_truth(ob, tag):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    fu = {}
    for f in tuple(bm.faces):
        m = {}
        for l in tuple(f.loops):
            u = l[uvl].uv
            m[l.vert.index] = (u.x, u.y)
        fu[f.index] = m
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

    cont = seam = 0
    for e in tuple(bm.edges):
        fl = tuple(e.link_faces)
        if len(fl) != 2:
            continue
        m1, m2 = fu[fl[0].index], fu[fl[1].index]
        ok = True
        for v in e.verts:
            a = m1.get(v.index)
            b = m2.get(v.index)
            if (a is None or b is None
                    or abs(a[0] - b[0]) >= EPS or abs(a[1] - b[1]) >= EPS):
                ok = False
                break
        if ok:
            cont += 1
            union(fl[0].index, fl[1].index)
        else:
            seam += 1
    groups = {}
    for f in tuple(bm.faces):
        groups.setdefault(find(f.index), set()).add(f.index)
    sizes = sorted((len(g) for g in groups.values()), reverse=True)
    print(f"[{tag}] faces={len(bm.faces)} edges continuous={cont} seam={seam}")
    print(f"[{tag}] GROUND TRUTH islands={len(groups)} sizes={sizes[:16]}")
    bm.free()
    return len(groups)


def current_detector(ob, tag):
    from native_udim_packer import packer
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    isl = packer.detect_islands(bm, uvl)
    sizes = sorted((len(i.face_indices) for i in isl), reverse=True)
    print(f"[{tag}] CURRENT detector islands={len(isl)} sizes={sizes[:16]}")
    bm.free()
    return len(isl)


# ---- monkey ---------------------------------------------------------------
bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object
gt_m = ground_truth(mon, "monkey")
cur_m = current_detector(mon, "monkey")

# ---- exact e2e T1 mesh ------------------------------------------------------
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
b = bpy.context.active_object
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8,
                                      location=(-6, 0, 0))
c = bpy.context.active_object
a.select_set(True); b.select_set(True); c.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
ob = bpy.context.active_object
ob.name = "t1"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
gt_t = ground_truth(ob, "t1-mesh")
cur_t = current_detector(ob, "t1-mesh")

print(f"\nmonkey: ground_truth={gt_m} current={cur_m}")
print(f"t1    : ground_truth={gt_t} current={cur_t}")
print("BASELINE DONE")
