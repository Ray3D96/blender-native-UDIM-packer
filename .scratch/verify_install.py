"""Fresh-process install verification: run with --background on a binary that
should already have the addon installed + enabled in its saved prefs.

Checks (all printed, final line is the verdict):
  * addon present in saved preferences and auto-loaded at startup
  * version tuple / VERSION string
  * operator registered
  * detector ground truth: built-in monkey -> exactly 5 UV islands
"""
import sys

import bpy
import bmesh

mods = [n for n in sys.modules if n.split(".")[0] == "native_udim_packer"]
print("VERIFY modules at startup:", mods or "(none!)")
enabled = "native_udim_packer" in bpy.context.preferences.addons.keys()
print("VERIFY enabled-in-prefs:", enabled)

ok = enabled
try:
    import native_udim_packer as A
    print("VERIFY version:", tuple(A.bl_info["version"]), A.VERSION)
    ok = ok and tuple(A.bl_info["version"]) == (0, 3, 0) and A.VERSION == "0.3.0"
except Exception as exc:  # noqa: BLE001
    print("VERIFY import failed:", exc)
    A = None

has_op = hasattr(bpy.ops.native_udim, "pack_to_grid") if A else False
print("VERIFY operator registered:", has_op)
ok = ok and has_op

# The 0.1.4 fix: settings must be a live PropertyGroup on the window manager
# (widgets bound to it are interactive; the old op-proxy bindings were not).
try:
    s = bpy.context.window_manager.native_udim
    print("VERIFY wm settings:", type(s).__name__,
          f"x={s.udim_x} y={s.udim_y} rot={s.rotate_90} "
          f"margin={s.margin} sel={s.use_selected}")
    ok = ok and int(s.udim_x) == 2 and int(s.udim_y) == 2
except Exception as exc:  # noqa: BLE001
    print("VERIFY wm settings FAILED:", exc)
    ok = False

if A is not None:
    bpy.ops.mesh.primitive_monkey_add(size=1.0)
    mon = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mon.data)
    uvl = bm.loops.layers.uv.active
    isl = A.packer.detect_islands(bm, uvl)
    sizes = sorted((len(i.face_indices) for i in isl), reverse=True)
    bm.free()
    bpy.ops.object.mode_set(mode='OBJECT')
    print("VERIFY monkey islands:", len(isl), "sizes:", sizes[:6])
    ok = ok and len(isl) == 5

print("VERIFY RESULT:", "OK" if ok else "PROBLEM")
