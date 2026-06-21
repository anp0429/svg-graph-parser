"""Stage 1 wired into the pipeline.

raw SVG paths -> geometric primitive classification -> typed connector assembly
-> endpoint matching -> Graph. This is what makes geometry.py load-bearing:
the production parser now runs through it, not around it.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .geometry import classify_primitive, classify_arrowhead, Primitive, Head
from .matcher import match_endpoint
from .model import Edge, Graph
from .svg_loader import load

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _points(d: str):
    n = [float(x) for x in _NUM.findall(d)]
    return list(zip(n[0::2], n[1::2]))


def _raw_paths(root):
    out = []
    for el in root.iter():
        if _localname(el.tag) != "path":
            continue
        d = el.get("d", "")
        pts = _points(d)
        if len(pts) < 2:
            continue
        out.append({
            "pts": pts,
            "filled": el.get("fill") not in (None, "none"),
            "closed": ("Z" in d or "z" in d),
        })
    return out


def parse_svg_geometric(svg_text: str, max_dist: float = 40.0) -> Graph:
    root = ET.fromstring(svg_text)

    nodes, _ = load(svg_text)                      # node rects + labels
    node_list = list(nodes)
    median_span = 120.0
    if node_list:
        spans = sorted((n.bbox.w ** 2 + n.bbox.h ** 2) ** 0.5 for n in node_list)
        median_span = spans[len(spans) // 2]

    paths = _raw_paths(root)
    lines = [p for p in paths
             if classify_primitive(p["pts"], p["closed"], p["filled"]) == Primitive.LINE]
    shapes = [p for p in paths
              if classify_primitive(p["pts"], p["closed"], p["filled"]) == Primitive.SHAPE]

    g = Graph(nodes={n.id: n for n in node_list})

    for i, L in enumerate(lines):
        start, end = L["pts"][0], L["pts"][-1]

        head_end = Head.NONE
        for s in shapes:
            h = classify_arrowhead(s["pts"], s["filled"], end, median_node_span=median_span)
            if h != Head.NONE:
                head_end = h
                break

        src = match_endpoint(start[0], start[1], node_list, max_dist)
        tgt = match_endpoint(end[0], end[1], node_list, max_dist)
        g.edges.append(Edge(id=f"e{i}", start=start, end=end,
                            source=src, target=tgt, head_type=head_end.value))
    return g