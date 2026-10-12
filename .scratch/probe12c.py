import bpy
ts = bpy.context.scene.tool_settings
for item in ts.bl_rna.properties['uv_sticky_select_mode'].enum_items:
    print("PROBE12C sticky:", item.identifier, flush=True)
for item in ts.bl_rna.properties['uv_select_mode'].enum_items:
    print("PROBE12C uvselmode:", item.identifier, flush=True)
