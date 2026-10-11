import bpy
L = bpy.types.UILayout
print("=== UILayout functions ===")
for f in L.bl_rna.functions:
    print(" *", f.identifier)
print()
for fname in ("operator", "prop"):
    f = L.bl_rna.functions.get(fname)
    if not f:
        continue
    print(f"=== {fname} params ===")
    for p in f.parameters:
        d = getattr(p, "default_value", None)
        try:
            d = str(d)
        except Exception:
            pass
        print(f"   {p.identifier}: type={p.type} default={d}")
    print()
# What does an operator proxy look like? Check BPyOpFunction RNA if exposed
import _bpy
cands = [n for n in dir(_bpy) if "opy" in n.lower() or "opfunc" in n.lower()]
print("_bpy op-ish:", cands)
