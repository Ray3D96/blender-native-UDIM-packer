"""Does uv.pack_islands renumber edit-bmesh faces? Minimal repro."""
import bpy
import bmesh

SCENE = ("/mnt/fusion/ai-projects/blender-uv-packer/"
         "QA_Test_Files/P_BLENDER_01.5.blend")

bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

pm = bpy.data.objects["PlugMetal"]


def sig(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    idx = sorted(f.index for f in bm.faces)
    n = len(idx)
    first, last = idx[:3], idx[-3:]
    # also: index of a geometrically-identified face (the one with the
    # smallest centroid x) to detect reordering vs mere count change
    cmin = min(bm.faces, key=lambda f: f.calc_center_median().x)
    bm.free()
    return n, first, last, cmin.index


# Case A: single-object edit session
print("A: enter edit (PlugMetal only)", flush=True)
bpy.ops.object.select_all(action='DESELECT')
pm.select_set(True)
bpy.context.view_layer.objects.active = pm
bpy.ops.object.mode_set(mode='EDIT')
before = sig(pm)
print(f"  before pack: n={before[0]} first={before[1]} last={before[2]} "
      f"cmin_idx={before[3]}", flush=True)
r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                            margin=0.0, scale=False)
after = sig(pm)
print(f"  after pack : n={after[0]} first={after[1]} last={after[2]} "
      f"cmin_idx={after[3]}  result={r}", flush=True)
print(f"  CHANGED: {before != after}", flush=True)
bpy.ops.object.mode_set(mode='OBJECT')

# Case B: multi-object edit session (like the engine)
print("B: enter multi-edit (all mesh objects)", flush=True)
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
bpy.ops.object.select_all(action='DESELECT')
for o in objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.mode_set(mode='EDIT')
before = sig(pm)
print(f"  before pack: n={before[0]} cmin_idx={before[3]}", flush=True)
r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                            margin=0.0, scale=False)
after = sig(pm)
print(f"  after pack : n={after[0]} cmin_idx={after[3]} result={r}",
      flush=True)
print(f"  CHANGED: {before != after}", flush=True)

# Case C: multi-edit with PARTIAL face selection (engine-like)
print("C: multi-edit, partial selection", flush=True)
bpy.ops.object.mode_set(mode='OBJECT')
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
bpy.ops.object.select_all(action='DESELECT')
for o in objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='FACE')
# deselect a chunk of PlugMetal faces (like the engine's non-tile faces)
bm = bmesh.from_edit_mesh(pm.data)
n_sel = 0
for f in bm.faces:
    if f.index < 940:
        f.select = True
        n_sel += 1
    else:
        f.select = False
bmesh.update_edit_mesh(pm.data)
bm.free()
before = sig(pm)
print(f"  sel={n_sel} before pack: cmin_idx={before[3]}", flush=True)
r = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                            margin=0.0, scale=False)
after = sig(pm)
print(f"  after pack : cmin_idx={after[3]} result={r}", flush=True)
print(f"  CHANGED: {before != after}", flush=True)
if before != after:
    bm = bmesh.from_edit_mesh(pm.data)
    sel_idx = sorted(f.index for f in bm.faces if f.select)
    unsel_idx = sorted(f.index for f in bm.faces if not f.select)
    print(f"  post-pack selected first10={sel_idx[:10]} "
          f"unselected={unsel_idx}", flush=True)
    bm.free()
