"""Install the release zip into whichever Blender runs this script.

Usage:  <blender> --background --python .scratch/install_user_blender.py \
    [path/to/zip]   (default: dist/native_udim_packer-0.2.0.zip)
Run with the TARGET Blender's own binary so prefs land in its portable dir.
"""
import os
import sys

import bpy

HERE = "/mnt/fusion/ai-projects/blender-uv-packer"
ZPATH = sys.argv[-1] if len(sys.argv) > 1 and sys.argv[-1].endswith(".zip") \
    else os.path.join(HERE, "dist", "native_udim_packer-0.2.0.zip")
print("INSTALL ZIP:", ZPATH, flush=True)

r = bpy.ops.preferences.addon_install(filepath=ZPATH)
print("INSTALL:", r, flush=True)
bpy.ops.preferences.addon_enable(module="native_udim_packer")
enabled = "native_udim_packer" in bpy.context.preferences.addons.keys()
print("ENABLED:", enabled, flush=True)
try:
    import native_udim_packer as _nup
    print("VERSION:", _nup.bl_info["version"], flush=True)
except Exception as e:  # pragma: no cover - diagnostics only
    print("VERSION probe failed:", e, flush=True)
bpy.ops.wm.save_userpref()
print("PREFS SAVED", flush=True)
