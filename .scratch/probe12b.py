import bpy
ts = bpy.context.scene.tool_settings
names = [n for n in dir(ts) if 'uv' in n.lower() or 'select' in n.lower() or 'sticky' in n.lower()]
print("PROBE12B attrs:", names, flush=True)
for n in names:
    try:
        print(f"PROBE12B {n} = {getattr(ts, n)!r}", flush=True)
    except Exception as e:
        print(f"PROBE12B {n} ERR {e}", flush=True)
