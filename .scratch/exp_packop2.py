"""pack_islands semantics, round 2.

E: margin respected when content fits? (two 0.4^2, margin=0.02)
F: does the operator relocate selected UVs to [0,1] from a far position?
   (single 0.3^2 at (5,7))
G: two islands far apart, both selected -> do they end up packed in [0,1]?
"""
import bpy
import bmesh

print("Blender", bpy.app.version_string)


def make_obj(name, quads):
    """quads: list of (x0, y0, w, h) UV rects; each becomes one quad-face island."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for (x0, y0, w, h) in quads:
        vs = [bm.verts.new(v) for v in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))]
        f = bm.faces.new(vs)
        corners = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
        for loop, c in zip(f.loops, corners):
            loop[uvl].uv = c
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def clean():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        if m.users == 0:
            bpy.data.meshes.remove(m)


def enter_edit(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")


def select_faces(ob, idxs):
    bm = bmesh.from_edit_mesh(ob.data)
    try:
        bm.faces.ensure_lookup_table()
        for f in tuple(bm.faces):
            f.select = (f.index in idxs)
        bmesh.update_edit_mesh(ob.data)
    finally:
        bm.free()


def face_boxes(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    try:
        uvl = bm.loops.layers.uv.active
        out = []
        for f in tuple(bm.faces):
            pts = [l[uvl].uv for l in tuple(f.loops)]
            xs = [q.x for q in pts]
            ys = [q.y for q in pts]
            out.append((min(xs), min(ys), max(xs), max(ys)))
        return out
    finally:
        bm.free()


def report(tag, ob):
    boxes = face_boxes(ob)
    x0 = min(b[0] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y0 = min(b[1] for b in boxes)
    y1 = max(b[3] for b in boxes)
    print(f"{tag}: n={len(boxes)} x[{x0:.4f},{x1:.4f}] y[{y0:.4f},{y1:.4f}]")
    for i, b in enumerate(boxes):
        print(f"   face{i}: x[{b[0]:.4f},{b[2]:.4f}] y[{b[1]:.4f},{b[3]:.4f}] "
              f"size {b[2]-b[0]:.4f}x{b[3]-b[1]:.4f}")


clean()
ob = make_obj("E", [(0.0, 0.0, 0.4, 0.4), (0.5, 0.5, 0.4, 0.4)])
enter_edit(ob)
select_faces(ob, {0, 1})
r = bpy.ops.uv.pack_islands(rotate=False, rotate_method="CARDINAL",
                            margin=0.02, scale=False)
print("E result:", r)
report("E fits+margin", ob)

clean()
ob = make_obj("F", [(5.0, 7.0, 0.3, 0.3)])
enter_edit(ob)
select_faces(ob, {0})
r = bpy.ops.uv.pack_islands(rotate=False, rotate_method="CARDINAL",
                            margin=0.0, scale=False)
print("F result:", r)
report("F far-single", ob)

clean()
ob = make_obj("G", [(5.0, 7.0, 0.4, 0.4), (9.0, 11.0, 0.4, 0.4)])
enter_edit(ob)
select_faces(ob, {0, 1})
r = bpy.ops.uv.pack_islands(rotate=False, rotate_method="CARDINAL",
                            margin=0.0, scale=False)
print("G result:", r)
report("G far-pair", ob)

print("EXPPACK2 DONE")
