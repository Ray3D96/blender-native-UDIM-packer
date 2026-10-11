# SPDX-License-Identifier: GPL-2.0-or-later
"""Probe: does uv.pack_islands(scale=True) scale UP a small selection?"""
import bpy
import bmesh


def make_small_island(name):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.name = name
    # UVs: one quad island at (0.1,0.1)-(0.3,0.2) -> area 0.02
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    coords = [(0.1, 0.1), (0.3, 0.1), (0.3, 0.2), (0.1, 0.2)]
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.loops[li].vertex_index
            uv[li].uv = coords[v]
    return ob


def bounds_of(ob):
    was_edit = bpy.context.mode == 'EDIT_MESH'
    if not was_edit:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    minx = miny = 1e9
    maxx = maxy = -1e9
    for f in tuple(bm.faces):
        for l in tuple(f.loops):
            u = l[uvl].uv
            minx = min(minx, u.x); maxx = max(maxx, u.x)
            miny = min(miny, u.y); maxy = max(maxy, u.y)
    bm.free()
    if bpy.context.mode == 'EDIT_MESH':
        bpy.ops.object.mode_set(mode='OBJECT')
    return (minx, miny, maxx, maxy)


def run_case(label, scale):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    ob = make_small_island("probe")
    before = bounds_of(ob)
    print(f"{label}: before bbox=({before[0]:.3f},{before[1]:.3f})-({before[2]:.3f},{before[3]:.3f}) "
          f"w={before[2]-before[0]:.3f} h={before[3]-before[1]:.3f}")
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    with bpy.context.temp_override(object=ob, active_object=ob):
        r = bpy.ops.uv.pack_islands(
            udim_source='CLOSEST_UDIM',
            rotate=False, rotate_method='ANY',
            scale=scale, merge_overlap=False,
            margin_method='FRACTION', margin=0.01)
    after = bounds_of(ob)
    print(f"{label}: result={r} after bbox=({after[0]:.3f},{after[1]:.3f})-({after[2]:.3f},{after[3]:.3f}) "
          f"w={after[2]-after[0]:.3f} h={after[3]-after[1]:.3f}")


run_case("scale=True ", True)
run_case("scale=False", False)
