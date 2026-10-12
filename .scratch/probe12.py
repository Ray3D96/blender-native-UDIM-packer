# Probe 12: map the pack_islands CANCEL gate precisely.
#
# Source analysis (Blender v5.2.2, uvedit_unwrap_ops.cc):
#   pack_islands_exec hardcodes only_selected_faces=True and
#   only_selected_uvs=True, then early-returns OPERATOR_CANCELLED when
#   uvedit_have_selection_multi() finds no loop passing
#   uvedit_uv_select_test() -- a toolsettings-dependent test:
#     SYNC ON  + sync_valid TRUE : per-loop BM_ELEM_SELECT_UV flag
#     SYNC ON  + sync_valid FALSE+ FACE mode:
#        sticky LOCATION : face selected OR other face shares UV vert
#        sticky DISABLE  : face selected
#        sticky VERT     : mesh vert selected
#     SYNC OFF              : face selected AND UV-vert selected
#
# This probe measures which (toolsettings, selection recipe) combos pass
# the gate for CANCEL-class face {1} and FINISH-class face {5}, plus a
# two-consecutive-session engine simulation.
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


def uv_snapshot(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    snap = []
    for f in tuple(bm.faces):
        for l in tuple(f.loops):
            u = l[uvl].uv
            snap.append((f.index, round(u.x, 6), round(u.y, 6)))
    bm.free()
    return snap


def select_faces(ob, sel, with_verts):
    bm = bmesh.from_edit_mesh(ob.data)
    for v in tuple(bm.verts):
        v.select = False
    for f in tuple(bm.faces):
        f.select = (f.index in sel)
        if with_verts and f.index in sel:
            for l in tuple(f.loops):
                l.vert.select = True
    bmesh.update_edit_mesh(ob.data)
    bm.free()


def pack_once(ob, tag):
    try:
        r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                    margin=MARGIN, scale=False)
    except RuntimeError as e:
        r = f"RAISED:{e}"
    # post-pack bbox of selected faces + full-mesh snapshot for change check
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    out = {}
    for f in tuple(bm.faces):
        if f.select:
            us = [l[uvl].uv for l in tuple(f.loops)]
            xs = [u.x for u in us]; ys = [u.y for u in us]
            out[f.index] = (round(min(xs), 4), round(min(ys), 4),
                            round(max(xs), 4), round(max(ys), 4))
    bm.free()
    print(f"PROBE12 {tag}: -> {r} post={out}", flush=True)
    return r


def case(tag, sync, sticky, recipe, sel):
    ob = build_t8()
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = sync
    if sync:
        ts.uv_sticky_select_mode = sticky
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    print(f"PROBE12 {tag}: echo sync={ts.use_uv_select_sync} "
          f"sticky={ts.uv_sticky_select_mode}", flush=True)
    before = uv_snapshot(ob)
    if recipe == 'A':
        select_faces(ob, sel, with_verts=False)
    else:
        select_faces(ob, sel, with_verts=True)
    r = pack_once(ob, f"{tag} (sync={int(sync)} sticky={sticky} rec={recipe})")
    after = uv_snapshot(ob)
    changed_nonselected = [s for s in after if s not in before]
    bpy.ops.object.mode_set(mode='OBJECT')
    print(f"PROBE12 {tag}: nonselected_uv_changes={len(changed_nonselected)}",
          flush=True)
    return r


BIG = (0.0, 0.0, 0.797, 0.797)

# Matrix: 4 toolsettings states x 2 recipes x 2 face classes
for sync in (True, False):
    stickies = ('DISABLED', 'SHARED_LOCATION', 'SHARED_VERTEX') if sync else ('NONE',)
    for sticky in stickies:
        for recipe in ('A', 'B'):
            for sel in ({1}, {5}):
                case(f"m-sync{int(sync)}-{sticky}-rec{recipe}-f{sorted(sel)[0]}",
                     sync, sticky, recipe, sel)

# Engine simulation: two consecutive edit sessions on ONE mesh (T8 pattern),
# forced state sync ON + sticky DISABLE + recipe B.
ob = build_t8()
ts = bpy.context.scene.tool_settings
ts.use_uv_select_sync = True
ts.uv_sticky_select_mode = 'DISABLED'

bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='FACE')
before1 = uv_snapshot(ob)
# session 1: tile {1} with BIG square
bm = bmesh.from_edit_mesh(ob.data)
uvl = bm.loops.layers.uv.active
for l, c in zip(tuple(bm.faces[1].loops),
                [(0.0, 0.0), (0.797, 0.0), (0.797, 0.797), (0.0, 0.797)]):
    l[uvl].uv = c
select_faces(ob, {1}, with_verts=True)
r1 = pack_once(ob, "SIM-session1-{1}")
bpy.ops.object.mode_set(mode='OBJECT')

# session 2: tile {5} with SMALL square
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='FACE')
bm = bmesh.from_edit_mesh(ob.data)
for l, c in zip(tuple(bm.faces[5].loops),
                [(0.0, 0.0), (0.3985, 0.0), (0.3985, 0.3985), (0.0, 0.3985)]):
    l[uvl].uv = c
select_faces(ob, {5}, with_verts=True)
r2 = pack_once(ob, "SIM-session2-{5}")
after2 = uv_snapshot(ob)
bpy.ops.object.mode_set(mode='OBJECT')
moved = [s for s in after2 if s not in before1]
print(f"PROBE12 SIM: r1={r1} r2={r2} total_uv_moved_entries={len(moved)}",
      flush=True)
print("PROBE12 DONE", flush=True)
