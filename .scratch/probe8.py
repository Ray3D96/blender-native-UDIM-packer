# Probe 8: isolation - delete all faces except the tested one, then pack.
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


def isolate_and_pack(tag, keep_face):
    ob = build_t8()
    # delete all faces except keep_face (object mode, bmesh on mesh data)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for f in sorted(bm.faces, key=lambda f: f.index, reverse=True):
        if f.index != keep_face:
            bmesh.ops.delete(bm, geom=[f], context='FACES')
    # reindex so the kept face becomes index 0? NO - keep original index by
    # NOT reindexing; but bmesh delete may leave a hole. We report both.
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()

    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    kept = [f.index for f in tuple(bm.faces)]
    uvl = bm.loops.layers.uv.active
    x0, y0, w, h = 0.0, 0.0, 0.797, 0.797
    for f in tuple(bm.faces):
        coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
        for l, c in zip(tuple(f.loops), coords):
            l[uvl].uv = c
        f.select = True
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=MARGIN, scale=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE8 {tag}: kept_original_index={keep_face} "
          f"indices_now={kept} -> {r}", flush=True)


isolate_and_pack("iso-face1", 1)
isolate_and_pack("iso-face5", 5)
isolate_and_pack("iso-face9", 9)
print("PROBE8 DONE", flush=True)
