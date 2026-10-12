"""Empirical validation of bpy.ops.uv.pack_islands semantics.

Tests (all headless --background):
  A: scale=False when content OVERFLOWS the 0-1 square -> shrink or overlap?
  B: scale=False when content FITS at size 1 -> sizes preserved or scaled up?
  C: selection scope -> only selected faces moved, others untouched?
  D: rotate=True CARDINAL + margin -> valid packing, rotation applied?
"""
import bpy
import bmesh


def clean():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


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


def face_boxes(ob):
    """Per-face UV boxes read from the live edit bmesh (one island per face)."""
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


def pair_overlap(a, b):
    ox = min(a[2], b[2]) - max(a[0], b[0])
    oy = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, ox) * max(0.0, oy)


def report(tag, ob):
    boxes = face_boxes(ob)
    worst = 0.0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            worst = max(worst, pair_overlap(boxes[i], boxes[j]))
    allx = [c for b in boxes for c in (b[0], b[2])]
    ally = [c for b in boxes for c in (b[1], b[3])]
    print(f"{tag}: n={len(boxes)} worst_bbox_overlap={worst:.6f} "
          f"x[{min(allx):.4f},{max(allx):.4f}] y[{min(ally):.4f},{max(ally):.4f}]")
    for i, b in enumerate(boxes):
        print(f"   face{i}: x[{b[0]:.4f},{b[2]:.4f}] y[{b[1]:.4f},{b[3]:.4f}] "
              f"size {b[2]-b[0]:.4f}x{b[3]-b[1]:.4f}")
    return boxes


def select_faces(ob, idxs):
    bm = bmesh.from_edit_mesh(ob.data)
    try:
        bm.faces.ensure_lookup_table()
        for f in tuple(bm.faces):
            f.select = (f.index in idxs)
        bmesh.update_edit_mesh(ob.data)
    finally:
        bm.free()


def enter_edit(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')


def to_object():
    bpy.ops.object.mode_set(mode='OBJECT')


# ---------------------------------------------------------------- TEST A
clean()
ob = make_obj("A", [(0.0, 0.0, 0.6, 0.6), (0.2, 0.2, 0.6, 0.6), (0.4, 0.0, 0.6, 0.6)])
enter_edit(ob)
select_faces(ob, {0, 1, 2})
bpy.ops.uv.pack_islands(rotate=False, margin=0.0, scale=False)
report("A overflow(scale=False)", ob)
to_object()

# ---------------------------------------------------------------- TEST B
clean()
ob = make_obj("B", [(0.0, 0.0, 0.4, 0.4), (0.5, 0.0, 0.4, 0.4)])
enter_edit(ob)
select_faces(ob, {0, 1})
bpy.ops.uv.pack_islands(rotate=False, margin=0.0, scale=False)
report("B fits(scale=False)", ob)
to_object()

# ---------------------------------------------------------------- TEST C
clean()
ob = make_obj("C", [(0.1, 0.1, 0.3, 0.3), (0.5, 0.5, 0.3, 0.3), (0.7, 0.2, 0.3, 0.3)])
enter_edit(ob)
before = face_boxes(ob)
select_faces(ob, {0})
bpy.ops.uv.pack_islands(rotate=False, margin=0.0, scale=False)
after = face_boxes(ob)
print(f"C selection-scope: face0 before={tuple(round(v,4) for v in before[0])} "
      f"after={tuple(round(v,4) for v in after[0])}")
same1 = all(abs(a - b) < 1e-9 for a, b in zip(before[1], after[1]))
same2 = all(abs(a - b) < 1e-9 for a, b in zip(before[2], after[2]))
print(f"C selection-scope: face1_untouched={same1} face2_untouched={same2}")
to_object()

# ---------------------------------------------------------------- TEST D
clean()
ob = make_obj("D", [(0.0, 0.0, 0.7, 0.35), (0.1, 0.4, 0.7, 0.35), (0.2, 0.7, 0.7, 0.35)])
enter_edit(ob)
select_faces(ob, {0, 1, 2})
bpy.ops.uv.pack_islands(rotate=True, rotate_method='CARDINAL', margin=0.02, scale=False)
boxes = report("D cardinal(margin=0.02)", ob)
rotated = [i for i, b in enumerate(boxes)
           if abs((b[2] - b[0]) - 0.35) < 1e-3 and abs((b[3] - b[1]) - 0.7) < 1e-3]
print(f"D cardinal: rotated_faces={rotated}")
to_object()

print("EXPPACK DONE")
