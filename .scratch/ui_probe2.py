import bpy
names = [n for n in dir(bpy.types) if any(k in n.upper() for k in ("LAYOUT", "UI_", "_UI", "PANEL"))]
print("UI-ish types in 5.2:", sorted(names))
print()
# Panel type itself:
print("Panel base:", bpy.types.Panel.__mro__)
