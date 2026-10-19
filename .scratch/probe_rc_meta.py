# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the RC zip and print the addon details (bl_info) fields."""
import sys

import bpy

ZPATH = "/mnt/fusion/ai-projects/blender-uv-packer/dist/native_udim_packer-0.3.0.zip"
r = bpy.ops.preferences.addon_install(filepath=ZPATH)
print("INSTALL:", r, flush=True)
bpy.ops.preferences.addon_enable(module="native_udim_packer")

# Purge any startup-loaded copy so we read the freshly installed files.
_old = sys.modules.get("native_udim_packer")
if _old is not None:
    try:
        _old.unregister()
    except Exception:
        pass
for n in [n for n in list(sys.modules)
          if n.split(".")[0] == "native_udim_packer"]:
    del sys.modules[n]
import native_udim_packer as A  # noqa: E402
A.register()

print("META name:", A.bl_info["name"], flush=True)
print("META author:", A.bl_info["author"], flush=True)
print("META version:", tuple(A.bl_info["version"]), flush=True)
print("META license:", A.bl_info.get("license"), flush=True)
print("META category:", A.bl_info["category"], flush=True)
print("META ok:", (A.bl_info["author"] == "Ray3D96, Qwen3.8 27B UD_6K_M, Deepseek Harness"
      and tuple(A.bl_info["version"]) == (0, 3, 0)
      and A.bl_info.get("license") == "GPL v3 or later"), flush=True)
