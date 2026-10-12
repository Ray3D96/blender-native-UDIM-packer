"""Test the zero-area-face hypothesis for Wire's pack_islands CANCELLED."""
import math

import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

ob = bpy.data.objects["Wire"]
me = ob.data


def face_uv_area(me):
    uvl = me.uv_layers.active.data
    out = []
    for p in me.polygons:
        pts = [uvl[p.loop_start + j].uv for j in range(p.loop_total)]
        s = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            s += x1 * y2 - x2 * y1
        out.append(abs(s) * 0.5)
    return out


areas = face_uv_area(me)
n_zero = sum(1 for a in areas if a < 1e-12)
n_tiny = sum(1 for a in areas if a < 1e-9)
print(f"W4 face uv areas: n={len(areas)} zero(<1e-12)={n_zero} "
      f"tiny(<1e-9)={n_tiny} min={min(areas):.3e} max={max(areas):.3e}")

zero_idxs = [i for i, a in enumerate(areas) if a < 1e-12]
print(f"W4 zero-area face indices (first 15): {zero_idxs[:15]}")


def try_pack_face_set(idxs, tag):
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(me)
    bm.faces.ensure_lookup_table()
    for f in tuple(bm.faces):
        f.select = (f.index in idxs)
    bmesh.update_edit_mesh(me)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    print(f"W4 {tag}: n={len(idxs)} -> {r}")
    return r


# 1: the first zero-area face alone
if zero_idxs:
    try_pack_face_set({zero_idxs[0]}, "one zero-area face")
# 2: a non-zero face alone
nz = [i for i, a in enumerate(areas) if a >= 1e-9]
try_pack_face_set({nz[0]}, "one normal face")
# 3: all NON-degenerate faces
try_pack_face_set(set(nz), "all non-degenerate faces")
# 4: all faces except zero ones, plus ONE zero face
if zero_idxs:
    try_pack_face_set(set(nz) | {zero_idxs[0]}, "non-degenerate + 1 zero")
print("W4DONE")
