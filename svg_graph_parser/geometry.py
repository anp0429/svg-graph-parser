"""Stage 1 -- geometric primitive analysis.

Format-agnostic on purpose: every input is a list of (x, y) points plus two
booleans the loader can derive from any vector format (SVG `Z` / PDF `h` close
op, and whether the path is filled). Nothing here reads SVG tags, draw.io
`<g>` groups, or cell-ids -- those are oracles used only to *score*, never to
reconstruct.
"""
from __future__ import annotations

import math
from enum import Enum


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def is_closed(pts, explicit_close=False, filled=False, eps=1.5) -> bool:
    """Does this path bound a region?

    Closure signal, strongest-first: an explicit close operator (SVG Z / PDF h),
    OR a fill (you cannot meaningfully fill an open path), OR the last point
    returning to the first within eps. The last test is what lets PDF input --
    which often omits an explicit close -- still resolve correctly.
    """
    if explicit_close or filled:
        return True
    return len(pts) >= 3 and _dist(pts[0], pts[-1]) <= eps


def bbox_of(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def area_span(pts) -> float:
    """Diagonal of the point set's bounding box -- a cheap size proxy."""
    x0, y0, x1, y1 = bbox_of(pts)
    return math.hypot(x1 - x0, y1 - y0)


class Primitive(Enum):
    LINE = "line"
    SHAPE = "shape"


def classify_primitive(pts, explicit_close=False, filled=False) -> Primitive:
    """Open path -> LINE (connector candidate). Closed region -> SHAPE."""
    return Primitive.SHAPE if is_closed(pts, explicit_close, filled) else Primitive.LINE


class Head(Enum):
    FILLED_TRIANGLE = "filled_triangle"
    OPEN_CHEVRON = "open_chevron"
    DIAMOND = "diamond"
    CIRCLE = "circle"
    NONE = "none"


def classify_arrowhead(shape_pts, filled, line_endpoint, *,
                       median_node_span=120.0, coincidence_eps=3.0) -> Head:
    """Type a candidate head shape sitting at a line's free end.

    Local geometry only -- the head's own shape plus coincidence with the line
    end. Guards against false positives (a small node that merely sits near a
    line) by requiring a vertex to coincide with the line endpoint.
    """
    span = area_span(shape_pts)
    if span > 0.4 * median_node_span:        # too big to be a head -> it's a node
        return Head.NONE

    # a vertex must touch the line's free end, else it's just a nearby shape
    if min(_dist(p, line_endpoint) for p in shape_pts) > coincidence_eps:
        return Head.NONE

    n = len(set((round(x, 1), round(y, 1)) for x, y in shape_pts))
    if filled and n <= 4:
        return Head.FILLED_TRIANGLE
    if filled and 4 <= n <= 5:
        return Head.DIAMOND
    if not filled and n <= 3:
        return Head.OPEN_CHEVRON
    if n >= 6:
        return Head.CIRCLE
    return Head.FILLED_TRIANGLE if filled else Head.OPEN_CHEVRON