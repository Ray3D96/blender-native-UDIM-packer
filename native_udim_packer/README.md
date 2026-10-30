# Native UDIM Packer

A 100% native Blender addon that packs the UV islands of your active (or all
selected) objects into a **user-defined UDIM tile grid** — in the spirit of
UVPackmaster, but built exclusively from `bpy`, `bmesh` and Blender's own
operators. No external engines, binaries or third-party libraries.

Licensed under GPL v3.0 or later.

## Features

- **UDIM grid layout** — choose the tile count along U and V (1×1, 2×2, 4×1,
  3×2, … up to 10×32). The grid you set is actually used: one oversized shell
  takes a tile of its own instead of swallowing every later tile. All islands
  then share **one** scale, set by the fullest tile, so texel density stays
  the same across the whole set.
- **Standard UDIM numbering** — tile (0,0) is UDIM **1001**, tile (1,0) is
  **1002**, …, tile (9,0) is **1010**; each higher row adds 10: row 2 starts
  at **1011**, row 3 at **1021**. X is capped at 10 because a UDIM row is 10
  tiles wide. Every island is shifted by whole integers into its tile's
  `[u, u+1] × [v, v+1]` region.
- **No overlaps** — each used tile is placed with Blender's own *Pack
  Islands* operator (`uv.pack_islands`), then re-read and checked with an
  exact polygon test. Islands from different objects are packed in the same
  call when they share a tile, so they cannot land on each other. A final
  re-center (and, when there is room, one shared growth) is a single
  move-and-scale per tile, which cannot create a new overlap.
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
- **90° rotation (optional)** — when enabled, the built-in packer may rotate
  *individual* islands by 90° (cardinal directions) inside their tile when
  that saves space; when disabled every island keeps its current orientation.
  Either way each island keeps a single rigid transform (scale + optional
  rotation + translation), so shapes are never distorted or stretched.
- **Multi-object** — pack several selected mesh objects into the same grid in
  one click. All objects share one texture set: their islands are assigned to
  the whole grid together and **never overlap, even between different
  objects** (each object keeps its own UV map).
- **Fast** — island detection and tile assignment run in Python; the actual
  placement is Blender's C-level packer, called once per used tile. A scene
  that took minutes with early builds of this addon packs in seconds.
- **Native building blocks only** — `bmesh` seam-aware island detection, a
  small deterministic Python assignment, and the built-in `uv.pack_islands`
  operator for placement. No external engines, no subprocess calls: the same
  input always produces the same layout.
- **Undoable** — the operator is registered with `UNDO` and pushes a labeled
  undo step ("Native UDIM: Pack to Grid").

## Requirements

- Blender **5.2 or newer** (developed and tested on 5.2.2 LTS).
- The objects need an **active UV map**. No other dependencies.

## Installation

1. In Blender open **Edit → Preferences → Add-ons** (or *Extensions* in the
   new-style UI).
2. Click **Install from Disk…** and select `native_udim_packer-0.3.2.zip`
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
> startup (this release: **0.3.2**).

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
   | **UDIM Grid X/Y** | Tile count along U / V. The panel lists the UDIM numbers (a 2×2 is 1001, 1002, 1011, 1012 — rows stride by 10). |
   | **Normalize Scale** | Make every shell proportional to its 3D size — uniform texel density across all packed objects, like *Average Islands Scale*.                  |
   | **Allow 90° Rotation** | Let the built-in packer rotate individual islands by 90° when that saves space. |
   | **Margin**        | Gap kept between islands and around tile edges, as a fraction of one tile (0.01 = 1%). |
   | **Selected Objects** | Pack all selected meshes; off = active object only. Ignored while *Pack Selected Islands* is on in edit mode — every mesh in that edit session is considered. |
   | **Pack Selected Islands** | Pack only the UV islands you have selected in the UV editor; every other island keeps its UVs exactly and is treated as an obstacle the new layout avoids (see below). |

5. Click **Pack to UDIM Grid**. The status bar reports how many islands were
   packed into which tiles/UDIMs. Undo with `Ctrl+Z`.

### Packing only selected islands

