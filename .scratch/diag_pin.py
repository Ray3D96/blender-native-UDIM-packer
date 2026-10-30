# SPDX-License-Identifier: GPL-3.0-or-later
"""Does uv.pack_islands keep pinned islands put and pack around them?"""
import bpy
import bmesh

def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

def write_quad(ob, corners):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    face = next(iter(tuple(bm.faces)))
    for l, (x, y) in zip(tuple(face.loops), corners):
        l[uvl].uv = (x, y)
    bm.to_mesh(me)
    bm.free()

def read_uv(ob):
    return [(round(d.uv.x, 4), round(d.uv.y, 4)) for d in ob.data.uv_layers.active.data]

clear()
bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))
pinned = bpy.context.active_object
pinned.name = "Pinned"
bpy.ops.mesh.primitive_plane_add(size=2, location=(3, 0, 0))
mover = bpy.context.active_object
mover.name = "Mover"
# Pinned island occupies the center of the tile. Mover starts at the origin.
write_quad(pinned, [(0.3, 0.3), (0.7, 0.3), (0.7, 0.7), (0.3, 0.7)])
write_quad(mover, [(0.0, 0.0), (0.35, 0.0), (0.35, 0.35), (0.0, 0.35)])
print("pin attrs", [a for a in dir(bpy.context.scene.tool_settings) if "pin" in a.lower()], flush=True)

bpy.ops.object.select_all(action="DESELECT")
pinned.select_set(True)
mover.select_set(True)
bpy.context.view_layer.objects.active = pinned
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_mode(type="FACE")
ts = bpy.context.scene.tool_settings
ts.use_uv_select_sync = True
# Pin only the first object.
bpy.ops.mesh.select_all(action="DESELECT")
bm = bmesh.from_edit_mesh(pinned.data)
for f in tuple(bm.faces):
    f.select = True
bmesh.update_edit_mesh(pinned.data)
bm.free()
rpin = bpy.ops.uv.pin(clear=False)
print("pin op", rpin, flush=True)
# select both
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
pinned.select_set(True)
mover.select_set(True)
bpy.context.view_layer.objects.active = pinned
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
before_p = read_uv(pinned)
r = bpy.ops.uv.pack_islands(rotate=False, margin=0.01, margin_method="FRACTION",
                            scale=False, pin=True, pin_method="LOCKED",
                            udim_source="CLOSEST_UDIM")
print("pack", r, flush=True)
bpy.ops.object.mode_set(mode="OBJECT")
after_p = read_uv(pinned)
after_m = read_uv(mover)
print("pinned before", before_p, flush=True)
print("pinned after ", after_p, flush=True)
print("pinned moved", before_p != after_p, flush=True)
print("mover after", after_m, flush=True)
xs = [p[0] for p in after_m]
ys = [p[1] for p in after_m]
print(f"mover bbox ({min(xs):.3f},{min(ys):.3f})-({max(xs):.3f},{max(ys):.3f})", flush=True)
# Does the mover sit entirely outside the pinned square?
def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
mb = (min(xs), min(ys), max(xs), max(ys))
print("aabb overlap with pin", overlap(mb, (0.3, 0.3, 0.7, 0.7)), flush=True)
print("DONE", flush=True)
