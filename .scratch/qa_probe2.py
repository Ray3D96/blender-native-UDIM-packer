"""Single-round phase timing for the QA scene.

Replays exactly what _execute_round does for ONE tile, with a stopwatch
around every phase: expose, enter-edit, UV-write+select, pack_islands,
measure pass, overlap check.
"""
import sys
import time

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"

import bpy  # noqa: E402

_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:
        print(f"[warn] {exc}", flush=True)
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, ADDON_PATH)
import native_udim_packer as A  # noqa: E402
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer import layout as L  # noqa: E402
A.register()

bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')  # commit saved multi-edit state
targets = [o for o in bpy.context.scene.objects
           if o.type == 'MESH' and o.data.uv_layers
           and o.data.uv_layers.active]
print(f"objects={len(targets)}", flush=True)

# Reproduce pack_objects' front half (detection, normalize, items, snapshot)
state = []
for ob in targets:
    islands = P._detect_object(ob)
    if islands is None:
        continue
    for i in islands:
        i.owner = ob
    state.append({"ob": ob, "islands": islands})
all_islands = [i for s in state for i in s["islands"]]
P.normalize_scales(all_islands)
items = []
for n, i in enumerate(all_islands):
    i._s_norm = i.norm_scale if i.norm_scale is not None else 1.0
    i._item_index = n
    w = max((i.max_uv[0] - i.min_uv[0]) * i._s_norm, 1e-6)
    h = max((i.max_uv[1] - i.min_uv[1]) * i._s_norm, 1e-6)
    items.append(L.Item(n, w, h))
for s in state:
    s["snapshot"] = P._snapshot_uv(s["ob"].data)

S = L.max_scale(1.0 - 2 * 0.0, items)
print(f"S={S!r} islands={len(items)}", flush=True)
assign = L.assign_ffd(items, 3, (1.0 - 0.0) ** 2 / (S * S), eta=0.92)
assert assign is not None
used = sorted(set(assign.values()))
print(f"eta=0.92 used tiles={used} "
      f"per-tile={[sum(1 for v in assign.values() if v == t) for t in used]}",
      flush=True)

t_focus = used[0]  # the fullest tile
members = [s for s in state
           if any(assign[i._item_index] == t_focus
                  for i in s["islands"])]
obs = [s["ob"] for s in members]
n_isl = sum(1 for s in members for i in s["islands"]
            if assign[i._item_index] == t_focus)
print(f"focus tile={t_focus} objects={len(obs)} islands={n_isl}", flush=True)

# ---- phase 1: expose -----------------------------------------------------
t0 = time.time()
undo_vis = []
undo_vis_t1 = []
for ob in obs:
    undo_vis.extend(P._expose_in_view_layer(ob))
print(f"phase expose      {time.time() - t0:7.2f}s", flush=True)