*Pack Selected Islands* repacks just the islands you picked in the UV editor,
leaving everything else exactly where it is — handy for fixing one crowded
region without disturbing a layout that already works:

1. Enter **Edit mode** (multi-edit with several objects) and select islands
   in the UV editor — click them in *Islands* selection mode or box-select.
   An island counts as selected when at least one of its faces is selected,
   so a partial selection still moves the whole island.
2. Enable **Pack Selected Islands** and click **Pack to UDIM Grid**. Only the
   selected islands are packed (sequential tile filling as usual); *Normalize
   Scale* in this mode equalizes texel density over the selected set only.
3. Untouched islands act as fixed obstacles: every search round and the final
   growth pass verify against them with the same exact overlap test used for
   packed islands, so the result never overlaps — if the free space is too
   small, the engine shrinks the content instead of colliding.
4. Afterwards you are back in edit mode with your original UV selection
   restored. Running the option in object mode (no live selection) or with
   nothing selected reports a clear error and changes nothing.

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
   islands instead of one island per face. Each island's bounding box and
   area are recorded once; nothing about the geometry is changed from here on.
2. **Optional normalization** — with *Normalize Scale* on, each island gets an
   equalizing factor `sqrt( (ΣUV / Σ3D) · 3Dᵢ / UVᵢ )`, which makes texel
   density identical for every island while preserving the total UV footprint.
   The factors are only *computed* here — nothing is applied yet, so they can
   never be disturbed by a later rescale.
3. **Tile assignment** — *all* target objects' islands are pooled (or only
   the selected ones, in *Pack Selected Islands* mode) and sorted
   largest-first. Each island goes to the earliest tile that still has a
   share of the total area, so the grid you asked for is actually used: one
   oversized shell takes a tile of its own instead of swallowing the rest.
4. **Measured fit, one shared scale** — each used tile is packed once by
   `uv.pack_islands` with `scale=True`, so Blender fills that tile for real
   and reports how large the islands got. Every tile is then scaled back to
   the *smallest* of those scales. Texel density stays identical across
   UDIMs, and the fullest tile is what sets it. Up to six follow-up moves
   shift the smallest island off the bottleneck tile onto a looser one, and
   a move is kept only when the shared scale rises by at least 5%.
5. **Native per-tile placement** — each tile is packed in one multi-object
   edit session covering every object that contributes islands to it, so
   islands from different objects cannot overlap. The result is checked with
   an exact polygon test. Content is then shifted by whole integers into its
   UDIM (`1001 + u + v·10`) and re-centered; if any tile still has room
   inside the margin, every tile grows by the same factor until the tightest
   axis is full.
6. **Pack Selected Islands** — this mode keeps the scale search instead of
   the measured fit, because the islands you did not select must not move.
   They are pinned so the native packer goes around them, and a tile they
   already fill is given less capacity. Every candidate is overlap-tested
   against them; if even the re-center would collide, it is skipped.
7. **Atomicity** — if anything fails mid-pack, every object's UVs are
   restored from the pre-pack snapshot and an error is reported. Nothing is
   left half-packed.

The design follows UVPackmaster's default strategy — one global uniform scale
that maximizes island size inside the tiles you asked for — reimplemented
natively. Assignment is plain Python; every island's shape is placed by
Blender's own packer.

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

- Each used tile is packed in one shared multi-object edit session covering
  every object that contributes islands to it; with several objects selected,
  undoing the operation takes one `Ctrl+Z` per object. The original object
  selection is restored afterwards, and when packing started from (multi-)edit
  mode you are returned to it with the same objects being edited.
- **Pinned UVs** — placement is delegated to the built-in packer per tile, so
  pinned vertices inside a packed tile behave exactly as they do for the
  regular *Pack Islands* operator.
- The grid is a layout for your UDIM texture set: paint/assign images with
  matching UDIM tiles (`1001 + u + v·10`) to see the result.
- **Capacity** — packing cannot create area: if the islands' total footprint
  (after normalization, when enabled) exceeds what the grid can hold, every
  island is shrunk uniformly by the same factor. Increase the grid or reduce
  normalize's effect on oversized shells if you need larger UVs. More UDIM
  tiles naturally let the largest islands stay larger.
