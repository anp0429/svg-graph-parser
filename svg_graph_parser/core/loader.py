"""Universal SVG loader: every primitive, every transform, with <use> resolved.

The first loader assumed nodes are <path> and connectors are <polyline>, with
no transforms. Real SVG (Inkscape, draw.io, Illustrator) uses the full
vocabulary: <rect>, <circle>, <ellipse>, <line>, <polyline>, <polygon>,
<path>, nested <g> transforms, and <use> elements that clone a referenced
element at a new transform.

This loader walks the tree once, carrying the composed transform from the root
down. For each drawable element it produces absolute points (already
transformed), so every downstream stage sees real coordinates and never has to
know about transforms or instancing again.

A <use href="#id"> is resolved by looking up the referenced element (or group)
and re-walking it with the use's own transform composed on top, plus the
x/y offset the spec adds.
"""

import xml.etree.ElementTree as ET

from svgpathtools import parse_path

from .transforms import parse_transform, multiply, apply_many, IDENTITY

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _tag(el):
    return el.tag.split("}")[-1]


def _href(el):
    for k in (f"{{{XLINK_NS}}}href", "href"):
        if k in el.attrib:
            return el.attrib[k]
    return None


def _num(attrib, key, default=0.0):
    v = attrib.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _local_points(el):
    """Local (untransformed) outline points for a drawable element.

    Returns a list of points, or None if this element is not drawable here.
    Curves and arcs in <path> are flattened by svgpathtools sampling.
    """
    tag = _tag(el)
    a = el.attrib

    if tag == "rect":
        x, y = _num(a, "x"), _num(a, "y")
        w, h = _num(a, "width"), _num(a, "height")
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    if tag == "circle":
        cx, cy, r = _num(a, "cx"), _num(a, "cy"), _num(a, "r")
        return _ellipse_points(cx, cy, r, r)

    if tag == "ellipse":
        cx, cy = _num(a, "cx"), _num(a, "cy")
        rx, ry = _num(a, "rx"), _num(a, "ry")
        return _ellipse_points(cx, cy, rx, ry)

    if tag == "line":
        return [(_num(a, "x1"), _num(a, "y1")), (_num(a, "x2"), _num(a, "y2"))]

    if tag in ("polyline", "polygon"):
        nums = [float(t) for t in a.get("points", "").replace(",", " ").split()]
        return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]

    if tag == "path":
        d = a.get("d", "")
        if not d:
            return None
        pts = []
        try:
            p = parse_path(d)
            n = max(2, int(p.length() / 4) if p.length() else 24)
            n = min(n, 200)
            for i in range(n + 1):
                z = p.point(i / n)
                pts.append((z.real, z.imag))
        except Exception:
            return None
        return pts

    return None


def _ellipse_points(cx, cy, rx, ry, n=48):
    import math
    return [(cx + rx * math.cos(2 * math.pi * i / n),
             cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


class Element:
    """A resolved drawable: tag, attributes, absolute points, and bbox."""
    def __init__(self, tag, attrib, points, group_id, closed=None):
        self.tag = tag
        self.attrib = attrib
        self.points = points
        self.group_id = group_id
        # rect, circle, ellipse, polygon are closed by definition; for a path
        # the loader passes closure parsed from the d-string (Z command).
        if closed is None:
            closed = tag in ("rect", "circle", "ellipse", "polygon")
        self.closed = closed
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        # paint: raw, labeled by what it is, never by what it means.
        self.fill = _style_attr(attrib, "fill")
        self.stroke = _style_attr(attrib, "stroke")
        self.stroke_style = _stroke_style(attrib)   # solid | dashed | dotted
        self.stroke_width = _style_attr(attrib, "stroke-width")


def load(svg_path):
    """Return (elements, canvas) where canvas is (width, height) or None.

    canvas lets downstream stages reject a background rect that spans the
    whole drawing, which is not a node.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    cw = _num(root.attrib, "width", 0.0)
    ch = _num(root.attrib, "height", 0.0)
    if (cw == 0.0 or ch == 0.0) and root.attrib.get("viewBox"):
        vb = root.attrib["viewBox"].replace(",", " ").split()
        if len(vb) == 4:
            cw, ch = float(vb[2]), float(vb[3])
    canvas = (cw, ch) if cw and ch else None

    # Index every element that has an id, so <use> can find its target.
    by_id = {}
    for el in root.iter():
        eid = el.attrib.get("id")
        if eid:
            by_id[eid] = el

    out = []
    group_counter = [0]

    def walk(el, matrix, group_id, depth, via_use=False):
        if depth > 40:
            return
        tag = _tag(el)
        # definition blocks are not drawable where they are DEFINED: their
        # contents are placed by reference (<use>). Skip them during normal
        # descent, but allow rendering when reached through a <use> (via_use).
        if tag in ("defs", "marker", "clipPath", "mask", "pattern"):
            return
        if tag == "symbol" and not via_use:
            return
        local_m = parse_transform(el.attrib.get("transform"))
        m = multiply(matrix, local_m)

        if tag == "use":
            href = _href(el)
            if href and href.startswith("#"):
                target = by_id.get(href[1:])
                if target is not None:
                    ux = _num(el.attrib, "x")
                    uy = _num(el.attrib, "y")
                    um = multiply(m, (1, 0, 0, 1, ux, uy))
                    walk(target, um, group_id, depth + 1, via_use=True)
            return

        if tag == "g" or tag == "svg" or tag == "switch":
            group_counter[0] += 1
            gid = group_counter[0]
            for child in el:
                walk(child, m, gid, depth + 1)
            return

        pts = _local_points(el)
        if pts:
            closed = None
            if _tag(el) == "path":
                d = el.attrib.get("d", "")
                closed = ("z" in d) or ("Z" in d)
            out.append(Element(_tag(el), el.attrib, apply_many(m, pts),
                               group_id, closed=closed))

        # Some drawables can still contain children (rare), walk them too.
        for child in el:
            walk(child, m, group_id, depth + 1)

    walk(root, IDENTITY, None, 0)
    return out, canvas


def _style_fill(attrib):
    """Return the fill value from either a fill attr or a style string."""
    if "fill" in attrib:
        return attrib["fill"].strip()
    style = attrib.get("style", "")
    for part in style.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip() == "fill":
                return v.strip()
    return None

def _style_attr(attrib, key):
    """Read a paint property from a direct attribute or the style string."""
    if key in attrib:
        return attrib[key].strip()
    for part in attrib.get("style", "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip() == key:
                return v.strip()
    return None


def _stroke_style(attrib):
    """Normalize stroke-dasharray to 'solid' | 'dashed' | 'dotted'."""
    dash = _style_attr(attrib, "stroke-dasharray")
    if not dash or dash in ("none", "0"):
        return "solid"
    nums = [float(x) for x in dash.replace(",", " ").split() if x]
    if not nums:
        return "solid"
    return "dotted" if max(nums) <= 2.0 else "dashed"   

if __name__ == "__main__":
    import sys
    els, canvas = load(sys.argv[1])
    print("resolved drawables: %d" % len(els))
    for e in els:
        b = e.bbox
        w, h = b[2] - b[0], b[3] - b[1]
        print("  %-9s bbox=(%6.1f,%6.1f,%6.1f,%6.1f) %5.1fx%-5.1f fill=%s"
              % (e.tag, b[0], b[1], b[2], b[3], w, h, _style_fill(e.attrib)))