# SPDX-License-Identifier: GPL-3.0-or-later
"""The user-facing operator and its settings.

Settings live in a :class:`PropertyGroup` on the ``WindowManager``
(``context.window_manager.native_udim``), NOT as properties of the
operator itself.  Blender 5.x reworked the object returned by
``layout.operator()``: it is a read-only snapshot, so widgets bound to it
with ``layout.prop(op, ...)`` render but cannot be interacted with (the
pattern was still fine in 4.x).  The built-in 5.x UI never binds widgets to
operator proxies; it binds them to persistent RNA properties on IDs or
PropertyGroups.  A PropertyGroup on the window manager is always available,
survives redraws, and works identically in every context, so the panel's
spinboxes/checkboxes are fully interactive again.
"""
from __future__ import annotations

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty
from bpy.types import Operator, PropertyGroup

from . import packer


class NATIVE_UDIM_PG_settings(PropertyGroup):
    """Pack-to-UDIM-grid settings shown in the UV editor's UDIM panel."""

    udim_x: IntProperty(
        name="Tiles X",
        description=(
            "Number of UDIM tiles along the U axis (horizontal). Capped at 10 "
            "because a standard UDIM row is 10 tiles wide (1001-1010); each "
            "higher row continues at +10 (1011, 1021, ...)"
        ),
        default=2, min=1, max=10,
    )
    udim_y: IntProperty(
        name="Tiles Y",
        description=(
            "Number of UDIM tiles along the V axis (vertical). Each row adds "
            "10 to the UDIM number: row 2 starts at 1011, row 3 at 1021"
        ),
        default=2, min=1, max=32,
    )
    normalize_scale: BoolProperty(
        name="Normalize Scale",
        description=(
            "Make every shell proportional to its 3D size: all islands end up "
            "with the same texel density (UV area per unit of 3D surface "
            "area), like Blender's Average Islands Scale. When off, the "
            "original relative island scales are preserved exactly - one "
            "uniform factor is applied to every island"
        ),
        default=False,
    )
    rotate_90: BoolProperty(
        name="Allow 90° Rotation",
        description=(
            "Let the built-in packer rotate individual islands by 90 degrees "
            "(cardinal directions) when that saves space; when off every "
            "island keeps its current orientation"
        ),
        default=True,
    )
    margin: FloatProperty(
        name="Margin",
        description=(
            "Gap kept between islands and tile edges, as a fraction of one "
            "UDIM tile (0.01 = 1% of the tile width)"
        ),
        default=0.005, min=0.0, max=0.05,
    )
    use_selected: BoolProperty(
        name="Selected Objects",
        description=(
            "Pack every selected mesh object into the same grid; when off, "
            "only the active object is packed"
        ),
        default=True,
    )
    pack_selected_islands: BoolProperty(
        name="Pack Selected Islands",
        description=(
            "Pack only the UV islands that are selected in the UV editor "
            "(an island counts as selected when at least one of its faces "
            "is); every other island keeps its UVs and is treated as an "
            "obstacle the new layout avoids. Needs a live selection: enter "
            "the UV editor, select islands, then run the operator"
        ),
        default=False,
    )


class NATIVE_UDIM_OT_pack_to_grid(Operator):
    """Pack the active/selected objects' UV islands into a UDIM tile grid.

    Grid size and options are read from
    ``context.window_manager.native_udim`` (the panel's settings).  All
    target objects share one texture set: their islands are assigned to the
    whole grid together (sequential first-fit-decreasing, filling tile 1001
    before opening 1002) and laid out with a single global uniform scale;
    each used tile is placed by the built-in ``uv.pack_islands`` operator,
    so islands never overlap - even between different objects - and
    relative sizes are preserved exactly.
    """

    bl_idname = "native_udim.pack_to_grid"
    bl_label = "Pack to UDIM Grid"
    bl_description = (
        "Pack UV islands of the active (or all selected) objects into a "
        "user-defined UDIM tile grid with one global uniform scale"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH'

    def _targets(self, context) -> list:
        # In (multi-)edit mode ``selected_objects`` contains every object
        # being edited, so the same logic works in both modes.
        if context.window_manager.native_udim.use_selected:
            obs = context.selected_objects
        else:
            obs = [context.active_object]
        return [o for o in obs if o.type == 'MESH']

    def execute(self, context):
        # Initialize the undo system and label this whole operation as a
        # single step ("Native UDIM: Pack to Grid" shows up in the undo
        # history). In background mode undo is disabled until this call.
        try:
            bpy.ops.ed.undo_push(message="Native UDIM: Pack to Grid")
        except (RuntimeError, AttributeError):
            pass

        targets = self._targets(context)
        if not targets:
            self.report({'WARNING'}, "No mesh object to pack")
            return {'CANCELLED'}

        s = context.window_manager.native_udim
        grid_x, grid_y = int(s.udim_x), int(s.udim_y)
        try:
            res = packer.pack_objects(
                targets, grid_x, grid_y,
                normalize_scale=bool(s.normalize_scale),
                rotate_90=bool(s.rotate_90),
                margin=float(s.margin),
                selected_islands=bool(s.pack_selected_islands),
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, f"Native UDIM: {exc}")
            return {'CANCELLED'}

        if "error" in res:
            self.report({'ERROR'}, f"Native UDIM: {res['error']}")
            return {'CANCELLED'}

        # ---- report ------------------------------------------------------
        lines = []
        for name, st in res["objects"].items():
            udim_list = ", ".join(str(u) for u in st["udims"][:8])
            more = " …" if len(st["udims"]) > 8 else ""
            lines.append(
                f"{name}: {st['islands']} islands → {len(st['tiles_used'])} tiles "
                f"({udim_list}{more})"
            )
        if res.get("untouched_islands"):
            lines.append(
                f"{res['untouched_islands']} unselected island(s) left in place")
        for name, msg in res.get("errors", {}).items():
            lines.append(f"{name}: {msg}")
        if res["shared_tiles"]:
            lines.append(
                f"note: {res['shared_tiles']} tile(s) are shared by several "
                f"objects; their islands were co-packed so nothing overlaps "
                f"between objects"
            )
        if not res.get("errors"):
            self.report({'INFO'}, " | ".join(lines))
        else:
            self.report({'WARNING'}, " | ".join(lines))
        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


def register():
    # The PropertyGroup must be registered BEFORE it is referenced from a
    # PointerProperty (an unregistered class has no bl_rna yet).
    bpy.utils.register_class(NATIVE_UDIM_PG_settings)
    bpy.types.WindowManager.native_udim = PointerProperty(
        type=NATIVE_UDIM_PG_settings)
    bpy.utils.register_class(NATIVE_UDIM_OT_pack_to_grid)


def unregister():
    bpy.utils.unregister_class(NATIVE_UDIM_OT_pack_to_grid)
    bpy.utils.unregister_class(NATIVE_UDIM_PG_settings)
    del bpy.types.WindowManager.native_udim
