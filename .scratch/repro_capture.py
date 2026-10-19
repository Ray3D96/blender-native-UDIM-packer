# SPDX-License-Identifier: GPL-2.0-or-later
"""Repro for the 0.3.0 capture crash (e2e_030.log, T9 multi-edit).

Imports the addon from the source tree (not the installed zip) so fixes can
be iterated without rebuilding.  Prints full tracebacks with flush=True.
"""
import bmesh
import bpy
import sys
import traceback

_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] old unregister: {exc}", flush=True)
for n in [n for n in list(sys.modules)
          if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[n]
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
import native_udim_packer as A  # noqa: E402
A.register()
from native_udim_packer import packer as P  # noqa: E402

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()


def make(name):
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    a = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    b = bpy.context.active_object
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.8,
                                          location=(-6, 0, 0))
    c = bpy.context.active_object
    a.select_set(True)
    b.select_set(True)
    c.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob


a = make("rpa")
b = make("rpB")

print("=== case 1: _capture_edit_selection in multi-edit ===", flush=True)
bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.mode_set(mode='EDIT')
try:
    for ob in (a, b):
        print(f"  capturing {ob.name} mode={ob.mode}", flush=True)
        r = P._capture_edit_selection(ob)
        nf = len(r[0]) if r[0] is not None else None
        nl = len(r[1]) if r[1] is not None else None
        print(f"  -> faces={nf} loops={nl}", flush=True)
    print("case1 OK", flush=True)
except Exception:
    traceback.print_exc()
    print("case1 FAILED", flush=True)

print("=== case 2: selected_islands pack, single-object edit ===",
      flush=True)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(a.data)
uvl = bm.loops.layers.uv.active
isls = P.detect_islands(bm, uvl)
print(f"  islands={len(isls)}", flush=True)
want = set()
for isl in sorted(isls, key=lambda i: -i.uv_area)[:6]:
    want |= isl.face_indices
for f in tuple(bm.faces):
    f.uv_select = (f.index in want)
n_sel = sum(1 for f in tuple(bm.faces) if f.uv_select)
print(f"  uv_selected faces={n_sel}", flush=True)
bmesh.update_edit_mesh(a.data)
bm.free()
try:
    r = P.pack_objects([a], 2, 2, False, True, 0.01, selected_islands=True)
    print(f"case2 result: err={r.get('error')} "
          f"packed={r.get('packed_islands')} "
          f"untouched={r.get('untouched_islands')}", flush=True)
    # Verify the original uv_select was restored face-for-face.
    bm3 = bmesh.from_edit_mesh(a.data)
    bad = sum(1 for f in tuple(bm3.faces)
              if f.uv_select != (f.index in want))
    n_now = sum(1 for f in tuple(bm3.faces) if f.uv_select)
    bm3.free()
    print(f"case2 selection restored: bad={bad} now={n_now}/{n_sel}",
          flush=True)
except Exception:
    traceback.print_exc()
    print("case2 FAILED", flush=True)

print("REPRO-DONE", flush=True)
