# SPDX-License-Identifier: GPL-2.0-or-later
"""End-to-end test for the Native UDIM Packer addon (Blender 5.2, background).

Installs the addon from the dist zip, enables it, then runs the operator on
several generated meshes and audits the resulting UV layout.
"""
import sys
import traceback

import bpy
import bmesh

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((status, name, detail))
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))


# ---------------------------------------------------------------- install --
ZPATH = "/mnt/fusion/ai-projects/blender-uv-packer/dist/native_udim_packer-0.1.6.zip"
r = bpy.ops.preferences.addon_install(filepath=ZPATH)
check("install from zip", r == {'FINISHED'}, str(r))
bpy.ops.preferences.addon_enable(module="native_udim_packer")
enabled = "native_udim_packer" in bpy.context.preferences.addons.keys()
check("addon enabled", enabled)

# Force a fully consistent in-memory state.  If an older build was loaded at
# startup, Blender's on-disk-change auto-reload re-executes only __init__.py
# and keeps the stale submodules (packer/islands/...) cached in sys.modules -
# a mixed-version state that silently ran old code in a previous test run.
# Unregister whatever is registered, purge every cached module, re-import
# from disk and register fresh, so the tests always exercise the zip's code.
import sys as _sys
_old = _sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:  # noqa: BLE001 - partial states only warn
        print(f"[warn] old module unregister: {exc}")
