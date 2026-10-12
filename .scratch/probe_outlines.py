# SPDX-License-Identifier: GPL-2.0-or-later
"""Outline + bbox-waste probe on the user's QA scene (Blender 5.2, background).

Answers three questions for the shape-aware packing design:
  1. How much area does the current bbox-based engine waste?
     (per island: polygon area vs bbox area; aggregate)
  2. Do islands have holes / concave outlines worth packing into?
     (outline loop counts, hole count, vertex counts)
  3. What does the CURRENT engine do on the user's exact settings
     (X=3, Y=1, normalize ON, margin 0.00)? Per-tile extent + aspect
     to explain the empty top band in their screenshot.
"""
import math
import sys
from collections import defaultdict

import bpy
import bmesh

# Force-reload from project source (Blender startup loads the installed copy).
_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] old module unregister: {exc}")
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
import native_udim_packer as A  # noqa: E402
A.register()
from native_udim_packer.islands import detect_islands, island_bounds  # noqa: E402

print(f"PROBE engine {A.VERSION}")


# --------------------------------------------------------------- outlines --
def _pip(pt, poly):
    """Ray-casting point-in-polygon (pure python)."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _shoelace(poly):
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s * 0.5


def island_outline(bm, uvl, face_indices):
    """Boundary loops of one island as lists of (x, y); holes included."""
    faces = [f for f in tuple(bm.faces) if f.index in face_indices]
    groups = defaultdict(list)
    for f in faces:
        ls = tuple(f.loops)
        n = len(ls)
        for i in range(n):
            a = ls[i].vert.index
            b = ls[(i + 1) % n].vert.index
            ua = (ls[i][uvl].uv.x, ls[i][uvl].uv.y)
            ub = (ls[(i + 1) % n][uvl].uv.x, ls[(i + 1) % n][uvl].uv.y)
            groups[frozenset((a, b))].append((f.index, i, a, b, ua, ub))
    boundary = []
    for insts in groups.values():
        if len(insts) == 1:
            boundary.append(insts[0])
            continue
        used = [False] * len(insts)
        for i in range(len(insts)):
            if used[i]:
                continue
            f1, _li, a1, b1, ua1, ub1 = insts[i]
            matched = False
            for j in range(i + 1, len(insts)):
                if used[j]:
                    continue
                _f2, _lj, a2, b2, ua2, ub2 = insts[j]
                if (a2, b2) == (b1, a1) and \
                   abs(ua2[0] - ub1[0]) < 1e-6 and abs(ua2[1] - ub1[1]) < 1e-6 and \
                   abs(ub2[0] - ua1[0]) < 1e-6 and abs(ub2[1] - ua1[1]) < 1e-6:
                    used[i] = used[j] = True
                    matched = True
                    break
            if not matched:
                boundary.append(insts[i])
                used[i] = True
    starts = defaultdict(list)
    for be in boundary:
        starts[be[2]].append(be)
    loops = []
    while any(starts.values()):
        startv = next(v for v, lst in starts.items() if lst)
        cur = starts[startv].pop()
        pts = [cur[4]]
        while True:
            opts = starts.get(cur[3], [])
            if not opts:
                break
            cur = opts.pop(0)
            pts.append(cur[4])
        if len(pts) >= 3:
            loops.append(pts)
    # classify outer vs hole by nesting (centroid inside another loop)
    info = []
    for lp in loops:
        area = _shoelace(lp)
        cx = sum(p[0] for p in lp) / len(lp)
        cy = sum(p[1] for p in lp) / len(lp)
        info.append((abs(area), (cx, cy), lp))
    info.sort(key=lambda t: -t[0])
    outers, holes = [], []
    placed_outers = []
    for _a, c, lp in info:
        is_hole = any(_pip(c, o) for o in placed_outers)
        if is_hole:
            holes.append(lp)
        else:
            outers.append(lp)
            placed_outers.append(lp)
    return outers, holes


def uv_area(bm, uvl, face_indices):
    total = 0.0
    for f in tuple(bm.faces):
        if f.index in face_indices:
            ls = tuple(f.loops)
            n = len(ls)
            a2 = 0.0
            for i in range(n):
                u1 = ls[i][uvl].uv
                u2 = ls[(i + 1) % n][uvl].uv
                a2 += u1.x * u2.y - u2.x * u1.y
            total += abs(a2) * 0.5
    return total


# ------------------------------------------------------------------- main --
path = "/mnt/fusion/ai-projects/blender-uv-packer/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=path)
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
targets = [o for o in meshes
           if o.data.uv_layers and o.data.uv_layers.active]
print(f"scene: {len(meshes)} objects, {len(targets)} with UV")

tot_poly = tot_bbox = 0.0
n_islands = 0
hole_islands = 0
max_verts = 0
ratios = []
print("\n--- per-island outline audit (pre-pack) ---")
for o in targets:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    uvl = bm.loops.layers.uv.active
    for isl in detect_islands(bm, uvl):
        minx, miny, maxx, maxy = island_bounds(bm, uvl, isl.face_indices)
        bbox_a = (maxx - minx) * (maxy - miny)
        poly_a = uv_area(bm, uvl, isl.face_indices)
        outers, holes = island_outline(bm, uvl, isl.face_indices)
        nverts = sum(len(lp) for lp in outers + holes)
        n_islands += 1
        tot_poly += poly_a
        tot_bbox += bbox_a
        max_verts = max(max_verts, nverts)
        if holes:
            hole_islands += 1
        r = poly_a / bbox_a if bbox_a > 1e-12 else 1.0
        ratios.append(r)
        if len(holes) or r < 0.75:
            print(f"  {o.name}: faces={len(isl.face_indices)} "
                  f"bbox={bbox_a:.4f} poly={poly_a:.4f} ratio={r:.3f} "
                  f"outers={len(outers)} holes={len(holes)} verts={nverts}")
    bm.free()

ratios.sort()
print(f"\nTOTAL islands={n_islands}  polygon_area={tot_poly:.4f} "
      f"bbox_area={tot_bbox:.4f}  bbox_waste={1 - tot_poly / tot_bbox:.3f}"
      f" (i.e. {tot_bbox - tot_poly:.4f} uv units^2 wasted by rectangles)")
print(f"ratio distribution: min={ratios[0]:.3f} p25={ratios[len(ratios)//4]:.3f} "
      f"median={ratios[len(ratios)//2]:.3f} max={ratios[-1]:.3f}")
print(f"islands with holes: {hole_islands}   max outline verts: {max_verts}")

# ------------------------------------------- current engine, user settings --
print("\n--- current engine on user settings: 3x1, normalize ON, margin 0.0 ---")
res = A.packer.pack_objects(targets, 3, 1, True, True, 0.0)
print("S* =", res.get("global_scale"), "tiles_used_total =",
      res.get("tiles_used_total"))
bm_all = {}
for o in targets:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    uvl = bm.loops.layers.uv.active
    for isl in detect_islands(bm, uvl):
        minx, miny, maxx, maxy = island_bounds(bm, uvl, isl.face_indices)
        t = (int(math.floor(minx + 1e-4)), int(math.floor(miny + 1e-4)))
        a = uv_area(bm, uvl, isl.face_indices)
        d = bm_all.setdefault(t, [0.0, math.inf, math.inf, -math.inf, -math.inf])
        d[0] += a
        d[1] = min(d[1], minx); d[2] = min(d[2], miny)
        d[3] = max(d[3], maxx); d[4] = max(d[4], maxy)
    bm.free()
for t in sorted(bm_all):
    a, mnx, mny, mxx, myy = bm_all[t]
    w = mxx - mnx
    h = myy - mny
    print(f"tile {t}: area_fill={a:.3f} content_bbox={w:.3f}x{h:.3f} "
          f"aspect(w/h)={w / max(h, 1e-9):.2f} "
          f"width_used={w:.3f} height_used={h:.3f}")
print("PROBE DONE")
