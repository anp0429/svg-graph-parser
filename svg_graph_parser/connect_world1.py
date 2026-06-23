"""Stage 3 (World 1): turn classified primitives into a directed edge list.

For each connector:
  - The end nearest its arrowhead is the target side; the other end is source.
  - The arrowhead tip points in the connector's travel direction. The shape
    nearest the tip is the target.
  - The shape nearest the source end is the source.
  - Emit source -> target.

Direction is read from geometry (the tip), never from draw order or grouping,
so it holds for arrows pointing any way, touching or not.
"""

import math

from .parse_world1 import parse_world1
from .constants_world1 import MATCH_TOL


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_to_box_dist(p, box):
    x, y = p
    dx = max(box[0] - x, 0, x - box[2])
    dy = max(box[1] - y, 0, y - box[3])
    return math.hypot(dx, dy)


def _nearest_shape(point, shapes, tol):
    best, best_d = None, tol
    for s in shapes:
        d = _point_to_box_dist(point, s.bbox)
        if d <= best_d:
            best, best_d = s, d
    return best


def _arrowhead_tip(head, travel):
    """Vertex of the arrowhead furthest along the travel direction."""
    cx = (head.bbox[0] + head.bbox[2]) / 2
    cy = (head.bbox[1] + head.bbox[3]) / 2
    tx, ty = travel
    best, best_proj = None, None
    for v in head.points:
        proj = (v[0] - cx) * tx + (v[1] - cy) * ty
        if best is None or proj > best_proj:
            best, best_proj = v, proj
    return best


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return (0.0, 0.0) if n == 0 else (dx / n, dy / n)


def build_edges(shapes, connectors):
    edges = []
    for c in connectors:
        a, b = c.points[0], c.points[-1]
        # Which end carries the arrowhead.
        hc = ((c.head.bbox[0] + c.head.bbox[2]) / 2,
              (c.head.bbox[1] + c.head.bbox[3]) / 2)
        if _dist(hc, b) <= _dist(hc, a):
            source_end, target_end = a, b
            travel = _unit(b[0] - c.points[-2][0], b[1] - c.points[-2][1])
        else:
            source_end, target_end = b, a
            travel = _unit(a[0] - c.points[1][0], a[1] - c.points[1][1])

        tip = _arrowhead_tip(c.head, travel)
        target = _nearest_shape(tip, shapes, MATCH_TOL)
        source = _nearest_shape(source_end, shapes, MATCH_TOL)
        if source is not None and target is not None and source is not target:
            edges.append((source, target))
    return edges


def reconstruct(svg_path):
    shapes, connectors, arrowheads, decorations = parse_world1(svg_path)
    edges = build_edges(shapes, connectors)
    return shapes, edges


def _label(s):
    t = (s.text or "").replace("\n", " ").replace("\t", " ")
    t = " ".join(t.split())
    return t[:24] if t else "(no text)"


if __name__ == "__main__":
    import sys
    shapes, edges = reconstruct(sys.argv[1])
    print("nodes=%d edges=%d" % (len(shapes), len(edges)))
    print()
    for src, dst in edges:
        print("  %-26s -> %s" % (_label(src), _label(dst)))
