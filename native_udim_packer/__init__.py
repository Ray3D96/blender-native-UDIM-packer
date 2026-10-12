# SPDX-License-Identifier: GPL-2.0-or-later
"""Native UDIM Packer.

Packs UV islands of the active/selected objects into a user-defined UDIM
tile grid (e.g. 1x1, 2x2, 4x1) using only Blender's built-in facilities:
bmesh seam-aware island detection, one global uniform scale solved by a
pure-Python first-fit-decreasing tile assignment with a measured
feasibility search, and per-tile placement by the built-in
``uv.pack_islands`` operator (shape-aware, no overlaps).

No external engines, binaries or third-party libraries are used.
"""

bl_info = {
    "name": "Native UDIM Packer",
    "author": "Blender community",
    "version": (0, 2, 0),
    "blender": (5, 2, 0),
    "location": "UV Editor > Sidebar (N) > UDIM tab",
    "description": (
        "Pack UV islands into a user-defined UDIM tile grid with native "
        "Blender operators: sequential tile filling, optional texel-density "
        "normalization and 90-degree rotation"
    ),
    "category": "UV",
}

# Dotted version string, shown in the panel so the running build is
# distinguishable at a glance.
VERSION = ".".join(str(p) for p in bl_info["version"])

from . import packer as _packer          # noqa: F401  (module imports)
from . import islands as _islands        # noqa: F401
from . import layout as _layout          # noqa: F401
from . import operators as _operators
from . import ui as _ui


def register():
    # Log the loaded build so the running version is verifiable in any
    # console (terminal launch, --background runs, crash logs).
    print(f"Native UDIM Packer v{VERSION} registered")
    _operators.register()
    _ui.register()


def unregister():
    _ui.unregister()
    _operators.unregister()
