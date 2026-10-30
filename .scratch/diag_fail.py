# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproduce pack failures and probe uv.pack_islands scale/pin behaviour."""
import sys
import traceback

import bpy
import bmesh

ROOT = "/mnt/fusion/ai-projects/blender-uv-packer"
# Force-reload the addon from source.
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
from native_udim_packer import packer

print("=== pack_islands RNA ===", flush=True)
try:
    props = bpy.ops.uv.pack_islands.get_rna_type().properties
    for p in props:
        if p.identifier == "rna_type":
            continue
        enum = ""
        if p.type == "ENUM":
            enum = " " + ",".join(i.identifier for i in p.enum_items)
        print(f"  {p.identifier}: {p.type} default={getattr(p, 'default', None)}{enum}",
              flush=True)
except Exception as exc:
    print("  RNA dump failed:", exc, flush=True)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)


def smart(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def scale_largest_island(ob, factor):
    """Multiply the largest UV island's UVs about its center by ``factor``."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    try:
        uvl = bm.loops.layers.uv.active
        islands = A.islands.detect_islands(bm, uvl)
        islands.sort(key=lambda i: i.uv_area, reverse=True)
        big = islands[0]
        cx = (big.min_uv[0] + big.max_uv[0]) * 0.5
        cy = (big.min_uv[1] + big.max_uv[1]) * 0.5
        for f in tuple(bm.faces):
            if f.index not in big.face_indices:
                continue
            for l in tuple(f.loops):
                u = l[uvl].uv
                u.x = cx + (u.x - cx) * factor
                u.y = cy + (u.y - cy) * factor
        bm.to_mesh(me)
    finally:
        bm.free()


def case(name, build, **kw):
    print(f"\n=== CASE {name} {kw} ===", flush=True)
    clear()
    obs = build()
    for ob in obs:
        smart(ob)
    if kw.pop("uneven", False):
        scale_largest_island(obs[0], 6.0)
    try:
        res = packer.pack_objects(obs, **kw)
    except Exception:
        traceback.print_exc()
        return
    err = res.get("error")
    print("  error:", err, flush=True)
    if not err:
        print("  islands:", res.get("packed_islands"),
              "tiles:", res.get("tiles_used_total"),
              "scale:", round(res.get("global_scale", 0), 4),
              "stretch:", round(res.get("stretch_factor", 0), 4),
              flush=True)
        for ob in obs:
            v = packer.verify_packing(ob, kw.get("grid_x", 2), kw.get("grid_y", 2))
            print(f"  verify {ob.name}: inside={v['all_inside']} islands={v['islands']}",
                  flush=True)


def cube():
    bpy.ops.mesh.primitive_cube_add(size=2)
    return [bpy.context.active_object]


def monkey():
    bpy.ops.mesh.primitive_monkey_add(size=2)
    return [bpy.context.active_object]


def multi():
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(3, 0, 0))
    b = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.8, location=(-3, 0, 0))
    c = bpy.context.active_object
    return [a, b, c]


def grid():
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=2)
    ob = bpy.context.active_object
    smart(ob)
    # seam every face so each quad is its own island
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.seams_from_islands()
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    return [ob]


# Skip smart() inside case() for grid — it already unwrapped. Handle below.

print("\n##### PACK CASES #####", flush=True)
case("cube-2x2", cube, grid_x=2, grid_y=2, margin=0.005, rotate_90=True)
case("cube-1x1", cube, grid_x=1, grid_y=1, margin=0.005, rotate_90=True)
case("monkey-2x2", monkey, grid_x=2, grid_y=2, margin=0.005, rotate_90=True)
case("monkey-1x1", monkey, grid_x=1, grid_y=1, margin=0.005, rotate_90=True)
case("monkey-uneven-2x2", monkey, grid_x=2, grid_y=2, margin=0.005,
     rotate_90=True, uneven=True)
case("monkey-uneven-norm", monkey, grid_x=2, grid_y=2, margin=0.005,
     rotate_90=True, uneven=True, normalize_scale=True)
case("multi-2x2", multi, grid_x=2, grid_y=2, margin=0.005, rotate_90=True)
case("multi-1x1-norot", multi, grid_x=1, grid_y=1, margin=0.02, rotate_90=False)

print("\n##### GRID (per-face islands) #####", flush=True)
clear()
bpy.ops.mesh.primitive_grid_add(x_subdivisions=6, y_subdivisions=6, size=2)
gob = bpy.context.active_object
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001)
# mark all edges as seams then re-unwrap so faces split
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.mark_seam(clear=False)
bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")
try:
    res = packer.pack_objects([gob], grid_x=2, grid_y=2, margin=0.005, rotate_90=True)
    print("  grid error:", res.get("error"), "islands", res.get("packed_islands"),
          "scale", res.get("global_scale"), flush=True)
except Exception:
    traceback.print_exc()

print("\n##### SCALE=TRUE UNIFORMITY #####", flush=True)
clear()
bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))
p1 = bpy.context.active_object
bpy.ops.mesh.primitive_plane_add(size=2, location=(3, 0, 0))
p2 = bpy.context.active_object
for ob, sc in ((p1, 0.4), (p2, 0.15)):
    me = ob.data
    me.uv_layers.new(name="UVMap")
    for li in me.uv_layers.active.data:
        li.uv = (0.0, 0.0)
    # write a square of size sc at origin via bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    for f in tuple(bm.faces):
        for l in tuple(f.loops):
            u = l[uvl].uv
            # vert local xy is +/-1 for size-2 plane; map to [0,sc]
            u.x = (l.vert.co.x + 1.0) * 0.5 * sc
            u.y = (l.vert.co.y + 1.0) * 0.5 * sc
    bm.to_mesh(me)
    bm.free()

bpy.ops.object.select_all(action="DESELECT")
p1.select_set(True)
p2.select_set(True)
bpy.context.view_layer.objects.active = p1
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
ts = bpy.context.scene.tool_settings
ts.use_uv_select_sync = True
ts.uv_sticky_select_mode = "DISABLED"
bpy.ops.mesh.select_mode(type="FACE")
print("  before pack scale=True", flush=True)
r = bpy.ops.uv.pack_islands(rotate=False, margin=0.01, scale=True)
print("  result", r, flush=True)
bpy.ops.object.mode_set(mode="OBJECT")
for ob in (p1, p2):
    uvs = [(d.uv.x, d.uv.y) for d in ob.data.uv_layers.active.data]
    xs = [u[0] for u in uvs]
    ys = [u[1] for u in uvs]
    print(f"  {ob.name} bbox ({min(xs):.4f},{min(ys):.4f})-({max(xs):.4f},{max(ys):.4f})"
          f" size=({max(xs)-min(xs):.4f},{max(ys)-min(ys):.4f})", flush=True)

print("\nDONE", flush=True)
