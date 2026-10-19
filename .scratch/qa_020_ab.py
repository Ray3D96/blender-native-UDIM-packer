"""QA-scene measurement for the native-packing engine (v4 + stretch).

Usage:
    blender --background --python .scratch/qa_measure.py            # rotate ON (user setting)
    blender --background --python .scratch/qa_measure.py rot        # rotate OFF

Packs the QA scene with the user's settings (grid 3x1, normalize ON,
margin 0), then measures pack time, S*, per-tile fills and the exact
overlap via a 512^2 raster audit.  Baseline (0.1.6, this machine):
rot ON  54.42s S*=1.005009 fills .4235/.4606/.4494 overlap 38 pairs ~0.71%
rot OFF 29.05s same fills, overlap 40 pairs ~1.07%
"""
import math
import sys
import time

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer/.scratch/qa_020_src"
SCENE = "/mnt/fusion/ai-projects/blender-uv-packer/QA_Test_Files/P_BLENDER_01.5.blend"
ROT = "rot" not in sys.argv  # default ON (user setting); "rot" arg -> OFF

import bpy
import bmesh
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

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
A.register()

# Optional experiment knob: "eta=0.85" in argv rebinds the layout solver to a
# single fixed FFD load factor (the shipped engine uses the full ladder).
ETA = None
for _a in sys.argv:
    if _a.startswith("eta="):
        ETA = float(_a[4:])
if ETA is not None:
    from native_udim_packer import layout as _L

    def _solve(items, gx, gy, m, oracle, **_kw):
        return _L.solve(items, gx, gy, m, oracle, etas=(ETA,))

    P._layout_solve = _solve

bpy.ops.wm.open_mainfile(filepath=SCENE)
targets = [o for o in bpy.context.scene.objects
           if o.type == 'MESH' and o.data.uv_layers
           and o.data.uv_layers.active]
print(f"QA rotate_90={ROT} version={A.VERSION} "
      f"objects={len(targets)} eta={ETA}")

t0 = time.time()
res = P.pack_objects(targets, 3, 1, True, ROT, 0.0)
dt = time.time() - t0
if "error" in res:
    print("QA PACK ERROR", res["error"])
    sys.exit(1)
print(f"QA PACK TIME {dt:.2f}s  S*={res.get('global_scale')!r} "
      f"K={res.get('stretch_factor')!r}")
print(f"QA tiles_used_total={res.get('tiles_used_total')} "
      f"shared_tiles={res.get('shared_tiles')}")

# ------------------------------------------------ per-tile fills ------
# The engine guarantees each island lies entirely inside one tile, so
# floor(min_uv) identifies its tile.  (The previous round(centroid)
# bucketing mis-assigned islands sitting in the upper/right half of a
# tile to the next tile.)
fills = {}
tile_bb = {}
n_islands = 0
crossing = 0
minx_all = miny_all = math.inf
maxx_all = maxy_all = -math.inf
for ob in targets:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for i in P.detect_islands(bm, uvl):
        n_islands += 1
        w = i.max_uv[0] - i.min_uv[0]
        h = i.max_uv[1] - i.min_uv[1]
        if w > 1.0 + 2e-4 or h > 1.0 + 2e-4:
            crossing += 1
        tu = int(math.floor(i.min_uv[0] + 1e-6))
        tv = int(math.floor(i.min_uv[1] + 1e-6))
        fills[(tu, tv)] = fills.get((tu, tv), 0.0) + w * h
        bb = tile_bb.setdefault(
            (tu, tv), [i.min_uv[0], i.min_uv[1], i.max_uv[0], i.max_uv[1]])
        if i.min_uv[0] < bb[0]:
            bb[0] = i.min_uv[0]
        if i.min_uv[1] < bb[1]:
            bb[1] = i.min_uv[1]
        if i.max_uv[0] > bb[2]:
            bb[2] = i.max_uv[0]
        if i.max_uv[1] > bb[3]:
            bb[3] = i.max_uv[1]
        minx_all = min(minx_all, i.min_uv[0])
        miny_all = min(miny_all, i.min_uv[1])
        maxx_all = max(maxx_all, i.max_uv[0])
        maxy_all = max(maxy_all, i.max_uv[1])
    bm.free()
