"""Test the bowtie / self-intersecting UV face hypothesis for Wire."""
import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

ob = bpy.data.objects["Wire"]
me = ob.data
uvl = me.uv_layers.active.data


def corners(p):
    return [tuple(uvl[p.loop_start + j].uv) for j in range(p.loop_total)]


def shoelace(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s * 0.5


def segs_intersect(p1, p2, p3, p4):
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if v > 1e-18:
            return 1
        if v < -1e-18:
            return -1
        return 0
    o1 = orient(p1, p2, p3)
    o2 = orient(p1, p2, p4)
    o3 = orient(p3, p4, p1)
    o4 = orient(p3, p4, p2)
    return o1 != o2 and o3 != o4


def is_simple(pts):
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            # skip adjacent edges (share a vertex)
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = pts[j], pts[(j + 1) % n]
            if segs_intersect(a, b, c, d):
                return False
    return True


bad_bowtie = []
bad_signed = 0
for p in me.polygons:
    pts = corners(p)
    sa = shoelace(pts)
    if abs(sa) < 1e-14:
        bad_signed += 1
        continue
    if not is_simple(pts):
        bad_bowtie.append((p.index, sa, pts))

print(f"W5 faces={len(me.polygons)} self-intersecting={len(bad_bowtie)} "
      f"zero-signed={bad_signed}")
for idx, sa, pts in bad_bowtie[:5]:
    print(f"W5   face {idx}: signed_area={sa:.3e} corners={pts}")


def make_quad_obj(name, uv_pts):
    bm = bmesh.new()
    uvl2 = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(v) for v in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
    f = bm.faces.new(vs)
    for loop, c in zip(f.loops, uv_pts):
        loop[uvl2].uv = c
    m2 = bpy.data.meshes.new(name)
    bm.to_mesh(m2)
    bm.free()
    o2 = bpy.data.objects.new(name, m2)
    bpy.context.collection.objects.link(o2)
    return o2


def pack_obj(o2):
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    o2.select_set(True)
    bpy.context.view_layer.objects.active = o2
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(o2.data)
    for f in tuple(bm.faces):
        f.select = True
    bmesh.update_edit_mesh(o2.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    return r


# control: a plain small quad
c1 = make_quad_obj("w5_ctrl", [(0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.1, 0.2)])
print("W5 control plain quad:", pack_obj(c1))

# repro: Wire face 0's exact corners
p0 = me.polygons[0]
pts0 = corners(p0)
print(f"W5 face0 corners={pts0} signed={shoelace(pts0):.3e}")
c2 = make_quad_obj("w5_face0", pts0)
print("W5 repro Wire face0:", pack_obj(c2))

# repro: a bowtie quad (same 4 points, crossing order)
c3 = make_quad_obj("w5_bowtie", [(0.1, 0.1), (0.2, 0.2), (0.2, 0.1), (0.1, 0.2)])
print("W5 repro synthetic bowtie:", pack_obj(c3))

# repro: Wire face0 with corners reordered to a simple polygon (if bowtie)
def reorder_simple(pts):
    # try all rotations/reversals of the given corner order
    n = len(pts)
    for start in range(n):
        rot = pts[start:] + pts[:start]
        for seq in (rot, list(reversed(rot))):
            if is_simple(seq) and abs(shoelace(seq)) > 1e-14:
                return seq
    return None

if bad_bowtie:
    idx, sa, pts = bad_bowtie[0]
    fixed = reorder_simple(pts)
    print(f"W5 first bowtie face {idx} fixable by reorder:", fixed is not None)
    if fixed:
        c4 = make_quad_obj("w5_fixed", fixed)
        print("W5 repro reordered face:", pack_obj(c4))

print("W5DONE")
