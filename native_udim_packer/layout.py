# SPDX-License-Identifier: GPL-2.0-or-later
"""Pure-Python rigid-shape layout solver for UDIM tile grids.

This module has NO Blender dependency so it can be unit-tested with plain
Python and iterated on fast.  It solves the core packing problem of the
addon:

    Given N islands (at *relative* size, i.e. after any texel-density
    normalization but before the final global scale), find ONE uniform
    scale factor S such that all islands - as rigid shapes, optionally
    90-degree rotatable - pack without overlap into an X x Y grid of unit
    tiles (each with border ``margin``), and maximize S.

Islands may be plain bounding boxes (the classic mode) or carry their real
outline: outer boundary loops plus optional hole loops in local
coordinates (bounding-box minimum at the origin).  Shape-aware packing
exploits concavities and holes, which is where bbox-based packing wastes
most of its space.

Why one global scale: applying a single factor to every island preserves
the relative sizes exactly, so texel density stays uniform across all
islands and objects - the same property that makes Blender's native
single-tile pack "not break" an existing Average-Islands-Scale result.
Maximizing S is what fills the tiles (maximum texture detail) instead of
spreading islands thin.

Solver pipeline:

1. Assign items to tiles with LPT load balancing (several deterministic
   orderings are tried; the best result wins).  Ordering quality is judged
   with a fast bounding-box-only proxy pack, so this step stays cheap even
   for shape-carrying items.
2. A bounded local search re-balances tile loads: items - and later item
   pairs - are moved/swapped out of the tightest tile while the objective
   ``(max_extent, sum_extent^2)`` strictly improves.  This removes the
   "one tile full, its neighbours half empty" situation plain LPT leaves
   behind.
3. Every tile is finally packed with the shape-aware greedy: bottom-left
   placement with polygon collision detection (outer-edge crossings plus
   vertex/midpoint containment against the solid region, i.e. inside an
   outer loop and outside every hole).  When the standard candidate set
   cannot place an item without growing the square, an expanded candidate
   set (edge alignments + hole-centre attractors) is tried before growth.

Packing feasibility is scale-invariant, so no binary search is needed:
the tightest tile's extent ``L*`` gives ``S = W / L*`` with
``W = 1 - 2*margin``; the border margin never scales with S and every item
is scaled by exactly S (times its per-item normalization pre-scale).

Deterministic: fixed sort keys, fixed tie-breaks, no randomness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

_EPS = 1e-9


@dataclass(frozen=True)
class Item:
    """One island at reference (relative) scale.

    ``outers``/``holes`` are optional real outlines: tuples of loops, each
    loop a tuple of ``(x, y)`` points in local coordinates with the
    island's bounding-box minimum at the origin.  Empty ``outers`` means
    "treat as a plain rectangle" (fast path, classic engine behaviour).
    """

    index: int          # stable id, e.g. position in the caller's list
    w: float            # bbox width  (> 0)
    h: float            # bbox height (> 0)
    outers: tuple = ()  # outer boundary loops (local coords)
    holes: tuple = ()   # hole loops (local coords)


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


# --------------------------------------------------------------- geometry --

def _perp_dist(p: tuple, a: tuple, b: tuple) -> float:
    """Distance from point p to segment ab."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-30:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _simplify_loop(loop: tuple, eps: float) -> tuple:
    """Douglas-Peucker simplification of a closed polygon loop.

    Dense mesh boundaries carry hundreds of near-collinear points; at
    packing precision they are pure cost.  ``eps`` is an absolute length in
    reference units; the result keeps at least the original extreme
    structure (the point farthest from the start splits the loop).
    """
    pts = list(loop)
    n = len(pts)
    if n < 5 or eps <= 0.0:
        return tuple(pts)

    def dp_chain(chain: list[tuple]) -> list[tuple]:
        m = len(chain)
        if m < 3:
            return []
        keep = [False] * m
        keep[0] = keep[-1] = True
        stack = [(0, m - 1)]
        while stack:
            ia, ib = stack.pop()
            pa, pb = chain[ia], chain[ib]
            dmax = -1.0
            imax = -1
            for i in range(ia + 1, ib):
                d = _perp_dist(chain[i], pa, pb)
                if d > dmax:
                    dmax = d
                    imax = i
            if imax >= 0 and dmax > eps:
                keep[imax] = True
                stack.append((ia, imax))
                stack.append((imax, ib))
        return [p for i, p in enumerate(chain) if keep[i]]

    # Split at the point farthest from pts[0] so both chains are well posed.
    i_max = max(range(1, n),
                key=lambda i: (pts[i][0] - pts[0][0]) ** 2
                + (pts[i][1] - pts[0][1]) ** 2)
    c1 = pts[:i_max + 1]
    c2 = pts[i_max:] + [pts[0]]
    r1 = dp_chain(c1)
    r2 = dp_chain(c2)
    out = r1[:-1] + r2[:-1]
    return tuple(out) if len(out) >= 3 else tuple(pts)


