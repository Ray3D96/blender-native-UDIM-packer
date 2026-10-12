# Probe 6: per-face anatomy of t8 + winding test.
# (a) dump every face: verts, normal, loops, original UVs, signed UV area
# (b) write the BIG square to face 1 with natural vs reversed loop order
#     and see which CANCELs; repeat for face 5.
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


def signed_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


ob = build_t8()
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
uvl = bm.loops.layers.uv.active
print("PROBE6 === face anatomy (original smart_project UVs) ===", flush=True)
for f in sorted(tuple(bm.faces), key=lambda f: f.index):
    uvs = [tuple(l[uvl].uv) for l in tuple(f.loops)]
    verts = [tuple(round(c, 3) for c in v.co) for v in tuple(f.verts)]
    sa = signed_area(uvs)
    print(f"PROBE6 face {f.index}: nloops={len(f.loops)} "
          f"area_uv={sa:+.4f} normal=({f.normal.x:+.2f},{f.normal.y:+.2f},"
          f"{f.normal.z:+.2f}) verts={verts}", flush=True)
    for li, l in enumerate(tuple(f.loops)):
        print(f"PROBE6   loop{li}: vert={l.vert.index} uv=({l[uvl].uv.x:.4f},"
              f"{l[uvl].uv.y:.4f})", flush=True)
bm.free()
bpy.ops.object.mode_set(mode='OBJECT')


def pack_with_winding(tag, face_idx, reverse):
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    ob = build_t8()
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    x0, y0, w, h = 0.0, 0.0, 0.797, 0.797
    coords = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    if reverse:
        coords = [coords[0], coords[3], coords[2], coords[1]]  # reversed order
    for f in tuple(bm.faces):
        if f.index == face_idx:
            loops = tuple(f.loops)
            for l, c in zip(loops, coords):
                l[uvl].uv = c
        f.select = (f.index == face_idx)
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=MARGIN, scale=False)
    # signed area of what we wrote
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for f in tuple(bm.faces):
        if f.index == face_idx:
            sa = signed_area([tuple(l[uvl].uv) for l in tuple(f.loops)])
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE6 {tag}: face={face_idx} reverse={reverse} "
          f"written_signed_area={sa:+.4f} -> {r}", flush=True)


pack_with_winding("W1-natural", 1, False)
pack_with_winding("W1-reversed", 1, True)
pack_with_winding("W5-natural", 5, False)
pack_with_winding("W5-reversed", 5, True)
print("PROBE6 DONE", flush=True)
