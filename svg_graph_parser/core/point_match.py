"""Point-to-shape matching by real polygon containment, with confidence.

Why this exists, and why it is separate from containment.py:

  containment.py answers "does shape A contain shape B?" and deliberately uses
  bounding boxes, so that overlapping-but-not-nested shapes (pie wedges) stay
  independent leaves. That is correct for THAT question.

  This file answers a different question: "which shape contains this POINT?"
  (an arrow tip, a connector endpoint). For that, bounding boxes are wrong: a
  point can sit in the empty corner of a wedge's bbox while being outside the
  actual wedge. So we test the point against the shape's REAL outline.

  Same overlapping wedges, opposite-direction question, different tool. The two
  files must stay separate. This one never imports or touches assign_containment.

The matcher returns (shape, confidence). Confidence is honest, three tiers:
  - point inside the shape's real polygon            -> 1.0
  - point inside MORE THAN ONE polygon (real overlap)-> 1.0 for the smallest
        (most specific) containing shape
  - point inside NO polygon                          -> nearest shape by bbox
        distance, confidence = 1 - distance/characteristic_length, floored at 0

The confidence is a measured distance over a real characteristic length, so it
means the same thing across files. No magic constants.
"""

import math


def point_in_polygon(point, verts):
    """Ray casting. True if point is inside the closed polygon `verts`.

    `verts` is the shape's outline as a list of (x, y). The polygon is treated
    as closed (last vertex joins the first). Degenerate shapes (< 3 vertices)
    are never "inside", so they fall through to the distance tier.
    """
    if not verts or len(verts) < 3:
        return False
    x, y = point
    n = len(verts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = verts[i]
        xj, yj = verts[j]
        # does the horizontal ray from the point cross this edge?
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _area(b):
    return (b[2] - b[0]) * (b[3] - b[1])


def _point_to_box_dist(p, box):
    x, y = p
    dx = max(box[0] - x, 0, x - box[2])
    dy = max(box[1] - y, 0, y - box[3])
    return math.hypot(dx, dy)


def match_shape(point, shapes, characteristic_length):
    """Return (shape, confidence) for the shape this point belongs to.

    shapes: objects with `.points` (real outline) and `.bbox`.
    characteristic_length: the file's typical node size, used to scale the
        distance-based confidence so it is comparable across diagrams.
    Returns (None, 0.0) if there are no shapes.
    """
    # Tier 1/2: real polygon containment.
    containing = [s for s in shapes if point_in_polygon(point, s.points)]
    if containing:
        # most specific (smallest) wins; ties broken by geometry for reproducibility
        best = min(containing, key=lambda s: (_area(s.bbox), s.bbox[0], s.bbox[1]))
        return best, 1.0

    # Tier 3: inside nothing. Nearest by bbox distance, confidence from distance.
    best, best_d = None, None
    for s in shapes:
        d = _point_to_box_dist(point, s.bbox)
        if best_d is None or d < best_d or \
           (d == best_d and (s.bbox[0], s.bbox[1]) < (best.bbox[0], best.bbox[1])):
            best, best_d = s, d
    if best is None:
        return None, 0.0
    if not characteristic_length:
        return best, 0.0
    conf = max(0.0, 1.0 - best_d / characteristic_length)
    return best, conf
