# SPDX-License-Identifier: GPL-2.0-or-later
"""Get exact RNA property identifiers on SpaceImageEditor in Blender 5.2."""
import bpy

props = bpy.types.SpaceImageEditor.bl_rna.properties
print("=== dict keys of SpaceImageEditor.bl_rna.properties ===")
for k in props.keys():
    p = props[k]
    extra = ""
    if isinstance(p, bpy.types.EnumProperty):
        extra = f" enum={[i.identifier for i in p.enum_items]}"
    elif isinstance(p, bpy.types.PointerProperty):
        try:
            extra = f" -> {p.rna_type}"
        except Exception:
            pass
    print(f"  key={k!r} name={p.name!r} type={p.type}{extra}")

print()
print("=== candidate bracket accesses ===")
for cand in ("mode", "Mode", "uv_editor", "UV Editor", "show_uv_editor"):
    try:
        p = props[cand]
        print(f"  {cand!r} OK -> name={p.name!r} type={p.type}")
    except KeyError:
        print(f"  {cand!r} missing")

print()
print("=== SpaceUVEditor keys (first 12) ===")
uprops = bpy.types.SpaceUVEditor.bl_rna.properties
for k in list(uprops.keys())[:12]:
    p = uprops[k]
    extra = ""
    if isinstance(p, bpy.types.EnumProperty):
        extra = f" enum={[i.identifier for i in p.enum_items]}"
    print(f"  key={k!r} name={p.name!r} type={p.type}{extra}")
