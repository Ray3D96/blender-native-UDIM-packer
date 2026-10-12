# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit tests for the v4 layout module (pure Python, no bpy).

Run with any plain Python 3.10+:  python3 .scratch/test_layout.py
Loads native_udim_packer/layout.py directly from its file path so the
package __init__ (which imports bpy) is never executed.
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT = os.path.join(HERE, "..", "native_udim_packer", "layout.py")

spec = importlib.util.spec_from_file_location("udim_layout", LAYOUT)
L = importlib.util.module_from_spec(spec)
sys.modules["udim_layout"] = L   # required by dataclasses on 3.14+
spec.loader.exec_module(L)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f" FAIL {name}  {detail}")


I = L.Item

# ---------------------------------------------------------------- tile_order
check("tile_order 3x1", L.tile_order(3, 1) == [(0, 0), (1, 0), (2, 0)])
check("tile_order 2x2", L.tile_order(2, 2) == [(0, 0), (1, 0), (0, 1), (1, 1)])
check("tile_order 1x3", L.tile_order(1, 3) == [(0, 0), (0, 1), (0, 2)])

# ------------------------------------------------------------------ max_scale
check("max_scale spans interior",
      abs(L.max_scale(0.98, [I(0, 0.49, 0.2)]) - 2.0) < 1e-12)
check("max_scale uses longer side",
      abs(L.max_scale(1.0, [I(0, 0.2, 0.5), I(1, 0.6, 0.1)]) - (1.0 / 0.6)) < 1e-12)
check("max_scale empty", L.max_scale(1.0, []) == 1.0)
check("max_scale degenerate", L.max_scale(1.0, [I(0, 0.0, 0.0)]) == 1.0)

# ----------------------------------------------------------------- assign_ffd
# Single tile: everything in it when capacity allows.
a = L.assign_ffd([I(0, 1, 1), I(1, 0.5, 0.5)], 1, 2.0)
check("ffd single tile", a == {0: 0, 1: 0}, str(a))

# Two tiles, FFD order: largest first into tile 0; second island goes to the
# earliest tile that accepts it (tile 0 if load allows).
a = L.assign_ffd([I(0, 0.5, 0.5), I(1, 0.4, 0.4)], 2, 1.0)
check("ffd fill first tile", a == {0: 0, 1: 0}, str(a))

# Capacity tight: 0.5^2 + 0.4^2 = 0.41 > eta*cap=0.92 -> second goes to tile 1.
a = L.assign_ffd([I(0, 0.9, 0.9), I(1, 0.5, 0.5)], 2, 1.0)
check("ffd opens second tile", a == {0: 0, 1: 1}, str(a))

# Sequential filling: with 3 tiles and content that needs all three, the
# earliest tiles are full before the last one is opened.
items = [I(0, 0.9, 0.9), I(1, 0.6, 0.6), I(2, 0.6, 0.6), I(3, 0.5, 0.5)]
a = L.assign_ffd(items, 3, 1.0)
check("ffd sequential", a is not None and a[0] == 0 and max(a.values()) == 2
      and len(set(a.values())) == 3, str(a))

# Impossible: one island bigger than any tile capacity.
a = L.assign_ffd([I(0, 2.0, 2.0)], 3, 1.0)
check("ffd impossible -> None", a is None)

# Area fits but the long side does not span the interior: must NOT be
# placed into an empty tile (geometric fit, not area, decides).
a = L.assign_ffd([I(0, 1.2, 0.5)], 2, 1.0)   # area .6 < cap 1.0, maxdim 1.2 > 1.0
check("ffd maxdim-alone rejection", a is None, str(a))

# Impossible at capacity but possible with more tiles.
items = [I(k, 0.9, 0.9) for k in range(4)]
a = L.assign_ffd(items, 2, 1.0)
check("ffd overflow -> None", a is None, str(a))

# Empty items -> empty assignment (not None).
check("ffd empty", L.assign_ffd([], 3, 1.0) == {})

