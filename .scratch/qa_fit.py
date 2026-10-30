# SPDX-License-Identifier: GPL-3.0-or-later
"""Pack the QA scene with the measured-fit path and report fill."""
import sys
import time
import traceback

import bpy
import bmesh

ROOT = "/mnt/fusion/ai-projects/blender-uv-packer"
_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception:
        pass
for n in [n for n in list(sys.modules) if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[n]
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import native_udim_packer as A
A.register()
from native_udim_packer import layout, packer

bpy.ops.wm.open_mainfile(filepath=ROOT + "/QA_Test_Files/P_BLENDER_01.5.blend")
obs = []
for ob in bpy.data.objects:
    if ob.type != "MESH" or ob.data is None or not ob.data.uv_layers:
        continue
    if len(ob.data.polygons) == 0:
        continue
    ob.hide_set(False)
    ob.hide_viewport = False
    obs.append(ob)
# One object per mesh datablock so linked duplicates are not packed twice.
seen = set()
unique = []
for ob in obs:
    if id(ob.data) in seen:
        continue
    seen.add(id(ob.data))
    unique.append(ob)
print(f"objects {len(obs)} unique-meshes {len(unique)} "
      f"polys {sum(len(o.data.polygons) for o in unique)}", flush=True)

def report(ob, gx, gy):
    v = packer.verify_packing(ob, gx, gy)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    try:
        uvl = bm.loops.layers.uv.active
        islands = packer.detect_islands(bm, uvl)
        polys = []
        tiles = {}
        for isl in islands:
            faces = []
            for f in tuple(bm.faces):
                if f.index in isl.face_indices:
                    faces.append([(l[uvl].uv.x, l[uvl].uv.y) for l in tuple(f.loops)])
            if not faces:
                continue
            polys.append(faces)
            bb = (isl.min_uv[0], isl.min_uv[1], isl.max_uv[0], isl.max_uv[1])
            key = (int(bb[0]) if bb[2] - bb[0] < 1 else -1,
                   int(bb[1]) if bb[3] - bb[1] < 1 else -1)
            rec = tiles.setdefault(key, [1e9, 1e9, -1e9, -1e9, 0])
            rec[0] = min(rec[0], bb[0])
            rec[1] = min(rec[1], bb[1])
            rec[2] = max(rec[2], bb[2])
            rec[3] = max(rec[3], bb[3])
            rec[4] += 1
        hit = layout.tile_islands_overlap(polys)
    finally:
        bm.free()
    return v["all_inside"], hit, tiles

def run(gx, gy):
    print(f"\n=== QA {gx}x{gy} ===", flush=True)
    t0 = time.perf_counter()
    try:
        res = packer.pack_objects(unique, grid_x=gx, grid_y=gy,
                                  normalize_scale=False, rotate_90=True,
                                  margin=0.005)
    except Exception:
        traceback.print_exc()
        return
    dt = time.perf_counter() - t0
    print(f"  {dt:.1f}s error={res.get('error')} "
          f"scale={res.get('global_scale')} stretch={res.get('stretch_factor')} "
          f"moves={res.get('rebalance_moves')} "
          f"islands={res.get('packed_islands')} "
          f"tiles={res.get('tiles_used_total')}", flush=True)
    if res.get("error"):
        return
    # Reload UVs from the meshes we packed. pack_objects leaves object mode.
    inside_all = True
    overlap_any = False
    combined = {}
    for ob in unique:
        inside, hit, tiles = report(ob, gx, gy)
        inside_all = inside_all and inside
        overlap_any = overlap_any or hit
        for key, rec in tiles.items():
            acc = combined.setdefault(key, [1e9, 1e9, -1e9, -1e9, 0])
            acc[0] = min(acc[0], rec[0])
            acc[1] = min(acc[1], rec[1])
            acc[2] = max(acc[2], rec[2])
            acc[3] = max(acc[3], rec[3])
            acc[4] += rec[4]
    print(f"  inside={inside_all} overlap={overlap_any}", flush=True)
    for key in sorted(combined):
        a = combined[key]
        w, h = a[2] - a[0], a[3] - a[1]
        print(f"  tile {key} islands={a[4]} size=({w:.3f},{h:.3f}) "
              f"origin=({a[0]:.3f},{a[1]:.3f})", flush=True)

run(4, 1)
print("\nDONE", flush=True)
