"""T15-style overlap audit (tessellate + barycentric pixel test) on the
QA scene after a 0.2.0 pack.  Decisive: if this reports 0 conflicts while
qa_measure's scanline raster reports ~96%, the scanline is buggy; if it
reports real conflicts, the engine wrote overlapping UVs."""
import math
import sys

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
ROT = "norot" not in sys.argv

import bpy
import bmesh
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception:
        pass
for _n in [n for n in list(sys.modules)
           if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[_n]
sys.path.insert(0, ADDON_PATH)
import native_udim_packer as A  # noqa: E402
from native_udim_packer import packer as P  # noqa: E402
A.register()

bpy.ops.wm.open_mainfile(filepath=SCENE)
targets = [o for o in bpy.context.scene.objects
           if o.type == 'MESH' and o.data.uv_layers
           and o.data.uv_layers.active]
res = P.pack_objects(targets, 3, 1, True, ROT, 0.0)
if "error" in res:
    print("D2 PACK ERROR", res["error"])
    sys.exit(1)
print(f"D2 rotate={ROT} S*={res.get('global_scale')!r} "
      f"tiles={res.get('tiles_used_total')}")

GRID = 512


def tri_covers(px, py, ax, ay, bx, by, cx, cy):
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def rasterize(tris):
    """Set of pixel indices covered by the triangles (pixel-center test)."""
    pix = set()
    for (a, b, c) in tris:
        xs = (a[0] * GRID, b[0] * GRID, c[0] * GRID)
        ys = (a[1] * GRID, b[1] * GRID, c[1] * GRID)
        x0 = max(int(math.floor(min(xs))), 0)
        x1 = min(int(math.ceil(max(xs))), GRID)
        y0 = max(int(math.floor(min(ys))), 0)
        y1 = min(int(math.ceil(max(ys))), GRID)
        for row in range(y0, y1):
            py = (row + 0.5) / GRID
            base = row * GRID
            for px in range(x0, x1):
                pxc = (px + 0.5) / GRID
                if tri_covers(pxc, py, a[0], a[1], b[0], b[1], c[0], c[1]):
                    pix.add(base + px)
    return pix


# collect islands per tile: list of (owner, faces, minuv, maxuv, pixelset)
by_tile = {}
for ob in targets:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for i in P.detect_islands(bm, uvl):
        tu = int(math.floor(i.min_uv[0] + 1e-6))
        tv = int(math.floor(i.min_uv[1] + 1e-6))
        tris = []
        for f in tuple(bm.faces):
            if f.index not in i.face_indices:
                continue
            pts = [Vector((l[uvl].uv.x - tu, l[uvl].uv.y - tv))
                   for l in tuple(f.loops)]
            # tessellate_polygon returns index triples into `pts`
            tris.extend(tuple(pts[k] for k in t)
                        for t in tessellate_polygon([pts]))
        by_tile.setdefault((tu, tv), []).append(
            (ob.name, len(i.face_indices), i.min_uv, i.max_uv,
             rasterize(tris)))
    bm.free()

total_conf = 0
pairs = {}
for tile, lst in sorted(by_tile.items()):
    grid = [-1] * (GRID * GRID)
    for ia, (name, nf, mnu, mxu, pix) in enumerate(lst):
        for p in pix:
            g = grid[p]
            if g != -1 and g != ia:
                total_conf += 1
                key = (tile, g, ia)
                pairs[key] = pairs.get(key, 0) + 1
            else:
                grid[p] = ia

print(f"D2 OVERLAP pairs={len(pairs)} pixels={total_conf} "
      f"area~{total_conf / (GRID * GRID):.6f}")
if pairs:
    worst = sorted(pairs.items(), key=lambda kv: -kv[1])[:8]
    for k, v in worst:
        tile, ga, ib = k
        A_ = lst = by_tile[tile]
        na, fa, mna, mxa, _ = A_[ga]
        nb, fb, mnb, mxb, _ = A_[ib]
        print(f"   worst {tile} {v}px: "
              f"[{na} isl#{ga} faces={fa} bbox=({mna[0]:.3f},{mna[1]:.3f},"
              f"{mxa[0]:.3f},{mxa[1]:.3f})] vs "
              f"[{nb} isl#{ib} faces={fb} bbox=({mnb[0]:.3f},{mnb[1]:.3f},"
              f"{mxb[0]:.3f},{mxb[1]:.3f})]")
print("D2DONE")