# Determinism: same input twice -> same output.
items = [I(k, 0.3 + 0.01 * k, 0.2 + 0.01 * k) for k in range(20)]
a1 = L.assign_ffd(items, 4, 1.0)
a2 = L.assign_ffd(items, 4, 1.0)
check("ffd deterministic", a1 == a2)

# Tie-break: equal area -> longer side first (index order otherwise).
items = [I(0, 0.5, 0.2), I(1, 0.4, 0.25), I(2, 0.5, 0.2)]  # areas .1/.1/.1
a = L.assign_ffd(items, 1, 1.0)
check("ffd tie-break", a == {0: 0, 1: 0, 2: 0}, str(a))

# --------------------------------------------------------------- next_scale
m = 0.02
interior = 1.0 - 2 * m          # 0.96
hi = 1.0 - m                    # 0.98

s, ok = L.next_scale(1.0, interior, [(0.0, 0.0, 0.5, 0.5)])
check("next_scale fit", ok and s == 1.0)

s, ok = L.next_scale(1.0, interior, [(0.0, 0.0, hi - 1e-5, 0.5)])
check("next_scale at-bound fits (tol)", ok and s == 1.0, f"{s} {ok}")

s, ok = L.next_scale(1.0, interior, [(0.0, 0.0, hi + 1e-3, 0.5)])
check("next_scale overflow shrinks", not ok and s < 1.0)
# expected factor: (hi / (hi+1e-3)) * 0.995
exp = 1.0 * (hi / (hi + 1e-3)) * 0.995
check("next_scale overflow magnitude", abs(s - exp) < 1e-12, f"{s} vs {exp}")

# y-axis overflow dominates.
s, ok = L.next_scale(1.0, interior, [(0.0, 0.0, 0.5, hi + 0.1)])
check("next_scale y overflow", not ok and abs(s - hi / (hi + 0.1) * 0.995) < 1e-12)

# Worst tile dominates when several overflow.
s, ok = L.next_scale(1.0, interior, [(0, 0, hi + 0.05, 0), (0, 0, hi + 0.2, 0)])
check("next_scale worst tile", not ok and abs(s - hi / (hi + 0.2) * 0.995) < 1e-12)

# Low-side-only oddity cannot claim feasibility via extent growth; the
# defensive branch keeps shrinking deterministically.
s, ok = L.next_scale(1.0, interior, [(0.0, 0.0, hi + 1e-3, hi + 2e-3)])
check("next_scale double overflow", not ok and s < 1.0)

# -------------------------------------------------------------------- solve
# Fake oracle: each tile's extent grows linearly with S (content scales up),
# with a packing-efficiency factor so the search must actually shrink.
def make_oracle(items, n_tiles, k):
    def oracle(assign, S):
        ext = [None] * n_tiles
        for t in sorted(set(assign.values())):
            load = sum(it.area for it in items if assign[it.index] == t)
            v = load * S * k
            e = ext[t] if ext[t] is not None else [0.0, 0.0, 0.0, 0.0]
            e[2] = max(e[2], v)
            e[3] = max(e[3], v * 0.8)
            ext[t] = e
        return ext
    return oracle

items = [I(0, 0.5, 0.5), I(1, 0.4, 0.4), I(2, 0.3, 0.3)]
oracle = make_oracle(items, 2, k=3.0)
res = L.solve(items, 2, 1, m, oracle)
S_final, assign_final, rounds, feasible = res
check("solve converges", feasible, f"S={S_final} rounds={rounds}")
# The real invariant: re-measuring the final state must be feasible.
_, ok_final = L.next_scale(S_final, interior,
                           [e for e in oracle(assign_final, S_final)
                            if e is not None])
check("solve final state feasible", ok_final, f"S={S_final}")
check("solve rounds small", rounds <= 6, f"rounds={rounds}")

# Single tile, content that fits at S_max immediately.
items1 = [I(0, 0.4, 0.3)]
res = L.solve(items1, 1, 1, m, lambda a, S: [[0.0, 0.0, 0.5, 0.5]])
check("solve immediate fit", res[3] and res[2] == 1
      and abs(res[0] - (interior / 0.4)) < 1e-9)

