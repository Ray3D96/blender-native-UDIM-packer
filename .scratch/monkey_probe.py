"""Ground-truth probe: does the default monkey have real per-face UV seams?

1. For many adjacent face pairs, compare UV positions at the shared edge
   endpoints (face A vs face B). Equal within 1e-6 -> continuous (my detector
   would merge); different -> a real seam (detector is correct to split).
2. Dump uv.pack_islands' full property set in Blender 5.2 (for the
   scale=False plan).
"""
import bpy
import bmesh
import math

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object

bm = bmesh.new()
bm.from_mesh(mon.data)
uvl = bm.loops.layers.uv.active

print("faces:", len(bm.faces), "verts:", len(bm.verts))

match = 0
seam = 0
samples = []
for e in bm.edges:
    if len(e.link_faces) != 2:
        continue
    f1, f2 = e.link_faces
    v_a, v_b = e.verts
    try:
        l1a = next(l for l in f1.loops if l.vert is v_a)[uvl].uv
        l1b = next(l for l in f1.loops if l.vert is v_b)[uvl].uv
        l2a = next(l for l in f2.loops if l.vert is v_a)[uvl].uv
        l2b = next(l for l in f2.loops if l.vert is v_b)[uvl].uv
    except StopIteration:
        continue
    d1 = math.hypot(l1a.x - l2a.x, l1a.y - l2a.y)
    d2 = math.hypot(l1b.x - l2b.x, l1b.y - l2b.y)
    if max(d1, d2) <= 1e-6:
        match += 1
    else:
        seam += 1
        if len(samples) < 5:
            samples.append((f1.index, f2.index,
                            (round(l1a.x, 4), round(l1a.y, 4)),
                            (round(l2a.x, 4), round(l2a.y, 4)),
                            round(max(d1, d2), 6)))

print(f"interior edges: continuous={match} seam={seam}")
for s in samples:
    print("  seam sample faces", s[0], s[1], "uvA=", s[2], "uvB=", s[3],
          "dist=", s[4])

# how many UV-vertex positions are shared at all?
uv_count = {}
for l in bm.loops:
    u = (round(l[uvl].uv.x, 6), round(l[uvl].uv.y, 6))
    uv_count[u] = uv_count.get(u, 0) + 1
shared_positions = sum(1 for c in uv_count.values() if c > 1)
print(f"distinct uv positions={len(uv_count)} shared-by->2-loops={shared_positions}")
bm.free()

# ------------------------------------------------- pack_islands properties --
op = bpy.ops.uv.pack_islands
print("\nuv.pack_islands properties (Blender 5.2):")
for key in op.properties.keys():
    try:
        val = getattr(op, key)
    except Exception as exc:
        val = f"<unreadable: {exc}>"
    print(f"  {key} = {val!r}")

print("PROBE DONE")