print(f"QA islands={n_islands} "
      f"fills={ {t: round(v, 4) for t, v in sorted(fills.items())} }")
# Per-tile content bbox extents in tile-local space (what the stretch pass
# sees): extent >= 1.0 on any axis means that axis already maxes the tile.
# Widths/heights are translation-invariant, so global-bbox deltas equal the
# tile-local extents the stretch pass uses.
ext = {t: (round(bb[2] - bb[0], 4), round(bb[3] - bb[1], 4))
       for t, bb in tile_bb.items()}
print(f"QA tile_extents={ext}")
print(f"QA LAYOUT bounds=({minx_all:.4f}, {miny_all:.4f}, "
      f"{maxx_all:.4f}, {maxy_all:.4f}) crossing_islands={crossing}")

# ------------------------------------------------ raster overlap ------
# Tessellation + pixel-center barycentric audit - the same overlap
# definition as e2e T15 and the D2 diagnostic: exact for non-convex
# faces, and because it samples pixel centers, islands that merely touch
# (margin=0) do not count as overlapping.
GRID = 512


def _tri_covers(px, py, a, b, c):
    d1 = (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (py - b[1])
    d2 = (px - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (py - c[1])
    d3 = (px - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (py - a[1])
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def _rasterize(tris):
    pix = set()
    for t in tris:
        xs = (t[0][0] * GRID, t[1][0] * GRID, t[2][0] * GRID)
        ys = (t[0][1] * GRID, t[1][1] * GRID, t[2][1] * GRID)
        x0 = max(int(math.floor(min(xs))), 0)
        x1 = min(int(math.ceil(max(xs))), GRID)
        y0 = max(int(math.floor(min(ys))), 0)
        y1 = min(int(math.ceil(max(ys))), GRID)
        for row in range(y0, y1):
            py = (row + 0.5) / GRID
            base = row * GRID
            for px in range(x0, x1):
                if _tri_covers((px + 0.5) / GRID, py, t[0], t[1], t[2]):
                    pix.add(base + px)
    return pix


records_by_tile = {}
for ob in targets:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for idx, i in enumerate(P.detect_islands(bm, uvl)):
        tu = int(math.floor(i.min_uv[0] + 1e-6))
        tv = int(math.floor(i.min_uv[1] + 1e-6))
        tris = []
        for f in tuple(bm.faces):
            if f.index in i.face_indices:
                pts = [Vector((l[uvl].uv.x - tu, l[uvl].uv.y - tv))
                       for l in tuple(f.loops)]
                tris.extend(tuple(pts[k] for k in t)
                            for t in tessellate_polygon([pts]))
        records_by_tile.setdefault((tu, tv), []).append(
            (ob.name, idx, len(i.face_indices), _rasterize(tris)))
    bm.free()

total_conf = 0
pair_counts = {}
for tile, lst in records_by_tile.items():
    grid = [-1] * (GRID * GRID)
    for ia, (name, idx, nf, pix) in enumerate(lst):
        for p in pix:
            g = grid[p]
            if g != -1 and g != ia:
                total_conf += 1
                key = (tile, g, ia)
                pair_counts[key] = pair_counts.get(key, 0) + 1
            else:
                grid[p] = ia

conf_area = total_conf / (GRID * GRID)
print(f"QA OVERLAP pairs={len(pair_counts)} pixels={total_conf} "
      f"area~{conf_area:.6f} ({conf_area * 100:.3f}%)")
if pair_counts:
    worst = sorted(pair_counts.items(), key=lambda kv: -kv[1])[:5]
    for k, v in worst:
        print(f"   worst {k}: {v}px")
print("QA DONE")
