"""Install 0.1.5 into the user's Blender (run with its own binary)."""
import bpy

ZPATH = "/mnt/fusion/ai-projects/blender-uv-packer/dist/native_udim_packer-0.1.5.zip"
r = bpy.ops.preferences.addon_install(filepath=ZPATH)
print("INSTALL:", r)
bpy.ops.preferences.addon_enable(module="native_udim_packer")
enabled = "native_udim_packer" in bpy.context.preferences.addons.keys()
print("ENABLED:", enabled)
bpy.ops.wm.save_userpref()
print("PREFS SAVED")
