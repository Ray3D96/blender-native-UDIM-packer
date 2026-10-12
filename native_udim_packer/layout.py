# SPDX-License-Identifier: GPL-2.0-or-later
"""Pure-Python rigid-rectangle layout solver for UDIM tile grids.

This module has NO Blender dependency so it can be unit-tested with plain
Python and iterated on fast.  It solves the core packing problem of the
addon:

    Given N islands (axis-aligned bounding boxes at *relative* size, i.e.
    after any texel-density normalization but before the final global
    scale), find ONE uniform scale factor S such that all islands - as
    rigid rectangles, optionally 90-degree rotatable - pack without
    overlap into an X x Y grid of unit tiles (each with border ``margin``),
    and maximize S.

Why one global scale: applying a single factor to every island preserves
the relative sizes exactly, so texel density stays uniform across all
islands and objects - the same property that makes Blender's native
single-tile pack "not break" an existing Average-Islands-Scale result.
Maximizing S is what fills the tiles (maximum texture detail) instead of
spreading islands thin.

Packing feasibility is scale-invariant (rectangles w, h fit in a box of
side L iff rectangles w/S, h/S fit in a box of side L/S), so the solver
needs no binary search:

1. Assign items to tiles with LPT load balancing (several deterministic
   orderings are tried; the best result wins).
2. Greedily pack each tile at reference scale into a growing square and
   record its required extent ``L_t``.
3. The global optimum within this heuristic family is
   ``S = W / max(L_t)`` where ``W = 1 - 2*margin``: the tightest tile is
   scaled to exactly fill the tile interior, every other tile fills at
   least as much (its load was balanced), and nothing overlaps.

The per-tile greedy is bottom-left placement with candidate coordinates
derived from placed rectangles; each item may grow the square by adding a
new row or column when needed.  Deterministic: fixed sort keys, fixed
tie-breaks, no randomness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

_EPS = 1e-9


@dataclass(frozen=True)
class Item:
    """One island's bounding box at reference (relative) scale."""

    index: int          # stable id, e.g. position in the caller's list
    w: float            # bbox width  (> 0)
    h: float            # bbox height (> 0)


@dataclass(frozen=True)
class Placement:
    """Where one item goes, in reference-scale coordinates."""

    item: int           # Item.index
    tile_u: int
    tile_v: int
    x0: float           # local coords inside the tile (reference scale)
    y0: float
    w: float            # footprint width  (Item.w or Item.h if rotated)
    h: float            # footprint height
    rotated: bool


def _orientations(it: Item, rotate_90: bool) -> list[tuple[float, float, bool]]:
    out = [(it.w, it.h, False)]
    if rotate_90 and abs(it.w - it.h) > 1e-12:
        out.append((it.h, it.w, True))
    return out


def _fits(x0: float, y0: float, fw: float, fh: float,
          placed: list[tuple[float, float, float, float]],
          g: float, E: float) -> bool:
    """True when the rect fits in [0, E]^2 with gap >= g from all placed.

    All coordinates are content-space: touching the region boundary is
    allowed (it maps onto the tile margin in the final UV layout).
    """
    if x0 < -_EPS or y0 < -_EPS:
        return False
    if x0 + fw > E + _EPS or y0 + fh > E + _EPS:
        return False
    for (px0, py0, px1, py1) in placed:
        # overlap when intervals interpenetrate beyond the required gap
        if (x0 < px1 + g - _EPS and px0 < x0 + fw + g - _EPS
                and y0 < py1 + g - _EPS and py0 < y0 + fh + g - _EPS):
            return False
    return True


def _bottom_left(fw: float, fh: float,
                 placed: list[tuple[float, float, float, float]],
                 g: float, E: float) -> tuple[float, float] | None:
    """Lowest-leftmost valid position for the rect inside [0, E]^2."""
    xs = sorted({0.0} | {p[2] + g for p in placed})
    ys = sorted({0.0} | {p[3] + g for p in placed})
    best: tuple[float, float] | None = None
    for x0 in xs:
        if x0 + fw > E + _EPS:
            continue
        for y0 in ys:
            if y0 + fh > E + _EPS:
                break  # ys ascending: nothing further up can fit at this x
            if _fits(x0, y0, fw, fh, placed, g, E):
                if best is None or (y0, x0) < best:
                    best = (x0, y0)
    return best


