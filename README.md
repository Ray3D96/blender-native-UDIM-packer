# blender-uv-packer

Repository for the **Native UDIM Packer** Blender addon: packs UV islands of
the selected objects into a user-defined UDIM tile grid, 100% natively
(`bpy` / `bmesh` / built-in operators only). Target platform: **Blender 5.2+**
(developed and tested on 5.2.2 LTS).

## Layout

| Path | What it is |
|------|------------|
| `native_udim_packer/` | The addon source (the installable package). See its [README](native_udim_packer/README.md) for features, usage and how-it-works. |
| `.scratch/e2e_test.py` | End-to-end test suite: installs the release zip into a real `blender --background` process and runs 39 checks (island-detection ground truth, tile containment, no-overlap audits, UDIM numbering spec, multi-object/multi-edit round-trips, UI binding guard). |
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

Expected: `SUMMARY: 39/39 passed`. The suite installs from
`dist/native_udim_packer-<version>.zip`, so build the zip first when releasing
(see below).

## Release discipline

1. Bump `bl_info["version"]` in `native_udim_packer/__init__.py` (the panel
   shows a `version X.Y.Z` stamp so the running build is identifiable).
2. Rebuild the zip from the folder, excluding `__pycache__`, and verify each
   entry's hash against the source.
3. Run the full e2e suite to green.
4. Delete the previous release zip from `dist/` — one distinguishable zip per
   release (current: **0.1.4**).
5. Install into target Blenders and verify with a fresh background process
   (`verify_install.py`).

Tags mark released states: `v0.1.4` is the first tagged release.
