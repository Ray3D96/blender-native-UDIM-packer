# Native UDIM Packer

A 100% native Blender addon that packs the UV islands of your active (or all
selected) objects into a **user-defined UDIM tile grid** — in the spirit of
UVPackmaster, but built exclusively from `bpy`, `bmesh` and Blender's own
operators. No external engines, binaries or third-party libraries.

## Features

- **UDIM grid layout** — choose the tile count along U and V (1×1, 2×2, 4×1,
  3×2, … up to 10×32). Islands are balanced across the tiles by area (LPT
  scheduling), so no tile is overloaded while others stay empty. The layout
  solver derives one global scale that fills the used tiles as densely as
  possible — islands come out as large as the grid allows, not spread thin.
- **Standard UDIM numbering** — tile (0,0) is UDIM **1001**, tile (1,0) is
  **1002**, …, tile (9,0) is **1010**; each higher row adds 10: row 2 starts
  at **1011**, row 3 at **1021**. X is capped at 10 because a UDIM row is 10
  tiles wide. Every island is shifted by whole integers into its tile's
  `[u, u+1] × [v, v+1]` region.
- **Islands stay intact** — the packer only moves, scales and rotates your
  existing UV islands; it never re-unwraps, cuts new seams or splits an
  island. A multi-face island always ends up whole inside a single tile.
- **Normalize scale (optional)** — when enabled, every island ends up with the
  same texel density (UV area per unit of 3D surface area), across all packed
  objects: shells stay proportional to their real-world size, exactly like
  Blender's built-in *Average Islands Scale*. When disabled, the original
  relative island scales are preserved **exactly** — the packer applies one
  single uniform factor to every island, so any scale equalization you did
  beforehand (built-in or otherwise) is never broken. If the total content
  exceeds the grid's capacity everything shrinks uniformly and proportions
  stay intact.
- **90° rotation (optional)** — islands may be rotated in 90° steps to fill
  tiles better; each island keeps a single rigid transform (scale + optional
  rotation + translation), so shapes are never distorted or stretched.
- **Multi-object** — pack several selected mesh objects into the same grid in
  one click. All objects share one texture set: their islands are balanced
  across the whole grid together and **never overlap, even between different
  objects** (each object keeps its own UV map).
- **Shape-aware packing** — each island is placed as its *actual* outline
  polygon (seam-walked boundary plus holes), not just its bounding box.
  Small islands nest into the holes of larger ones, concave notches can be
  interlocked, and the margin gap is enforced between the real shapes — so
  empty space inside an island's bounding box is no longer wasted. Islands
  that are tiny or effectively rectangular automatically use a faster
  rectangle path with identical results to before.
- **Native building blocks only** — `bmesh` seam-aware island detection plus a
  pure-Python layout solver (LPT-balanced tile assignment, bounded local
  search for tile balancing, greedy bottom-left placement with polygon
  collision testing, one closed-form global scale). No external engines, no
  subprocess calls, fully deterministic: the same input always produces the
  same layout.
- **Undoable** — the operator is registered with `UNDO` and pushes a labeled
  undo step ("Native UDIM: Pack to Grid").

## Requirements

- Blender **5.2 or newer** (developed and tested on 5.2.2 LTS).
- The objects need an **active UV map**. No other dependencies.

## Installation

1. In Blender open **Edit → Preferences → Add-ons** (or *Extensions* in the
   new-style UI).
2. Click **Install from Disk…** and select `native_udim_packer-0.1.6.zip`
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
> startup (this release: **0.1.6**).

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
   | **Normalize Scale** | Make every shell proportional to its 3D size — uniform texel density across all packed objects, like *Average Islands Scale*.                  |
   | **Allow 90° Rotation** | Let the packer rotate islands in 90° steps to fill tiles better. |
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
   islands instead of one island per face. The same seam walk also extracts
   each island's **outline**: the closed outer boundary loop plus any hole
   loops (classified by nesting), which feeds shape-aware packing.
