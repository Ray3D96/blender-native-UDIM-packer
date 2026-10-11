# Native UDIM Packer

A 100% native Blender addon that packs the UV islands of your active (or all
selected) objects into a **user-defined UDIM tile grid** — in the spirit of
UVPackmaster, but built exclusively from `bpy`, `bmesh` and Blender's own
operators. No external engines, binaries or third-party libraries.

## Features

- **UDIM grid layout** — choose the tile count along U and V (1×1, 2×2, 4×1,
  3×2, … up to 10×32). Islands are balanced across the tiles by area, so no
  tile is overloaded while others stay empty.
- **Standard UDIM numbering** — tile (0,0) is UDIM **1001**, tile (1,0) is
  **1002**, …, tile (9,0) is **1010**; each higher row adds 10: row 2 starts
  at **1011**, row 3 at **1021**. X is capped at 10 because a UDIM row is 10
  tiles wide. Every island is shifted by whole integers into its tile's
  `[u, u+1] × [v, v+1]` region.
- **Islands stay intact** — the packer only moves, scales and rotates your
  existing UV islands; it never re-unwraps, cuts new seams or splits an
  island. A multi-face island always ends up whole inside a single tile.
- **Normalize scale (optional)** — when enabled, every island is pre-scaled so
  that texel density (UV area per unit of 3D surface area) is equal across all
  islands; tiles then fill evenly. When disabled, the original relative island
  scales are preserved as much as possible (islands that still do not fit a
  tile are shrunk by the native packer).
- **90° rotation (optional)** — uses the native packer's `CARDINAL` rotation
  to improve tile fill. A built-in manual shelf-packer (with its own 90°
  rotation) is used as a fallback only if the native operator cannot run.
- **Multi-object** — pack several selected mesh objects into the same grid in
  one click. All objects share one texture set: their islands are balanced
  across the whole grid together and **never overlap, even between different
  objects** (each object keeps its own UV map).
- **Native building blocks only** — `bmesh` seam-aware island detection,
  `bpy.ops.uv.pack_islands` as the packing engine, and manual integer tile
  offsets. Pinned UVs are respected by the native packer.
- **Undoable** — the operator is registered with `UNDO` and pushes a labeled
  undo step ("Native UDIM: Pack to Grid").

## Requirements

- Blender **5.2 or newer** (developed and tested on 5.2.2 LTS).
- The objects need an **active UV map**. No other dependencies.

## Installation

1. In Blender open **Edit → Preferences → Add-ons** (or *Extensions* in the
   new-style UI).
2. Click **Install from Disk…** and select `native_udim_packer-0.1.4.zip`
   (or unzip it and point the installer at the `native_udim_packer` folder).
3. Enable **Native UDIM Packer**.

Alternatively, copy the `native_udim_packer` folder into your user addon
directory (`~/.config/blender/<version>/scripts/addons/`) and enable it in
Preferences.

> **Upgrading from an older build:** installing over an already-enabled
> addon does not hot-reload it — fully quit Blender and start it again after
> installing. Two ways to verify which build is actually running: the panel
> shows a `version x.y.z` stamp at the top of the UDIM tab, and the addon
> prints `Native UDIM Packer v<version> registered` to the console on
> startup (this release: **0.1.4**).

## Usage

1. Open a **UV Editor** (Image Editor → *UV* mode in Blender 5.x, or *UV
   shading* in older versions) so the sidebar is visible. The panel also
   appears in the image editor in any other mode — packing works from every
   editor state.
2. Press **N** in that editor and open the **UDIM** tab.
3. Select the object(s) to pack. This works in **Object mode** as well as in
   **(multi-)Edit mode**: with several objects selected and `Tab` pressed,
   *Pack to UDIM Grid* packs all of them into the same grid at once. When you
   start from edit mode you are returned to it afterwards, with the same
   objects still being edited.
4. Set the options:

   | Option            | Meaning                                                                 |
   |-------------------|-------------------------------------------------------------------------|
   | **UDIM Grid X/Y** | Tile count along U / V. The panel shows the total tile count and UDIM range. |
   | **Normalize Scale** | Equalize texel density across islands before packing.                  |
   | **Allow 90° Rotation** | Let the packer rotate islands by 90° (CARDINAL) to fill tiles better. |
   | **Margin**        | Gap between islands and tile edges, as a fraction of one tile (0.01 = 1%). |
   | **Selected Objects** | Pack all selected meshes; off = active object only.                   |

