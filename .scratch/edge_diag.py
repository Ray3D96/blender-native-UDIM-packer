"""Edge-level diagnosis of detect_islands' cross-edge comparison.

For interior edges, print which vertices the two link_loops start at (vs the
edge's two verts) and the UV distance compared. Also re-dump
uv.pack_islands properties (previous probe crashed before that).
"""
import bpy
import bmesh
import math

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)


def diag(ob, tag, n=8):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    same = 0
    opp = 0
    matched_same = 0
    matched_opp = 0
    shown = 0
    for e in tuple(bm.edges):
        ls = tuple(e.link_loops)
        if len(ls) != 2:
            continue
        l1, l2 = ls
        ev = {v.index for v in e.verts}
        s1, s2 = l1.vert.index, l2.vert.index
        u1, u2 = l1[uvl].uv, l2[uvl].uv
        d = math.hypot(u1.x - u2.x, u1.y - u2.y)
        if s1 == s2:
            same += 1
            if d <= 1e-6:
                matched_same += 1
        else:
            opp += 1
            if d <= 1e-6:
                matched_opp += 1
        if shown < n:
            print(f"{tag} edge {e.index}: faces {l1.face.index},{l2.face.index} "
                  f"loop-starts ({s1},{s2}) edge-verts {sorted(ev)} "
                  f"d={d:.9f}")
            shown += 1
    print(f"{tag}: interior edges loop-start SAME={same} (match {matched_same}) "
          f"OPPOSITE={opp} (match {matched_opp})")
    bm.free()


bpy.ops.mesh.primitive_monkey_add(size=1.0)
diag(bpy.context.active_object, "monkey")

# smart-projected cube like e2e T1's first component
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.ops.mesh.primitive_cube_add(size=2.0)
c = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
diag(c, "cube-sp")

# ------------------------------------------------- pack_islands properties --
op = bpy.ops.uv.pack_islands
print("\nuv.pack_islands properties (Blender 5.2):")
for key in op.properties.keys():
    try:
        val = getattr(op, key)
    except Exception as exc:
        val = f"<unreadable: {exc}>"
    print(f"  {key} = {val!r}")

print("DIAG DONE")
