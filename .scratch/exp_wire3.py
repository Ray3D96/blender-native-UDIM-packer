"""Probe which QA objects uv.pack_islands rejects, and why (Wire)."""
import math

import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print(f"PROBE objects={len(objs)}")


def uv_finite_stats(me):
    uvl = me.uv_layers.active.data
    bad = 0
    n = len(uvl)
    minx = miny = math.inf
    maxx = maxy = -math.inf
    for d in uvl:
        x, y = d.uv
        if not (math.isfinite(x) and math.isfinite(y)):
            bad += 1
        else:
            minx = min(minx, x); maxx = max(maxx, x)
            miny = min(miny, y); maxy = max(maxy, y)
    return n, bad, (round(minx, 3), round(miny, 3),
                    round(maxx, 3), round(maxy, 3))


def try_pack(ob):
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    r_mode = bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(ob.data)
    for f in tuple(bm.faces):
        f.select = True
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                margin=0.0, scale=False)
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    return r


for ob in objs:
    n, bad, bbox = uv_finite_stats(ob.data)
    r = try_pack(ob)
    flag = "" if r == {'FINISHED'} else "  <<< REJECTED"
    print(f"PROBE {ob.name:20s} polys={len(ob.data.polygons):5d} "
          f"uvloops={n:6d} nonfinite={bad:4d} bbox={bbox} -> {r}{flag}")

# control: fresh cube in the same scene
bpy.ops.mesh.primitive_cube_add(size=1)
cube = bpy.context.active_object
cube.name = "probe_cube"
r = try_pack(cube)
print(f"PROBE probe_cube (fresh)              -> {r}")
print("PROBEDONE")
