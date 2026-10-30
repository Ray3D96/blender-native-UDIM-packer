# SPDX-License-Identifier: GPL-3.0-or-later
"""Why does the default Suzanne 3x1 pack overlap?"""
import sys

import bpy
import bmesh

ROOT = "/mnt/fusion/ai-projects/blender-uv-packer"
_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception:
        pass
for n in [n for n in list(sys.modules) if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[n]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import native_udim_packer as A
A.register()
from native_udim_packer import packer, layout

bpy.ops.mesh.primitive_monkey_add(size=1.0)
ob = bpy.context.active_object
res = packer.pack_objects([ob], 3, 1, False, True, 0.01)
print("RESULT", {k: res.get(k) for k in
                 ("error", "global_scale", "stretch_factor", "tiles_used_total",
                  "packed_islands")}, flush=True)
v = packer.verify_packing(ob, 3, 1)
print("verify", v["all_inside"], flush=True)
for p in v["per_island"]:
    print(" ", p["tile"], p["udim"], p["bounds"], "inside", p["inside"], flush=True)

bm = bmesh.new()
bm.from_mesh(ob.data)
uvl = bm.loops.layers.uv.active
islands = packer.detect_islands(bm, uvl)
polys = []
for isl in islands:
    faces = []
    for f in tuple(bm.faces):
        if f.index in isl.face_indices:
            faces.append([(l[uvl].uv.x, l[uvl].uv.y) for l in tuple(f.loops)])
    polys.append(faces)
bm.free()
print("islands", len(polys), "overlap", layout.tile_islands_overlap(polys), flush=True)
import mathutils.geometry as geom
from mathutils import Vector

def tris_of(faces):
    out = []
    for pts in faces:
        vs = [Vector((p[0], p[1], 0.0)) for p in pts]
        for t in geom.tessellate_polygon([vs]):
            out.append(tuple(vs[k] for k in t))
    return out

tri_sets = [tris_of(f) for f in polys]
hits = 0
for i in range(len(tri_sets)):
    for j in range(i + 1, len(tri_sets)):
        for a in tri_sets[i]:
            for b in tri_sets[j]:
                if geom.intersect_tri_tri_2d(*a, *b):
                    hits += 1
                    pa = [(p.x, p.y) for p in a]
                    pb = [(p.x, p.y) for p in b]
                    ours = layout.polygons_overlap([pa], [pb])
                    print(f"  tri hit {i},{j} ours={ours}", flush=True)
                    print(f"    A {[(round(p[0],5), round(p[1],5)) for p in pa]}", flush=True)
                    print(f"    B {[(round(p[0],5), round(p[1],5)) for p in pb]}", flush=True)
                    break
            else:
                continue
            break
print("tri hits", hits, flush=True)
# which pair
for i in range(len(polys)):
    for j in range(i + 1, len(polys)):
        if layout.polygons_overlap(polys[i], polys[j]):
            print(f"  pair {i},{j} overlaps", flush=True)