try:
    # ---- phase 2: enter multi-edit ---------------------------------------
    t0 = time.time()
    P._enter_multi_edit(obs)
    print(f"phase enter-edit  {time.time() - t0:7.2f}s", flush=True)

    # ---- phase 3: write UVs + select -------------------------------------
    t0 = time.time()
    import bmesh  # noqa: E402
    fsets = {}
    for s in members:
        ob, snap = s["ob"], s["snapshot"]
        face_map = {}
        for i in s["islands"]:
            if assign[i._item_index] != t_focus:
                continue
            k = i._s_norm * S
            minx0, miny0 = i.min_uv[0], i.min_uv[1]
            for fi in i.face_indices:
                face_map[fi] = [((x - minx0) * k, (y - miny0) * k)
                                for (x, y) in snap[fi]]
        fset = set(face_map)
        fsets[ob.name] = fset
        me = ob.data
        bm = bmesh.from_edit_mesh(me)
        try:
            uvl = bm.loops.layers.uv.active
            for f in tuple(bm.faces):
                uv_list = face_map.get(f.index)
                if uv_list is not None:
                    for l, (x, y) in zip(tuple(f.loops), uv_list):
                        l[uvl].uv = (x, y)
                f.select = (f.index in fset)
            bmesh.update_edit_mesh(me)
        finally:
            bm.free()
    print(f"phase write+sel   {time.time() - t0:7.2f}s", flush=True)

    # ---- phase 4: the native pack ----------------------------------------
    t0 = time.time()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    print(f"phase pack        {time.time() - t0:7.2f}s  result={r}",
          flush=True)

    # ---- phase 5: measure pass -------------------------------------------
    t0 = time.time()
    face_polys = {}
    for s in members:
        ob = s["ob"]
        fset = fsets[ob.name]
        bm = bmesh.from_edit_mesh(ob.data)
        try:
            uvl = bm.loops.layers.uv.active
            polys = {}
            for f in tuple(bm.faces):
                if f.index not in fset:
                    continue
                polys[f.index] = [(l[uvl].uv.x, l[uvl].uv.y)
                                  for l in tuple(f.loops)]
            face_polys[ob.name] = polys
        finally:
            bm.free()
    print(f"phase measure     {time.time() - t0:7.2f}s", flush=True)
    P._exit_edit()  # close tile-0 session before opening tile 1's

    # ---- phase 6: overlap check -------------------------------------------
    def run_check(tile_idx, label):
        tile_polys = []
        for s in members_all:
            fp = face_polys_all.get(s["ob"].name, {})
            for i in s["islands"]:
                if assign[i._item_index] != tile_idx:
                    continue
                try:
                    tile_polys.append([fp[fi] for fi in i.face_indices])
                except KeyError as exc:
                    raise SystemExit(
                        f"DEBUG missing face {exc} in "
                        f"{s['ob'].name}: n_faces_in_fp={len(fp)} "
                        f"island_faces={sorted(i.face_indices)[:8]}... "
                        f"n_isl_faces={len(i.face_indices)}")
        sizes = [len(p) for p in tile_polys]
        big = sorted(sizes, reverse=True)[:5]
        print(f"{label}: islands={len(tile_polys)} "
              f"faces/island top5={big} total_faces={sum(sizes)}",
              flush=True)
        t0 = time.time()
        hits = 0
        slow = []
        for x in range(len(tile_polys)):
            for y in range(x + 1, len(tile_polys)):
                tp = time.time()
                if L.polygons_overlap(tile_polys[x], tile_polys[y]):
                    hits += 1
                    if hits <= 3:
                        print(f"  OVERLAP isl{x} vs isl{y}", flush=True)
                dt = time.time() - tp
                if dt > 0.2:
                    slow.append((dt, x, y, len(tile_polys[x]),
                                 len(tile_polys[y])))
        dt6 = time.time() - t0
        slow.sort(reverse=True)
        print(f"{label}: overlapchk {dt6:.2f}s hits={hits} "
              f"slow_pairs(>0.2s)={len(slow)}", flush=True)
        for dt, x, y, fx, fy in slow[:8]:
            print(f"    {dt:7.2f}s  isl{x}({fx}f) vs isl{y}({fy}f)",
                  flush=True)

    # Re-pack tile 1 as well so both tiles' post-pack UVs are available.
    t1 = used[1]
    members_t1 = [s for s in state
                  if any(assign[i._item_index] == t1 for i in s["islands"])]
    obs_t1 = [s["ob"] for s in members_t1]
    for ob in obs_t1:
        undo_vis_t1.extend(P._expose_in_view_layer(ob))
    P._enter_multi_edit(obs_t1)
    for ob in obs_t1:
        print(f"  t1 obj {ob.name:24s} mode={ob.mode:9s} "
              f"sel={ob.select_get()} hide_vl={ob.hide_viewport} "
              f"hide_get={ob.hide_get()}", flush=True)

    def pm_count(label):
        bm = bmesh.from_edit_mesh(pm.data)
        n = sum(1 for f in bm.faces if f.index in fs_pm)
        bm.free()
        print(f"  CK {label}: PlugMetal fset-match={n}/{len(fs_pm)}",
              flush=True)

    fsets_t1 = {}
    for s in members_t1:
        ob, snap = s["ob"], s["snapshot"]
        face_map = {}
        for i in s["islands"]:
            if assign[i._item_index] != t1:
                continue
            k = i._s_norm * S
            minx0, miny0 = i.min_uv[0], i.min_uv[1]
            for fi in i.face_indices:
                face_map[fi] = [((x - minx0) * k, (y - miny0) * k)
                                for (x, y) in snap[fi]]
        fset = set(face_map)
        fsets_t1[ob.name] = fset
        me = ob.data
        bm = bmesh.from_edit_mesh(me)
        try:
            uvl = bm.loops.layers.uv.active
            for f in tuple(bm.faces):
                uv_list = face_map.get(f.index)
                if uv_list is not None:
                    for l, (x, y) in zip(tuple(f.loops), uv_list):
                        l[uvl].uv = (x, y)
                f.select = (f.index in fset)
            bmesh.update_edit_mesh(me)
        finally:
            bm.free()
    # ---- diag: PlugMetal fset vs edit bmesh --------------------------------
    pm = next(s["ob"] for s in members_t1 if s["ob"].name == "PlugMetal")
    fs_pm = sorted(fsets_t1["PlugMetal"])
    print(f"DIAG fset size={len(fs_pm)} faces={fs_pm[:40]}", flush=True)
    pm_isls = [i for i in next(s for s in state
                               if s["ob"].name == "PlugMetal")["islands"]
               if assign[i._item_index] == t1]
    print(f"DIAG PlugMetal t1 islands={len(pm_isls)} "
          f"face_counts={[len(i.face_indices) for i in pm_isls]} "
          f"union={len(set(fi for i in pm_isls for fi in i.face_indices))}",
          flush=True)
    bm = bmesh.from_edit_mesh(pm.data)
    found = sorted(f.index for f in bm.faces if f.index in fs_pm)
    print(f"DIAG edit-bmesh found={len(found)} "
          f"missing_from_edit={sorted(set(fs_pm) - set(found))[:20]}",
          flush=True)
    bm.free()

    def pm_count(label):
        bm = bmesh.from_edit_mesh(pm.data)
        n = sum(1 for f in bm.faces if f.index in fs_pm)
        bm.free()
        print(f"  CK {label}: PlugMetal fset-match={n}/{len(fs_pm)}",
              flush=True)

    t0 = time.time()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    print(f"phase pack-tile1  {time.time() - t0:.2f}s result={r}",
          flush=True)
    pm_count("after-pack")
    face_polys_all = {}
    for s in members_t1:
        ob = s["ob"]
        fset = fsets_t1[ob.name]
        bm = bmesh.from_edit_mesh(ob.data)
        try:
            uvl = bm.loops.layers.uv.active
            polys = {}
            for f in tuple(bm.faces):
                if f.index not in fset:
                    continue
                polys[f.index] = [(l[uvl].uv.x, l[uvl].uv.y)
                                  for l in tuple(f.loops)]
            if ob.name == "PlugMetal":
                keys = sorted(polys)
                print(f"  CK read-PM polys={len(keys)} first20={keys[:20]}",
                      flush=True)
                allidx = [f.index for f in bm.faces][:25]
                print(f"  CK read-PM handle first25 idx={allidx}",
                      flush=True)
            face_polys_all[ob.name] = polys
        finally:
            bm.free()
        if ob.name == "PlugMetal":
            pm_count("after-read-PM")
    P._exit_edit()

    # Merge both tiles' data and check each.
    members_all = state
    face_polys_all.update(face_polys)
    run_check(t_focus, f"tile{t_focus}")
    run_check(t1, f"tile{t1}")
finally:
    if (bpy.context.object is not None
            and bpy.context.object.mode == 'EDIT'):
        P._exit_edit()
    for fn in reversed(undo_vis_t1):
        fn()
    for fn in reversed(undo_vis):
        fn()
print("done", flush=True)
