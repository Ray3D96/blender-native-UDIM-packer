# Probe 2: does uv.pack_islands CANCEL depend on the UV state of
# UNSELECTED faces (the tile-1 call saw unselected faces holding
# tile-0's overflowed >1.0 positions)?
import bmesh
import bpy


def build_four_quads(unsel_pos):
    """One object, 4 quads. Quad0 = big square at origin (selected),
    quad1 = small square at origin (selected), quad2/3 unselected with
    UVs at unsel_pos (either inside or outside [0,1]^2)."""
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    me = bpy.data.meshes.new("four")
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")

    def quad(uvs):
        v = [bm.verts.new((i, j, 0)) for i in (0, 1) for j in (0, 1)]
        f = bm.faces.new(v)
        for l, c in zip(f.loops, uvs):
            l[uvl].uv = c

    quad([(0.0, 0.0), (0.797, 0.0), (0.797, 0.797), (0.0, 0.797)])   # big
    quad([(0.05, 0.05), (0.4485, 0.05), (0.4485, 0.4485), (0.05, 0.4485)])  # small
    for _ in range(2):
        x0, y0 = unsel_pos
        quad([(x0, y0), (x0 + 0.3, y0), (x0 + 0.3, y0 + 0.3), (x0, y0 + 0.3)])

    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("four", me)
    bpy.context.collection.objects.link(ob)
    return ob


def pack_case(name, unsel_pos):
    ob = build_four_quads(unsel_pos)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for i, f in enumerate(tuple(bm.faces)):
        f.select = (i < 2)          # only the two squares at origin
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.008, scale=False)
    bm = bmesh.from_edit_mesh(ob.data)
    xs = [l[uvl].uv.x for f in bm.faces for l in f.loops]
    ys = [l[uvl].uv.y for f in bm.faces for l in f.loops]
    ext = (round(min(xs), 4), round(min(ys), 4),
           round(max(xs), 4), round(max(ys), 4))
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE2 {name}: {r} all-extent={ext}", flush=True)


# unselected faces inside [0,1]^2
pack_case("unsel-inside", (0.55, 0.55))
# unselected faces OUTSIDE [0,1]^2 (mimics tile-0 overflow leftovers)
pack_case("unsel-outside", (1.05, 1.05))
# repeat outside case for determinism
for k in range(3):
    pack_case(f"unsel-outside-rep{k}", (1.05, 1.05))
print("PROBE2 DONE", flush=True)
