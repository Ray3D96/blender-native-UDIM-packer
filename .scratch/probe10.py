# Probe 10: which OTHER faces trigger face-1's CANCEL?
# E1: face1 + its 4 neighbors (f0,f2,f4,f5)
# E2: face1 + only neighbor f0
# E3: face1 + only non-adjacent small-cube faces (f6..f11)
# E4: face1 + only far face f9
# E5: face1 + only the other 3 big side faces (f0,f2,f3)
# E6: face1 + only top/bottom pair (f4,f5)
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


def run(tag, keep):
    """keep: set of ORIGINAL face indices to KEEP (must include 1).
    Selection target = big-cube +Y face (center (0,1,0)), found by geometry
    because deletion renumbers indices."""
    ob = build_t8()
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for f in sorted(bm.faces, key=lambda f: f.index, reverse=True):
        if f.index not in keep:
            bmesh.ops.delete(bm, geom=[f], context='FACES')
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    x0, y0, w, h = 0.0, 0.0, 0.797, 0.797
    sel_idx = []
    for f in tuple(bm.faces):
        c = f.calc_center_median()
        if abs(c.x) < 1e-4 and abs(c.y - 1.0) < 1e-4 and abs(c.z) < 1e-4:
            coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
            for l, cc in zip(tuple(f.loops), coords):
                l[uvl].uv = cc
            f.select = True
            sel_idx.append(f.index)
        else:
            f.select = False
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=MARGIN, scale=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE10 {tag}: keep_orig={sorted(keep)} sel_now={sel_idx} -> {r}",
          flush=True)


run("E1-1+4neighbors", {1, 0, 2, 4, 5})
run("E2-1+neighbor-f0", {1, 0})
run("E3-1+smallcube", {1} | set(range(6, 12)))
run("E4-1+far-f9", {1, 9})
run("E5-1+other-sides", {1, 0, 2, 3})
run("E6-1+topbottom", {1, 4, 5})
print("PROBE10 DONE", flush=True)