- **Deterministic** — the assignment and scale search are fully deterministic;
  placement uses Blender's own packer, which is deterministic for a given
  selection and margin. The same input always produces the same layout.

## Changelog

- **0.3.2** — measured tile fit. Each tile is packed once with Blender's
  own fill (`scale=True`), then islands are moved off the bottleneck tile
  while every island keeps the same texel density (at most six moves,
  and only when a move gains at least 5%). The grid you ask for is
  actually used: a single oversized shell no longer swallows the later
  tiles. Fixed-island packing still uses the scale search, because those
  islands have to stay put.
- **0.3.1** — the scale search no longer gives up after a long creep.
  A candidate that overflows or overlaps now drops by a real step and the
  gap is binary-searched, so packs that used to die with "scale search did
  not converge after 48 rounds" finish. Margin is a fraction of the tile
  (what the slider says). In *Pack Selected Islands*, fixed islands are
  pinned so the native packer goes around them, and a tile they already
  fill loses capacity so the selection spills onto later tiles instead of
  stacking on top. That option also no longer requires *Selected Objects*:
  in edit mode every mesh in the session is considered. Uneven island
  scales no longer need a manual Average Islands Scale pass for the pack
  to succeed; turn on *Normalize Scale* when you want even texel density.
- **0.3.0** — new option *Pack Selected Islands*: pack only the UV islands
  selected in the UV editor (an island counts as selected when at least one
  of its faces is selected); every other island keeps its UVs exactly. In
  this mode the unselected islands are fixed obstacles: every scale-search
  round and the final re-center/growth pass verify the packed content
  against them with the same exact overlap test used for packed islands —
  the growth factor is bisected down to the largest clean value, and if even
  the pure re-centering translation would collide, no transform is applied
  at all. *Normalize Scale* equalizes texel density over the selected set
  only. Needs a live selection: running the option in object mode, or with
  nothing selected, reports a clear error and changes nothing; on exit the
  original UV selection is restored. The result dict additionally reports
  `packed_islands` / `untouched_islands`.
- **0.2.1** — final re-center + growth pass. After the scale search finishes,
  each used tile's content is re-centered on its tile center; when headroom
  remains inside the margin box, every tile is then scaled by one global
  uniform factor, limited by the tightest tile/axis: the UDIM with the least
  room to grow sets the size for all the others, so texel density stays equal
  across tiles while the bottleneck axis reaches its margin boundary. If a
  dense packing already spans wider than the [m, 1-m] box - `uv.pack_islands`
  treats its margin as island-to-island spacing only - the factor stays at
  1.0 and only the re-centering is applied. It is a single similarity
  transform per tile (move + scale about the content center), so it costs
  milliseconds, never re-packs, and cannot create any new overlap. The
  reported global scale now includes this growth factor (`stretch_factor` is
  reported separately).
- **0.2.0** — new packing engine. Placement is now done by Blender's built-in
  `uv.pack_islands` operator (once per used tile, with every object sharing
  that tile packed together in one multi-object edit session), which
  eliminates the overlaps that could occur with the earlier pure-Python
  placement and makes packing several times faster. Tiles are filled
  sequentially (1001 first, then 1002, …) instead of load-balanced, matching
  how UDIM sets are usually painted; a measured global-scale search maximizes
  texel density for the chosen tile count — it starts at the largest possible
  scale and only spreads content over more tiles when even the greediest
  filling overflows. Every placement round is additionally re-read and
  verified with an exact polygon-overlap test across all island pairs in each
  tile; a dirty round is rejected and the content uniformly shrunk, so
  overlapping islands can never be written. *Allow 90° Rotation* now means
  the built-in packer may rotate individual islands (cardinal directions);
  when off, orientations are preserved. On failure, UVs are restored from a
  pre-pack snapshot.
- **0.1.6** — shape-aware placement (outline polygons with holes), balanced
  tile rebalance. Superseded by the 0.2.0 engine.
- **0.1.5** — multi-object packing into one shared grid, UDIM spec numbering.
- **0.1.4** — first tagged release: single-object UDIM grid packing.

## License

GPL-3.0-or-later. Inspired by the UX of UVPackmaster; no UVPackmaster code is
included or called.
