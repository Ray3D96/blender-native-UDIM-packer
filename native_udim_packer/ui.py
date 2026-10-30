# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panel for the UV editor (N-panel, own "UDIM" tab).

Layout is inspired by UVPackmaster's grouped sidebar panels: a prominent
main operator button on top, then a small number of clearly labeled
options with tooltips.
"""
from __future__ import annotations

import bpy
from bpy.types import Panel

from . import VERSION
from .packer import udim_number


class NATIVE_UDIM_PT_main(Panel):
    """Native UDIM Packer panel (image/UV editor sidebar)."""

    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UDIM"
    bl_label = "Native UDIM Packer"

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH'

    def draw(self, context):
        layout = self.layout

        # Version stamp: makes the running build distinguishable at a glance.
        layout.label(text=f"version {VERSION}")

        # All settings live in a PropertyGroup on the window manager.  In
        # Blender 5.x the object returned by ``layout.operator()`` is a
        # read-only snapshot, so widgets bound to it with
        # ``layout.prop(op, ...)`` render but cannot be clicked/dragged.
        # The built-in 5.x UI instead binds widgets to persistent RNA
        # properties on IDs / PropertyGroups - which is what we do here.
        settings = context.window_manager.native_udim

        # ---- main operator ------------------------------------------------
        layout.operator("native_udim.pack_to_grid", icon='GROUP_UVS')

        layout.separator()

        # ---- grid --------------------------------------------------------
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.label(text="UDIM Grid", icon='UV_FACESEL')
        row = col.row(align=True)
        row.prop(settings, "udim_x", text="X")
        row.prop(settings, "udim_y", text="Y")
        xs, ys = int(settings.udim_x), int(settings.udim_y)
        nums = [udim_number(tu, tv) for tv in range(ys) for tu in range(xs)]
        # A dash reads as "every number in between", which is wrong: a 2×2
        # grid is 1001, 1002, 1011, 1012, not 1001–1012.
        if len(nums) <= 4:
            shown = ", ".join(str(n) for n in nums)
        else:
            shown = f"{len(nums)} tiles, from {nums[0]}"
        col.label(text=shown, icon='UV_FACESEL')

        layout.separator()

        # ---- options -----------------------------------------------------
        box = layout.box()
        col = box.column(align=True)
        col.prop(settings, "normalize_scale")
        col.prop(settings, "rotate_90")
        col.prop(settings, "margin")
        col.prop(settings, "use_selected")
        col.prop(settings, "pack_selected_islands")


def register():
    bpy.utils.register_class(NATIVE_UDIM_PT_main)


def unregister():
    bpy.utils.unregister_class(NATIVE_UDIM_PT_main)
