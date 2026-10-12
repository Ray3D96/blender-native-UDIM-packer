# Probe 3: (a) confirm whether the packer OVERLAPS when it cannot fit
# (per-face bboxes + overlap area after packing the T8 shape); (b) bisect
# the engine sequence - is tile-1's CANCEL caused by tile-0's session, or
# inherent to selecting faces {1,9} of the real 12-face t8 mesh?
import bmesh
import bpy

MARGIN = 0.008


def build_t8():
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    b = bpy.context.active_object
    a.select_set(True); b.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = "t8"
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def face_bboxes(ob):
    me = ob.data
    bm = bmesh.from_edit_mesh(me)
    uvl = bm.loops.layers.uv.active
    out = {}
    for f in tuple(bm.faces):
        us = [l[uvl].uv for l in tuple(f.loops)]
        xs = [u.x for u in us]; ys = [u.y for u in us]
        out[f.index] = (min(xs), min(ys), max(xs), max(ys))
    bm.free()
    return out


def overlap_area(b1, b2):
    w = min(b1[2], b2[2]) - max(b1[0], b2[0])
    h = min(b1[3], b2[3]) - max(b1[1], b2[1])
    return max(0.0, w) * max(0.0, h)


def enter_edit_select(ob, sel, uv_by_face):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for f in tuple(bm.faces):
        if f.index in uv_by_face:
            x0, y0, w, h = uv_by_face[f.index]
            coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
            for l, c in zip(tuple(f.loops), coords):
                l[uvl].uv = c
        f.select = (f.index in sel)
    bmesh.update_edit_mesh(ob.data)
    bm.free()


def do_pack(tag):
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=MARGIN, scale=False)
    bb = face_bboxes(bpy.context.view_layer.objects.active)
    print(f"PROBE3 {tag}: pack={r}", flush=True)
    for i in sorted(bb):
        b = bb[i]
        print(f"PROBE3   face {i}: ({b[0]:.4f},{b[1]:.4f})-({b[2]:.4f},{b[3]:.4f})",
              flush=True)
    return r, bb


# ---- (a) overlap confirmation on the real mesh -----------------------------
ob = build_t8()
# engine-like UV writes: face 5/1 big square at origin, face 8/9 small
BIG = (0.0, 0.0, 0.797, 0.797)
SMALL = (0.0, 0.0, 0.3985, 0.3985)

# Case A: fresh session, select {1,9} only (tile-1's faces as FIRST call)
enter_edit_select(ob, {1, 9}, {1: BIG, 9: SMALL})
rA, bbA = do_pack("caseA-fresh-{1,9}")
bpy.ops.object.mode_set(mode='OBJECT')

# Case B: fresh session, select {5,8} only (tile-0's faces as FIRST call)
enter_edit_select(ob, {5, 8}, {5: BIG, 8: SMALL})
rB, bbB = do_pack("caseB-fresh-{5,8}")
bpy.ops.object.mode_set(mode='OBJECT')

# Case C: engine sequence - tile0 {5,8} first, re-enter, then tile1 {1,9}
enter_edit_select(ob, {5, 8}, {5: BIG, 8: SMALL})
rC1, _ = do_pack("caseC-tile0-{5,8}")
bpy.ops.object.mode_set(mode='OBJECT')
enter_edit_select(ob, {1, 9}, {1: BIG, 9: SMALL})
rC2, bbC = do_pack("caseC-tile1-after-tile0")
bpy.ops.object.mode_set(mode='OBJECT')

# overlap report for case A (fresh {1,9})
if rA == {'FINISHED'}:
    ov = overlap_area(bbA[1], bbA[9])
    print(f"PROBE3 caseA overlap area faces 1&9 = {ov:.4f} "
          f"(big area={0.797**2:.4f})", flush=True)
print("PROBE3 DONE", flush=True)
