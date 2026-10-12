# Probe 7: full 12-face CANCEL map + parameter variations + isolation.
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


def pack_single(tag, face_idx, square=None, rotate=True, margin=MARGIN,
                scale=False, keep_original=False):
    """square: (x0,y0,w,h) to write, or None/keep_original -> no UV write."""
    ob = build_t8()
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    if square and not keep_original:
        bm = bmesh.from_edit_mesh(ob.data)
        uvl = bm.loops.layers.uv.active
        x0, y0, w, h = square
        for f in tuple(bm.faces):
            if f.index == face_idx:
                coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h),
                          (x0, y0 + h)]
                for l, c in zip(tuple(f.loops), coords):
                    l[uvl].uv = c
            f.select = (f.index == face_idx)
        bmesh.update_edit_mesh(ob.data)
        bm.free()
    else:
        bm = bmesh.from_edit_mesh(ob.data)
        for f in tuple(bm.faces):
            f.select = (f.index == face_idx)
        bm.free()
    r = bpy.ops.uv.pack_islands(rotate=rotate, rotate_method="CARDINAL",
                                margin=margin, scale=scale)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE7 {tag}: -> {r}", flush=True)


BIG = (0.0, 0.0, 0.797, 0.797)
SMALL = (0.0, 0.0, 0.3985, 0.3985)

# 1) full map: every face alone, written with its cube's square size
for i in range(6):
    pack_single(f"map-face{i}-big", i, BIG)
for i in range(6, 12):
    pack_single(f"map-face{i}-small", i, SMALL)

# 2) face 1 with ORIGINAL uv (no overwrite)
pack_single("face1-original-uv", 1, keep_original=True)
# 3) face 5 with original uv
pack_single("face5-original-uv", 5, keep_original=True)

# 4) parameter variations on face 1 (BIG write)
pack_single("face1-m0", 1, BIG, margin=0.0)
pack_single("face1-norotate", 1, BIG, rotate=False)
pack_single("face1-scale", 1, BIG, scale=True)
print("PROBE7 DONE", flush=True)
