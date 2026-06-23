"""World 1 reconstruction on the universal loader.

Consumes resolved drawables (use-instanced, transform-composed, all primitive
types) and reconstructs a directed graph from geometry.

Stages:
  1. load drawables (core.loader) and text (core.text_reader)
  2. classify each drawable: shape, connector, or arrowhead
  3. associate each arrowhead to the nearest connector endpoint
  4. drop decorations (a connector with both ends inside one shape, no head)
  5. containment: a shape that contains other shapes is a group, not a node
  6. attach each text run to the shape that contains it
  7. build edges: directed from the arrowhead tip; headless lines undirected
"""

import math

from ..core.loader import load, _style_fill
from ..core.text_reader import load_text
from ..core.containment import assign_containment
from .constants import ARROWHEAD_MAX_SIDE, ATTACH_TOL, MATCH_TOL, TEXT_PAD
from ..core.point_match import match_shape
# Scale-relative knobs. Move to constants.py once you are happy with them.
MATCH_TOL_FACTOR = 0.6      # match tolerance = this * typical node size
TRAVEL_BACKOFF_FRAC = 0.15  # read direction over this fraction of connector length

MIN_EDGE_CONFIDENCE = 1.0 - MATCH_TOL_FACTOR   # = 0.4, see note below

# ---------------------------------------------------------------- geometry helpers

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return (0.0, 0.0) if n == 0 else (dx / n, dy / n)


def _point_in_box(p, box, pad=0.0):
    x, y = p
    return (box[0] - pad <= x <= box[2] + pad
            and box[1] - pad <= y <= box[3] + pad)


def _point_to_box_dist(p, box):
    x, y = p
    dx = max(box[0] - x, 0, x - box[2])
    dy = max(box[1] - y, 0, y - box[3])
    return math.hypot(dx, dy)


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _connector_length(points):
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _travel_at_end(points, at_last_end, backoff):
    """Unit vector out through the chosen end, ignoring a tiny last segment.

    Walk inward from the end until we have covered `backoff` of path length,
    then take direction from that inner point to the end. A small kink or
    rounded corner at the very tip no longer flips the direction.
    """
    seq = list(reversed(points)) if at_last_end else list(points)
    tip, ref = seq[0], seq[-1]
    acc, prev = 0.0, tip
    for p in seq[1:]:
        acc += _dist(prev, p)
        prev = p
        if acc >= backoff:
            ref = p
            break
    return _unit(tip[0] - ref[0], tip[1] - ref[1])


