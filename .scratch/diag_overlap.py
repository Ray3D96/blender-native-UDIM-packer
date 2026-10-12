"""Diagnostic for 0.1.6 overlaps (user QA scene).

Usage:
    blender --background --python .scratch/diag_overlap.py            # rotate ON (user setting)
    blender --background --python .scratch/diag_overlap.py rot        # rotate OFF

Packs the QA scene with the user's settings (grid 3x1, normalize ON,
margin 0), then measures:
  1. EXACT post-pack overlap area between every pair of distinct islands
     in the same tile (Sutherland-Hodgman convex face-pair intersection;
     faces from smart_project are convex - non-convex ones are counted).
  2. Per-island outline audit: true face-union area vs island_outline()
     raw loops vs Douglas-Peucker simplified loops (same eps as engine),
     to see whether shape-bounds detection loses geometry.
"""
import sys
import math
import time

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
ROT = "rot" not in sys.argv  # default ON (user setting); "rot" arg -> OFF

import bpy
import bmesh

# ---- force-reload the addon from source (established pattern) --------
_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:  # noqa: BLE001 - partial states only warn
        print(f"[warn] old module unregister: {exc}")
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, ADDON_PATH)
import native_udim_packer as A  # noqa: E402
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer import islands as I  # noqa: E402
from native_udim_packer import layout as L  # noqa: E402
A.register()

bpy.ops.wm.open_mainfile(filepath=SCENE)
targets = [o for o in bpy.context.scene.objects
           if o.type == 'MESH' and o.data.uv_layers
           and o.data.uv_layers.active]
print(f"DIAG rotate_90={ROT} targets={[o.name for o in targets]}")

t0 = time.time()
res = P.pack_objects(targets, 3, 1, True, ROT, 0.0)
dt = time.time() - t0
if "error" in res:
    print("PACK ERROR", res["error"])
    sys.exit(1)
print(f"PACK TIME {dt:.2f}s  S*={res.get('global_scale')!r}")


# ------------------------------------------------- geometry helpers ----
def shoelace(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s * 0.5


def is_convex(pts):
    pos = neg = False
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        cx, cy = pts[(i + 2) % n]
        c = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if c > 1e-14:
            pos = True
        elif c < -1e-14:
            neg = True
    return not (pos and neg)


# ------------------------------------------------ raster overlap audit --
GRID = 512  # pixels per tile unit


def _row_intervals(edges, y):
    """X-intervals where horizontal line at y crosses polygon edges."""
    xs = []
    for (x1, y1, x2, y2) in edges:
        if (y1 <= y < y2) or (y2 <= y < y1):
            t = (y - y1) / (y2 - y1)
            xs.append(x1 + t * (x2 - x1))
    xs.sort()
    out = []
    for i in range(0, len(xs) - 1, 2):
        out.append((xs[i], xs[i + 1]))
    return out


def raster_overlap(records_by_tile):
    """Count pixels covered by two different islands (512^2 per tile).

    Returns (total_conflict_pixels, {(tile, ia, ib): pixel_count}).
    Faces of one island never overlap each other, so painting with
    even-odd intervals per face and conflict-checking at paint time is
    exact up to pixel resolution.
    """
    total = 0
    pair_counts = {}
    for tile, lst in records_by_tile.items():
        tu, tv = tile
        grid = [-1] * (GRID * GRID)
        # precompute edges in tile-local pixel coords
        isl_edges = []
        for r in lst:
            edges = []
            for pts in r[3]:
                n = len(pts)
                for i in range(n):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i + 1) % n]
                    edges.append(((x1 - tu) * GRID, (y1 - tv) * GRID,
                                  (x2 - tu) * GRID, (y2 - tv) * GRID))
            isl_edges.append(edges)
        for idx, (r, edges) in enumerate(zip(lst, isl_edges)):
            minx, miny, maxx, maxy = r[4]
            minx -= tu
            maxx -= tu
            miny -= tv
            maxy -= tv
            px0 = max(0, int(minx * GRID))
            px1 = min(GRID - 1, int(maxx * GRID))
            py0 = max(0, int(miny * GRID))
            py1 = min(GRID - 1, int(maxy * GRID))
            for py in range(py0, py1 + 1):
                y = (py + 0.5) / GRID
                for (xa, xb) in _row_intervals(edges, y):
                    ix0 = max(px0, int(xa))
                    ix1 = min(px1, int(xb))
                    if ix1 < ix0:
                        continue
                    base = py * GRID
                    for px in range(ix0, ix1 + 1):
                        p = base + px
                        prev = grid[p]
                        if prev == -1:
                            grid[p] = idx
                        elif prev != idx:
                            total += 1
                            key = (tile, prev, idx) if prev < idx \
                                else (tile, idx, prev)
                            pair_counts[key] = pair_counts.get(key, 0) + 1
    return total, pair_counts


# --------------------------------------------------- post-pack audit ---
records = []   # (obj, k, tile, faces, bbox, true_area)
nonconvex_faces = 0
outline_flags = []

