# Probe 13: two consecutive edit sessions on ONE mesh (the e2e T8 pattern:
# first pack FINISHED, second CANCELLED).  Vary one factor at a time to
# find the minimal state that makes session 2 pass.
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


def dump(ob, tag):
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    parts = []
    for f in tuple(bm.faces):
        us = [l[uvl].uv for l in tuple(f.loops)]
        xs = [u.x for u in us]; ys = [u.y for u in us]
        sel = "S" if f.select else "."
        parts.append(f"{sel}{f.index}:({min(xs):.3f},{min(ys):.3f},"
                     f"{max(xs):.3f},{max(ys):.3f})")
    bm.free()
    print(f"PROBE13 {tag} DUMP: " + " ".join(parts), flush=True)


def session(ob, tag, sel, force_sync=None, sticky=None, with_verts=False,
            set_face_mode=False):
    ts = bpy.context.scene.tool_settings
    if force_sync is not None:
        ts.use_uv_select_sync = force_sync
    if sticky is not None:
        ts.uv_sticky_select_mode = sticky
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    if set_face_mode:
        bpy.ops.mesh.select_mode(type='FACE')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for v in tuple(bm.verts):
        v.select = False
    for f in tuple(bm.faces):
        if f.index in sel:
            # engine-like UV write: 0.5 square at (0.1, 0.1)
            for l, c in zip(tuple(f.loops),
                            [(0.1, 0.1), (0.6, 0.1), (0.6, 0.6), (0.1, 0.6)]):
                l[uvl].uv = c
            for l in tuple(f.loops):
                if with_verts:
                    l.vert.select = True
        f.select = (f.index in sel)
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    try:
        r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                    margin=MARGIN, scale=False)
    except RuntimeError as e:
        r = f"RAISED:{e}"
    print(f"PROBE13 {tag}: sel={sorted(sel)} -> {r} "
          f"sync={ts.use_uv_select_sync} sticky={ts.uv_sticky_select_mode}",
          flush=True)
    dump(ob, tag)
    bpy.ops.object.mode_set(mode='OBJECT')
    return r


def variant(tag, **kw):
    ob = build_t8()
    r1 = session(ob, f"{tag}-s1", {0, 6}, **kw)
    r2 = session(ob, f"{tag}-s2", {1, 7}, **kw)
    print(f"PROBE13 {tag}: RESULT s1={r1} s2={r2}", flush=True)


# V0: engine-as-is (no toolsettings change, no select_mode call)
variant("V0-baseline")
# V1: + explicit FACE select mode
variant("V1-facemode", set_face_mode=True)
# V2: + force sync ON (sticky default)
variant("V2-syncON", force_sync=True)
# V3: + force sync ON + sticky DISABLED
variant("V3-syncON-DIS", force_sync=True, sticky="DISABLED")
# V4: + vertex selection recipe only
variant("V4-verts", with_verts=True)
print("PROBE13 DONE", flush=True)
