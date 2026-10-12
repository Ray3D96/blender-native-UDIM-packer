# SPDX-License-Identifier: GPL-2.0-or-later
"""Diagnose v2 layout decisions on T1 (normalize ON vs OFF), no writeback."""
import sys

import bpy
import bmesh

# Force the SOURCE code (not the installed addon loaded at startup).
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
import native_udim_packer as _A  # noqa: E402
_A.register()
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer.layout import Item, solve  # noqa: E402
print(f"loaded source addon version {_A.bl_info['version']}")


def make_t1(name):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    b = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8,
                                          location=(-6, 0, 0))
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


def clean():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        if m.users == 0:
            bpy.data.meshes.remove(m)


def diag(ob, normalize, gx=2, gy=2, margin=0.01):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    islands = P.detect_islands(bm, uvl)
    bm.free()
    if normalize:
        P.normalize_scales(islands)

    items, meta = [], []
    for n, i in enumerate(islands):
        s_norm = i.norm_scale if i.norm_scale is not None else 1.0
        w = (i.max_uv[0] - i.min_uv[0]) * s_norm
        h = (i.max_uv[1] - i.min_uv[1]) * s_norm
        items.append(Item(n, w, h))
        meta.append((w, h, s_norm, i.world_area, i.uv_area))

    S, placements = solve(items, gx, gy, margin, True)
    W = 1 - 2 * margin
    print(f"--- normalize={normalize} grid={gx}x{gy} ---")
    print(f"islands={len(islands)} S*={S:.4f}")
    # per-tile extents + area load
    from collections import defaultdict
    ext = defaultdict(float)
    area = defaultdict(float)
    for p in placements:
        ext[(p.tile_u, p.tile_v)] = max(ext[(p.tile_u, p.tile_v)],
                                       max(p.x0 + p.w, p.y0 + p.h))
        area[(p.tile_u, p.tile_v)] += p.w * p.h
    for t in sorted(ext):
        print(f"  tile{t}: extent={ext[t]:.3f} ref_area={area[t]:.3f} "
              f"final_fill~{area[t] * S * S / (W * W):.3f}")
    # top-5 reference items
    order = sorted(range(len(items)), key=lambda n: -(items[n].w * items[n].h))
    print("  top items (ref w x h, s_norm, world_area, uv_area):")
    for n in order[:6]:
        w, h, sn, wa, ua = meta[n]
        pl = next(p for p in placements if p.item == n)
        print(f"    #{n}: {w:.3f} x {h:.3f} (sn={sn:.3f}, "
              f"w3d={wa:.2f}, uv={ua:.4f}) -> tile{pl.tile_u},{pl.tile_v}")
    tot_uv = sum(m[4] for m in meta)
    tot_w = sum(m[3] for m in meta)
    print(f"  totals: uv={tot_uv:.3f} world={tot_w:.2f} ratio={tot_uv/tot_w:.5f}")
    bound = (gx * gy * W * W / sum(i.w * i.h for i in items)) ** 0.5
    print(f"  area-bound S={bound:.4f}  achieved/bound={S / bound:.3f}")


clean()
ob = make_t1("diag")
diag(ob, False)
diag(ob, True)
print("DIAG DONE")
