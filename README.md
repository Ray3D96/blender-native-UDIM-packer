# blender-native-UDIM-packer

Repository for the **Native UDIM Packer** Blender addon: packs UV islands of
the selected objects into a user-defined UDIM tile grid, 100% natively
(`bpy` / `bmesh` / built-in operators only). Target platform: **Blender 5.2+**
(developed and tested on 5.2.2 LTS).

## What it does

Automatically packs the UV islands of one or more mesh objects into however
many UDIMs you ask for — e.g. a 2×2 grid gives you tiles **1001, 1002,
1011, 1012**, and a 3×1 grid gives **1001–1003**. Blender's built-in *Pack Islands* operator can
only fill the single 0–1 UV square (one UDIM); this addon extends that same
native packing to a user-defined UDIM count, with standard UDIM numbering
(row stride of 10: 1001…1010, then 1011…).

- **Sequential tile filling** — tile 1001 is packed as densely as possible
  before the next tile opens, so texel density stays maximal for the chosen
  grid.
- **Native only** — built exclusively from `bpy`, `bmesh` and Blender's own
  `uv.pack_islands` operator; no external engines or binaries.
- **Move/scale/rotate only** — islands are never cut, merged or re-unwrapped.
- **Options** — equalize texel density (*Normalize Scale*), allow 90°
  rotation, adjustable margin, pack all selected objects into one shared
  grid, or pack only the UV islands you have selected in the UV editor.

## How to use

1. **Install:** Edit > Preferences > Add-ons > *Install…* → select
   `native_udim_packer-X.Y.Z.zip` → enable **Native UDIM Packer**.
2. **Select** one or more mesh objects that already have a UV map (any
   unwrap works — *Smart UV Project* is a good default).
3. In the **UV Editor**, select all UVs (`A`) and run *UV > Average >
   Islands > Scale*. **Important:** average island scale before use for
   best results — uneven native island scales are a known rough edge of the
   current packer (fix planned).
4. Press `N` and switch the sidebar to the **UDIM** tab.
5. Set the grid size (tiles along X and Y, e.g. 2×2) and any options you
   want, then click **Pack to UDIM Grid**.
6. **Inspect** the result in the UV editor or an Image Editor with a UDIM
   tile image — the islands now live in tiles 1001, 1002, ….

See the [addon README](native_udim_packer/README.md) for the full feature
list, per-option behaviour and how the packing engine works.

## AI Disclosure

Made using Local AI: Qwen 3.8-27B UD_Q6_K_M, Deepseek Harness.

This project was designed, implemented, and tested with the assistance of a
locally-run model (no cloud services). A human set the requirements, drove
testing in live Blender sessions, and made all release decisions; the full
source is available under GPL v3.0 or later for review.

## Layout

| Path | What it is |
|------|------------|
| `native_udim_packer/` | The addon source (the installable package). See its [README](native_udim_packer/README.md) for features, usage and how-it-works. |
| `.scratch/e2e_test.py` | End-to-end test suite: installs the release zip into a real `blender --background` process and runs 58 checks (island-detection ground truth, tile containment, measured zero-overlap raster audit, UDIM numbering spec, sequential-fill ordering, final re-center/growth invariants, selected-islands packing with untouched-island obstacles, multi-object/multi-edit round-trips, UI binding guard). |
| `.scratch/verify_install.py` | Fresh-process install verification (auto-load, version, live settings group, monkey → 5 islands). |
| `.scratch/install_user_blender.py` | Installs the current release zip into a target Blender portable. |
| `dist/` | Release artifacts — **not tracked** (gitignored). One zip per release: `native_udim_packer-X.Y.Z.zip`. |

Not tracked (gitignored): the local `blender-5.2.2-linux-x64/` install used as
the e2e binary, `References/` (UVPackmaster source kept for UX inspiration),
and `QA_Test_Files/` (manual QA `.blend` scenes).

## Running the e2e suite

From this directory:

```sh
./blender-5.2.2-linux-x64/blender --background --python .scratch/e2e_test.py
```

Expected: `SUMMARY: 58/58 passed`. The suite installs from
`dist/native_udim_packer-<version>.zip`, so build the zip first when releasing
(see below).

## Release discipline

1. Bump `bl_info["version"]` in `native_udim_packer/__init__.py` (the panel
   shows a `version X.Y.Z` stamp so the running build is identifiable).
2. Rebuild the zip from the folder, excluding `__pycache__`, and verify each
   entry's hash against the source.
3. Run the full e2e suite to green.
4. Delete the previous release zip from `dist/` — one distinguishable zip per
   release (current: **0.3.0**).
5. Install into target Blenders and verify with a fresh background process
   (`verify_install.py`).

Tags mark released states: `v0.1.4` is the first tagged release.
