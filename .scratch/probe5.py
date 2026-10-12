# Probe 5: CLEAN isolation - rebuild the t8 mesh for EVERY case (no state
# carry-over), map which single/pair selections CANCEL, and test whether
# unselected-face UV positions are the trigger.
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


def run_case(tag, sel, uv_by_face, move_others=None):
    """move_others: None | 'far' (others to [3,6]^2) | 'corner' (tiny at 0.9)."""
    ob = build_t8()
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
        elif move_others == 'far':
            for l in tuple(f.loops):
                u = l[uvl].uv
                l[uvl].uv = (3.0 + u.x, 3.0 + u.y)
        elif move_others == 'corner':
            for l in tuple(f.loops):
                u = l[uvl].uv
                l[uvl].uv = (0.9 + 0.02 * u.x, 0.9 + 0.02 * u.y)
        f.select = (f.index in sel)
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=MARGIN, scale=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE5 {tag}: sel={sorted(sel)} move_others={move_others} -> {r}",
          flush=True)


run_case("C1-only-1", {1}, {1: BIG})
run_case("C2-only-5", {5}, {5: BIG})
run_case("C3-only-8", {8}, {8: SMALL})
run_case("C4-only-9", {9}, {9: SMALL})
run_case("C5-{1,9}", {1, 9}, {1: BIG, 9: SMALL})
run_case("C6-{5,8}", {5, 8}, {5: BIG, 8: SMALL})
run_case("C7-only-1-others-far", {1}, {1: BIG}, move_others='far')
run_case("C8-only-1-others-corner", {1}, {1: BIG}, move_others='corner')
print("PROBE5 DONE", flush=True)
