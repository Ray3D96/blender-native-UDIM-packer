"""Standalone tests for native_udim_packer.layout (no Blender needed).

Run:  python3 .scratch/test_layout.py
"""
import importlib.util
import math
import os
import random
import sys

# Load layout.py directly (it is pure stdlib) to avoid the package
# __init__ importing bpy.
_spec = importlib.util.spec_from_file_location(
    "layout",
    os.path.join(os.path.dirname(__file__), "..",
                 "native_udim_packer", "layout.py"))
layout = importlib.util.module_from_spec(_spec)
sys.modules["layout"] = layout
_spec.loader.exec_module(layout)
Item, solve, layout_stats = layout.Item, layout.solve, layout.layout_stats

EPS = 1e-6
FAILS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        FAILS.append(name)


def audit(S, placements, items_by_index, grid_x, grid_y, margin):
    """Containment + gap + exactly-once. Returns (ok, problems)."""
    probs = []
    seen = set()
    per_tile: dict[tuple[int, int], list] = {}
    for p in placements:
        it = items_by_index[p.item]
        if p.item in seen:
            probs.append(f"item {p.item} placed twice")
        seen.add(p.item)
        if not (0 <= p.tile_u < grid_x and 0 <= p.tile_v < grid_y):
            probs.append(f"item {p.item} in out-of-grid tile "
                         f"({p.tile_u},{p.tile_v}) for {grid_x}x{grid_y}")
        # final mapping: uv = tile_origin + margin + content_coord * S;
        # tile (tu, tv) spans [tu+m, tu+1-m] x [tv+m, tv+1-m].
        x0 = p.tile_u + margin + p.x0 * S
        y0 = p.tile_v + margin + p.y0 * S
        x1 = x0 + p.w * S
        y1 = y0 + p.h * S
        if not (p.tile_u + margin - EPS <= x0
                and p.tile_v + margin - EPS <= y0
                and x1 <= p.tile_u + 1.0 - margin + EPS
                and y1 <= p.tile_v + 1.0 - margin + EPS):
            probs.append(f"item {p.item} out of tile bounds "
                         f"[{x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f}]")
        per_tile.setdefault((p.tile_u, p.tile_v), []).append(
            (p.item, x0, y0, x1, y1))
    missing = set(items_by_index) - seen
    if missing:
        probs.append(f"unplaced items: {sorted(missing)[:5]}...")
    for t, rects in per_tile.items():
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                ox = min(a[3], b[3]) - max(a[1], b[1])
                oy = min(a[4], b[4]) - max(a[2], b[2])
                if ox > 1e-9 and oy > 1e-9:
                    probs.append(
                        f"tile {t}: overlap items {a[0]} & {b[0]} "
                        f"(ox={ox:.5f} oy={oy:.5f})")
    return (not probs, probs)


def make_items(seed, n, size_lo=0.02, size_hi=0.3):
    rnd = random.Random(seed)
    items = []
    for i in range(n):
        w = rnd.uniform(size_lo, size_hi)
        h = rnd.uniform(size_lo, size_hi)
        items.append(Item(i, w, h))
    return items


def run_case(name, items, gx, gy, margin, rotate):
    S, placements = solve(items, gx, gy, margin, rotate)
    by_idx = {it.index: it for it in items}
    ok, probs = audit(S, placements, by_idx, gx, gy, margin)
    st = layout_stats(S, placements, by_idx, gx, gy)
    fills = sorted(st["per_tile_fill"].values())
    detail = (f"S={S:.4f} tiles_used={st['tiles_used']}/{gx*gy} "
              f"fill min={fills[0]:.3f} max={fills[-1]:.3f} "
              f"avg={sum(fills)/len(fills):.3f}") if fills else "no placements"
    check(name, ok and S > 0, detail + (" | " + "; ".join(probs[:4])
                                        if probs else ""))
    return S, st


# --- T1-like: 18 rectangles from the e2e mesh (approx real bboxes) --------
t1_items = [
    Item(0, 0.36, 0.30), Item(1, 0.24, 0.20), Item(2, 0.24, 0.20),
    Item(3, 0.18, 0.15), Item(4, 0.18, 0.15), Item(5, 0.16, 0.13),
    Item(6, 0.14, 0.12), Item(7, 0.13, 0.11), Item(8, 0.12, 0.10),
    Item(9, 0.11, 0.09), Item(10, 0.10, 0.08), Item(11, 0.09, 0.07),
    Item(12, 0.08, 0.06), Item(13, 0.07, 0.05), Item(14, 0.06, 0.05),
    Item(15, 0.05, 0.04), Item(16, 0.04, 0.03), Item(17, 0.03, 0.02),
]
S1, st1 = run_case("T1-like 2x2", t1_items, 2, 2, 0.005, True)
# Density measured the principled way: S vs the area upper bound
# S <= sqrt(B * W^2 / sum(a_i)).  A good greedy should reach >= 75% of it
# in the dense regime (N > B).
W1 = 1 - 2 * 0.005
ub1 = math.sqrt(4 * W1 * W1 / sum(i.w * i.h for i in t1_items))
check("T1-like S >= 75% of area bound", S1 >= 0.75 * ub1,
      f"S={S1:.3f} bound={ub1:.3f} ratio={S1/ub1:.2f}")

