"""Introspect the 5.2 UI RNA: what does layout.operator()/prop() look like now?"""
import bpy

print("=== UI_LAYOUT methods ===")
for p in bpy.types.UI_LAYOUT.bl_rna.properties:
    print("  prop:", p.identifier, p.type)
for m in ("operator", "prop", "prop_int", "prop_float", "template_IDproperties"):
    attr = getattr(bpy.types.UI_LAYOUT, m, None)
    if attr is not None and hasattr(attr, "function") or (attr is not None and "function" in str(type(attr))):
        pass
    print(f"  method {m}:", type(getattr(bpy.types.UI_LAYOUT, m, None)))

print("=== UI_LAYOUT.operator function signature ===")
f = bpy.types.UI_LAYOUT.bl_rna.functions.get("operator")
if f:
    for p in f.parameters:
        print("   param:", p.identifier, p.type, "default=", getattr(p, "default_value", None))

print("=== UI_LAYOUT.prop function signature ===")
f = bpy.types.UI_LAYOUT.bl_rna.functions.get("prop")
if f:
    for p in f.parameters:
        print("   param:", p.identifier, p.type)

print("=== BPyOpFunction (operator proxy) RNA ===")
# We cannot create a layout headlessly; inspect the type via an op call instead.
import bmesh
bpy.ops.mesh.primitive_cube_add()
ob = bpy.context.active_object
opfunc = bpy.ops.object.mode_set  # BPyOpCallable, not the proxy - just for reference
print("type of bpy.ops.object.mode_set:", type(opfunc))
# The layout.operator() return type in 5.x:
import _bpy
print([n for n in dir(_bpy) if "Op" in n or "op" in n][:20])
