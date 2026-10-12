# Probe 4: map which face selections of the t8 mesh make uv.pack_islands
# CANCEL. All cases write identical square UVs to the selected faces.
import bmesh
import bpy

MARGIN = 0.008
BIG = (0.0, 0.0, 0.797, 0.797)
SMALL = (0.0, 0.0, 0.3985, 0.3985)


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


def run_case(ob, tag, sel, uv_by_face, rotate=True, margin=MARGIN):
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
    r = bpy.ops.uv.pack_islands(rotate=rotate, rotate_method="CARDINAL",
                                margin=margin, scale=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE4 {tag}: sel={sorted(sel)} rot={rotate} m={margin} -> {r}",
          flush=True)


ob = build_t8()
# A1: only face 1 (big square)
run_case(ob, "A1-only-1-big", {1}, {1: BIG})
# A2: only face 9 (small square)
run_case(ob, "A2-only-9-small", {9}, {9: SMALL})
# A3: swapped sizes on {1,9}
run_case(ob, "A3-{1,9}-swapped", {1, 9}, {1: SMALL, 9: BIG})
# A4: {1,9} with squares at distinct positions (no shared origin)
run_case(ob, "A4-{1,9}-separate", {1, 9},
         {1: (0.0, 0.0, 0.797, 0.797), 9: (0.5, 0.5, 0.3985, 0.3985)})
# A5: different pair - big-cube face 2 + small-cube face 7
run_case(ob, "A5-{2,7}", {2, 7}, {2: BIG, 7: SMALL})
# A6: another pair - faces 0 and 6
run_case(ob, "A6-{0,6}", {0, 6}, {0: BIG, 6: SMALL})
# A7: the three small-cube faces 6,7,8 + big face 1 (3+1)
run_case(ob, "A7-{1,6,7,8}", {1, 6, 7, 8},
         {1: BIG, 6: SMALL, 7: SMALL, 8: SMALL})
print("PROBE4 DONE", flush=True)
