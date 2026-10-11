# SPDX-License-Identifier: GPL-2.0-or-later
"""Debug T4: which islands lose texel density after normalize+pack?"""
import bpy
import bmesh

from native_udim_packer import packer as P


def make_test_object(name):
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
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def analyze(ob, label):
    was_edit = bpy.context.mode == 'EDIT_MESH'
    if not was_edit:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    islands = P.detect_islands(bm, uvl)
    rows = []
    for i in islands:
        minx, miny, maxx, maxy = P.island_bounds(bm, uvl, i.face_indices)
        cu, cv = (minx + maxx) / 2, (miny + maxy) / 2
        rows.append({
            "tile": (int(round(cu)), int(round(cv))),
            "uv_area": i.uv_area,
            "world_area": i.world_area,
            "ratio": i.uv_area / i.world_area if i.world_area > 1e-9 else 0.0,
        })
    bm.free()
    if not was_edit:
        bpy.ops.object.mode_set(mode='OBJECT')
    ratios = [r["ratio"] for r in rows if r["ratio"] > 1e-12]
    lo, hi = min(ratios), max(ratios)
    print(f"== {label}: spread={hi/lo:.3f} (min={lo:.5f} max={hi:.5f})")
    per_tile = {}
    for r in rows:
        per_tile.setdefault(r["tile"], []).append(r)
    for t in sorted(per_tile):
        rs = [r["ratio"] for r in per_tile[t]]
        print(f"   tile {t}: n={len(rs)} ratio min={min(rs):.5f} max={max(rs):.5f} "
              f"spread={max(rs)/min(rs):.3f}")
    worst = sorted(rows, key=lambda r: r["ratio"])[:4]
    for r in worst:
        print(f"   low: tile={r['tile']} uv={r['uv_area']:.5f} world={r['world_area']:.3f} "
              f"ratio={r['ratio']:.5f}")
    return rows


clean_scene()
ob = make_test_object("t4dbg")

# pre-pack: record post-normalization expected areas (what normalize_scales would give)
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
uvl = bm.loops.layers.uv.active
pre_islands = P.detect_islands(bm, uvl)
P.normalize_scales(pre_islands)
expected = {}   # world_area -> expected uv area after normalization
for i in pre_islands:
    s = i.norm_scale or 1.0
    expected[round(i.world_area, 6)] = (i.uv_area * s * s, s)
bm.free()
bpy.ops.object.mode_set(mode='OBJECT')

res = P.pack_objects([ob], 4, 1, True, True, 0.01)
print("fallback:", res["fallback_tiles"], res["fallback_reasons"])

rows = analyze(ob, "t4dbg normalize=ON")

# effective shrink per island: actual uv_area / expected post-norm uv_area
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
uvl = bm.loops.layers.uv.active
post_islands = P.detect_islands(bm, uvl)
print("effective shrink (actual_uv / expected_uv):")
for i in sorted(post_islands, key=lambda x: x.world_area, reverse=True)[:10]:
    exp_uv, s = expected.get(round(i.world_area, 6), (None, None))
    if exp_uv:
        print(f"   world={i.world_area:.3f} norm_s={s:.3f} exp_uv={exp_uv:.5f} "
              f"act_uv={i.uv_area:.5f} shrink={i.uv_area/exp_uv:.3f}")
bm.free()
bpy.ops.object.mode_set(mode='OBJECT')