# Convergence failure raises RuntimeError (oracle never fits).
def oracle_never(assign, S):
    return [[0.0, 0.0, 5.0, 5.0]]
try:
    L.solve([I(0, 0.5, 0.5)], 1, 1, m, oracle_never, max_rounds=5)
    check("solve non-convergence raises", False)
except RuntimeError:
    check("solve non-convergence raises", True)

# Determinism of the full search.
oracle_det = make_oracle(items, 3, k=2.0)
r1 = L.solve(items, 3, 1, m, oracle_det)
r2 = L.solve(items, 3, 1, m, oracle_det)
check("solve deterministic", r1[0] == r2[0] and r1[1] == r2[1])

# Scale-invariant overflow (packer efficiency bound below the greedy FFD
# load target): shrinking S alone can never fix a greedily filled tile;
# only spreading the content thinner can.  The full eta ladder finds that
# spread within one shrink step and lands near S_max, while a greedy-only
# search crawls down to a much smaller scale.
decay_items = [I(0, 0.4, 0.4)] + [I(k + 1, 0.05, 0.05) for k in range(30)]

def oracle_load(assign, S):
    cap = (interior / S) ** 2
    ext = [None] * 3
    for t in sorted(set(assign.values())):
        load = sum(it.area for it in decay_items if assign[it.index] == t)
        v = hi * (load / (0.85 * cap)) ** 0.5
        e = ext[t] if ext[t] is not None else [0.0, 0.0, 0.0, 0.0]
        e[2] = max(e[2], v)
        e[3] = max(e[3], v)
        ext[t] = e
    return ext

res_d = L.solve(decay_items, 3, 1, m, oracle_load)
check("solve ladder converges", res_d[3], f"rounds={res_d[2]}")
check("solve ladder lands near S_max", res_d[0] > 2.0, f"S={res_d[0]:.4f}")
check("solve ladder fast", res_d[2] <= 3, f"rounds={res_d[2]}")
res_nd = L.solve(decay_items, 3, 1, m, oracle_load, max_rounds=48,
                 etas=(0.92,))      # greedy ladder entry only
check("solve greedy-only lands smaller",
      res_nd[3] and res_nd[0] < res_d[0] * 0.95,
      f"ladder S={res_d[0]:.4f} vs greedy S={res_nd[0]:.4f}")
print(f"  (info) ladder: S={res_d[0]:.4f} rounds={res_d[2]} | "
      f"greedy-only: S={res_nd[0]:.4f} rounds={res_nd[2]}")

# ------------------------------------------------------------- integration-ish
# Simulate the real QA-scale scenario: 268 islands, 3 tiles, margin 0.
# Oracle approximates the native packer: a tile overflows iff its assigned
# total reference area * S^2 exceeds the interior area (plus packing loss).
import math
rng_items = []
a = 0.5
for k in range(268):
    w = a * (0.05 + ((k * 37) % 100) / 100.0 * 0.95)
    h = w * (0.4 + ((k * 53) % 100) / 100.0 * 0.6)
    rng_items.append(I(k, w, h))

def oracle_real(assign, S):
    interior_area = interior ** 2
    ext = [None] * 3
    for t in sorted(set(assign.values())):
        load = sum(it.area for it in rng_items if assign[it.index] == t)
        # packing efficiency ~0.85; overflow when S^2*load/0.85 > interior_area
        v = math.sqrt(load * S * S / 0.85 / interior_area)
        e = ext[t] if ext[t] is not None else [0.0, 0.0, 0.0, 0.0]
        e[2] = max(e[2], v)
        e[3] = max(e[3], v)
        ext[t] = e
    return ext

res = L.solve(rng_items, 3, 1, m, oracle_real)
S_final, assign_final, rounds, feasible = res
check("solve 268 islands converges", feasible, f"rounds={rounds}")
used = sorted(set(assign_final.values()))
check("solve 268 uses tiles sequentially (prefix)",
      used == list(range(len(used))), str(used))