2. **Optional normalization** — with *Normalize Scale* on, each island gets an
   equalizing factor `sqrt( (ΣUV / Σ3D) · 3Dᵢ / UVᵢ )`, which makes texel
   density identical for every island while preserving the total UV footprint.
   The factors are only *computed* here — nothing is applied yet, so they can
   never be disturbed by a later rescale.
3. **Tile balancing** — *all* target objects' islands are pooled and assigned
   to tiles with LPT scheduling (largest-first into the currently emptiest
   tile). Three deterministic orderings (area, longest side, perimeter) are
   tried and the assignment with the best balance is kept; a bounded local
   search then moves/swaps a few of the largest islands between tiles until
   the per-tile extents are as even as possible.
4. **Global rigid layout** — each tile's islands are packed at reference scale
   with a greedy bottom-left placement (90° rotation candidates when enabled),
   growing a bounding square per tile until everything fits. Islands with a
   meaningful outline are placed as their real polygon: the outline is
   simplified with Douglas–Peucker, collision is tested edge-by-edge plus
   point-in-polygon (holes count as empty space), and placement tries two
   phases — first the classic bottom-left candidate set plus *hole
   attractors* (small islands are offered the centre of every hole in a
   placed island), then an expanded set of outline-edge alignments that lets
   concave notches interlock. The margin gap is enforced between offset
   shapes, so two islands keep a true `margin`-wide clearance even where one
   wraps around the other. Islands that are tiny or effectively rectangular
   use the classic rectangle path (identical to earlier releases). One uniform
   scale `S*` then closes the whole grid: every island receives exactly one
   rigid transform — scale `normᵢ · S*`, optional 90° rotation, translation
   into its tile's `[u+margin, …] × [v+margin, …]` interior. Because there is
   a single global factor, relative island sizes are preserved exactly
   (normalize off) or made proportional to real-world size (normalize on), and
   used tiles come out as full as this heuristic family allows. If the content
   exceeds grid capacity, `S* < 1` shrinks everything uniformly — proportions
   intact.
5. **Isolated writeback** — each object is edited in its own edit session: its
   live islands are re-detected and matched to the plan (island fingerprint =
   face count + 3D/UV area + UV bbox size), then moved/scaled/rotated into
   place with bmesh. Objects that cannot be matched or written are left
   untouched and reported in the error list; nothing is ever partially packed.
6. **Verification** — after writeback, every island's bounds are re-measured:
   each must sit strictly inside its assigned unit tile, and no two islands
   may overlap (shape-level triangle test). The operator reports the result.

The design follows UVPackmaster's default strategy — a single global uniform
scale (`MAX_SCALE`) that maximizes island size within the target box, with
simultaneous multi-tile balancing — reimplemented deterministically in pure
Python so it runs inside Blender without any external engine.

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

- Each object is packed in its own isolated edit session; with several objects
  selected, undoing the operation takes one `Ctrl+Z` per object. The original
  object selection is restored afterwards, and when packing started from
  (multi-)edit mode you are returned to it with the same objects being edited.
- **Pinned UVs are not respected** — the layout solver treats every island as
  a rigid body, so pinned islands move with their island like all others.
  This differs from the built-in *Pack Islands* operator on purpose: honoring
  pins would break the global scale guarantee.
- The grid is a layout for your UDIM texture set: paint/assign images with
  matching UDIM tiles (`1001 + u + v·10`) to see the result.
- **Capacity** — packing cannot create area: if the islands' total footprint
  (after normalization, when enabled) exceeds what the grid can hold, every
  island is shrunk uniformly by the same factor. Increase the grid or reduce
  normalize's effect on oversized shells if you need larger UVs.
- The pure-Python solver is deterministic and fast: thousands of simple
  (rectangular) islands pack in well under a second, and typical real-world
  scenes with full outline packing take only a few seconds on typical
  hardware.

## License

GPL-2.0-or-later. Inspired by the UX of UVPackmaster; no UVPackmaster code is
included or called.
