# Probe 11: distinguish "min selected index" vs "contains top/bottom-class"
# rules, and test the sacrificial-face workaround.
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


def run(tag, sel, squares):
    """squares: dict face_idx -> (x0,y0,w,h); selected faces without a square
    keep original UVs."""
    ob = build_t8()
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for f in tuple(bm.faces):
        if f.index in squares:
            x0, y0, w, h = squares[f.index]
            coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
            for l, c in zip(tuple(f.loops), coords):
                l[uvl].uv = c
        f.select = (f.index in sel)
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=MARGIN, scale=False)
    # post-pack bboxes of selected faces
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    out = {}
    for f in tuple(bm.faces):
        if f.index in sel:
            us = [l[uvl].uv for l in tuple(f.loops)]
            xs = [u.x for u in us]; ys = [u.y for u in us]
            out[f.index] = (round(min(xs), 4), round(min(ys), 4),
                            round(max(xs), 4), round(max(ys), 4))
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE11 {tag}: sel={sorted(sel)} -> {r} post={out}", flush=True)


BIG = (0.0, 0.0, 0.797, 0.797)
SMALL = (0.0, 0.0, 0.3985, 0.3985)

# rule discriminators (all selected faces get squares so all are "islands")
run("F1-{0,4}", {0, 4}, {0: BIG, 4: SMALL})
run("F2-{3,5}", {3, 5}, {3: BIG, 5: SMALL})
run("F3-{4,9}", {4, 9}, {4: BIG, 9: SMALL})
run("F4-{0,4,9}", {0, 4, 9}, {0: BIG, 4: SMALL, 9: SMALL})

# sacrificial-face workaround for the engine case {1,9}
run("F5-{1,9}+sac4", {1, 9, 4}, {1: BIG, 9: SMALL})
run("F6-{1,9}+sac10", {1, 9, 10}, {1: BIG, 9: SMALL})
print("PROBE11 DONE", flush=True)
