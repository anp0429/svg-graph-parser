"""Combined arrow glyphs.

Some tools draw a connector arrow as one self-contained path: a short shaft
fused with an arrowhead, no separate line element. draw.io, Graphviz, and
radial cycle diagrams all do this. Such a glyph has a tail (shaft end) and a
tip (arrowhead apex), so it carries its own direction.

Tip detection: the arrowhead barbs flare to their widest cross-section just
behind the apex. So along the glyph's long axis, the tip is the extreme end
nearer the widest perpendicular spread; the tail is the far end. This is more
robust than "farthest from centroid", which the arrowhead's mass biases.
"""

import math


def _principal_axis(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return "x" if w >= h else "y"


def arrow_endpoints(points):
    """Return (tail, tip) for a combined arrow glyph, or None if degenerate."""
    if len(points) < 3:
        return None
    axis = _principal_axis(points)
    ai = 0 if axis == "x" else 1
    pi = 1 - ai

    # the two extremes along the long axis
    lo = min(points, key=lambda p: p[ai])
    hi = max(points, key=lambda p: p[ai])

    # find the axis position of the widest perpendicular spread (the barbs)
    # bucket points by rounded axis coord, measure perpendicular extent
    buckets = {}
    for p in points:
        key = round(p[ai])
        buckets.setdefault(key, []).append(p[pi])
    widest_key, widest_span = None, -1
    for key, perp in buckets.items():
        span = max(perp) - min(perp)
        if span > widest_span:
            widest_span, widest_key = span, key

    # tip is the extreme closer to the widest cross-section
    d_lo = abs(lo[ai] - widest_key)
    d_hi = abs(hi[ai] - widest_key)
    if d_hi <= d_lo:
        return lo, hi   # tail=lo, tip=hi
    return hi, lo       # tail=hi, tip=lo


def is_arrow_glyph(element, max_side, min_points=5):
    """Heuristic: a small path with enough vertices to be an arrow shape.

    Works for filled or stroked arrows. Size below the arrowhead threshold and
    a vertex count consistent with a shaft-plus-head outline.
    """
    w = element.bbox[2] - element.bbox[0]
    h = element.bbox[3] - element.bbox[1]
    side = max(w, h)
    return element.tag == "path" and side <= max_side and len(element.points) >= min_points