loads = [0.0] * 3
for it in rng_items:
    loads[assign_final[it.index]] += it.area
max_area = max(it.area for it in rng_items)
check("solve 268 first tile fullest (FFD bound)",
      loads[0] >= loads[-1] - max_area,
      f"loads={[round(x, 4) for x in loads]}")
print(f"  (info) S*={S_final:.6f} rounds={rounds} "
      f"used={used} loads={[round(x, 4) for x in loads]}")

# --------------------------------------------------------- polygons_overlap
SQ = lambda x, y, s: [(x, y), (x + s, y), (x + s, y + s), (x, y + s)]

check("overlap disjoint",
      not L.polygons_overlap([SQ(0, 0, 0.4)], [SQ(0.5, 0.5, 0.4)]))
check("overlap crossing",
      L.polygons_overlap([SQ(0, 0, 0.6)], [SQ(0.4, 0.4, 0.6)]))
check("overlap touching edge",
      not L.polygons_overlap([SQ(0, 0, 0.5)], [SQ(0.5, 0, 0.5)]))
check("overlap touching corner",
      not L.polygons_overlap([SQ(0, 0, 0.5)], [SQ(0.5, 0.5, 0.5)]))
check("overlap containment",
      L.polygons_overlap([SQ(0, 0, 0.9)], [SQ(0.1, 0.1, 0.2)]))
# T-junction: one vertex exactly on the other's edge -> contact, not overlap.
touch_tri = [(0.3, 1.2), (0.7, 1.2), (0.5, 1.0)]
check("overlap T-junction contact",
      not L.polygons_overlap([SQ(0, 0, 1.0)], [touch_tri]))
cross_tri = [(0.3, 1.2), (0.7, 1.2), (0.5, 0.8)]
check("overlap T-crossing",
      L.polygons_overlap([SQ(0, 0, 1.0)], [cross_tri]))
# Concave L-shape: a square in the notch is disjoint, one in the body hits.
lshape = [(0, 0), (1, 0), (1, 0.5), (0.5, 0.5), (0.5, 1), (0, 1)]
check("overlap concave notch",
      not L.polygons_overlap([lshape], [SQ(0.6, 0.6, 0.3)]))
check("overlap concave body",
      L.polygons_overlap([lshape], [SQ(0.4, 0.4, 0.3)]))
# Collinear slide: B shares A's bottom edge line and slides into it -
# positive-area overlap with no proper crossing and no strict vertex.
slide_b = [(0.5, 0), (1.5, 0), (1.5, 1), (0.5, 1)]
check("overlap collinear slide",
      L.polygons_overlap([SQ(0, 0, 1.0)], [slide_b]))
# Same geometry but B only touches A's bottom edge line from outside: no.
touch_b = [(0.5, 0), (1.5, 0), (1.5, -1), (0.5, -1)]
check("overlap collinear touch",
      not L.polygons_overlap([SQ(0, 0, 1.0)], [touch_b]))
# Multi-polygon lists: any pair hitting is enough.
check("overlap multi disjoint",
      not L.polygons_overlap([SQ(0, 0, 0.2)], [SQ(0.9, 0.9, 0.2)]))
check("overlap multi one hit",
      L.polygons_overlap([SQ(0, 0, 0.2), SQ(0.9, 0.9, 0.2)],
                         [SQ(0.85, 0.85, 0.3)]))

# ------------------------------------------------- tile_islands_overlap (fast)
def GRID(x, y, s, k):
    """Square at (x,y) size s split into k*k quads -> list of face polys."""
    faces = []
    d = s / k
    for i in range(k):
        for j in range(k):
            x0, y0 = x + i * d, y + j * d
            faces.append([(x0, y0), (x0 + d, y0),
                          (x0 + d, y0 + d), (x0, y0 + d)])
    return faces

