"""Density + scale-consistency probe (Blender 5.2, background).

Quantifies the three user-reported symptoms of release 0.1.4:
  A. how dense is Blender's native single-tile pack (reference quality)?
  B. what fill ratio + relative-scale distortion does OUR 0.1.4 produce?
  C. same measurements on the user's QA scene P_BLENDER_01.5.blend.

Metrics (rotation-invariant, no island matching needed):
  * area ratio per island = uv_area_after / uv_area_before  (= s^2 for a
    uniform scale s).  A perfectly scale-consistent pack has all ratios
    equal -> distortion = max(ratio)/min(ratio) ~ 1.0.
  * fill ratio = total packed island area / (tiles used * 1.0).
"""
import math
import sys

import bpy
import bmesh

# Force-reload from the project source: Blender startup may have already
# loaded an installed copy into sys.modules, in which case a plain import
# would silently test the old build.
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


def uv_area(bm, uvl, face_indices):
    total = 0.0
    for f in tuple(bm.faces):
        if f.index in face_indices:
            loops = tuple(f.loops)
            n = len(loops)
            a2 = 0.0
            for i in range(n):
                u1 = loops[i][uvl].uv
                u2 = loops[(i + 1) % n][uvl].uv
                a2 += u1.x * u2.y - u2.x * u1.y
            total += abs(a2) * 0.5
    return total


def island_stats(ob):
    """Per-island (area, bbox diagonal) for an object's active UV map."""
    me = ob.data
    bm = bmesh.from_edit_mesh(me) if bpy.context.mode == 'EDIT_MESH' \
        else bmesh.new()
    if bpy.context.mode != 'EDIT_MESH':
        bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    out = []
    for isl in detect_islands(bm, uvl):
        minx, miny, maxx, maxy = island_bounds(bm, uvl, isl.face_indices)
        diag = math.hypot(maxx - minx, maxy - miny)
        out.append((uv_area(bm, uvl, isl.face_indices), diag))
    if bpy.context.mode != 'EDIT_MESH':
        bm.free()
    return out


def report(tag, before, after):
    ratios = sorted(a / b for (b, _), (a, _) in zip(before, after)
                    if b > 1e-12)
    if not ratios:
        print(f"{tag}: NO RATIO DATA")
        return None
    dist = max(ratios) / min(ratios)
    tot_after = sum(a for a, _ in after)
    xs = []
    print(f"{tag}: islands={len(after)} "
          f"area_ratio min={min(ratios):.4f} max={max(ratios):.4f} "
          f"distortion(x{dist:.2f}) total_area_after={tot_after:.4f}")
    return tot_after


def bounds_of(ob):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    minx = miny = math.inf
    maxx = maxy = -math.inf
    for f in tuple(bm.faces):
        for l in tuple(f.loops):
            u = l[uvl].uv
            minx, maxx = min(minx, u.x), max(maxx, u.x)
            miny, maxy = min(miny, u.y), max(maxy, u.y)
    bm.free()
    return (minx, miny, maxx, maxy)


def build_t1():
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
    c1 = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(6, 0, 0))
    c2 = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8,
                                          location=(-6, 0, 0))
    c3 = bpy.context.active_object
    bpy.ops.object.select_all(action='DESELECT')
    for o in (c1, c2, c3):
        o.select_set(True)
    bpy.context.view_layer.objects.active = c1
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = "t1"
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


def clean():
    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.mode != 'OBJECT' \
        else None
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


# ============================ PART A =======================================
print("=== PART A: native single-tile pack, T1 (18 islands) ===")
clean()
ob = build_t1()
before = island_stats(ob)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
res = bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=True,
                              scale=True, merge_overlap=False,
                              margin_method='FRACTION', margin=0.005)
print("native pack:", res)
bpy.ops.object.mode_set(mode='OBJECT')
after = island_stats(ob)
tot = report("A native-1tile", before, after)
bx = bounds_of(ob)
tiles_u = int(math.floor(bx[2] + 1e-4)) - int(math.floor(bx[0] + 1e-4)) + 1
tiles_v = int(math.floor(bx[3] + 1e-4)) - int(math.floor(bx[1] + 1e-4)) + 1
print(f"A bounds={tuple(round(v, 3) for v in bx)} span={tiles_u}x{tiles_v} "
      f"fill={tot / max(tiles_u * tiles_v, 1):.3f}")

# ============================ PART B =======================================
print(f"=== PART B: our {A.VERSION} pack_objects, T1, 2x2, normalize off ===")
clean()
ob = build_t1()
before = island_stats(ob)
res = A.packer.pack_objects([ob], 2, 2, False, True, 0.005)
print("our pack:", {k: v for k, v in res.items() if k != "objects"},
      res.get("objects", {}).get(ob.name))
after = island_stats(ob)
tot = report("B our-2x2", before, after)
# per-tile fill
bm = bmesh.new()
bm.from_mesh(ob.data)
uvl = bm.loops.layers.uv.active
tiles = {}
for isl in detect_islands(bm, uvl):
    minx, miny, _, _ = island_bounds(bm, uvl, isl.face_indices)
    t = (int(math.floor(minx + 1e-4)), int(math.floor(miny + 1e-4)))
    a = uv_area(bm, uvl, isl.face_indices)
    tiles[t] = tiles.get(t, 0.0) + a
bm.free()
for t in sorted(tiles):
    print(f"B tile {t}: fill={tiles[t]:.3f}")

# ============================ PART C =======================================
print("=== PART C: user QA scene P_BLENDER_01.5.blend ===")
path = "/mnt/fusion/ai-projects/blender-uv-packer/QA_Test_Files/P_BLENDER_01.5.blend"
try:
    bpy.ops.wm.open_mainfile(filepath=path)
except Exception as exc:  # noqa: BLE001
    print("C open FAILED:", exc)
    raise SystemExit(0)
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
print(f"C inventory: {len(bpy.data.objects)} objects, "
      f"{len(meshes)} meshes")
for o in meshes:
    uv = bool(o.data.uv_layers and o.data.uv_layers.active)
    print(f"  - {o.name}: faces={len(o.data.polygons)} uv={uv}")
targets = [o for o in meshes if o.data.uv_layers and o.data.uv_layers.active]
if targets:
    before = {}
    for o in targets:
        bpy.context.view_layer.objects.active = o
        before[o.name] = island_stats(o)
    res = A.packer.pack_objects(targets, 2, 2, False, True, 0.005)
    print("C our pack:", {k: v for k, v in res.items() if k != "objects"})
    for name, st in res.get("objects", {}).items():
        print(f"  C {name}: {st}")
    after = {}
    for o in targets:
        bpy.context.view_layer.objects.active = o
        after[o.name] = island_stats(o)
    tot_all = 0.0
    for name in before:
        t = report(f"C {name}", before[name], after[name])
        if t:
            tot_all += t
    # per-tile fill across the whole set
    tiles = {}
    for o in targets:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        uvl = bm.loops.layers.uv.active
        for isl in detect_islands(bm, uvl):
            minx, miny, _, _ = island_bounds(bm, uvl, isl.face_indices)
            tt = (int(math.floor(minx + 1e-4)), int(math.floor(miny + 1e-4)))
            tiles[tt] = tiles.get(tt, 0.0) + uv_area(bm, uvl, isl.face_indices)
        bm.free()
    for t in sorted(tiles):
        print(f"C tile {t}: fill={tiles[t]:.3f}")

print("PROBE DONE")
