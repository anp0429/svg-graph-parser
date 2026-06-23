"""World 1 reconstruction on the universal loader.

This is the loader-based pipeline. Unlike the original Flowgorithm-only path,
it consumes resolved drawables (use-instanced, transform-composed, all
primitive types) and so handles real Inkscape and draw.io output.

Stages:
  1. load drawables (core.loader) and text (core.text_reader)
  2. classify each drawable: shape, connector, or arrowhead
  3. associate each arrowhead to the nearest connector endpoint
  4. drop decorations (a connector with both ends inside one shape, no head)
  5. attach each text run to the shape that contains its anchor
  6. build directed edges, direction from the arrowhead tip
"""

import math

from ..core.loader import load, _style_fill
from ..core.text_reader import load_text
from .constants import ARROWHEAD_MAX_SIDE, ATTACH_TOL, MATCH_TOL, TEXT_PAD


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _point_in_box(p, box, pad=0.0):
    x, y = p
    return (box[0] - pad <= x <= box[2] + pad
            and box[1] - pad <= y <= box[3] + pad)


def _point_to_box_dist(p, box):
    x, y = p
    dx = max(box[0] - x, 0, x - box[2])
    dy = max(box[1] - y, 0, y - box[3])
    return math.hypot(dx, dy)


def classify(els):
    """Tag each drawable with a role. Returns nothing; sets el.role/head/text."""
    for e in els:
        e.role = None
        e.head = None
        e.text = None
        fill = (_style_fill(e.attrib) or "none").lower()
        w, h = e.bbox[2] - e.bbox[0], e.bbox[3] - e.bbox[1]
        side = max(w, h)
        is_open = fill in ("none", "")
        if is_open:
            e.role = "connector"
        elif side <= ARROWHEAD_MAX_SIDE:
            e.role = "arrowhead"
        else:
            e.role = "shape"


def associate_arrowheads(els):
    heads = [e for e in els if e.role == "arrowhead"]
    lines = [e for e in els if e.role == "connector"]
    for h in heads:
        hc = ((h.bbox[0] + h.bbox[2]) / 2, (h.bbox[1] + h.bbox[3]) / 2)
        best, best_d = None, ATTACH_TOL
        for ln in lines:
            ends = [ln.points[0], ln.points[-1]]
            d = min(_dist(hc, e) for e in ends)
            if d < best_d:
                best, best_d = ln, d
        if best is not None:
            best.head = h


def filter_decorations(els):
    shapes = [e for e in els if e.role == "shape"]
    dropped = []
    for ln in [e for e in els if e.role == "connector"]:
        if ln.head is not None:
            continue
        a, b = ln.points[0], ln.points[-1]
        for s in shapes:
            if _point_in_box(a, s.bbox) and _point_in_box(b, s.bbox):
                ln.role = "decoration"
                dropped.append(ln)
                break
    return dropped


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def attach_text(els, text_runs):
    """Attach node labels to shapes. Return runs that are NOT node labels.

    A run is a node label only if it sits strictly inside a shape and is
    closer to that shape's center than to any connector endpoint. Branch
    labels like "Yes" and "No" sit near a connector end and near a shape
    edge, so they fail this test and are returned as edge-label candidates.
    """
    shapes = [e for e in els if e.role == "shape"]
    connectors = [e for e in els if e.role == "connector"]
    endpoints = []
    for c in connectors:
        endpoints.append(c.points[0])
        endpoints.append(c.points[-1])

    leftovers = []
    for t in text_runs:
        # nearest shape that strictly contains the anchor
        host, host_d = None, None
        for s in shapes:
            if _point_in_box(t.anchor, s.bbox, pad=0.0):
                d = _dist(t.anchor, _center(s.bbox))
                if host is None or d < host_d:
                    host, host_d = s, d
        if host is None:
            leftovers.append(t)
            continue
        # is it closer to a connector endpoint than to the shape center?
        nearest_ep = min((_dist(t.anchor, e) for e in endpoints), default=1e9)
        if nearest_ep < host_d:
            leftovers.append(t)  # behaves like an edge label, not a node label
        else:
            host.text = (host.text + " " + t.text) if host.text else t.text
    return leftovers


def _arrowhead_tip(head, travel):
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


def _nearest_shape(point, shapes, tol):
    best, best_d = None, tol
    for s in shapes:
        d = _point_to_box_dist(point, s.bbox)
        if d <= best_d:
            best, best_d = s, d
    return best


class Edge:
    def __init__(self, source, target, connector):
        self.source = source
        self.target = target
        self.connector = connector
        self.label = None


def build_edges(els):
    shapes = [e for e in els if e.role == "shape"]
    connectors = [e for e in els if e.role == "connector" and e.head is not None]
    edges = []
    for c in connectors:
        a, b = c.points[0], c.points[-1]
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
            edges.append(Edge(source, target, c))
    return edges


def attach_edge_labels(edges, leftover_runs):
    """Assign each leftover text run to the edge whose connector it sits on.

    A branch label (Yes/No) sits near its connector. We attach each leftover
    run to the edge whose connector has the nearest point to the run anchor,
    within a tolerance.
    """
    for run in leftover_runs:
        best, best_d = None, MATCH_TOL
        for e in edges:
            for p in e.connector.points:
                d = _dist(run.anchor, p)
                if d < best_d:
                    best, best_d = e, d
        if best is not None:
            best.label = (best.label + " " + run.text) if best.label else run.text


def reconstruct_universal(svg_path):
    els = load(svg_path)
    classify(els)
    associate_arrowheads(els)
    filter_decorations(els)
    leftovers = attach_text(els, load_text(svg_path))
    shapes = [e for e in els if e.role == "shape"]
    edges = build_edges(els)
    attach_edge_labels(edges, leftovers)
    return shapes, edges


def _label(s):
    return (s.text or "(no text)")[:28]


if __name__ == "__main__":
    import sys
    shapes, edges = reconstruct_universal(sys.argv[1])
    print("nodes=%d edges=%d" % (len(shapes), len(edges)))
    print()
    for s in shapes:
        b = s.bbox
        print("  SHAPE (%5.0f,%5.0f,%5.0f,%5.0f) text=%r"
              % (b[0], b[1], b[2], b[3], _label(s)))
    print()
    for e in edges:
        tag = (" [%s]" % e.label) if e.label else ""
        print("  %-26s -%s-> %s"
              % (_label(e.source), e.label or "", _label(e.target)))