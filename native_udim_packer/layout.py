# SPDX-License-Identifier: GPL-3.0-or-later
"""Tile assignment and global-scale search for the hybrid packing engine.

The actual per-tile placement is done by Blender's built-in
``bpy.ops.uv.pack_islands`` operator (C speed, shape-aware, and it never
overlaps the islands it packs).  This module decides two things in pure
Python - no bpy import, unit-testable with plain Python:

* which tile each island goes to.  The assignment is *sequential
  first-fit-decreasing*: islands are processed largest-first and each one
  goes into the earliest tile that can still accept it, so tile 1001 is
  filled before 1002 opens, 1002 before 1003, and so on.  The last used
  tile is generally partially filled - that is exactly what "maximally
  fill the first UDIM" means.

* the single global scale ``S*``.  It is found by a shrinking search:
  start at the largest scale where the biggest island still spans one
  tile interior, run the assignment + native packing, and measure each
  used tile's post-pack extent.  A tile whose content overflows its
  ``[0, 1-margin]`` bound tells us the content is too big: shrink S in
  proportion to the measured overflow and retry.  At every scale the
  assignment is re-tried from greediest filling to sparsest (an "eta
  ladder"), so the search always returns the greediest tile layout that
  fits at the highest possible scale - maximum texel density, with the
  first UDIMs filled before later ones open.  Because the feasibility
  oracle is the packer itself (not an area estimate), the converged
  scale is feasible *by measurement* - no overlap can survive.

The search is deterministic: same islands, same grid, same margin ->
same result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


class PackRefusedError(RuntimeError):
    """The native packer refused a placement round.

    Raised by the feasibility oracle when ``bpy.ops.uv.pack_islands``
    returns anything other than FINISHED (Blender cancels silently when
    its toolsettings-dependent selection gate finds nothing to pack) or
    when the post-pack result contains overlapping islands - the native
    packer is allowed to do that when content does not fit at
    ``scale=False``, in which case a FINISHED result with in-bounds
    extents is NOT proof of a clean layout.  :func:`solve` treats a
    refusal as "infeasible without measured extents" and shrinks the
    scale conservatively instead of aborting the whole pack.
    """


@dataclass(frozen=True)
class Item:
    """One UV island at reference size (after any normalization).

    ``w``/``h`` are the island's bounding-box size in reference units;
    ``index`` is its position in the caller's island list.
    """
    index: int
    w: float
    h: float

    @property
    def area(self) -> float:
        return self.w * self.h


def tile_order(grid_x: int, grid_y: int) -> list[tuple[int, int]]:
    """Row-major tile positions: (0,0), (1,0), ... i.e. 1001, 1002, ..."""
    return [(tu, tv) for tv in range(grid_y) for tu in range(grid_x)]


def max_scale(tile_interior: float, items) -> float:
    """Largest scale at which the biggest island still spans one tile.

    The packer keeps fitting content inside the tile interior, so the
    single largest side of any island must satisfy
    ``maxdim * S <= tile_interior``.
    """
    md = 0.0
    for it in items:
        d = max(it.w, it.h)
        if d > md:
            md = d
    if md <= 1e-9:
        return 1.0
    return tile_interior / md


def assign_ffd(items, n_tiles: int, cap: float, eta: float = 0.92) -> dict | None:
    """Sequential first-fit-decreasing assignment to ``n_tiles`` tiles.

    ``cap`` is the tile capacity in reference area units; an island's
    bounding box fits one tile interior iff its longer side is <=
    ``sqrt(cap)``.  Islands are processed in decreasing area (ties: longer
    side first, then index).  Each island goes to the earliest tile that
    accepts it: a used tile accepts while ``load + area <= eta * cap``; an
    empty tile accepts when the island geometrically fits one interior on
    its own (guaranteed at :func:`max_scale`).

    Returns ``{item.index: tile_pos}`` with ``tile_pos`` in row-major
    order (0 = first tile), or ``None`` when no assignment exists at this
    capacity.
    """
    if n_tiles <= 0:
        return {} if not items else None
    sqrt_cap = cap ** 0.5
    order = sorted(items, key=lambda it: (-it.area, -max(it.w, it.h), it.index))
    loads = [0.0] * n_tiles
    assign: dict[int, int] = {}
    for it in order:
        a = it.area
        fits_alone = max(it.w, it.h) <= sqrt_cap * (1.0 + 1e-9)
        for t in range(n_tiles):
            if loads[t] == 0.0:
                if not fits_alone:
                    continue
            elif loads[t] + a > eta * cap:
                continue
            assign[it.index] = t
            loads[t] += a
            break
        else:
            return None
    return assign


# ---------------------------------------------------------------------------
# Exact 2D polygon-overlap predicates (pure Python, no bpy).
#
# Used to verify the native packer's output: two islands overlap iff their
# union has positive area, which for simple polygons is equivalent to
# "some edge pair properly crosses" or "a vertex of one lies strictly
# inside the other".  Boundary contact (shared point or edge, e.g. at
# margin=0) is NOT an overlap and is deliberately not reported.
#
# ``_EPS`` doubles as the touching tolerance: geometry whose separation
# from a shared boundary is below ~2e-6 UV units (sub-pixel at any real
# texture size) is treated as contact, so float noise on edges the native
# packer laid exactly against each other cannot trigger a false refusal.
# ---------------------------------------------------------------------------

_EPS = 1e-6


def _orient(a, b, c):
    """Strict sign of the cross product (b-a) x (c-a)."""
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if v > _EPS:
        return 1
    if v < -_EPS:
        return -1
    return 0


def _on_segment(p, q, r):
    """Is q on segment pr? (collinearity assumed by callers)"""
    return (min(p[0], r[0]) - _EPS <= q[0] <= max(p[0], r[0]) + _EPS and
            min(p[1], r[1]) - _EPS <= q[1] <= max(p[1], r[1]) + _EPS)


def _seg_cross_proper(a, b, c, d):
    """Do segments ab and cd cross at an interior point of both?

    Strict general position only: any collinear endpoint (shared corner,
    T-junction, or a sliding edge) yields orientation 0 and is NOT a
    proper crossing - boundary contact must not read as overlap.
    """
    o1 = _orient(a, b, c)
    o2 = _orient(a, b, d)
    o3 = _orient(c, d, a)
    o4 = _orient(c, d, b)
    return (o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0
            and o1 != o2 and o3 != o4)


def _point_strictly_inside(pt, poly):
    """Even-odd test; boundary points are NOT inside."""
    x, y = pt
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if _orient((xi, yi), (xj, yj), pt) == 0 and \
                _on_segment((xi, yi), pt, (xj, yj)):
            return False          # on the boundary -> not strictly inside
        if (yi > y) != (yj > y):
            x_hit = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_hit:
                inside = not inside
        j = i
    return inside


def _poly_bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _point_on_boundary(pt, poly):
    """Is pt on any edge of poly? (within _EPS)"""
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if _orient(a, b, pt) == 0 and _on_segment(a, pt, b):
            return True
    return False


def _polys_overlap_single(pa, pb):
    """Exact positive-area intersection test for one pair of simple
    polygons (closed vertex lists).  Assumes the caller already knows the
    two bounding boxes intersect.  Touching at points or edges is NOT an
    overlap."""
    for i in range(len(pa)):
        a = pa[i]
        b = pa[(i + 1) % len(pa)]
        for j in range(len(pb)):
            if _seg_cross_proper(a, b, pb[j], pb[(j + 1) % len(pb)]):
                return True
    for v in pa:
        if _point_strictly_inside(v, pb):
            return True
    for v in pb:
        if _point_strictly_inside(v, pa):
            return True
    # Midpoint net: catches collinear slide-overlaps (e.g. two axis-aligned
    # rectangles whose shared edge line overlaps while one slides into the
    # other) where no vertex is strictly inside and no crossing is proper.
    # A midpoint strictly inside the other polygon always implies
    # positive-area intersection.
    for i in range(len(pa)):
        mx = (pa[i][0] + pa[(i + 1) % len(pa)][0]) * 0.5
        my = (pa[i][1] + pa[(i + 1) % len(pa)][1]) * 0.5
        if _point_strictly_inside((mx, my), pb):
            return True
    for j in range(len(pb)):
        mx = (pb[j][0] + pb[(j + 1) % len(pb)][0]) * 0.5
        my = (pb[j][1] + pb[(j + 1) % len(pb)][1]) * 0.5
        if _point_strictly_inside((mx, my), pa):
            return True
    # Coincident faces: two identical (or re-triangulated) quads have every
    # vertex AND every edge midpoint on the other's boundary, so all the
    # tests above are silent.  When the bboxes agree and each polygon's
    # vertices all lie on the other's boundary, the two simple polygons
    # enclose the same region - a positive-area overlap.
    bba = _poly_bbox(pa)
    bbb = _poly_bbox(pb)
    if (abs(bba[0] - bbb[0]) <= _EPS and abs(bba[1] - bbb[1]) <= _EPS and
            abs(bba[2] - bbb[2]) <= _EPS and abs(bba[3] - bbb[3]) <= _EPS):
        if all(_point_on_boundary(v, pb) for v in pa) and \
                all(_point_on_boundary(v, pa) for v in pb):
            return True
    return False


def polygons_overlap(polys_a, polys_b):
    """True iff any polygon of ``polys_a`` intersects any polygon of
    ``polys_b`` with positive area.  Touching at points or edges does not
    count.  ``polys_*`` are lists of closed vertex lists ``(x, y)`` (no
    repeated closing vertex)."""
    for pa in polys_a:
        bba = _poly_bbox(pa)
        for pb in polys_b:
            bbb = _poly_bbox(pb)
            if (bba[2] < bbb[0] - _EPS or bbb[2] < bba[0] - _EPS or
                    bba[3] < bbb[1] - _EPS or bbb[3] < bba[1] - _EPS):
                continue          # AABBs apart -> polygons apart
            if _polys_overlap_single(pa, pb):
                return True
    return False


def tile_islands_overlap(tile_polys, static_flags=None):
    """True iff any two distinct islands in ``tile_polys`` overlap with
    positive area - the same semantics as :func:`polygons_overlap`, but
    for a whole tile at once.

    ``tile_polys`` is a list of islands; each island is a list of closed
    vertex lists ``(x, y)``.  Candidate face pairs are found with a
    uniform spatial grid over the faces' bounding boxes, so the cost
    scales with local density instead of the product of the two island
    sizes - that is what keeps the per-round verification cheap on meshes
    whose islands contain thousands of faces.  Every candidate pair still
    goes through the exact predicate, so the result is identical to the
    blind pairwise comparison.

    ``static_flags`` (optional, one bool per island) marks islands that
    are fixed pre-existing content (selected-islands mode).  Pairs where
    BOTH sides are static are skipped: any overlap there predates this
    pack and must not make the new layout infeasible.
    """
    n_isl = len(tile_polys)
    if n_isl < 2:
        return False
    gminx = gminy = float("inf")
    gmaxx = gmaxy = float("-inf")
    faces = []            # (minx, miny, maxx, maxy, island, poly)
    for isl, polys in enumerate(tile_polys):
        for p in polys:
            bb = _poly_bbox(p)
            faces.append((bb[0], bb[1], bb[2], bb[3], isl, p))
            if bb[0] < gminx:
                gminx = bb[0]
            if bb[1] < gminy:
                gminy = bb[1]
            if bb[2] > gmaxx:
                gmaxx = bb[2]
            if bb[3] > gmaxy:
                gmaxy = bb[3]
    span = max(gmaxx - gminx, gmaxy - gminy)
    if span <= 0.0:
        return False

    ncells = 128
    inv_c = ncells / span

    def cell_of(v):
        k = int((v - gminx) * inv_c)
        if k < 0:
            return 0
        if k >= ncells:
            return ncells - 1
        return k

    grid: dict[int, list] = {}
    for idx, f in enumerate(faces):
        i0, i1 = cell_of(f[0]), cell_of(f[2])
        j0, j1 = cell_of(f[1]), cell_of(f[3])
        for i in range(i0, i1 + 1):
            base = i * ncells
            for j in range(j0, j1 + 1):
                key = base + j
                bucket = grid.get(key)
                if bucket is None:
                    grid[key] = [idx]
                else:
                    bucket.append(idx)

    seen = set()
    for bucket in grid.values():
        m = len(bucket)
        if m < 2:
            continue
        for a in range(m):
            fa = faces[bucket[a]]
            ia = fa[4]
            for b in range(a + 1, m):
                fb = faces[bucket[b]]
                if ia == fb[4]:
                    continue          # same island: disjoint faces
                if (static_flags is not None and static_flags[ia]
                        and static_flags[fb[4]]):
                    continue          # both pre-existing statics
                if (fa[2] < fb[0] - _EPS or fb[2] < fa[0] - _EPS or
                        fa[3] < fb[1] - _EPS or fb[3] < fa[1] - _EPS):
                    continue          # AABBs apart -> polygons apart
                key = (bucket[a], bucket[b])
                if key in seen:
                    continue          # pair already exact-tested
                seen.add(key)
                if _polys_overlap_single(fa[5], fb[5]):
                    return True
    return False


def next_scale(S: float, tile_interior: float, extents, tol: float = 2e-4):
    """Step the scale search from measured post-pack tile extents.

    ``extents`` is a list of ``(minx, miny, maxx, maxy)`` per used tile in
    0..1 UV space (before the integer tile offset).  Content that fits is
    kept within ``[~0, 1-margin]`` by the packer; anything above
    ``1 - margin + tol`` on x or y means that tile overflowed.

    Returns ``(S_next, feasible)``: the unchanged scale when every tile
    fits, otherwise a smaller scale (proportional to the worst overflow,
    with a small safety factor) and ``False``.
    """
    m = (1.0 - tile_interior) * 0.5
    hi = 1.0 - m
    f = 1.0
    feasible = True
    for e in extents:
        if e[2] > hi + tol or e[3] > hi + tol:
            feasible = False
            over_max = max(e[2], e[3])
            if over_max > hi:
                f = min(f, hi / over_max)
    if feasible:
        return S, True
    if f >= 1.0:      # defensive: overflow the packer cannot express as
        f = 0.9       # extent growth - keep shrinking deterministically
    return S * max(f, 1e-6) * 0.995, False


def final_growth_factor(extents_by_tile, margin: float) -> float:
    """Global re-center + growth factor for a finished layout.

    ``extents_by_tile`` maps each used tile to the tile-local (0..1 UV
    space) content bbox ``(minx, miny, maxx, maxy)`` measured after the
    final packing round.  Every tile's content is first re-centered on its
    tile center, which gives each axis symmetric headroom; the largest
    uniform factor that keeps every tile inside its margin boundary is

        K = min over used tiles t and axes a of (1 - 2m) / extent_a(t)

    i.e. the tightest tile/axis sets the scale for everything, so one
    global factor equalizes texel density while maxing out the bottleneck.
    Returns 1.0 when nothing can grow or no tile is used; the result is
    always >= 1.0 (float noise below the current size clamps to 1.0).
    """
    interior = 1.0 - 2.0 * margin
    if interior <= 0.0:
        return 1.0
    k = math.inf
    for extent in extents_by_tile.values():
        w = extent[2] - extent[0]
        h = extent[3] - extent[1]
        if w > 1e-9:
            k = min(k, interior / w)
        if h > 1e-9:
            k = min(k, interior / h)
    if not math.isfinite(k):
        return 1.0
    return max(1.0, k)


def solve(items, grid_x: int, grid_y: int, margin: float, oracle,
          max_rounds: int = 48,
          etas: tuple[float, ...] = (0.92, 0.85, 0.75, 0.65, 0.5)):
    """Run the full assignment + scale search.

    ``oracle(assign, S)`` must place every island according to ``assign``
    at global scale ``S`` (native per-tile packing in Blender), then
    return the measured post-pack extent ``(minx, miny, maxx, maxy)`` of
    each used tile in 0..1 space as a list indexed by row-major tile
    position (``None`` for unused tiles).  The oracle may raise
    :class:`PackRefusedError` when the native packer cancels or produces
    overlapping islands; that is treated as infeasible without measured
    extents and answered with a conservative ``S * 0.9`` shrink.

    The search maximizes the global scale first: it starts at ``S_max``,
    the largest scale at which the biggest island still spans one tile,
    and only shrinks when no assignment fits at the current scale.  At
    every candidate scale it walks a ladder of FFD load targets from
    greediest to sparsest (``etas``): the greedy filling - "maximally
    fill the first UDIM before opening the next" - is preferred whenever
    it still fits at that scale; when it does not, sparser assignments
    spread the content over more tiles, which is exactly what lets the
    largest islands stay large when several UDIMs are available.  A tile
    whose measured extent overflows its ``[0, 1-margin]`` bound yields a
    proportional shrink; the most optimistic suggestion of the round wins
    and the search retries from the greedy end of the ladder there.

    Returns ``(S_final, assign_final, rounds_used, feasible)``.  Raises
    RuntimeError when the search does not converge within ``max_rounds``
    outer rounds (each round may call the oracle once per ladder entry).
    """
    n_tiles = grid_x * grid_y
    interior = max(1.0 - 2.0 * margin, 1e-3)
    S = max_scale(interior, items)
    rounds = 0
    for rnd in range(max_rounds):
        rounds = rnd + 1
        cap = (interior / S) ** 2
        best_next: float | None = None
        for eta in etas:
            a = assign_ffd(items, n_tiles, cap, eta)
            if a is None:
                continue
            try:
                extents = oracle(a, S)
            except PackRefusedError:
                # The native packer refused this assignment (silent cancel
                # or overlapping output).  No measured extents are
                # available, so fall back to a conservative shrink; sparser
                # ladder entries and smaller scales are still tried.
                if best_next is None or S * 0.9 > best_next:
                    best_next = S * 0.9
                continue
            S_next, feasible = next_scale(S, interior,
                                          [e for e in extents if e is not None])
            if feasible:
                return S, a, rounds, True
            if best_next is None or S_next > best_next:
                best_next = S_next
        if best_next is None:      # defensive: nothing assignable at this cap
            S *= 0.9
        else:
            S = max(best_next, 1e-6)
    raise RuntimeError(
        "UDIM pack: scale search did not converge after "
        f"{max_rounds} rounds (S={S:.6g})")
