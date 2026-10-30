# Known issues — v0.3.0 RC (reported by user)

Addressed in 0.3.1: the scale search converges instead of dying after 48
creeping rounds; Pack Selected Islands pins fixed islands and does not
require Selected Objects in edit mode. Normalize Scale is the in-addon
Average Islands Scale — skipping it keeps relative sizes (a huge island
shrinks the rest with it) but the pack completes.

## 1. Pack breaks unless island scales are averaged first
User report: running "Pack to UDIM Grid" without first applying an
average-island-scale operation in the UV editor produces a broken pack.

Suspected mechanism: with very uneven native island scales and
*Normalize Scale* off, the per-tile `uv.pack_islands(scale=False)` rounds /
the measured feasibility search misbehave (overlap or infeasible rounds).
Need a repro: build UVs where one island's scale is far from the rest
(e.g. manually scale a single island in the UV editor), pack with
normalize off, and observe. Candidate directions: an internal pre-pass that
equalizes island scales before packing (with/without the option), or a
clearer failure mode instead of a broken layout.

## 2. "Selected Objects" effectively required together with "Pack Selected Islands"
User report: with *Pack Selected Islands* on, *Selected Objects* must also be
on; with it off only the active object is packed even when several objects
are in a multi-edit session with selected islands.

Current behaviour: the target set is decided by `use_selected` first
(active-only vs all selected), and `selected_islands` only filters within
that set. Candidate fix: when `selected_islands=True` and packing starts
from (multi-)edit mode, target every object in the current edit session
regardless of `use_selected` — capture already reads per-object selection
for any EDIT object it is given, so this is mostly a target-list change plus
e2e coverage (multi-edit, islands selected on 2+ objects, use_selected off).