check("tile single island", not L.tile_islands_overlap([GRID(0, 0, 0.5, 3)]))
check("tile empty", not L.tile_islands_overlap([]))
check("tile disjoint multi-face",
      not L.tile_islands_overlap([GRID(0, 0, 0.4, 3), GRID(0.6, 0.6, 0.4, 3)]))
check("tile touching edge",
      not L.tile_islands_overlap([GRID(0, 0, 0.5, 3), GRID(0.5, 0, 0.5, 3)]))
check("tile touching corner",
      not L.tile_islands_overlap([GRID(0, 0, 0.5, 3), GRID(0.5, 0.5, 0.5, 3)]))
check("tile crossing",
      L.tile_islands_overlap([GRID(0, 0, 0.6, 3), GRID(0.4, 0.4, 0.6, 3)]))
check("tile containment",
      L.tile_islands_overlap([GRID(0, 0, 0.9, 4), [SQ(0.1, 0.1, 0.2)]]))
# One overlapping pair buried among many disjoint islands.
many = [GRID(i * 0.2, j * 0.2, 0.15, 2) for i in range(5) for j in range(5)]
many.append(GRID(0.9, 0.9, 0.2, 2))
check("tile one hit among many",
      L.tile_islands_overlap(many + [[SQ(0.85, 0.85, 0.3)]]))

# Performance sanity: 256 islands x 16 faces, all disjoint -> must be fast.
perf = [GRID(i * 0.0625, j * 0.0625, 0.05, 4)
        for i in range(16) for j in range(16)]
t0 = time.perf_counter()
res = L.tile_islands_overlap(perf)
dt = time.perf_counter() - t0
print(f"  (info) tile perf: {len(perf)} islands, "
      f"{sum(len(i) for i in perf)} faces -> {res} in {dt:.3f}s")
check("tile perf disjoint result", not res)
check("tile perf fast (<2s)", dt < 2.0)
# Same tile but the last island shifted into its neighbour: overlap found.
perf_hit = [list(i) for i in perf]
perf_hit[-1] = [ [(px - 0.03, py) for (px, py) in f] for f in perf[-1] ]
t0 = time.perf_counter()
res = L.tile_islands_overlap(perf_hit)
dt = time.perf_counter() - t0
print(f"  (info) tile perf hit: {res} in {dt:.3f}s")
check("tile perf hit found", res)

# ------------------------------------------------------- solve with refusal
# Oracle simulating the native packer: refuses (cancel / overlap) while the
# scale is above a threshold, places cleanly below it.
def make_refusal_oracle(items, n_tiles, thresh):
    def oracle(assign, S):
        if S > thresh:
            raise L.PackRefusedError("simulated refusal")
        ext = [None] * n_tiles
        for t in sorted(set(assign.values())):
            load = sum(it.area for it in items if assign[it.index] == t)
            v = min(load * S * 2.0, hi - 1e-4)
            e = ext[t] if ext[t] is not None else [0.0, 0.0, 0.0, 0.0]
            e[2] = max(e[2], v)
            e[3] = max(e[3], v)
            ext[t] = e
        return ext
    return oracle

items_r = [I(0, 0.5, 0.5), I(1, 0.4, 0.4)]
res_r = L.solve(items_r, 2, 1, m, make_refusal_oracle(items_r, 2, 1.5))
check("solve refusal converges", res_r[3], f"S={res_r[0]} rounds={res_r[2]}")
check("solve refusal stays below threshold",
      res_r[0] <= 1.5 + 1e-12, f"S={res_r[0]:.6f}")

# Persistent refusal: deterministic shrink must exhaust max_rounds and raise
# the plain non-convergence error (not leak PackRefusedError).
def oracle_always_refuse(assign, S):
    raise L.PackRefusedError("always")
try:
    L.solve([I(0, 0.5, 0.5)], 1, 1, m, oracle_always_refuse, max_rounds=6)
    check("solve always-refusal raises", False)
except RuntimeError as e:
    check("solve always-refusal raises", "did not converge" in str(e),
          str(e))

print()
print(f"RESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