5. Click **Pack to UDIM Grid**. The status bar reports how many islands were
   packed into which tiles/UDIMs. Undo with `Ctrl+Z`.

### Quick example

For a 2×2 tile set (UDIMs 1001, 1002, 1011, 1012): set X = 2, Y = 2, enable
*Allow 90° Rotation*, keep *Normalize Scale* off to preserve your unwrap's
relative scales, and click **Pack to UDIM Grid**. For a horizontal strip of
three tiles (UDIMs 1001, 1002, 1003) set X = 3, Y = 1; for a vertical stack
(UDIMs 1001, 1011, 1021) set X = 1, Y = 3.

## How it works

1. **Island detection** — a seam-aware union-find over bmesh faces: two faces
   across a shared edge are connected only when **both** shared vertices have
   matching UV coordinates in the two faces (i.e. the edge is not a UV seam).
   Comparing explicit per-vertex corners (not loop starts, which sit at
   opposite ends of a shared edge) is what keeps multi-face islands intact —
   e.g. Blender's built-in monkey mesh correctly resolves to its 5 real UV
   islands instead of one island per face.
2. **Optional normalization** — each island is scaled about its centroid by
   `sqrt( (ΣUV / Σ3D) · 3Dᵢ / UVᵢ )`, which equalizes texel density while
   preserving the total UV footprint.
3. **Tile balancing** — *all* target objects' islands are pooled and sorted
   by area, then assigned largest-first to the currently emptiest tile (LPT
   scheduling), spreading the load evenly across the whole shared grid.
4. **Per-tile native packing** — for each non-empty tile owned by a single
   object, only that tile's faces are selected, translated so their
   bounding-box minimum sits at the origin, and packed with
   `bpy.ops.uv.pack_islands(udim_source='CLOSEST_UDIM', rotate=…,
   rotate_method='CARDINAL', scale=True, margin_method='FRACTION', …)`.
5. **Measured integer re-offset** — the addon measures where the native
   packer actually placed the selection and shifts it by the whole-tile delta
   to the assigned tile. The result is correct regardless of which UDIM tile
   the editor context would have targeted, and every island ends up strictly
   inside `[tu, tu+1] × [tv, tv+1]`.
6. **Shared tiles** — when a tile contains islands from several objects, the
   native operator (which only sees one object) cannot coordinate them, so the
   addon lays out the whole combined set with its built-in shelf packer: one
   shared layout per tile guarantees that no island of one object overlaps an
   island of another.
7. **Fallback** — if the native operator fails for a tile, the same pure-Python
   shelf packer places that tile's islands directly into its assigned tile
   (with 90° rotation when enabled, and shrink-to-fit when the islands do not
   fit). The fallback never overlaps other tiles' content.
8. **Density restoration** — with *Normalize Scale* on, each single-object
   tile is measured afterwards: `uv.pack_islands(scale=True)` scales small
   selections *up* to fill the tile, which would leave every tile at a
   different texel density. The addon therefore shrinks each over-dense tile's
   content uniformly (about the tile center) back to the equalized density.
   Tiles are only ever shrunk, never enlarged, so containment is preserved.

## Notes & limitations

- **Settings live in the panel, not on the operator.** The grid size and
  options are stored in a `PropertyGroup` on the window manager
  (`context.window_manager.native_udim`) and the *Pack to UDIM Grid* button
  reads them when clicked. This is the pattern Blender 5.x itself uses: the
  object returned by `layout.operator()` is a read-only snapshot in 5.x, so
  widgets bound to it would render but could not be interacted with. From a
  script you can therefore configure a pack like this:

  ```python
  import bpy
  s = bpy.context.window_manager.native_udim
  s.udim_x, s.udim_y = 3, 1          # horizontal strip: UDIMs 1001-1003
  s.normalize_scale = False
  bpy.ops.native_udim.pack_to_grid()
  ```

- Each object is packed in its own isolated edit session (so the native
  packer never sees another object's UVs); with several objects selected,
  undoing the operation takes one `Ctrl+Z` per object. The original object
  selection is restored afterwards, and when packing started from (multi-)
  edit mode you are returned to it with the same objects being edited.
  Pinned UVs are passed through to the native packer and behave as they do
  with the built-in *Pack Islands* operator.
- The grid is a layout for your UDIM texture set: paint/assign images with
  matching UDIM tiles (`1001 + u + v·10`) to see the result.
- Very large grids (many small islands per tile) are limited only by the
  native packer's performance.

## License

GPL-2.0-or-later. Inspired by the UX of UVPackmaster; no UVPackmaster code is
included or called.