# --- asymmetric grids: flat index must map column-first (regression) --------
run_case("T1-like 4x1 strip", t1_items, 4, 1, 0.005, True)
_, pl1c = solve(t1_items, 4, 1, 0.005, True)
check("4x1 placements stay in grid row", all(p.tile_v == 0 for p in pl1c),
      f"tiles={sorted({(p.tile_u, p.tile_v) for p in pl1c})}")
_, pl1d = solve(t1_items, 1, 4, 0.005, True)
check("1x4 placements stay in grid column", all(p.tile_u == 0 for p in pl1d),
      f"tiles={sorted({(p.tile_u, p.tile_v) for p in pl1d})}")

# --- single tile: approach native reference --------------------------------
S2, st2 = run_case("T1-like 1x1", t1_items, 1, 1, 0.005, True)
check("1x1 fill >= 0.70 (native ref 0.727)",
      st2["per_tile_fill"] and list(st2["per_tile_fill"].values())[0] >= 0.70,
      f"fill={list(st2['per_tile_fill'].values())}")

# --- big case: ~250 items (user QA scene scale), 2x2 ------------------------
big = make_items(42, 250)
S3, st3 = run_case("big 250-item 2x2", big, 2, 2, 0.005, True)
fills = sorted(st3["per_tile_fill"].values())
check("big: balanced fills (max/min < 1.5)",
      len(fills) == 4 and fills[-1] / max(fills[0], 1e-9) < 1.5,
      f"fills={[round(f, 3) for f in fills]}")

# --- huge grid: 10x32 = 320 tiles, 250 items --------------------------------
S4, st4 = run_case("big 250-item 10x32", big, 10, 32, 0.005, True)

# --- over-capacity: total area >> grid capacity -> S < 1 --------------------
huge = [Item(i, 0.4, 0.4) for i in range(20)]  # 3.2 units^2 into 4 tiles
S5, st5 = run_case("over-capacity 20x0.4sq 2x2", huge, 2, 2, 0.01, True)
check("over-capacity shrinks (S < 1)", S5 < 1.0, f"S={S5:.4f}")

# --- single item ------------------------------------------------------------
one = [Item(0, 0.7, 0.3)]
S6, st6 = run_case("single wide item 1x1", one, 1, 1, 0.005, True)
# width-limited: content extent E = max(w,h) = 0.7 -> S* = W / E, and the
# item's long edge exactly spans the tile interior [m, 1-m].
W = 1 - 0.01
expect_S = W / 0.7
check("single item scale exact", abs(S6 - expect_S) < 1e-9,
      f"S={S6:.6f} expect={expect_S:.6f}")

# --- rotation off: tall items must not rotate --------------------------------
tall = [Item(0, 0.1, 0.8), Item(1, 0.1, 0.8), Item(2, 0.1, 0.8)]
S7, pl7 = solve(tall, 1, 1, 0.005, False)
check("rotate off keeps orientation", all(not p.rotated for p in pl7))
ok7, probs7 = audit(S7, pl7, {t.index: t for t in tall}, 1, 1, 0.005)
check("rotate off valid layout", ok7, "; ".join(probs7[:3]))

# --- determinism -------------------------------------------------------------
r_a = solve(big, 2, 2, 0.005, True)
r_b = solve(big, 2, 2, 0.005, True)
check("deterministic", r_a == r_b)

# --- margin=0 -----------------------------------------------------------------
S8, pl8 = solve(t1_items, 2, 2, 0.0, True)
ok8, probs8 = audit(S8, pl8, {t.index: t for t in t1_items}, 2, 2, 0.0)
check("margin=0 valid", ok8 and S8 > 0, "; ".join(probs8[:3]))

# --- performance ---------------------------------------------------------------
import time  # noqa: E402
t0 = time.perf_counter()
for _ in range(5):
    solve(make_items(7, 1000), 10, 10, 0.005, True)
dt = (time.perf_counter() - t0) / 5
check("perf: 1000 items 10x10 < 2s", dt < 2.0, f"{dt*1000:.0f} ms")

print()
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("RESULT: ALL PASS")
