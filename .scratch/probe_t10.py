"""What does the v4 engine do with the T10 monkey on a 3x1 grid?"""
import sys
import time

import bpy
import bmesh

HERE = "/mnt/fusion/ai-projects/blender-uv-packer"
for m in [k for k in list(sys.modules)
          if k.startswith("native_udim_packer")]:
    del sys.modules[m]
sys.path.insert(0, HERE)
from native_udim_packer import packer as P  # noqa: E402
from native_udim_packer import layout as L   # noqa: E402


def islands_of(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    parts = []
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        comp = set()
        while stack:
            g = stack.pop()
            if g.index in comp:
                continue
            comp.add(g.index)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in comp:
                        stack.append(h)
        seen |= comp
        parts.append(sorted(comp))
    bm.free()
    return parts


bpy.ops.mesh.primitive_monkey_add(size=1.0)
mon = bpy.context.active_object

pre = islands_of(mon)
print(f"pre-pack islands={len(pre)} faces={[len(p) for p in pre]}",
      flush=True)

# island bboxes at reference size (normalize off -> as-is)
bm = bmesh.new()
bm.from_mesh(mon.data)
bm.faces.ensure_lookup_table()
uvl = bm.loops.layers.uv.active
items = []
for k, part in enumerate(pre):
    xs, ys = [], []
    for fi in part:
        for l in bm.faces[fi].loops:
            xs.append(l[uvl].uv.x)
            ys.append(l[uvl].uv.y)
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    items.append(L.Item(k, w, h))
    print(f"  isl{k}: faces={len(part)} bbox=({w:.4f}, {h:.4f}) "
          f"area={w * h:.4f}", flush=True)
bm.free()

total_area = sum(it.area for it in items)
print(f"total reference area={total_area:.4f}", flush=True)
S = L.max_scale(1.0, items)
print(f"S_max={S:.6f} cap_at_Smax={(1.0 / S) ** 2:.4f} "
      f"eta0.92*cap={0.92 * (1.0 / S) ** 2:.4f}", flush=True)
a = L.assign_ffd(items, 3, (1.0 / S) ** 2, eta=0.92)
print(f"ffd@Smax eta=.92 -> {sorted(set(a.values())) if a else None} "
      f"per-tile={[sum(1 for v in a.values() if v == t) for t in range(3)]}",
      flush=True)

t0 = time.time()
r = P.pack_objects([mon], 3, 1, False, True, 0.0)
print(f"pack {time.time() - t0:.2f}s result={r}", flush=True)

post = islands_of(mon)
bm = bmesh.new()
bm.from_mesh(mon.data)
bm.faces.ensure_lookup_table()
uvl = bm.loops.layers.uv.active
for k, part in enumerate(post):
    xs, ys = [], []
    for fi in part:
        for l in bm.faces[fi].loops:
            xs.append(l[uvl].uv.x)
            ys.append(l[uvl].uv.y)
    udim = 1001 + int(min(xs)) + 10 * int(min(ys))
    print(f"  post isl{k}: faces={len(part)} "
          f"bbox=({min(xs):.4f},{min(ys):.4f})-({max(xs):.4f},{max(ys):.4f}) "
          f"udim={udim}", flush=True)
bm.free()