def _signed_area2(poly: tuple) -> float:
    """Twice the signed area (shoelace); positive for CCW winding."""
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s


def _line_line(p1: tuple, p2: tuple, p3: tuple, p4: tuple) -> tuple | None:
    """Intersection of the two infinite lines p1p2 and p3p4 (or None)."""
    d1x, d1y = p2[0] - p1[0], p2[1] - p1[1]
    d2x, d2y = p4[0] - p3[0], p4[1] - p3[1]
    den = d1x * d2y - d1y * d2x
    if abs(den) < 1e-12:
        return None
    t = ((p3[0] - p1[0]) * d2y - (p3[1] - p1[1]) * d2x) / den
    return (p1[0] + t * d1x, p1[1] + t * d1y)


def _offset_loop(loop: tuple, g: float, grow_interior: bool) -> tuple:
    """Offset a simple polygon loop uniformly by ``g``.

    ``grow_interior=True`` expands the enclosed region (used for outer
    loops); ``False`` shrinks it (used for hole loops, so the solid grows
    into the hole).  The offset vertex is the intersection of the two
    adjacent offset edges; parallel edges fall back to the midpoint.
    """
    n = len(loop)
    if n < 3 or g <= 0.0:
        return tuple(loop)
    ccw = _signed_area2(loop) > 0.0
    k = g if (ccw == grow_interior) else -g
    offs = []
    for i in range(n):
        p = loop[i]
        q = loop[(i + 1) % n]
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy) or 1e-12
        # Right-hand normal of (dx, dy); for a CCW loop it points outward.
        offs.append((dy / L * k, -dx / L * k))
    out = []
    for i in range(n):
        a = loop[(i - 1) % n]
        b = loop[i]
        c = loop[(i + 1) % n]
        oa, ob = offs[(i - 1) % n], offs[i]
        p1 = (a[0] + oa[0], a[1] + oa[1])
        p2 = (b[0] + oa[0], b[1] + oa[1])
        p3 = (b[0] + ob[0], b[1] + ob[1])
        p4 = (c[0] + ob[0], c[1] + ob[1])
        inter = _line_line(p1, p2, p3, p4)
        if inter is None:
            inter = ((p2[0] + p3[0]) * 0.5, (p2[1] + p3[1]) * 0.5)
        out.append(inter)
    return tuple(out)


def _seg_cross(p1: tuple, p2: tuple, q1: tuple, q2: tuple) -> bool:
    """True when segments p1p2 and q1q2 properly cross (interior point)."""
    def cross(ax: float, ay: float, bx: float, by: float) -> float:
        return ax * by - ay * bx

    d1 = cross(q2[0] - q1[0], q2[1] - q1[1], p1[0] - q1[0], p1[1] - q1[1])
    d2 = cross(q2[0] - q1[0], q2[1] - q1[1], p2[0] - q1[0], p2[1] - q1[1])
    d3 = cross(p2[0] - p1[0], p2[1] - p1[1], q1[0] - p1[0], q1[1] - p1[1])
    d4 = cross(p2[0] - p1[0], p2[1] - p1[1], q2[0] - p1[0], q2[1] - p1[1])
    return (((d1 > 0.0 and d2 < 0.0) or (d1 < 0.0 and d2 > 0.0))
            and ((d3 > 0.0 and d4 < 0.0) or (d3 < 0.0 and d4 > 0.0)))