for _n in [n for n in list(_sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del _sys.modules[_n]
import native_udim_packer as _A
_A.register()

has_op = hasattr(bpy.ops.native_udim, "pack_to_grid")
check("operator registered", has_op)
check("release version is 0.1.6", tuple(_A.bl_info["version"]) == (0, 1, 6),
      str(tuple(_A.bl_info["version"])))
check("VERSION string for panel stamp", _A.VERSION == "0.1.6", _A.VERSION)

# Settings must be a persistent PropertyGroup on the window manager - the
# only pattern whose widgets are interactive in Blender 5.x (widgets bound
# to the layout.operator() snapshot render but cannot be clicked).
_wm_settings = bpy.context.window_manager.native_udim
check("T0 wm settings group registered with defaults",
      int(_wm_settings.udim_x) == 2 and int(_wm_settings.udim_y) == 2
      and _wm_settings.rotate_90 is True and _wm_settings.use_selected is True
      and abs(float(_wm_settings.margin) - 0.005) < 1e-9,
      f"x={_wm_settings.udim_x} y={_wm_settings.udim_y} "
      f"rot={_wm_settings.rotate_90} sel={_wm_settings.use_selected} "
      f"margin={_wm_settings.margin}")
# Persist the enabled state so a fresh launch of this install auto-loads it.
bpy.ops.wm.save_userpref()

# ---------------------------------------------------------------- helpers --
def make_test_object(name):
    """Cube + small cube + icosphere joined; smart-projected UVs."""
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    b = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8, location=(-6, 0, 0))
    c = bpy.context.active_object
    a.select_set(True); b.select_set(True); c.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def clean_scene():
    # T9 intentionally ends in (multi-)edit mode; object operators poll-fail
    # there, so return to object mode first.
    if bpy.context.mode == 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def uv_stats(ob):
    """Per-island (uv_area, world_area, tile) via the addon; handles mode."""
    from native_udim_packer import packer
    was_edit = bpy.context.mode == 'EDIT_MESH'
    if not was_edit:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    islands = packer.detect_islands(bm, uvl)
    out = []
    for i in islands:
        minx, miny, maxx, maxy = packer.island_bounds(bm, uvl, i.face_indices)
        cu, cv = (minx + maxx) / 2, (miny + maxy) / 2
        out.append({
            "uv_area": i.uv_area,
            "world_area": i.world_area,
            "tile": (int(round(cu)), int(round(cv))),
            "bounds": (minx, miny, maxx, maxy),
        })
    bm.free()
    if not was_edit:
        bpy.ops.object.mode_set(mode='OBJECT')
    return out


def set_grid(gx, gy, normalize=False, rotate=True, margin=0.01):
    # 5.x design: settings live on the window manager, not on the operator.
    s = bpy.context.window_manager.native_udim
    s.udim_x, s.udim_y = gx, gy
    s.normalize_scale, s.rotate_90, s.margin = normalize, rotate, margin


def run_pack(ob, gx, gy, normalize, rotate, margin=0.01):
    set_grid(gx, gy, normalize, rotate, margin)
    bpy.context.window_manager.native_udim.use_selected = True
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    return bpy.ops.native_udim.pack_to_grid()


def audit(ob, gx, gy):
    """All islands inside [0,gx]x[0,gy] and each inside its own unit tile."""
    from native_udim_packer import packer
    was_edit = bpy.context.mode == 'EDIT_MESH'
    if not was_edit:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
    res = packer.verify_packing(ob, gx, gy)
    if not was_edit:
        bpy.ops.object.mode_set(mode='OBJECT')
    ok = res["all_inside"]
    if not ok:
        bs = [p["bounds"] for p in res["per_island"]]
        lox = min(b[0] for b in bs); hix = max(b[2] for b in bs)
        loy = min(b[1] for b in bs); hiy = max(b[3] for b in bs)
        bad = [p for p in res["per_island"] if not p["inside"]]
        print(f"    audit detail: overall=({lox:.4f},{loy:.4f})-({hix:.4f},{hiy:.4f}) "
              f"grid=[0,{gx}]x[0,{gy}] bad={len(bad)} e.g. {bad[:3]}")
    # shape-level overlap check: actual UV polygon intersection between any
    # two islands (AABBs may legitimately intersect for concave islands)
    tris = shrunken_island_tris(ob)
    overlaps = count_overlaps(tris, tris, self_pairs=True)
    if overlaps:
        ok = False
        print(f"    audit detail: {overlaps} island pairs with intersecting UV polygons")
    return ok, res


def shrunken_island_tris(ob):
    """Per-island triangulated UV polygons, shrunk 0.1% about each island's
    own center so boundary contact is not counted as overlap."""
    from native_udim_packer import packer
    import mathutils.geometry as geom
    from mathutils import Vector
    need_enter = bpy.context.mode != 'EDIT_MESH'
    if need_enter:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
    bm2 = bmesh.from_edit_mesh(ob.data)
    uvl2 = bm2.loops.layers.uv.active
    isl2 = packer.detect_islands(bm2, uvl2)
    tris = []  # per island: list of (Vector, Vector, Vector) in UV space
    for i in isl2:
        tlist = []
        for f in tuple(bm2.faces):
            if f.index in i.face_indices:
                pts = [Vector((l[uvl2].uv.x, l[uvl2].uv.y, 0.0))
                       for l in tuple(f.loops)]
                for t in geom.tessellate_polygon([pts]):
                    tlist.append(tuple(pts[k] for k in t))
        tris.append(tlist)
    bm2.free()
    if need_enter:
        bpy.ops.object.mode_set(mode='OBJECT')

    def shrink(tlist):
        if not tlist:
            return tlist
        xs = [v.x for t in tlist for v in t]; ys = [v.y for t in tlist for v in t]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        out = []
        for t in tlist:
            out.append(tuple(Vector(((v.x - cx) * 0.999 + cx,
                                     (v.y - cy) * 0.999 + cy, 0.0)) for v in t))
        return out
    return [shrink(t) for t in tris]


def count_overlaps(tris_a, tris_b, self_pairs=False):
    """Number of island pairs (i in a, j in b) with intersecting polygons."""
    import mathutils.geometry as geom
    n = 0
    if self_pairs:
        for a in range(len(tris_a)):
            for b in range(a + 1, len(tris_a)):
                if _pair_hits(tris_a[a], tris_a[b]):
                    n += 1
    else:
        for ta_ in tris_a:
            for tb_ in tris_b:
                if _pair_hits(ta_, tb_):
                    n += 1
    return n


def _pair_hits(ta, tb):
    import mathutils.geometry as geom
    for a in ta:
        for b in tb:
            if geom.intersect_tri_tri_2d(*a, *b):
                return True
    return False


# ================================================================ tests ===
# --- Test 0: island detector ground truth (regression for the shatter bug)
def flood_fill_islands(ob):
    """Independent island partition: BFS over faces with explicit per-vertex
    UV corner matching (different code path from islands.detect_islands)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    faces = tuple(bm.faces)
    corners = {}
    for f in faces:
        m = {}
        for l in tuple(f.loops):
            u = l[uvl].uv
            m[l.vert.index] = (u.x, u.y)
        corners[f.index] = m
    # adjacency: face -> set of non-seam neighbour faces
    adj = {f.index: set() for f in faces}
    bm.edges.ensure_lookup_table()
    for e in tuple(bm.edges):
        fl = tuple(e.link_faces)
        if len(fl) != 2:
            continue
        m1, m2 = corners[fl[0].index], corners[fl[1].index]
        ok = True
        for v in e.verts:
            a = m1.get(v.index)
            b = m2.get(v.index)
            if (a is None or b is None
                    or abs(a[0] - b[0]) >= 1e-6 or abs(a[1] - b[1]) >= 1e-6):
                ok = False
                break
        if ok:
            adj[fl[0].index].add(fl[1].index)
            adj[fl[1].index].add(fl[0].index)
    seen = set()
    parts = []
    for f in faces:
        if f.index in seen:
            continue
        stack = [f.index]
        part = set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            part.add(x)
            stack.extend(adj[x] - seen)
        parts.append(frozenset(part))
    bm.free()
    return sorted(parts, key=len, reverse=True)


def addon_island_partition(ob):
    from native_udim_packer import packer
    was_edit = bpy.context.mode == 'EDIT_MESH'
    if not was_edit:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    isl = packer.detect_islands(bm, uvl)
    parts = sorted((frozenset(i.face_indices) for i in isl), key=len, reverse=True)
    bm.free()
    if not was_edit:
        bpy.ops.object.mode_set(mode='OBJECT')
    return parts


clean_scene()
bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object
gt = flood_fill_islands(mon)
det = addon_island_partition(mon)
check("T0 monkey: independent flood fill finds 5 real islands", len(gt) == 5,
      f"islands={len(gt)} faces/island={[len(p) for p in gt]}")
check("T0 monkey: detect_islands matches ground-truth partition exactly",
      det == gt,
      f"detect={len(det)} vs truth={len(gt)} "
      f"faces/detect={[len(p) for p in det][:8]}")
check("T0 monkey: islands are multi-face (no per-face shattering)",
      len(det) > 1 and max(len(p) for p in det) > 1,
      f"max faces/island={max(len(p) for p in det) if det else 0}")

# --- Test 1: 2x2 grid, normalize OFF, rotate ON --------------------------
clean_scene()
ob = make_test_object("t1")
r = run_pack(ob, 2, 2, normalize=False, rotate=True)
check("T1 operator FINISHED", r == {'FINISHED'}, str(r))
ok, res = audit(ob, 2, 2)
tiles_used = sorted({p["tile"] for p in res["per_island"]})
check("T1 all islands inside tiles (2x2)", ok,
      f"islands={res['islands']} tiles={tiles_used}")
check("T1 uses <=4 tiles", len(tiles_used) <= 4)

# --- Test 2: 1x1 grid ------------------------------------------------------
clean_scene()
ob = make_test_object("t2")
r = run_pack(ob, 1, 1, normalize=False, rotate=True)
ok, res = audit(ob, 1, 1)
check("T2 all islands inside [0,1]^2", ok and r == {'FINISHED'},
      f"islands={res['islands']}")

# --- Test 3: 4x1 grid ------------------------------------------------------
clean_scene()
ob = make_test_object("t3")
r = run_pack(ob, 4, 1, normalize=False, rotate=True)
ok, res = audit(ob, 4, 1)
tiles_used = sorted({p["tile"] for p in res["per_island"]})
check("T3 all islands inside tiles (4x1)", ok and r == {'FINISHED'},
      f"islands={res['islands']} tiles={tiles_used}")

# --- Test 4: normalize ON vs OFF density ----------------------------------
def density_spread(ob):
    stats = uv_stats(ob)
    ratios = [s["uv_area"] / s["world_area"] for s in stats
              if s["world_area"] > 1e-9 and s["uv_area"] > 1e-9]
    if not ratios:
        return None
    lo, hi = min(ratios), max(ratios)
    return hi / lo

clean_scene()
ob_off = make_test_object("t4off")
run_pack(ob_off, 4, 1, normalize=False, rotate=True)
spread_off = density_spread(ob_off)

clean_scene()
ob_on = make_test_object("t4on")
run_pack(ob_on, 4, 1, normalize=True, rotate=True)
spread_on = density_spread(ob_on)
check("T4 normalize tightens texel density",
      spread_on is not None and spread_off is not None and spread_on < spread_off,
      f"spread on={spread_on:.2f} off={spread_off:.2f}")

# --- Test 5: multi-object --------------------------------------------------
clean_scene()
o1 = make_test_object("t5a")
bpy.ops.mesh.primitive_cube_add(size=1.5, location=(0, 10, 0))
o2 = bpy.context.active_object
o2.name = "t5b"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
o1.select_set(True); o2.select_set(True)
bpy.context.view_layer.objects.active = o1
set_grid(2, 2, False, True, 0.01)
r = bpy.ops.native_udim.pack_to_grid()
ok1, res1 = audit(o1, 2, 2)
ok2, res2 = audit(o2, 2, 2)
check("T5 both objects packed into grid", r == {'FINISHED'} and ok1 and ok2,
      f"a:{res1['islands']} b:{res2['islands']}")
# cross-object overlap: islands of the two objects share one texture set and
# must never intersect, even inside tiles both objects use
t1 = shrunken_island_tris(o1)
t2 = shrunken_island_tris(o2)
xov = count_overlaps(t1, t2, self_pairs=False)
check("T5 no cross-object UV overlap", xov == 0, f"cross pairs={xov}")

# --- Test 6: single-tile engine pack (dense, no overlaps) ------------------
clean_scene()
ob = make_test_object("t6")
from native_udim_packer import packer as P
r6 = P.pack_objects([ob], 1, 1, False, True, 0.01)
ok, res = audit(ob, 1, 1)
check("T6 single-tile engine pack fits [0,1]^2",
      "error" not in r6 and ok, f"islands={res['islands']}")
# overlap check via AABBs
stats = uv_stats(ob)
boxes = [(s["bounds"][0], s["bounds"][1], s["bounds"][2], s["bounds"][3]) for s in stats]
overlap = False
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        a, b = boxes[i], boxes[j]
        if (a[0] < b[2] - 1e-6 and b[0] < a[2] - 1e-6 and
                a[1] < b[3] - 1e-6 and b[1] < a[3] - 1e-6):
            overlap = True
check("T6 no AABB overlaps in single-tile pack", not overlap, f"n={len(boxes)}")

# --- Test 6b: over-capacity shrinks uniformly, still fits ------------------
clean_scene()
ob = make_test_object("t6b")
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
uvl = bm.loops.layers.uv.active
for f in tuple(bm.faces):          # blow up UVs 3x -> total area >> one tile
    for l in tuple(f.loops):
        l[uvl].uv.x *= 3.0
        l[uvl].uv.y *= 3.0
bmesh.update_edit_mesh(ob.data)
bm.free()
bpy.ops.object.mode_set(mode='OBJECT')
r6b = P.pack_objects([ob], 1, 1, False, True, 0.01)
ok, res = audit(ob, 1, 1)
check("T6b over-capacity pack fits [0,1]^2 (uniform shrink)",
      "error" not in r6b and ok, f"islands={res['islands']} scale={r6b.get('global_scale')}")

# --- Test 7: rotation off vs on still valid --------------------------------
clean_scene()
ob = make_test_object("t7")
r = run_pack(ob, 2, 2, normalize=False, rotate=False)
ok, res = audit(ob, 2, 2)
check("T7 rotate=off packs validly", ok and r == {'FINISHED'},
      f"islands={res['islands']}")

# --- Test 8: 3x2 grid, two-cube mesh (dense multi-tile pack) ---------------
clean_scene()
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
r = run_pack(ob, 3, 2, normalize=True, rotate=True, margin=0.008)
ok, res = audit(ob, 3, 2)
tiles_used = sorted({p["tile"] for p in res["per_island"] if p["tile"]})
check("T8 3x2 pack valid (containment + no overlap)", ok and r == {'FINISHED'},
      f"islands={res['islands']} tiles={tiles_used}")
check("T8 all 6 tiles used", len(tiles_used) == 6, f"tiles={tiles_used}")

# --- Test 9: multi-object pack starting from (multi-)edit mode -------------
# Replicates the user workflow: select several objects, Tab into multi-edit,
# click "Pack to UDIM Grid" in the sidebar.  Both objects must be packed into
# the shared grid and the user must be returned to edit mode afterwards.
clean_scene()
o1 = make_test_object("t9a")
bpy.ops.mesh.primitive_cube_add(size=1.5, location=(0, 10, 0))
o2 = bpy.context.active_object
o2.name = "t9b"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
o1.select_set(True); o2.select_set(True)
bpy.context.view_layer.objects.active = o1
bpy.ops.object.mode_set(mode='EDIT')          # multi-object edit mode (Tab)
check("T9 in multi-edit with 2 objects",
      bpy.context.mode == 'EDIT_MESH' and len(bpy.context.selected_objects) == 2,
      f"mode={bpy.context.mode} sel={[o.name for o in bpy.context.selected_objects]}")

set_grid(2, 2, False, True, 0.01)
r = bpy.ops.native_udim.pack_to_grid()
check("T9 operator FINISHED from multi-edit", r == {'FINISHED'}, str(r))
mode_after = bpy.context.mode
sel_after = {o.name for o in bpy.context.selected_objects}
active_after = bpy.context.active_object

ok1, res1 = audit(o1, 2, 2)
ok2, res2 = audit(o2, 2, 2)
t1 = shrunken_island_tris(o1)
t2 = shrunken_island_tris(o2)
xov = count_overlaps(t1, t2, self_pairs=False)
check("T9 both objects packed from edit mode", ok1 and ok2 and xov == 0,
      f"a:{res1['islands']} b:{res2['islands']} cross={xov}")
all_tiles = sorted({p["tile"] for p in res1["per_island"] if p["tile"]} |
                   {p["tile"] for p in res2["per_island"] if p["tile"]})
check("T9 islands span multiple UDIMs", len(all_tiles) >= 3, f"tiles={all_tiles}")
check("T9 returned to edit mode with selection restored",
      mode_after == 'EDIT_MESH' and sel_after == {"t9a", "t9b"}
      and active_after is not None and active_after.name == "t9a",
      f"mode={mode_after} sel={sorted(sel_after)} "
      f"active={active_after.name if active_after else None}")

# --- Test 10: built-in monkey mesh (the user's repro) ---------------------
# The default Suzanne UV layout has 5 real multi-face islands.  Packing must
# keep every island intact (no shattering/cutting), stay inside the grid, and
# use the standard UDIM numbering (X stride 1, Y stride 10).
from native_udim_packer import packer as _P

check("T10 udim_number spec: X row", _P.udim_number(0, 0) == 1001
      and _P.udim_number(2, 0) == 1003 and _P.udim_number(9, 0) == 1010,
      f"{_P.udim_number(0, 0)},{_P.udim_number(2, 0)},{_P.udim_number(9, 0)}")
check("T10 udim_number spec: Y rows", _P.udim_number(0, 1) == 1011
      and _P.udim_number(0, 2) == 1021,
      f"{_P.udim_number(0, 1)},{_P.udim_number(0, 2)}")

clean_scene()
bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object
pre_parts = addon_island_partition(mon)
check("T10 monkey pre-pack: 5 intact islands", len(pre_parts) == 5,
      f"islands={len(pre_parts)} faces={[len(p) for p in pre_parts]}")

r = run_pack(mon, 3, 1, normalize=False, rotate=True)
check("T10 operator FINISHED (3x1)", r == {'FINISHED'}, str(r))
ok, res = audit(mon, 3, 1)
post_parts = addon_island_partition(mon)
check("T10 island count preserved after pack (no cutting/shattering)",
      len(post_parts) == len(pre_parts) == 5,
      f"pre={len(pre_parts)} post={len(post_parts)} "
      f"faces/post={[len(p) for p in post_parts]}")
check("T10 all islands inside their tiles (3x1)", ok,
      f"islands={res['islands']}")
udims_x = sorted({p["udim"] for p in res["per_island"] if p["udim"]})
check("T10 X=3 packs into exactly UDIM 1001/1002/1003",
      set(udims_x) == {1001, 1002, 1003}, f"udims={udims_x}")

clean_scene()
bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object
r = run_pack(mon, 1, 3, normalize=False, rotate=True)
check("T10 operator FINISHED (1x3)", r == {'FINISHED'}, str(r))
ok, res = audit(mon, 1, 3)
udims_y = sorted({p["udim"] for p in res["per_island"] if p["udim"]})
check("T10 Y=3 packs into exactly UDIM 1001/1011/1021",
      ok and set(udims_y) == {1001, 1011, 1021}, f"udims={udims_y}")

# --- Test 12: pack must NOT break pre-existing scale averaging -------------
# v2 applies exactly one uniform factor to every island (normalize off), so
# the spread of per-island texel densities must be unchanged by packing.
clean_scene()
ob = make_test_object("t12")
spread_before = density_spread(ob)
run_pack(ob, 2, 2, normalize=False, rotate=True)
spread_after = density_spread(ob)
check("T12 pack preserves relative texel densities (normalize off)",
      spread_before is not None and spread_after is not None
      and abs(spread_after / spread_before - 1.0) < 1e-6,
      f"before={spread_before:.6f} after={spread_after:.6f}")

# --- Test 13: normalize = uniform texel density, cross-object --------------
clean_scene()
ob = make_test_object("t13")
run_pack(ob, 2, 2, normalize=True, rotate=True)
stats = uv_stats(ob)
dens = [s["uv_area"] / s["world_area"] for s in stats
        if s["world_area"] > 1e-9 and s["uv_area"] > 1e-9]
spread_on = max(dens) / min(dens)
check("T13 normalize gives uniform texel density (single object)",
      spread_on < 1.001, f"spread={spread_on:.6f}")

clean_scene()
o_a = make_test_object("t13a")
bpy.ops.mesh.primitive_cube_add(size=1.5, location=(0, 10, 0))
o_b = bpy.context.active_object
o_b.name = "t13b"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
set_grid(2, 2, True, True, 0.01)
bpy.context.window_manager.native_udim.use_selected = True
bpy.ops.object.select_all(action='DESELECT')
o_a.select_set(True); o_b.select_set(True)
bpy.context.view_layer.objects.active = o_a
r13 = bpy.ops.native_udim.pack_to_grid()
da = [s["uv_area"] / s["world_area"] for s in uv_stats(o_a)
      if s["world_area"] > 1e-9]
db = [s["uv_area"] / s["world_area"] for s in uv_stats(o_b)
      if s["world_area"] > 1e-9]
all_d = da + db
spread_xo = max(all_d) / min(all_d)
check("T13 normalize equalizes density ACROSS objects",
      r13 == {'FINISHED'} and spread_xo < 1.001,
      f"cross-object spread={spread_xo:.6f} (a:{len(da)} b:{len(db)})")

# --- Test 14: used tiles are filled densely --------------------------------
clean_scene()
ob = make_test_object("t14")
r14 = P.pack_objects([ob], 2, 2, False, True, 0.01)
ok, res = audit(ob, 2, 2)
# per-tile fill from island bounding boxes (interior = (1-2m)^2)
tile_area = {}
for p in res["per_island"]:
    if p["tile"] is None:
        continue
    w = p["bounds"][2] - p["bounds"][0]
    h = p["bounds"][3] - p["bounds"][1]
    tile_area[p["tile"]] = tile_area.get(p["tile"], 0.0) + w * h
interior = (1 - 2 * 0.01) ** 2
fills = {t: v / interior for t, v in tile_area.items()}
lo, hi = min(fills.values()), max(fills.values())
check("T14 used tiles filled densely and balanced",
      "error" not in r14 and ok and len(fills) >= 2
      and lo >= 0.40 and hi / lo <= 1.5,
      f"fills={ {t: round(v, 3) for t, v in fills.items()} }")

# --- Test 11: panel draw() headless crash guard ----------------------------
# Blender 5.x raises AttributeError when draw() assigns attributes to the
# object returned by layout.operator() (e.g. op.text = ...), aborting the
# whole panel.  This mock mimics that behaviour so any such regression is
# caught without a live UI.
class _MockSettings:
    """Mimics context.window_manager.native_udim (persistent RNA)."""

    def __init__(self):
        object.__setattr__(self, "_vals", {
            "udim_x": 2, "udim_y": 2, "normalize_scale": False,
            "rotate_90": True, "margin": 0.01, "use_selected": True})

    def __getattr__(self, name):
        vals = object.__getattribute__(self, "_vals")
        if name in vals:
            return vals[name]
        raise AttributeError(f"settings has no attribute {name!r}")

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        if name not in self._vals:
            raise AttributeError(
                f"'_MockSettings' object has no attribute {name!r}")
        object.__getattribute__(self, "_vals")[name] = value


class _MockOpProxy:
    """Mimics the 5.x layout.operator() return value: a READ-ONLY snapshot.
    Any read or write raises AttributeError, exactly like the real binary -
    so if draw() ever touches an op proxy (old 4.x pattern), it fails here."""

    def __getattr__(self, name):
        raise AttributeError(
            f"5.x operator proxy is a read-only snapshot; no attribute {name!r}")

    def __setattr__(self, name, value):
        raise AttributeError(
            f"'_MockOpProxy' object has no attribute {name!r} "
            "(5.x operator proxies are read-only snapshots)")


class _MockLayoutElem:
    BINDINGS = []  # (proxy, prop_name) recorded by every prop() call

    def __getattr__(self, name):
        if name == "operator":
            return lambda idname, *a, **k: _MockOpProxy()
        if name == "prop":
            def prop(proxy, prop_name, *a, **k):
                getattr(proxy, prop_name)  # validates the property exists
                _MockLayoutElem.BINDINGS.append((proxy, prop_name))
                return _MockLayoutElem()
            return prop
        return _MockLayoutElem()

    def __call__(self, *a, **k):
        return _MockLayoutElem()


class _MockWM:
    pass


class _MockCtx:
    pass


from native_udim_packer.ui import NATIVE_UDIM_PT_main


class _DrawHost:
    """Plain stand-in carrying .layout; draw() only reads self.layout.
    (Panel is an RNA struct and cannot be instantiated headlessly via
    __new__, so the unbound method call exercises the exact same body.)"""


_settings = _MockSettings()
_wm = _MockWM()
_wm.native_udim = _settings
_ctx = _MockCtx()
_ctx.window_manager = _wm

_host = _DrawHost()
_host.layout = _MockLayoutElem()
_MockLayoutElem.BINDINGS.clear()
try:
    NATIVE_UDIM_PT_main.draw(_host, _ctx)
    check("T11 panel draw() completes without exception (5.x-safe)", True)
except Exception as exc:  # noqa: BLE001 - report any draw-time failure
    check("T11 panel draw() completes without exception (5.x-safe)", False,
          f"{type(exc).__name__}: {exc}")

# The 5.x lesson encoded as an assertion: every widget must be bound to the
# persistent wm settings group - never to the read-only operator snapshot.
bound = _MockLayoutElem.BINDINGS
to_settings = all(p is _settings for p, _ in bound)
check("T11 widgets bind to wm settings (not the op proxy)",
      len(bound) >= 6 and to_settings,
      f"bindings={len(bound)} all_to_settings={to_settings}")

# ---------------------------------------------------------------- summary --
print()
fails = [r for r in RESULTS if r[0] == "FAIL"]
print(f"SUMMARY: {len(RESULTS) - len(fails)}/{len(RESULTS)} passed")
for st, name, detail in fails:
    print(f"  FAILED: {name} ({detail})")
sys.exit(1 if fails else 0)
