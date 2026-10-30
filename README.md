# Native UDIM Packer

A Blender addon that packs UV islands into **as many UDIM tiles as you ask for**, using only Blender itself (`bpy`, `bmesh`, and the built-in *Pack Islands* operator). No external engines or binaries.

Blender's own *Pack Islands* fills a single 0–1 square (one UDIM). This addon does that same native pack across a grid you choose, and keeps **one texel density** for every island.

**Blender 5.2 or newer.** Developed and tested on 5.2.2 LTS. Licensed under [GPL v3.0 or later](LICENSE).

## UDIM numbers

A UDIM row is 10 tiles wide. The addon follows that, so the numbers are not 1001, 1002, 1003, 1004 in a square.

| Grid | Tiles you get |
|------|----------------|
| 1×1 | **1001** |
| 3×1 | **1001, 1002, 1003** |
| 1×3 | **1001, 1011, 1021** |
| 2×2 | **1001, 1002, 1011, 1012** |
| 4×1 | **1001, 1002, 1003, 1004** |

X (tiles across) is capped at 10. Y (rows) goes up to 32. The UV Editor sidebar lists the actual numbers for small grids, so you don't have to calculate them.

## Install

1. Download `native_udim_packer-0.3.2.zip` from the [release](https://github.com/Ray3D96/blender-native-UDIM-packer/releases).
2. In Blender: **Edit → Preferences → Add-ons → Install from Disk…** and pick the zip.
3. Enable **Native UDIM Packer**.
4. Quit Blender and start it again. An upgrade does not hot-reload an addon that is already enabled.

The panel is in the **UV Editor**, sidebar (`N`) → **UDIM**. The first line is a version stamp (`version 0.3.2`). The system console also prints `Native UDIM Packer v0.3.2 registered` at startup.

## How to use

1. Select one or more mesh objects that already have a UV map. *Smart UV Project* is a fine starting unwrap. The addon never re-unwraps, cuts seams, or splits an island.
2. Open the **UV Editor**, press `N`, and open the **UDIM** tab.
3. Set **Tiles X** and **Tiles Y**.
4. Choose the options below, then click **Pack to UDIM Grid**.
5. Look at the UV Editor, or at an Image Editor with a UDIM tile image. Undo is one step: `Ctrl+Z`.

Packing from **Edit mode** (including multi-object edit) returns you to that same edit session when it finishes.

### Options

| Option | What it does |
|--------|----------------|
| **Normalize Scale** | Gives every island the same texel density, like Blender's *Average Islands Scale*. It runs as part of the pack, so you do not have to average scales by hand first. Off keeps your current relative sizes: one oversized island scales everything else down with it, and the pack still finishes. |
| **Allow 90° Rotation** | Lets individual islands turn by 90° when that fits better. Off keeps each island's current orientation. Shapes are never stretched. |
| **Margin** | Gap between islands, as a fraction of one tile. `0.01` is 1% of the tile. |
| **Selected Objects** | On: every selected mesh shares one grid. Off: only the active object. |
| **Pack Selected Islands** | Packs only the UV islands selected in the UV editor. An island counts as selected when at least one of its faces is. Everything else stays exactly where it is and is treated as an obstacle. In edit mode this ignores *Selected Objects* and looks at every mesh in the edit session. It needs a live selection: object mode, or nothing selected, reports an error and changes nothing. Your original UV selection is restored afterwards. |

### What the result should look like

- Every packed island sits inside one tile of the grid. Islands are not cut across a tile border.
- Islands do not overlap, including islands that belong to different objects.
- All packed islands share one scale. The fullest tile sets that scale, so the other tiles can have a little empty room. That room is the cost of keeping texel density even. Turning on more tiles lets the islands get larger.
- With *Normalize Scale* off, the size relationship between islands is unchanged. With it on, islands are proportional to their 3D surface area.

## Changelog

### 0.3.2

Each tile is packed once with Blender's own fill, then every island is scaled back to the fullest tile's scale so texel density stays uniform. Up to six follow-up moves shift a small island off the crowded tile, and a move is kept only when the shared scale actually improves. The grid size you set is used: one oversized shell no longer swallows the later tiles.

### 0.3.1

Packs that used to fail with "scale search did not converge after 48 rounds" now finish. The margin slider is a fraction of the tile, which is what it always claimed to be. *Pack Selected Islands* pins the islands that stay put so the packer goes around them, and it no longer also requires *Selected Objects* while you are in edit mode.

### 0.3.0

*Pack Selected Islands*: pack only the islands selected in the UV editor. Unselected islands keep their UVs exactly and block the new layout. If even sliding the packed islands to the tile center would hit them, they are left alone.

### Earlier

0.2.1 added the final re-center and shared growth pass. 0.2.0 switched placement to Blender's `uv.pack_islands` (once per tile, several objects together) and sequential UDIM filling. 0.1.4 was the first tagged release.

The [addon README](native_udim_packer/README.md) has the full option list, how the engine works, and the older notes.

## AI disclosure

Made using local AI: Qwen 3.8-27B UD_Q6_K_M, Deepseek Harness.

A locally run model designed, implemented, and tested this project. No cloud service was used. A human set the requirements, tested it in Blender, and made the release decisions. The source is GPL v3.0 or later so it can be reviewed.

## For developers

| Path | What it is |
|------|------------|
| `native_udim_packer/` | The installable addon. |
| `.scratch/e2e_test.py` | End-to-end suite. Installs the release zip into `blender --background` and runs 58 checks. |
| `.scratch/test_layout.py` | Pure-Python tests for tile assignment and the overlap predicates. |
| `dist/` | Release zips. Not tracked. One zip per release: `native_udim_packer-X.Y.Z.zip`. |

Not tracked: the local `blender-5.2.2-linux-x64/` binary, `References/`, and `QA_Test_Files/`.

From this directory, after building the zip:

```sh
./blender-5.2.2-linux-x64/blender --background --python .scratch/e2e_test.py
```

Expected: `SUMMARY: 58/58 passed`.

```sh
python3 .scratch/test_layout.py
```

To release: bump `bl_info["version"]` in `native_udim_packer/__init__.py`, rebuild the zip from that folder (no `__pycache__`), run both test commands, and keep a single zip in `dist/`. Current release: **0.3.2**.
