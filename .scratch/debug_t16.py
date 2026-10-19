# SPDX-License-Identifier: GPL-2.0-or-later
"""Debug T16 failure: replicate the e2e T14 scene, hook
_stretch_final_layout to capture its EXACT measurement inputs (the
face->tile map from pre-pack detection + per-tile bboxes measured with
and without ensure_lookup_table), then compare against the post-stretch
truth.  Prints K and all three bbox sets.
"""
import sys
import math
import bpy
import bmesh

# --- force-reload the addon from source -------------------------------
for _m in [m for m in list(sys.modules)
           if m == "native_udim_packer" or m.startswith("native_udim_packer.")]:
    _old = sys.modules.pop(_m)
    try:
        _old.unregister()
    except Exception:
        pass
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
import native_udim_packer as A  # noqa: E402
from native_udim_packer import packer as P  # noqa: E402

print(f"DBG version={A.bl_info['version']}")


def make_test_object(name):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    b = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8,
                                          location=(-6, 0, 0))
    c = bpy.context.active_object
    bpy.ops.object.select_all(action='DESELECT')
    for o in (a, b, c):
        o.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def measure(state, assign_final, positions, use_lookup):
    """Same face->tile map as _stretch_final_layout; per-tile union bbox."""
    face_tile = {}
    for s in state:
        m = {}
        for i in s["islands"]:
            t = assign_final[i._item_index]
            for fi in i.face_indices:
                m[fi] = t
        face_tile[id(s["ob"])] = m
    bboxes = {}
    bad = 0
    for s in state:
        ob = s["ob"]
        fmap = face_tile[id(ob)]
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        try:
            if use_lookup:
                bm.faces.ensure_lookup_table()
            uvl = bm.loops.layers.uv.active
            for f in tuple(bm.faces):
                t = fmap.get(f.index)
                if t is None:
                    bad += 1
                    continue
                bb = bboxes.setdefault(
                    t, [math.inf, math.inf, -math.inf, -math.inf])
                for l in tuple(f.loops):
                    x, y = l[uvl].uv.x, l[uvl].uv.y
                    if x < bb[0]:
                        bb[0] = x
                    if x > bb[2]:
                        bb[2] = x
                    if y < bb[1]:
                        bb[1] = y
                    if y > bb[3]:
                        bb[3] = y
        finally:
            bm.free()
    local = {t: [bb[0] - positions[t][0], bb[1] - positions[t][1],
                 bb[2] - positions[t][0], bb[3] - positions[t][1]]
             for t, bb in bboxes.items()}
    return local, bad


def show(tag, local, lin):
    print(f"DBG {tag}:")
    for t in sorted(local):
        e = local[t]
        w, h = e[2] - e[0], e[3] - e[1]
        cx = (e[0] + e[2]) / 2
        cy = (e[1] + e[3]) / 2
        print(f"DBG   tile{t}: w={w:.6f} h={h:.6f} "
              f"frac=({w / lin:.5f},{h / lin:.5f}) center=({cx:.6f},{cy:.6f})")


# --- hook the stretch pass ---------------------------------------------
orig_stretch = P._stretch_final_layout
captured = {}


def hooked(state, assign_final, positions, margin):
    localA, badA = measure(state, assign_final, positions, use_lookup=False)
    localB, badB = measure(state, assign_final, positions, use_lookup=True)
    captured["no_lookup"] = (localA, badA)
    captured["with_lookup"] = (localB, badB)
    return orig_stretch(state, assign_final, positions, margin)


P._stretch_final_layout = hooked

# --- replicate T14 ------------------------------------------------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
ob = make_test_object("t16dbg")

m = 0.01
lin = 1 - 2 * m
r = P.pack_objects([ob], 2, 2, False, True, m)
print(f"DBG r: S*={r.get('global_scale')!r} K={r.get('stretch_factor')!r} "
      f"error={r.get('error')}")

from native_udim_packer.layout import tile_order  # noqa: E402
pos_list = tile_order(2, 2)


def remap(local):
    """Keys are internal tile indices; convert to (tu,tv)."""
    return {pos_list[t]: e for t, e in local.items()}


show("PRE-stretch no-lookup   (bad_index=%d)" % captured["no_lookup"][1],
     remap(captured["no_lookup"][0]), lin)
show("PRE-stretch with-lookup (bad_index=%d)" % captured["with_lookup"][1],
     remap(captured["with_lookup"][0]), lin)

# post-stretch truth: re-detect on written UVs, tile by island center
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bm = bmesh.new()
bm.from_mesh(ob.data)
uvl = bm.loops.layers.uv.active
isl = P.detect_islands(bm, uvl)
bm.faces.ensure_lookup_table()
truth = {}
for i in isl:
    tu = int(round((i.min_uv[0] + i.max_uv[0]) / 2))
    tv = int(round((i.min_uv[1] + i.max_uv[1]) / 2))
    bb = truth.setdefault((tu, tv), [math.inf, math.inf, -math.inf, -math.inf])
    for fi in i.face_indices:
        f = bm.faces[fi] if fi < len(bm.faces) else None
        if f is None:
            continue
        for l in tuple(f.loops):
            x, y = l[uvl].uv.x, l[uvl].uv.y
            bb[0] = min(bb[0], x - tu)
            bb[1] = min(bb[1], y - tv)
            bb[2] = max(bb[2], x - tu)
            bb[3] = max(bb[3], y - tv)
bm.free()
show("POST-stretch truth", truth, lin)
print("DBG DONE")