def _typical_node_size(shapes):
    """Median bbox diagonal: the characteristic length the file is drawn at."""
    diags = sorted(math.hypot(s.bbox[2] - s.bbox[0], s.bbox[3] - s.bbox[1])
                   for s in shapes)
    return diags[len(diags) // 2] if diags else None


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



# ---------------------------------------------------------------- pipeline stages

def classify(els, canvas=None):
    """Tag each drawable with a role. Sets el.role/head/text.

    rect, circle, ellipse are closed by type, so they are nodes regardless of
    fill. For paths and polygons we use closure: a closed small shape is an
    arrowhead, an open shape is a connector, a closed large shape is a node.
    """
    cw, ch = (canvas or (0, 0))
    canvas_area = cw * ch
    for e in els:
        e.role = None
        e.head = None
        e.text = None
        w, h = e.bbox[2] - e.bbox[0], e.bbox[3] - e.bbox[1]
        side = max(w, h)
        area = w * h

        if canvas_area and area >= 0.9 * canvas_area:
            e.role = "background"
            continue
        if e.tag in ("rect", "circle", "ellipse"):
            e.role = "shape"
            continue
        if e.tag == "line":
            e.role = "connector"
            continue

        # path or polygon
        closed = getattr(e, "closed", None)
        if closed is None:
            fill = (_style_fill(e.attrib) or "none").lower()
            closed = fill not in ("none", "")
        if closed and side <= ARROWHEAD_MAX_SIDE:
            e.role = "arrowhead"
        elif not closed:
            e.role = "connector"
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


def attach_text(els, text_runs):
    """Attach node labels to shapes. Return runs that are NOT node labels.

    A run is a node label only if it sits strictly inside a shape and is closer
    to that shape's center than to any connector endpoint. Branch labels like
    "Yes"/"No" sit near a connector end, so they fail this test and are
    returned as edge-label candidates.
    """
    shapes = [e for e in els if e.role == "shape"]
    connectors = [e for e in els if e.role == "connector"]
    endpoints = []
    for c in connectors:
        endpoints.append(c.points[0])
        endpoints.append(c.points[-1])

    leftovers = []
    for t in text_runs:
        host, host_d = None, None
        for s in shapes:
            if _point_in_box(t.anchor, s.bbox, pad=0.0):
                d = _dist(t.anchor, _center(s.bbox))
                if host is None or d < host_d:
                    host, host_d = s, d
        if host is None:
            leftovers.append(t)
            continue
        nearest_ep = min((_dist(t.anchor, e) for e in endpoints), default=1e9)
        if nearest_ep < host_d:
            leftovers.append(t)  # behaves like an edge label, not a node label
        else:
            host.text = (host.text + " " + t.text) if host.text else t.text
    return leftovers


class Edge:
    def __init__(self, source, target, connector, directed=True, style=None,
                 source_confidence=1.0, target_confidence=1.0):
        self.source = source
        self.target = target
        self.connector = connector
        self.directed = directed
        self.label = None
        self.style = style
        self.source_confidence = source_confidence
        self.target_confidence = target_confidence

def _marker_direction(c):
    """Direction from SVG marker refs, if present. Returns 'end', 'start', or None.

    A connector with marker-end has its arrowhead at the LAST point (target side);
    marker-start puts it at the FIRST point. This is stated explicitly by the SVG,
    so no geometry is needed. marker-end wins if both are present.
    """
    style = c.attrib.get("style", "")
    def present(key):
        if key in c.attrib and c.attrib[key] not in ("none", ""):
            return True
        # style string form: "marker-end:url(#...)"
        for part in style.split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                if k.strip() == key and v.strip() not in ("none", ""):
                    return True
        return False
    if present("marker-end"):
        return "end"
    if present("marker-start"):
        return "start"
    return None


def build_edges(els):
    shapes = [e for e in els if e.role == "shape"]
    connectors = [e for e in els if e.role == "connector"]

    char_len = _typical_node_size(shapes)

    edges = []
    for c in connectors:
        if len(c.points) < 2:
            continue
        a, b = c.points[0], c.points[-1]
        style = getattr(c, "stroke_style", None)
        backoff = max(TRAVEL_BACKOFF_FRAC * _connector_length(c.points), 1.0)

        # CASE 0: SVG marker direction (marker-end / marker-start). Stated by the
        # SVG itself, so direction is exact with no tip detection.
        mdir = _marker_direction(c)
        if c.head is None and mdir is not None:
            if mdir == "end":
                source_end, target_end = a, b
            else:
                source_end, target_end = b, a
            target, tconf = match_shape(target_end, shapes, char_len)
            source, sconf = match_shape(source_end, shapes, char_len)
            if (source is not None and target is not None and source is not target
                    and sconf >= MIN_EDGE_CONFIDENCE and tconf >= MIN_EDGE_CONFIDENCE):
                edges.append(Edge(source, target, c, directed=True, style=style,
                                  source_confidence=sconf, target_confidence=tconf))
            continue

        # CASE 1: separate arrowhead. Direction from the tip.
        if c.head is not None:
            hc = ((c.head.bbox[0] + c.head.bbox[2]) / 2,
                  (c.head.bbox[1] + c.head.bbox[3]) / 2)
            at_last = _dist(hc, b) <= _dist(hc, a)
            source_end = a if at_last else b
            travel = _travel_at_end(c.points, at_last, backoff)
            tip = _arrowhead_tip(c.head, travel)
            target, tconf = match_shape(tip, shapes, char_len)
            source, sconf = match_shape(source_end, shapes, char_len)
            if (source is not None and target is not None and source is not target
                    and sconf >= MIN_EDGE_CONFIDENCE and tconf >= MIN_EDGE_CONFIDENCE):
                edges.append(Edge(source, target, c, directed=True, style=style,
                                  source_confidence=sconf, target_confidence=tconf))

        # CASE 2 (combined arrow) HOOK: arrows.py finds tip/tail, not wired yet.
        # When wired: tip/tail -> match_shape each -> directed Edge with confidences.

        # CASE 3: headless line. Emit undirected.
        else:
            s_a, ca = match_shape(a, shapes, char_len)
            s_b, cb = match_shape(b, shapes, char_len)
            if (s_a is not None and s_b is not None and s_a is not s_b
                    and ca >= MIN_EDGE_CONFIDENCE and cb >= MIN_EDGE_CONFIDENCE):
                ends = sorted([(s_a, ca), (s_b, cb)],
                              key=lambda x: (x[0].bbox[0], x[0].bbox[1]))
                edges.append(Edge(ends[0][0], ends[1][0], c, directed=False, style=style,
                                  source_confidence=ends[0][1],
                                  target_confidence=ends[1][1]))

    return edges


def attach_edge_labels(edges, leftover_runs):
    """Assign each leftover text run to the edge whose connector it sits on."""
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
    els, canvas = load(svg_path)
    classify(els, canvas)
    associate_arrowheads(els)
    filter_decorations(els)
    shapes = [e for e in els if e.role == "shape"]
    leaves, containers = assign_containment(shapes)
    for c in containers:
        c.role = "container"   # remove from the node set
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
        arrow = "->" if e.directed else "--"
        tag = (" [%s]" % e.label) if e.label else ""
        st = (" {%s}" % e.style) if e.style and e.style != "solid" else ""
        print("  %-26s %s %s%s%s"
              % (_label(e.source), arrow, _label(e.target), tag, st))