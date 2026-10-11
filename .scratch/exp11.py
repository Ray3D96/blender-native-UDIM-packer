import bpy, os, zipfile, tempfile

# 1) ed.undo_push exists?
print("undo_push:", hasattr(bpy.ops.ed, "undo_push"))

# 2) classic addon install from disk (legacy bl_info addon)
tmp = tempfile.mkdtemp(prefix="addon_test_")
pkg = os.path.join(tmp, "test_addon_pkg")
os.makedirs(pkg)
with open(os.path.join(pkg, "__init__.py"), "w") as f:
    f.write('''bl_info = {
    "name": "Test Addon",
    "author": "x",
    "version": (0, 1),
    "blender": (4, 0, 0),
    "location": "Test",
    "description": "test",
    "category": "Generic",
}
def register(): pass
def unregister(): pass
''')
zpath = os.path.join(tmp, "test_addon_pkg.zip")
with zipfile.ZipFile(zpath, "w") as z:
    for root, _, files in os.walk(pkg):
        for fn in files:
            p = os.path.join(root, fn)
            z.write(p, os.path.relpath(p, tmp))
print("zip at:", zpath)
try:
    r = bpy.ops.preferences.addon_install(filepath=zpath)
    print("addon_install result:", r)
except Exception as e:
    print("addon_install FAILED:", type(e).__name__, e)
mods = [m.__name__ for m in bpy.context.preferences.addons.modules] if hasattr(bpy.context.preferences, "addons") else []
print("installed legacy addons:", mods)