def pack_tile(items: list[Item], rotate_90: bool,
              g: float) -> tuple[float, list[tuple[int, float, float,
                                                   float, float, bool]]]:
    """Greedily pack one tile's items into a growing square.

    Returns ``(E, placements)`` where ``E`` is the required CONTENT extent
    in reference units (the bounding side of all placed items) and
    placements are ``(item_index, x0, y0, w, h, rotated)`` in content-
    space coordinates inside ``[0, E]`` with pairwise gap >= ``g``.

    The caller maps content space into a final tile with
    ``uv = tile_origin + margin + coord * S`` where
    ``S = (1 - 2*margin) / max_t(E_t)``; the border margin therefore never
    scales with S and every item is scaled by exactly S.

    Items are processed largest first; each is placed at the lowest-
    leftmost valid position (best of both orientations when rotation is
    allowed).  When nothing fits, the region grows just enough for a new
    top row or right column to hold the item (which always exists).
    """
    if not items:
        return 0.0, []
    order = sorted(
        items,
        key=lambda it: (-(it.w * it.h), -max(it.w, it.h), it.index))
    E = max(max(it.w, it.h) for it in items)
    placed: list[tuple[float, float, float, float]] = []
    out: list[tuple[int, float, float, float, float, bool]] = []

    for it in order:
        cands = _orientations(it, rotate_90)
        pos = None
        chosen = None
        for (fw, fh, rot) in cands:
            p = _bottom_left(fw, fh, placed, g, E)
            if p is not None and (pos is None or p < pos):
                pos, chosen = p, (fw, fh, rot)
        if pos is None:
            # Grow the region so a new top row / right column fits; pick
            # the orientation needing the smallest growth.
            max_x1 = max((p[2] for p in placed), default=0.0)
            max_y1 = max((p[3] for p in placed), default=0.0)
            best_e = None
            for (fw, fh, rot) in cands:
                e_req = max(E, fw, fh, max_x1 + g + fw, max_y1 + g + fh)
                if best_e is None or e_req < best_e:
                    best_e = e_req
            E = best_e
            for (fw2, fh2, rot2) in cands:
                p = _bottom_left(fw2, fh2, placed, g, E)
                if p is not None and (pos is None or p < pos):
                    pos, chosen = p, (fw2, fh2, rot2)
            if pos is None:  # pragma: no cover - defensive
                raise RuntimeError("layout solver failed to place an item")
        x0, y0 = pos
        fw, fh, rot = chosen
        placed.append((x0, y0, x0 + fw, y0 + fh))
        out.append((it.index, x0, y0, fw, fh, rot))

    return E, out


def _try_assignment(items: list[Item], grid_x: int, grid_y: int,
                    rotate_90: bool, g: float,
                    key) -> tuple[float, dict[tuple[int, int],
                                              list[Item]]] | None:
    """LPT-assign items to tiles with a given sort key; pack every tile.

    Returns ``(max_extent, tile_items)`` or ``None`` when infeasible
    (should not happen: the square always grows).
    """
    n_tiles = grid_x * grid_y
    loads = [0.0] * n_tiles
    assign: dict[int, list[Item]] = {t: [] for t in range(n_tiles)}
    for it in sorted(items, key=key):
        t = min(range(n_tiles), key=lambda i: (loads[i], i))
        assign[t].append(it)
        loads[t] += it.w * it.h

    max_extent = 0.0
    sum_extent2 = 0.0
    for t in range(n_tiles):
        if not assign[t]:
            continue
        L, _ = pack_tile(assign[t], rotate_90, g)
        max_extent = max(max_extent, L)
        sum_extent2 += L * L
    return (max_extent, sum_extent2, assign)


def solve(items: list[Item], grid_x: int, grid_y: int, margin: float,
          rotate_90: bool) -> tuple[float, list[Placement]]:
    """Solve the global layout.

    Returns ``(S, placements)``: the maximum uniform scale (within this
    heuristic family) and each item's placement in reference-scale,
    content-space tile-local coordinates.  The caller maps a placement to
    final UV space with ``x = tile_u + margin + x0 * S`` etc., and applies
    total scale ``S * per-item pre-scale`` when writing back.

    Deterministic: three fixed orderings (area, height, width) are tried;
    the layout with the smallest tightest-tile extent wins (ties broken by
    best balance, then ordering index).
    """
    if not items:
        return 1.0, []
    g = max(float(margin), 0.0)
    W = 1.0 - 2.0 * g
    if W <= 1e-9:
        raise ValueError("margin too large for a unit tile")

    keys = [
        lambda it: (-(it.w * it.h), -max(it.w, it.h), it.index),
        lambda it: (-max(it.w, it.h), -(it.w * it.h), it.index),
        lambda it: (-(it.w + it.h), -(it.w * it.h), it.index),
    ]
    best = None  # (max_extent, sum_extent2, order_idx, assign)
    for idx, key in enumerate(keys):
        res = _try_assignment(items, grid_x, grid_y, rotate_90, g, key)
        if res is None:
            continue
        cand = (res[0], res[1], idx, res[2])
        if best is None or (cand[0], cand[1]) < (best[0], best[1]):
            best = cand
    assert best is not None
    max_extent, _, _, assign = best

    S = W / max_extent if max_extent > 1e-12 else 1.0
    placements: list[Placement] = []
    for t in sorted(assign):
        if not assign[t]:
            continue
        L, packed = pack_tile(assign[t], rotate_90, g)
        # Flat tile index -> (column, row): column first along U.
        tu, tv = t % grid_x, t // grid_x
        for (idx_i, x0, y0, fw, fh, rot) in packed:
            placements.append(Placement(
                item=idx_i, tile_u=tu, tile_v=tv,
                x0=x0, y0=y0, w=fw, h=fh, rotated=rot))
    return S, placements


def layout_stats(S: float, placements: list[Placement],
                 items_by_index: dict[int, Item],
                 grid_x: int, grid_y: int) -> dict:
    """Fill ratio per tile (area-based) - for tests and diagnostics."""
    W = 1.0
    per_tile: dict[tuple[int, int], float] = {}
    for p in placements:
        it = items_by_index[p.item]
        a = it.w * it.h * S * S
        key = (p.tile_u, p.tile_v)
        per_tile[key] = per_tile.get(key, 0.0) + a / W
    return {
        "scale": S,
        "tiles_used": len(per_tile),
        "per_tile_fill": per_tile,
        "total_fill": sum(per_tile.values()) / max(grid_x * grid_y, 1),
    }
