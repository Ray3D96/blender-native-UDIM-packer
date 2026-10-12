# Diagnostic: reproduce the T8 CANCELLED from uv.pack_islands (tile 1002).
# Builds the exact T8 mesh, runs the real engine with an instrumented
# _execute_round wrapper AND a shimmed bpy.ops.uv.pack_islands that dumps
# the live selection + UV bboxes around every native pack call.
import sys
import bmesh
import bpy

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer/native_udim_packer"

# ---- force-reload block (sys.modules hazard) ------------------------------
for m in list(sys.modules):
    if m.startswith("native_udim_packer"):
        del sys.modules[m]
sys.path.insert(0, "/mnt/fusion/ai-projects/blender-uv-packer")
from native_udim_packer import packer as P  # noqa: E402

# ---- build the exact T8 mesh ----------------------------------------------
for o in list(bpy.context.scene.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.mesh.primitive_cube_add(size=2)
a = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
b = bpy.context.active_object
a.select_set(True); b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
ob = bpy.context.active_object
ob.name = "t8"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')


def dump_selection(tag):
    if bpy.context.mode != 'EDIT_MESH':
        print(f"DBG [{tag}] not in edit mode (mode={bpy.context.mode})",
              flush=True)
        return
    me = ob.data
    bm = bmesh.from_edit_mesh(me)
    try:
        uvl = bm.loops.layers.uv.active
        n_sel = 0
        for f in tuple(bm.faces):
            if not f.select:
                continue
            n_sel += 1
            us = [l[uvl].uv for l in tuple(f.loops)]
            xs = [u.x for u in us]; ys = [u.y for u in us]
            print(f"DBG [{tag}] sel face idx={f.index} "
                  f"bbox=({min(xs):.4f},{min(ys):.4f})-"
                  f"({max(xs):.4f},{max(ys):.4f})", flush=True)
        if n_sel == 0:
            print(f"DBG [{tag}] NO FACES SELECTED", flush=True)
    finally:
        bm.free()


# ---- shim bpy.ops.uv.pack_islands inside the packer module -----------------
class _UvShim:
    def __init__(self, real_uv):
        self._real = real_uv

    def pack_islands(self, **kw):
        dump_selection("pre-pack")
        r = self._real.pack_islands(**kw)
        print(f"DBG pack_islands({kw}) -> {r}", flush=True)
        if r != {'FINISHED'}:
            dump_selection("post-cancel")
        return r

    def __getattr__(self, name):
        return getattr(self._real, name)


class _OpsShim:
    def __init__(self, real_ops):
        self._real = real_ops

    @property
    def uv(self):
        return _UvShim(self._real.uv)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _BpyShim:
    def __init__(self, real_bpy):
        self._real = real_bpy

    @property
    def ops(self):
        return _OpsShim(self._real.ops)

    def __getattr__(self, name):
        return getattr(self._real, name)


P.bpy = _BpyShim(bpy)

# ---- instrument rounds ------------------------------------------------------
orig_round = P._execute_round


def dbg_round(state, assign, positions, S, rotate_90, margin):
    members_by_tile = {}
    for s in state:
        for t in {assign[i._item_index] for i in s["islands"]}:
            members_by_tile.setdefault(t, []).append(s)
    print(f"DBG round S={S:.6f} tiles_used={sorted(members_by_tile)}",
          flush=True)
    detail = {}
    for t in sorted(members_by_tile):
        isl = []
        for s in members_by_tile[t]:
            for i in s["islands"]:
                if assign[i._item_index] == t:
                    w = i.max_uv[0] - i.min_uv[0]
                    h = i.max_uv[1] - i.min_uv[1]
                    isl.append(f"faces={len(i.face_indices)} "
                               f"ref=({w:.3f},{h:.3f}) atS=({w * S:.3f},"
                               f"{h * S:.3f})")
        detail[t] = isl
    for t in sorted(detail):
        print(f"DBG   tile {t} (udim {P.udim_number(*positions[t])}): "
              f"{detail[t]}", flush=True)
    try:
        ext = orig_round(state, assign, positions, S, rotate_90, margin)
        print(f"DBG round OK extents={ext}", flush=True)
        return ext
    except Exception as exc:
        print(f"DBG round FAILED at S={S:.6f}: {exc!r}", flush=True)
        raise


P._execute_round = dbg_round

res = P.pack_objects([ob], 3, 2, normalize_scale=True, rotate_90=True,
                     margin=0.008)
print("DBG result:", {k: v for k, v in res.items() if k != "objects"},
      flush=True)
if "objects" in res:
    for name, st in res["objects"].items():
        print(f"DBG obj {name}: islands={st['islands']} "
              f"tiles={sorted(st['tiles_used'])} "
              f"scale={res.get('global_scale')}", flush=True)
print("DBG DONE", flush=True)