def _pip(pt: tuple, poly: tuple) -> bool:
    """Ray-casting point-in-polygon (pure Python)."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _in_solid(pt: tuple, shape: "_Shape", ox: float, oy: float) -> bool:
    """True when absolute point ``pt`` lies in the solid part of ``shape``.

    The solid is "inside at least one outer loop and outside every hole".
    ``shape`` is local; ``(ox, oy)`` is its placement offset.
    """
    qx = pt[0] - ox
    qy = pt[1] - oy
    for o in shape.outers:
        if not _pip((qx, qy), o):
            continue
        for hloop in shape.holes:
            if _pip((qx, qy), hloop):
                return False
        return True
    return False


# ------------------------------------------------------------------ shapes --

class _Shape:
    """Collision shape of one item orientation, local coordinates.

    ``outers``/``holes`` are tuples of point tuples; the derived edge and
    vertex lists exist to keep the hot collision loop cheap.  ``bbox`` is
    the actual loop extent (offset shapes extend beyond w/h).
    """

    __slots__ = ("w", "h", "outers", "holes", "edges", "vpts", "midpts",
                 "attractors", "bbox")

    def __init__(self, w: float, h: float, outers: tuple, holes: tuple):
        self.w = w
        self.h = h
        self.outers = outers
        self.holes = holes
        edges = []
        vpts = []
        midpts = []
        minx = miny = math.inf
        maxx = maxy = -math.inf
        for loop in outers:
            n = len(loop)
            for i in range(n):
                p1 = loop[i]
                p2 = loop[(i + 1) % n]
                vpts.append(p1)
                midpts.append(((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5))
                edges.append((p1, p2, (min(p1[0], p2[0]), min(p1[1], p2[1]),
                                       max(p1[0], p2[0]), max(p1[1], p2[1]))))
                if p1[0] < minx:
                    minx = p1[0]
                if p1[1] < miny:
                    miny = p1[1]
                if p1[0] > maxx:
                    maxx = p1[0]
                if p1[1] > maxy:
                    maxy = p1[1]
        self.edges = tuple(edges)
        self.vpts = tuple(vpts)
        self.midpts = tuple(midpts)
        self.bbox = (minx, miny, maxx, maxy)
        att = []
        for hloop in holes:
            hx = sum(p[0] for p in hloop) / len(hloop)
            hy = sum(p[1] for p in hloop) / len(hloop)
            att.append((hx, hy))
        self.attractors = tuple(att)


def _rect_shape(w: float, h: float) -> _Shape:
    loop = ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h))
    return _Shape(w, h, (loop,), ())


def _build_shape(it: Item, rot: bool) -> _Shape:
    """Collision shape for one item orientation (simplified outlines).

    The rotated orientation applies a 90-degree counter-clockwise rotation
    about the bounding box - the same transform the writeback performs
    (``rotate_faces_90`` steps=1) - landing in ``[0, h] x [0, w]``.
    """
    if it.outers:
        w0, h0 = it.w, it.h
        eps = max(1e-4, 0.002 * math.hypot(w0, h0))
        outers = tuple(_simplify_loop(lp, eps) for lp in it.outers)
        holes = tuple(_simplify_loop(lp, eps) for lp in it.holes)
        if rot:
            outers = tuple(tuple((h0 - y, x) for (x, y) in lp)
                           for lp in outers)
            holes = tuple(tuple((h0 - y, x) for (x, y) in lp)
                          for lp in holes)
            fw, fh = h0, w0
        else:
            fw, fh = w0, h0
        outers = tuple(lp for lp in outers if len(lp) >= 3)
        holes = tuple(lp for lp in holes if len(lp) >= 3)
        if not outers:
            return _rect_shape(fw, fh)
        return _Shape(fw, fh, outers, holes)
    fw, fh = (it.h, it.w) if rot else (it.w, it.h)
    return _rect_shape(fw, fh)


def _offset_shape(shape: _Shape, g: float) -> _Shape:
    """Collision shape grown by ``g`` (Minkowski sum with a disc).

    Outer loops expand, hole loops shrink, so the solid region grows
    uniformly and the gap between two shapes is enforced at ~``g``.
    Holes consumed entirely by the growth are dropped.
    """
    if g <= 0.0:
        return shape
    outers = []
    for lp in shape.outers:
        olp = _offset_loop(lp, g, True)
        if len(olp) >= 3 and _signed_area2(olp) * _signed_area2(lp) > 0.0:
            outers.append(olp)
    holes = []
    for lp in shape.holes:
        olp = _offset_loop(lp, g, False)
        a0 = abs(_signed_area2(lp))
        if (len(olp) >= 3 and a0 > 1e-18
                and abs(_signed_area2(olp)) > 0.25 * a0):
            holes.append(olp)
    if not outers:  # degenerate - fall back to the exact shape
        return shape
    return _Shape(shape.w + 2.0 * g, shape.h + 2.0 * g,
                  tuple(outers), tuple(holes))


def _overlap(a: _Shape, oa: tuple, b: _Shape, ob: tuple) -> bool:
    """True when shape ``a`` at offset ``oa`` collides with ``b`` at ``ob``.

    Complete for simple polygons with holes: (1) proper outer-edge
    crossings catch boundary intersections; (2) a vertex of one shape
    inside the solid of the other catches containment; (3) edge midpoints
    add robustness for non-convex hole boundaries that no endpoint sees.
    Touching (shared edges/points) is NOT a collision - islands may touch.
    """
    ab = a.bbox
    bb = b.bbox
    if not (oa[0] + ab[0] < ob[0] + bb[2] and ob[0] + bb[0] < oa[0] + ab[2]
            and oa[1] + ab[1] < ob[1] + bb[3] and ob[1] + bb[1] < oa[1] + ab[3]):
        return False
    # 1) outer x outer edge crossings (per-edge bbox prefilter)
    for (p1, p2, ebb) in a.edges:
        ax0 = oa[0] + min(ebb[0], ebb[2])
        ay0 = oa[1] + min(ebb[1], ebb[3])
        ax1 = oa[0] + max(ebb[0], ebb[2])
        ay1 = oa[1] + max(ebb[1], ebb[3])
        for (q1, q2, qbb) in b.edges:
            if not (ax0 < ob[0] + qbb[2] and ob[0] + qbb[0] < ax1
                    and ay0 < ob[1] + qbb[3] and ob[1] + qbb[1] < ay1):
                continue
            if _seg_cross((p1[0] + oa[0], p1[1] + oa[1]),
                          (p2[0] + oa[0], p2[1] + oa[1]),
                          (q1[0] + ob[0], q1[1] + ob[1]),
                          (q2[0] + ob[0], q2[1] + ob[1])):
                return True
    # 2) a's outer vertices inside b's solid
    for v in a.vpts:
        if _in_solid((v[0] + oa[0], v[1] + oa[1]), b, ob[0], ob[1]):
            return True
    # 3) b's outer vertices inside a's solid
    for v in b.vpts:
        if _in_solid((v[0] + ob[0], v[1] + ob[1]), a, oa[0], oa[1]):
            return True
    # 4) edge midpoints (non-convex hole robustness)
    for m in a.midpts:
        if _in_solid((m[0] + oa[0], m[1] + oa[1]), b, ob[0], ob[1]):
            return True
    for m in b.midpts:
        if _in_solid((m[0] + ob[0], m[1] + ob[1]), a, oa[0], oa[1]):
            return True
    return False


# ------------------------------------------------- rectangle fast path -----

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


def _pack_tile_rect(items: list[Item], rotate_90: bool,
                    g: float) -> tuple[float, list[tuple[int, float, float,
                                                         float, float, bool]]]:
    """Classic bbox-only greedy pack (also the fast proxy for balancing)."""
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


# ------------------------------------------------------ shape-aware pack ---

def _fits_shape(cshape: _Shape, c_is_rect: bool, x0: float, y0: float,
                placed: list[dict], g: float, E: float) -> bool:
    """True when the candidate shape fits at (x0, y0) inside [0, E]^2.

    Rect-vs-rect pairs keep the classic interval gap test (fast and exact);
    any pair involving a real outline is tested with polygon collision
    against the placed item's offset shape (which encodes the gap).
    """
    if x0 < -_EPS or y0 < -_EPS:
        return False
    if x0 + cshape.w > E + _EPS or y0 + cshape.h > E + _EPS:
        return False
    for p in placed:
        if c_is_rect and p["rect"]:
            px0, py0, px1, py1 = p["aabb"]
            if (x0 < px1 + g - _EPS and px0 < x0 + cshape.w + g - _EPS
                    and y0 < py1 + g - _EPS and py0 < y0 + cshape.h + g - _EPS):
                return False
        else:
            if _overlap(cshape, (x0, y0), p["cshape"], p["pos"]):
                return False
    return True


def _attractor_positions(placed: list[dict], fw: float, fh: float,
                         E: float) -> list[tuple[float, float]]:
    """Candidate positions centred on the holes of placed shapes."""
    out = []
    for p in placed:
        if p["shape"] is None:
            continue
        for (ax, ay) in p["shape"].attractors:
            cx = max(ax - fw * 0.5, 0.0)
            cy = max(ay - fh * 0.5, 0.0)
            if cx + fw <= E + _EPS and cy + fh <= E + _EPS:
                out.append((cx, cy))
    return out


def _place_phase1(sh: _Shape, is_rect: bool, fw: float, fh: float,
                  placed: list[dict], g: float, E: float) -> tuple | None:
    """Lowest-leftmost position from the classic candidate set + attractors."""
    xs = sorted({0.0} | {p["aabb"][2] + g for p in placed})
    ys = sorted({0.0} | {p["aabb"][3] + g for p in placed})
    cands: list[tuple[float, float]] = []
    for x0 in xs:
        if x0 + fw > E + _EPS:
            continue
        for y0 in ys:
            if y0 + fh > E + _EPS:
                break
            cands.append((x0, y0))
    cands.extend(_attractor_positions(placed, fw, fh, E))
    for (x0, y0) in sorted(set(cands), key=lambda t: (t[1], t[0])):
        if _fits_shape(sh, is_rect, x0, y0, placed, g, E):
            return (x0, y0)
    return None


def _place_phase2(sh: _Shape, fw: float, fh: float,
                  placed: list[dict], g: float, E: float) -> tuple | None:
    """Expanded search for concave interlocking before the square grows.

    Adds edge alignments of placed items (AABB edges, plus outline-vertex
    anchors of the largest real shapes) so that a notch cut into a placed
    outline can be found at its true offset; hole attractors are included
    as in phase 1.  Rectangles never need it (the classic candidate set is
    complete for axis-aligned boxes).  Outline anchors are capped to the
    largest 8 shapes so the candidate grid stays bounded.
    """
    xs = {0.0}
    ys = {0.0}
    for p in placed:
        px0, py0, px1, py1 = p["aabb"]
        xs.add(px1 + g)
        xs.add(px0)
        if px1 + g - fw >= 0.0:
            xs.add(px1 + g - fw)
        ys.add(py1 + g)
        ys.add(py0)
        if py1 + g - fh >= 0.0:
            ys.add(py1 + g - fh)
    anchors = []
    for p in sorted(placed, key=lambda q: -(q["shape"].w * q["shape"].h)):
        if not p["rect"]:
            anchors.append(p)
        if len(anchors) >= 8:
            break
    for p in anchors:
        ox, oy = p["pos"]
        for (vx, vy) in p["shape"].vpts:
            ax = vx + ox
            ay = vy + oy
            xs.add(ax + g)
            if ax - g - fw >= 0.0:
                xs.add(ax - g - fw)
            ys.add(ay + g)
            if ay - g - fh >= 0.0:
                ys.add(ay - g - fh)
    cands = [(x, y) for x in xs for y in ys
             if x >= -_EPS and y >= -_EPS
             and x + fw <= E + _EPS and y + fh <= E + _EPS]
    cands.extend(_attractor_positions(placed, fw, fh, E))
    for (x0, y0) in sorted(set(cands), key=lambda t: (t[1], t[0])):
        if _fits_shape(sh, False, x0, y0, placed, g, E):
            return (x0, y0)
    return None


def pack_tile(items: list[Item], rotate_90: bool,
              g: float) -> tuple[float, list[tuple[int, float, float,
                                                   float, float, bool]]]:
    """Greedily pack one tile's items into a growing square.

    Returns ``(E, placements)`` where ``E`` is the required CONTENT extent
    in reference units (the bounding side of all placed items) and
    placements are ``(item_index, x0, y0, w, h, rotated)`` in content-
    space coordinates inside ``[0, E]``.

    The caller maps content space into a final tile with
    ``uv = tile_origin + margin + coord * S`` where
    ``S = (1 - 2*margin) / max_t(E_t)``; the border margin therefore never
    scales with S and every item is scaled by exactly S.

    Tiles without real outlines use the classic bbox-only greedy (fast,
    identical to the original engine).  Shape-carrying tiles use polygon
    collision: items are processed largest first, each placed at the
    lowest-leftmost valid position (best of both orientations when
    rotation is allowed), exploiting concavities and holes.  When nothing
    fits without growth, an expanded candidate set is tried before the
    region grows just enough for a new top row or right column.
    """
    if not items:
        return 0.0, []
    if not any(it.outers for it in items):
        return _pack_tile_rect(items, rotate_90, g)

    order = sorted(
        items,
        key=lambda it: (-(it.w * it.h), -max(it.w, it.h), it.index))
    E = max(max(it.w, it.h) for it in items)
    placed: list[dict] = []
    out: list[tuple[int, float, float, float, float, bool]] = []
    cache: dict[tuple[int, bool], _Shape] = {}

    def get_shape(it: Item, rot: bool) -> _Shape:
        key = (it.index, rot)
        sh = cache.get(key)
        if sh is None:
            sh = _build_shape(it, rot)
            cache[key] = sh
        return sh

    for it in order:
        cands = _orientations(it, rotate_90)
        pos = None
        chosen = None
        # Phase 1: classic candidate set + hole attractors.
        for (fw, fh, rot) in cands:
            p = _place_phase1(get_shape(it, rot), not it.outers, fw, fh,
                              placed, g, E)
            if p is not None and (pos is None or p < pos):
                pos, chosen = p, (fw, fh, rot)
        # Phase 2: expanded candidate set for concave interlocking.
        # Rectangles can use it too in mixed tiles (they can sit inside a
        # placed shape's notch); the internal guard keeps it cheap.
        if pos is None:
            for (fw, fh, rot) in cands:
                p = _place_phase2(get_shape(it, rot), fw, fh, placed, g, E)
                if p is not None and (pos is None or p < pos):
                    pos, chosen = p, (fw, fh, rot)
        # Grow the region so a new top row / right column fits; pick the
        # orientation needing the smallest growth, then retry both phases.
        if pos is None:
            max_x1 = max((p["aabb"][2] for p in placed), default=0.0)
            max_y1 = max((p["aabb"][3] for p in placed), default=0.0)
            best_e = None
            for (fw, fh, rot) in cands:
                e_req = max(E, fw, fh, max_x1 + g + fw, max_y1 + g + fh)
                if best_e is None or e_req < best_e:
                    best_e = e_req
            E = best_e
            for (fw2, fh2, rot2) in cands:
                p = _place_phase1(get_shape(it, rot2), not it.outers, fw2,
                                  fh2, placed, g, E)
                if p is None and it.outers:
                    p = _place_phase2(get_shape(it, rot2), fw2, fh2,
                                      placed, g, E)
                if p is not None and (pos is None or p < pos):
                    pos, chosen = p, (fw2, fh2, rot2)
            if pos is None:  # pragma: no cover - defensive
                raise RuntimeError("layout solver failed to place an item")
        x0, y0 = pos
        fw, fh, rot = chosen
        sh = get_shape(it, rot)
        placed.append({
            "aabb": (x0, y0, x0 + fw, y0 + fh),
            "pos": (x0, y0),
            "shape": sh,
            "cshape": _offset_shape(sh, g) if g > 0.0 else sh,
            "rect": not it.outers,
        })
        out.append((it.index, x0, y0, fw, fh, rot))

    return E, out


# ------------------------------------------------------- assignment -------

def _lpt_assign(items: list[Item], n_tiles: int, key) -> dict[int, list[Item]]:
    """Longest-processing-time load balancing with a given sort key."""
    loads = [0.0] * n_tiles
    assign: dict[int, list[Item]] = {t: [] for t in range(n_tiles)}
    for it in sorted(items, key=key):
        t = min(range(n_tiles), key=lambda i: (loads[i], i))
        assign[t].append(it)
        loads[t] += it.w * it.h
    return assign


def _rect_proxy(lst: list[Item]) -> list[Item]:
    return [Item(it.index, it.w, it.h) for it in lst]


def _rebalance(assign: dict[int, list[Item]], grid_x: int, grid_y: int,
               rotate_90: bool, g: float, max_passes: int = 4) -> dict:
    """Bounded local search that evens out tile extents.

    Plain LPT balances total AREA per tile; the resulting pack EXTENTS can
    still be very uneven (a few wide items stack taller than other tiles'
    contents), which caps the global scale and leaves neighbour tiles
    visibly underfilled.  Here the tightest tile donates its largest items
    - and later single item pairs - to emptier tiles while the proxy
    objective ``(max_extent, -tiles_used, spread)`` strictly improves:
    first shrink the extent that caps the global scale, then (at equal max)
    never sacrifice a used tile, then even out the extents of the tiles that
    remain.  Because per-tile fill balance is exactly AREA balance (the
    global scale is common to every tile), a trial must also keep the
    area ratio between used tiles within 1.5x of the current one and must
    never empty a tile - otherwise the "improved" extent just moves density
    into fewer, sparser UDIMs.  Near-equal-area swaps that tighten extents
    still pass.  Trials are evaluated with the fast bbox-only pack; the
    winning assignment is repacked shape-aware by the caller.  Deterministic:
    fixed caps and orders, strict improvement only.
    """
    n_tiles = grid_x * grid_y

    def ext_of(lst: list[Item]) -> float:
        return _pack_tile_rect(_rect_proxy(lst), rotate_90, g)[0] if lst else 0.0

    # LPT already balanced per-tile AREA (= per-tile fill balance, since the
    # global scale is common to every tile).  ``areas`` tracks the current
    # per-tile area and is updated as trials are accepted.
    areas = {t: sum(i.w * i.h for i in assign[t])
             for t in range(n_tiles) if assign[t]}

    for _ in range(max_passes):
        ext = {t: ext_of(assign[t]) for t in range(n_tiles) if assign[t]}
        if len(ext) < 2:
            break
        order = sorted(ext, key=lambda t: (-ext[t], t))
        tb = order[0]
        lo = min(ext.values())
        if ext[tb] <= lo * 1.03 + 1e-9:
            break  # balanced enough

        def trial_key(t: int, e_tb: float, e_t: float) -> tuple:
            """(max extent, -tiles used, spread) after the trial move."""
            used = [e for k, e in ext.items() if k not in (tb, t)]
            used += [e_tb, e_t]
            used = [e for e in used if e > 1e-12]
            hi = max(used)
            return (hi, -len(used), hi - min(used))

        vals0 = sorted(ext.values(), reverse=True)
        old_key = (vals0[0], -len(vals0), vals0[0] - vals0[-1])

        def area_ok() -> tuple:
            """Post-trial areas of the two changed tiles + balance check.

            The trial must not worsen the current per-tile AREA ratio: a
            one-way move that makes one tile denser and another sparser
            just moves density between UDIMs (visibly uneven fill) without
            helping the user.  Only extent-improving trials that keep - or
            improve - area balance pass; near-equal-area swaps qualify.
            """
            a_tb = sum(i.w * i.h for i in assign[tb])
            a_t = sum(i.w * i.h for i in assign[t])
            if a_tb <= 1e-12 or a_t <= 1e-12:
                return a_tb, a_t, False  # never empty a tile
            cur = sorted(areas.values(), reverse=True)
            old_r = cur[0] / cur[-1] if cur[-1] > 1e-12 else float("inf")
            used_a = [a for k, a in areas.items() if k not in (tb, t)]
            used_a += [a_tb, a_t]
            ratio = max(used_a) / min(used_a)
            return a_tb, a_t, ratio <= old_r + 1e-9

        improved = False
        # -- moves: largest items of the tightest tile to emptier tiles
        for it in sorted(assign[tb], key=lambda i: (-(i.w * i.h), i.index))[:10]:
            if improved:
                break
            for t in order[1:4]:
                assign[tb].remove(it)
                assign[t].append(it)
                e_tb = ext_of(assign[tb])
                e_t = ext_of(assign[t])
                a_tb, a_t, ok_a = area_ok()
                if trial_key(t, e_tb, e_t) < old_key and ok_a:
                    ext[tb] = e_tb
                    ext[t] = e_t
                    areas[tb] = a_tb
                    areas[t] = a_t
                    improved = True
                    break
                assign[t].remove(it)
                assign[tb].append(it)

        # -- swaps: one item of the tightest tile with a large item elsewhere
        if not improved:
            for it in sorted(assign[tb], key=lambda i: (-(i.w * i.h), i.index))[:6]:
                if improved:
                    break
                for t in order[1:3]:
                    if improved:
                        break
                    for jt in sorted(assign[t],
                                     key=lambda i: (-(i.w * i.h), i.index))[:2]:
                        assign[tb].remove(it)
                        assign[t].append(it)
                        assign[t].remove(jt)
                        assign[tb].append(jt)
                        e_tb = ext_of(assign[tb])
                        e_t = ext_of(assign[t])
                        a_tb, a_t, ok_a = area_ok()
                        if trial_key(t, e_tb, e_t) < old_key and ok_a:
                            ext[tb] = e_tb
                            ext[t] = e_t
                            areas[tb] = a_tb
                            areas[t] = a_t
                            improved = True
                            break
                        # reverse the swap exactly
                        assign[t].remove(it)
                        assign[tb].append(it)
                        assign[tb].remove(jt)
                        assign[t].append(jt)
        if not improved:
            break
    return assign


def solve(items: list[Item], grid_x: int, grid_y: int, margin: float,
          rotate_90: bool) -> tuple[float, list[Placement]]:
    """Solve the global layout.

    Returns ``(S, placements)``: the maximum uniform scale (within this
    heuristic family) and each item's placement in reference-scale,
    content-space tile-local coordinates.  The caller maps a placement to
    final UV space with ``x = tile_u + margin + x0 * S`` etc., and applies
    total scale ``S * per-item pre-scale`` when writing back.

    Deterministic: three fixed orderings (area, max-dim, w+h) are tried;
    the assignment with the smallest tightest-tile extent wins (ties broken
    by most tiles used, then tightest extent spread, then ordering index);
    a bounded local search evens out tile extents under the same objective
    before the final shape-aware pack.
    """
    if not items:
        return 1.0, []
    g = max(float(margin), 0.0)
    W = 1.0 - 2.0 * g
    if W <= 1e-9:
        raise ValueError("margin too large for a unit tile")

    n_tiles = grid_x * grid_y
    keys = [
        lambda it: (-(it.w * it.h), -max(it.w, it.h), it.index),
        lambda it: (-max(it.w, it.h), -(it.w * it.h), it.index),
        lambda it: (-(it.w + it.h), -(it.w * it.h), it.index),
    ]
    best = None  # (max_extent, -tiles_used, spread, order_idx, assign)
    for idx, key in enumerate(keys):
        assign = _lpt_assign(items, n_tiles, key)
        ext = {t: _pack_tile_rect(_rect_proxy(assign[t]), rotate_90, g)[0]
               for t in range(n_tiles) if assign[t]}
        vals = sorted(ext.values(), reverse=True)
        cand = (vals[0], -len(vals), vals[0] - vals[-1], idx, assign)
        if best is None or (cand[0], cand[1], cand[2]) < \
                (best[0], best[1], best[2]):
            best = cand
    assert best is not None
    _, _, _, _, assign = best

    assign = _rebalance(assign, grid_x, grid_y, rotate_90, g)

    max_extent = 0.0
    placements: list[Placement] = []
    for t in sorted(assign):
        if not assign[t]:
            continue
        L, packed = pack_tile(assign[t], rotate_90, g)
        max_extent = max(max_extent, L)
        # Flat tile index -> (column, row): column first along U.
        tu, tv = t % grid_x, t // grid_x
        for (idx_i, x0, y0, fw, fh, rot) in packed:
            placements.append(Placement(
                item=idx_i, tile_u=tu, tile_v=tv,
                x0=x0, y0=y0, w=fw, h=fh, rotated=rot))

    S = W / max_extent if max_extent > 1e-12 else 1.0
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
