"""Find which visibility flag blocks pack_islands on Wire; verify fix."""
import bpy
import bmesh

ADDON_PATH = "/mnt/fusion/ai-projects/blender-uv-packer"
SCENE = ADDON_PATH + "/QA_Test_Files/P_BLENDER_01.5.blend"
bpy.ops.wm.open_mainfile(filepath=SCENE)
if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
    bpy.ops.object.mode_set(mode='OBJECT')

ob = bpy.data.objects["Wire"]


def walk_layer(lc, path=""):
    p = f"{path}/{lc.name}" if path else lc.name
    print(f"W10 layer {p}: exclude={lc.exclude} hide_viewport={lc.hide_viewport} "
          f"collection.hide_viewport={lc.collection.hide_viewport}")
    for child in lc.children:
        walk_layer(child, p)


vl = bpy.context.view_layer
walk_layer(vl.layer_collection)
print(f"W10 Wire users_collection: {[c.name for c in ob.users_collection]}")
print(f"W10 Wire hide_get={ob.hide_get()} hide_viewport={ob.hide_viewport} "
      f"visible_get={ob.visible_get()}")


def pack_wire(tag):
    if bpy.context.object is not None and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    r1 = bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(ob.data)
    for f in tuple(bm.faces):
        f.select = True
    bmesh.update_edit_mesh(ob.data)
    bm.free()
    r2 = bpy.ops.uv.pack_islands(rotate=True, rotate_method="CARDINAL",
                                 margin=0.0, scale=False)
    if ob.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
    print(f"W10 {tag}: visible_get={ob.visible_get()} pack -> {r2}")
    return r2 == {'FINISHED'}


# baseline re-confirm
pack_wire("baseline (hidden)")

# walk up the ancestor chain of Wire's collection node; clear blocking flags
def find_node(lc, names):
    if lc.collection.name in names:
        return lc
    for child in lc.children:
        r = find_node(child, names)
        if r is not None:
            return r
    return None


def ancestors(node):
    chain = [node]
    # rebuild parent pointers by searching the tree
    def parent_of(lc, target, trail):
        for child in lc.children:
            if child is target:
                return trail + [lc]
            r = parent_of(child, target, trail + [lc])
            if r is not None:
                return r
        return None
    p = parent_of(vl.layer_collection, node, [])
    if p:
        chain = list(reversed(p)) + chain
    return chain


names = {c.name for c in ob.users_collection}
node = find_node(vl.layer_collection, names)
chain = ancestors(node)
print(f"W10 ancestor chain: {[lc.collection.name for lc in chain]}")

undo = []
for lc in chain:
    if lc.exclude:
        undo.append((lc, "exclude", True))
        lc.exclude = False
    if lc.hide_viewport:
        undo.append((lc, "hide_viewport", True))
        lc.hide_viewport = False
    if lc.collection.hide_viewport:
        undo.append((lc.collection, "hide_viewport", True))
        lc.collection.hide_viewport = False
print(f"W10 cleared {len(undo)} blocking flag(s)")
pack_wire("after un-exclude/un-hide chain")

for obj2, attr, old in undo:
    setattr(obj2, attr, old)
print("W10 restored flags")
pack_wire("after restore (should fail again)")
print("W10DONE")