for ob in targets:
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    isls = I.detect_islands(bm, uvl)
    for k, isl in enumerate(isls):
        faces_pts = []
        minx = miny = math.inf
        maxx = maxy = -math.inf
        true_area = 0.0
        for f in tuple(bm.faces):
            if f.index not in isl.face_indices:
                continue
            pts = [tuple(l[uvl].uv) for l in tuple(f.loops)]
            faces_pts.append(pts)
            if not is_convex(pts):
                nonconvex_faces += 1
            true_area += abs(shoelace(pts))
            for (x, y) in pts:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
        eps_t = 1e-4
        single = (maxx - minx < 1.0 - 2 * eps_t and maxy - miny < 1.0 - 2 * eps_t
                  and math.floor(maxx - eps_t) == math.floor(minx + eps_t))
        tile = (math.floor(minx + eps_t), math.floor(miny + eps_t)) if single else None

        # outline audit: raw loops vs DP-simplified (engine eps formula)
        outers, holes = I.island_outline(bm, uvl, isl.face_indices)
        raw_area = abs(sum(shoelace(lp) for lp in outers)
                       - sum(shoelace(lp) for lp in holes))
        w0 = isl.max_uv[0] - isl.min_uv[0]
        h0 = isl.max_uv[1] - isl.min_uv[1]
        eps_dp = max(1e-4, 0.002 * math.hypot(w0, h0))
        so = tuple(L._simplify_loop(lp, eps_dp) for lp in outers)
        sh = tuple(L._simplify_loop(lp, eps_dp) for lp in holes)
        simp_area = abs(sum(shoelace(lp) for lp in so)
                        - sum(shoelace(lp) for lp in sh))
        if true_area > 1e-9:
            dev_raw = (raw_area - true_area) / true_area
            dev_simp = (simp_area - true_area) / true_area
            if abs(dev_raw) > 0.001 or abs(dev_simp) > 0.001:
                outline_flags.append(
                    (ob.name, k, round(true_area, 6), round(raw_area, 6),
                     round(simp_area, 6), round(dev_raw * 100, 3),
                     round(dev_simp * 100, 3), len(isl.face_indices)))
        records.append((ob.name, k, tile, faces_pts,
                        (minx, miny, maxx, maxy), true_area))
    bm.free()

# raster overlap per tile (robust to non-convex faces)
by_tile = {}
for r in records:
    if r[2] is not None:
        by_tile.setdefault(r[2], []).append(r)

total_px, pair_counts = raster_overlap(by_tile)
px_area = 1.0 / (GRID * GRID)
total_ov = total_px * px_area

tile_fill = {}
for tile, lst in by_tile.items():
    tile_fill[tile] = (len(lst), sum(r[5] for r in lst))
used_area = sum(v[1] for v in tile_fill.values())

pairs_hit = []
for (tile, ia, ib), cnt in pair_counts.items():
    a = by_tile[tile][ia]
    b = by_tile[tile][ib]
    pairs_hit.append((cnt * px_area, tile, (a[0], a[1]), (b[0], b[1])))
pairs_hit.sort(reverse=True)

print(f"nonconvex_faces={nonconvex_faces}")
print(f"tiles={ {t: (n, round(f, 4)) for t, (n, f) in sorted(tile_fill.items())} }")
if used_area:
    print(f"OVERLAP raster pairs={len(pairs_hit)} total_px={total_px} "
          f"area~{total_ov:.6f} ({100.0 * total_ov / used_area:.3f}% of used area)")
else:
    print("OVERLAP no tiles")
for (area, tile, a, b) in pairs_hit[:12]:
    print(f"  worst: {a[0]}[{a[1]}] x {b[0]}[{b[1]}] tile={tile} area~{area:.6f}")

# outline audit: negative dev = collision shape SMALLER than content (danger)
neg_flags = [f for f in outline_flags if f[5] < 0 or f[6] < 0]
pos_flags = [f for f in outline_flags if f not in neg_flags]
neg_flags.sort(key=lambda t: min(t[5], t[6]))
print(f"OUTLINE-FLAGS n={len(outline_flags)} (dev>0.1%): "
      f"dangerous(neg)={len(neg_flags)} conservative(pos)={len(pos_flags)}")
for f in neg_flags[:12]:
    print(f"  NEG {f[0]}[{f[1]}] faces={f[7]} true={f[2]} raw={f[3]} "
          f"simpl={f[4]} dev_raw={f[5]}% dev_simp={f[6]}%")
for f in pos_flags[:6]:
    print(f"  POS {f[0]}[{f[1]}] faces={f[7]} true={f[2]} raw={f[3]} "
          f"simpl={f[4]} dev_raw={f[5]}% dev_simp={f[6]}%")

print("DIAG-SUMMARY rot=%s pack_time=%.2fs S*=%s overlap_pairs=%d "
      "overlap_area~%.6f outline_neg=%d outline_pos=%d"
      % ("ON" if ROT else "OFF", dt, res.get("global_scale"),
         len(pairs_hit), total_ov, len(neg_flags), len(pos_flags)))
