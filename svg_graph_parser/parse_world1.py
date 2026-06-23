"""Stage 2 (World 1): classify primitives, associate arrowheads and text,
and drop decorations with the two-pass rule.

Design floor: nodes are found by geometry, not by grouping, so this survives
ungrouped hand-drawn SVGs. Grouping is used only as an accelerator for the
first decoration pass.

Two-pass decoration filter:
  Pass 1: a connector line sharing a group with a shape is a decoration.
  Pass 2: a remaining line whose ends sit inside and touch one shape, and that
          has no arrowhead, is a decoration.
Survivors with an arrowhead are real connectors.
"""

import math
import xml.etree.ElementTree as ET

from .geometry_world1 import path_bbox, parse_points, points_bbox
from .constants_world1 import ARROWHEAD_MAX_SIDE, ATTACH_TOL, TEXT_PAD

NS = "{http://www.w3.org/2000/svg}"


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


class Prim:
    def __init__(self, kind, attrib, group):
        self.kind = kind          # 'path' | 'polyline' | 'polygon' | 'text'
        self.attrib = attrib
        self.group = group        # id of immediate enclosing <g>, or None
        self.points = None
        self.bbox = None
        self.text = None
        self.role = None          # 'shape' | 'connector' | 'arrowhead' | 'text'
        self.head = None          # arrowhead Prim attached to a connector
        self.anchor = None        # text anchor point


def load_primitives(svg_path):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    prims = []
    counter = [0]

    def walk(el, group):
        tag = el.tag.replace(NS, "")
        if tag == "g":
            counter[0] += 1
            gid = counter[0]
            for child in el:
                walk(child, gid)
            return
        if tag in ("path", "polyline", "polygon", "text"):
            prims.append((tag, el, group))
        for child in el:
            walk(child, group)

    walk(root, None)

    out = []
    for tag, el, group in prims:
        p = Prim(tag, el.attrib, group)
        if tag == "path":
            p.bbox = path_bbox(el.attrib.get("d", ""))
        elif tag in ("polyline", "polygon"):
            p.points = parse_points(el.attrib.get("points", ""))
            p.bbox = points_bbox(p.points)
        elif tag == "text":
            x = float(el.attrib.get("x", "0"))
            y = float(el.attrib.get("y", "0"))
            p.anchor = (x, y)
            p.text = "".join(el.itertext()).strip()
        out.append(p)
    return out


def classify(prims):
    for p in prims:
        if p.kind == "text":
            p.role = "text"
        elif p.kind == "path":
            fill = p.attrib.get("fill", "none")
            p.role = "shape" if fill != "none" else "connector"
        elif p.kind == "polygon":
            side = max(p.bbox[2] - p.bbox[0], p.bbox[3] - p.bbox[1])
            p.role = "arrowhead" if side <= ARROWHEAD_MAX_SIDE else "shape"
        elif p.kind == "polyline":
            fill = p.attrib.get("fill", "none")
            p.role = "connector" if fill == "none" else "shape"
    return prims


def associate_arrowheads(prims):
    heads = [p for p in prims if p.role == "arrowhead"]
    lines = [p for p in prims if p.role == "connector"]
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
    return prims


def filter_decorations(prims):
    shapes = [p for p in prims if p.role == "shape"]
    lines = [p for p in prims if p.role == "connector"]
    dropped = []

    # Pass 1: line shares a group with a shape -> decoration.
    shape_groups = {s.group for s in shapes if s.group is not None}
    for ln in lines:
        if ln.group in shape_groups:
            ln.role = "decoration"
            dropped.append(("group", ln))

    # Pass 2: remaining line with no arrowhead whose BOTH ends sit inside the
    # SAME shape -> decoration. Both ends, one shape. A real connector reaches
    # from one shape to another, so it can never satisfy this.
    for ln in [l for l in lines if l.role == "connector"]:
        if ln.head is not None:
            continue
        a, b = ln.points[0], ln.points[-1]
        for s in shapes:
            both_inside = _point_in_box(a, s.bbox) and _point_in_box(b, s.bbox)
            if both_inside:
                ln.role = "decoration"
                dropped.append(("geom", ln))
                break

    return dropped


def associate_text(prims):
    shapes = [p for p in prims if p.role == "shape"]
    texts = [p for p in prims if p.role == "text"]
    for t in texts:
        best, best_d = None, None
        for s in shapes:
            if _point_in_box(t.anchor, s.bbox, pad=TEXT_PAD):
                d = _point_to_box_dist(t.anchor, s.bbox)
                if best is None or d < best_d:
                    best, best_d = s, d
        if best is not None:
            if best.text is None:
                best.text = t.text
            else:
                best.text += " " + t.text
    return prims


def parse_world1(svg_path):
    prims = load_primitives(svg_path)
    classify(prims)
    associate_arrowheads(prims)
    filter_decorations(prims)
    associate_text(prims)
    shapes = [p for p in prims if p.role == "shape"]
    connectors = [p for p in prims if p.role == "connector"]
    arrowheads = [p for p in prims if p.role == "arrowhead"]
    decorations = [p for p in prims if p.role == "decoration"]
    return shapes, connectors, arrowheads, decorations


if __name__ == "__main__":
    import sys
    shapes, connectors, arrowheads, decorations = parse_world1(sys.argv[1])
    print("shapes=%d connectors=%d arrowheads=%d decorations_dropped=%d"
          % (len(shapes), len(connectors), len(arrowheads), len(decorations)))
    print()
    for s in shapes:
        b = s.bbox
        print("  SHAPE (%4.0f,%4.0f,%4.0f,%4.0f)  text=%r"
              % (b[0], b[1], b[2], b[3], (s.text or "")[:40]))
    print()
    for c in connectors:
        print("  CONNECTOR ends=%s head=%s"
              % ([(round(c.points[0][0]), round(c.points[0][1])),
                  (round(c.points[-1][0]), round(c.points[-1][1]))],
                 "yes" if c.head else "NO"))