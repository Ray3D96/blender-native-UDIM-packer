# Probe: what makes uv.pack_islands(scale=False) return CANCELLED?
# Minimal cases, each in a fresh object + fresh edit session.
import bmesh
import bpy

RESULTS = []


def fresh_quads(specs):
    """specs: list of (size, x0, y0) squares as UV layout on one quad each."""
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    obs = []
    for (sz, x0, y0) in specs:
        me = bpy.data.meshes.new(f"q{len(obs)}")
        bm = bmesh.new()
        v = [bm.verts.new((i, j, 0)) for i in (0, 1) for j in (0, 1)]
        f = bm.faces.new(v)
        uvl = bm.loops.layers.uv.new("UVMap")
        coords = [(x0, y0), (x0 + sz, y0), (x0 + sz, y0 + sz), (x0, y0 + sz)]
        for l, c in zip(f.loops, coords):
            l[uvl].uv = c
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"q{len(obs)}", me)
        bpy.context.collection.objects.link(ob)
        obs.append(ob)
    return obs


def pack_case(name, specs, rotate=True, margin=0.0):
    obs = fresh_quads(specs)
    bpy.ops.object.select_all(action='DESELECT')
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    r = bpy.ops.uv.pack_islands(rotate=rotate, rotate_method="CARDINAL",
                                margin=margin, scale=False)
    # measure resulting extent
    me = obs[0].data
    bm = bmesh.from_edit_mesh(me)
    uvl = bm.loops.layers.uv.active
    xs = [l[uvl].uv.x for f in bm.faces for l in f.loops]
    ys = [l[uvl].uv.y for f in bm.faces for l in f.loops]
    ext = (min(xs), min(ys), max(xs), max(ys))
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    RESULTS.append((name, r, tuple(round(v, 4) for v in ext)))
    print(f"PROBE {name}: {r} extent={tuple(round(v, 4) for v in ext)}",
          flush=True)


# 1: single square 0.8 inside tile
pack_case("single-0.8", [(0.8, 0.1, 0.1)])
# 2: single square 1.5 (bigger than the tile itself)
pack_case("single-1.5", [(1.5, 0.0, 0.0)])
# 3: the T8 shape - 0.797 + 0.399 squares both starting near origin
pack_case("t8-shape-m0", [(0.797, 0.0, 0.0), (0.399, 0.05, 0.05)])
# 4: same shape with margin 0.008
pack_case("t8-shape-m0008", [(0.797, 0.0, 0.0), (0.399, 0.05, 0.05)],
          margin=0.008)
# 5: repeat the T8 shape 8 times to test determinism
for k in range(8):
    pack_case(f"t8-shape-rep{k}", [(0.797, 0.0, 0.0), (0.399, 0.05, 0.05)],
              margin=0.008)
# 6: two squares that DO fit side by side (sanity: FINISHED expected)
pack_case("fit-0.5+0.4", [(0.5, 0.0, 0.0), (0.4, 0.6, 0.1)])

print("PROBE SUMMARY:", {n: r for n, r, _ in RESULTS}, flush=True)
print("PROBE DONE", flush=True)
