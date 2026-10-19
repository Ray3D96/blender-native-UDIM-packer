"""Probe: what UV state does the QA blend hold right now? (packed vs original)"""
import sys
import bpy
import bmesh

SCENE = "/mnt/fusion/ai-projects/blender-uv-packer/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
targets = [o for o in bpy.context.scene.objects
           if o.type == 'MESH' and o.data.uv_layers
           and o.data.uv_layers.active]
minx = miny = 1e9
maxx = maxy = -1e9
n_isl = 0
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
for m in [n for n in list(sys.modules) if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[m]
from native_udim_packer import packer as P  # noqa: E402
for ob in targets:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    for i in P.detect_islands(bm, uvl):
        n_isl += 1
        minx = min(minx, i.min_uv[0]); miny = min(miny, i.min_uv[1])
        maxx = max(maxx, i.max_uv[0]); maxy = max(maxy, i.max_uv[1])
    bm.free()
print(f"PROBE targets={len(targets)} islands={n_isl}")
print(f"PROBE global UV bounds=({minx:.4f}, {miny:.4f}, {maxx:.4f}, {maxy:.4f})")
