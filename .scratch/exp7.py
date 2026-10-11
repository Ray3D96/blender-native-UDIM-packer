import bpy

bpy.ops.mesh.primitive_cube_add(size=2)
c = bpy.context.active_object
print("S0 loc:", tuple(c.location))

# initialize undo system
bpy.ops.ed.undo_push(message="batch test")

# change 1: direct data change
c.location.x += 1.0
print("S1 loc (after +1 x):", tuple(c.location))

# change 2: a UNDO-flagged operator on the same object
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
print("S2 loc (after apply -> 0):", tuple(c.location), "origin:", tuple(c.data.vertices[0].co if False else c.matrix_world.translation))

# undo #1: what reverts?
bpy.ops.ed.undo()
print("U1 loc (after undo #1):", tuple(c.location))
# undo #2
bpy.ops.ed.undo()
print("U2 loc (after undo #2):", tuple(c.location))
