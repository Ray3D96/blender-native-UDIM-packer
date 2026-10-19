# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe Blender 5.2 bmesh selection API - defensive version."""
import bmesh
import bpy

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(size=1)
ob = bpy.context.active_object
print(f"uv layer: {ob.data.uv_layers.active.name}", flush=True)

bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)


def show(label, fn):
    try:
        print(f"{label}: {fn()}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: EXC {type(exc).__name__}: {exc}", flush=True)


show("len(bm.loops)", lambda: len(bm.loops))
show("dir(BMLoopSeq)", lambda: sorted(a for a in dir(bm.loops)
                                      if not a.startswith("__")))
show("bm.loops[0] type", lambda: type(bm.loops[0]).__name__)

f0 = tuple(bm.faces)[0]
l0 = tuple(f0.loops)[0]
show("BMLoop attrs", lambda: sorted(a for a in dir(l0)
                                    if not a.startswith("__")))
show("BMFace attrs", lambda: sorted(a for a in dir(f0)
                                    if not a.startswith("__")))
show("BMElem base select?", lambda: hasattr(l0, "select"))

# RNA-level property list (what the docs would show)
show("RNA BMLoop props",
     lambda: [p.identifier for p in bpy.types.BMLoop.bl_rna.properties])
show("RNA BMFace props",
     lambda: [p.identifier for p in bpy.types.BMFace.bl_rna.properties])

# Selection experiments - what can we SET?
show("f.select read", lambda: f0.select)
try:
    f0.select = True
    bmesh.update_edit_mesh(ob.data)
    print("face select set OK", flush=True)
except Exception as exc:  # noqa: BLE001
    print(f"face select set EXC {type(exc).__name__}: {exc}", flush=True)

# Try selecting a UV island the way the editor does, via ops that may poll.
for op in ("uv.select_all", "uv.island_select"):
    try:
        if op == "uv.select_all":
            bpy.ops.uv.select_all(action='SELECT')
        else:
            bpy.ops.uv.island_select()
        print(f"{op} OK", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"{op} EXC {type(exc).__name__}: {exc}", flush=True)

bm2 = bmesh.from_edit_mesh(ob.data)
faces2 = tuple(bm2.faces)
show("face selects after ops", lambda: [f.select for f in faces2])
show("loop attr candidates",
     lambda: [(a, getattr(tuple(faces2[0].loops)[0], a))
              for a in ("select", "uv_select", "selected")
              if hasattr(tuple(faces2[0].loops)[0], a)])
bm2.free()
print("PROBE-DONE", flush=True)
