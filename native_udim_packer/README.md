# Native UDIM Packer

A 100% native Blender addon that packs the UV islands of your active (or all
selected) objects into a **user-defined UDIM tile grid** — in the spirit of
UVPackmaster, but built exclusively from `bpy`, `bmesh` and Blender's own
operators. No external engines, binaries or third-party libraries.

## Features

- **UDIM grid layout** — choose the tile count along U and V (1×1, 2×2, 4×1,
  3×2, … up to 10×32). Tiles are filled **sequentially**: the packer fills
  tile 1001 as densely as it can before opening 1002, then 1003, and so on in
  row-major order — no island is placed in a later tile while an earlier one
  still has room. A global scale search then makes the islands as large as
  the grid allows (maximum texel density for the chosen tile count).
- **Standard UDIM numbering** — tile (0,0) is UDIM **1001**, tile (1,0) is
  **1002**, …, tile (9,0) is **1010**; each higher row adds 10: row 2 starts
  at **1011**, row 3 at **1021**. X is capped at 10 because a UDIM row is 10
  tiles wide. Every island is shifted by whole integers into its tile's
  `[u, u+1] × [v, v+1]` region.
- **No overlaps, guaranteed** — each used tile is placed with Blender's own
  *Pack Islands* algorithm (the built-in `uv.pack_islands` operator), which
  never lets islands overlap and respects the margin between them. As a
  second line of defense the addon re-reads the UVs it just wrote and runs an
  exact polygon-overlap test across every pair of islands in each tile; if a
  round ever comes back dirty, it is rejected and the content is uniformly
  shrunk until the pack is clean. The final re-center/growth pass (step 5)
  applies one similarity transform per tile — a move + uniform scale about
  the tile's own content center — which preserves all relative geometry
  inside each tile, so it cannot create an overlap either. The guarantee
  holds within a tile and across objects: co-packed tiles are verified after
  every placement round, so an island can never be written on top of another
  one's space.
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
  small deterministic Python search (first-fit-decreasing tile assignment +
  measured global-scale refinement), and the built-in `uv.pack_islands`
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
2. Click **Install from Disk…** and select `native_udim_packer-0.3.0.zip`
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
> startup (this release: **0.3.0**).

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
   | **Allow 90° Rotation** | Let the built-in packer rotate individual islands by 90° when that saves space. |
   | **Margin**        | Gap kept between islands and around tile edges, as a fraction of one tile (0.01 = 1%). |
   | **Selected Objects** | Pack all selected meshes; off = active object only.                   |
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
3. **Sequential tile assignment** — *all* target objects' islands are pooled
   (or only the selected ones, in *Pack Selected Islands* mode) and sorted
   largest-first (first-fit-decreasing). Each island goes to the
   **earliest** tile that still accepts it: an empty tile always accepts an
   island whose bounding box spans at most one tile interior; a used tile
   accepts while its assigned area stays below the current load target
   (starting at ~92% of capacity — see step 4). The result is exactly the
   requested filling order — 1001 full before 1002 opens, 1002 full before
   1003 — with the largest islands anchored in the earliest tiles and
   smaller ones filling the remainder.
4. **Global scale search** — the search starts at `S_max`, the scale at which
   the largest island exactly spans one tile interior (the biggest islands
   stay as big as physically possible). At every candidate scale the
   assignment is retried with progressively lower per-tile load targets
   (~92%, 85%, 75%, … of capacity), greediest first: the greediest filling
   that still fits wins, so the first UDIM is filled before later ones open —
   and only when even the greedy filling overflows does content spread to
   more tiles, which is exactly what lets the largest islands stay large
   when several UDIMs are available. One *round* = assign the grid at that
   scale, place every used tile natively (step 5), then **measure** the real
   post-pack extent of each tile. If every measured extent fits its tile,
   the scale is final; otherwise the scale is shrunk in proportion to the
   worst overflow and a fresh round starts again from the greediest target.
   The search converges in one or a few rounds and always ends with a
   measured-feasible layout — there is no analytic estimate that could be
   wrong about what fits.
5. **Native per-tile placement** — each used tile is packed in a single
   multi-object edit session that covers *every* object contributing islands
   to that tile: the scaled UVs of all members are written from the snapshot,
   only this tile's faces are selected, and exactly one `uv.pack_islands`
   call places them — shape-aware, cardinal rotation when enabled, margin
   respected, `scale=False` so sizes are never touched. Packing a tile's
   islands from different objects in one session is what makes cross-object
   overlap impossible: the native packer sees every island of the tile and
   avoids all of them. The packed result is then re-read and verified with
   an exact polygon-overlap test across every pair of islands in the tile —
   if it ever comes back dirty, the round is rejected and the scale search
   shrinks the content instead. Only a clean tile is shifted by whole
   integers into its `[u, u+1] × [v, v+1]` region. Because placement is
   done by Blender's own packer and every round is verified afterwards,
   islands inside a tile cannot overlap — and because the scale search
   re-measures after every round, no island can end up outside its tile
   either. After the final round, each used tile's content is re-centered on
   its tile center; when headroom remains inside the margin box, all tiles
   are then grown by one uniform factor limited by the tightest tile/axis,
   so the bottleneck UDIM is maxed out while texel density stays equal
   across tiles: one similarity transform per tile, no re-packing, no new
   overlaps.
6. **Atomicity** — the search rounds *are* the writeback: the final round
   leaves every object's mesh holding its finished placement, so no second
   pass can disturb it. If anything fails mid-pack, every object's UVs are
   restored from the pre-pack snapshot and an error is reported — nothing is
   ever partially packed.
7. **Verification** — after writeback, every island's bounds are re-measured:
   each must sit strictly inside its assigned unit tile. The operator reports
   the result.

The design follows UVPackmaster's default strategy — a single global uniform
scale (`MAX_SCALE`) that maximizes island size within the target box, with
sequential multi-tile filling — reimplemented natively: the assignment and
scale search are small deterministic Python, while all shape handling is done
by Blender's own packer.

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

GPL-2.0-or-later. Inspired by the UX of UVPackmaster; no UVPackmaster code is
included or called.
