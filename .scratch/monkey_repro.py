"""Repro: pack a default monkey, measure island fragmentation before/after.

Diagnoses the user report: 'shatters the UVs and cuts them up in multiple
places' + 'only packs 1001 and 1002'.
"""
import bpy
import bmesh
import math

# ------------------------------------------------------------- clean scene --
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)

bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object
print("monkey uv layers:", [u.name for u in mon.data.uv_layers])

import native_udim_packer.islands as I
import native_udim_packer.packer as P


def snapshot(ob, tag):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    isl = I.detect_islands(bm, uvl)
    sizes = sorted((len(x.face_indices) for x in isl), reverse=True)
    minx = miny = math.inf
    maxx = maxy = -math.inf
    for x in isl:
        a, b, c, d = I.island_bounds(bm, uvl, x.face_indices)
        minx, miny = min(minx, a), min(miny, b)
        maxx, maxy = max(maxx, c), max(maxy, d)
    fid = {}
    for k, x in enumerate(isl):
        for f in x.face_indices:
            fid[f] = k
    print(f"[{tag}] islands={len(isl)} faces/island={sizes}")
    print(f"[{tag}] uv bounds=({minx:.4f},{miny:.4f})-({maxx:.4f},{maxy:.4f})")
    bm.free()
    return fid


def split_analysis(ob, before, after, tag):
    """Faces that were in the same island before but are separated now."""
    groups = {}
    for f, k in before.items():
        groups.setdefault(k, []).append(f)
    splits = 0
    detail = []
    for k, faces in groups.items():
        ids_now = {after.get(f) for f in faces}
        if len(ids_now) > 1:
            splits += 1
            detail.append((k, len(faces), len(ids_now)))
    print(f"[{tag}] original islands now split into multiple pieces: "
          f"{splits}" + (f" -> {detail[:8]}" if detail else ""))
    return splits


# -------------------------------------------------- scenario 1: their click --
print("\n=== SCENARIO 1: default monkey, pack with DEFAULTS (x=2,y=1) ===")
before = snapshot(mon, "before")
r = bpy.ops.native_udim.pack_to_grid()  # defaults: udim_x=2, udim_y=1
print("pack:", r)
after = snapshot(mon, "after-pack-1")
s1 = split_analysis(mon, before, after, "after-pack-1")

# containment audit (must be in edit mode per verify_packing contract? it uses
# from_edit_mesh -> enter edit first)
bpy.context.view_layer.objects.active = mon
if bpy.context.mode != 'EDIT_MESH':
    bpy.ops.object.mode_set(mode='EDIT')
audit = P.verify_packing(mon, 2, 1)
print("audit: islands=%d all_inside=%s" % (audit["islands"], audit["all_inside"]))
bad = [p for p in audit["per_island"] if not p["inside"]]
print("audit bad tiles:", [(p["tile"], p["bounds"]) for p in bad[:8]])
bpy.ops.object.mode_set(mode='OBJECT')

# ------------------------------------------------- scenario 2: click again --
print("\n=== SCENARIO 2: click Pack a SECOND time (same defaults) ===")
before2 = snapshot(mon, "before-pack-2")
r2 = bpy.ops.native_udim.pack_to_grid()
print("pack:", r2)
after2 = snapshot(mon, "after-pack-2")
s2 = split_analysis(mon, before2, after2, "after-pack-2")

# ------------------------------------------- scenario 3: their X=3 example --
print("\n=== SCENARIO 3: fresh monkey, pack with x=3, y=1 (user example) ===")
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon2 = bpy.context.active_object
before3 = snapshot(mon2, "before-3")
r3 = bpy.ops.native_udim.pack_to_grid(udim_x=3, udim_y=1)
print("pack:", r3)
after3 = snapshot(mon2, "after-pack-3")
s3 = split_analysis(mon2, before3, after3, "after-pack-3")

# ------------------------------------------- scenario 4: Y axis (user says
# Y=3 must give 1001, 1011, 1021) ------------------------------------------------
print("\n=== SCENARIO 4: fresh monkey, pack with x=1, y=3 ===")
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon3 = bpy.context.active_object
r4 = bpy.ops.native_udim.pack_to_grid(udim_x=1, udim_y=3)
print("pack:", r4)

print("\nREPRO DONE")
