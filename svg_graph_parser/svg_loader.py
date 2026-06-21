"""Parse an SVG into raw geometry: node shapes and edge endpoints.

Heuristics (MVP, documented so reviewers see the boundaries):
  * Nodes  : <rect> and <ellipse> elements (filled shapes).
  * Edges  : <path fill="none" ...> elements (connectors are unfilled strokes).
  * Labels : a <text> whose anchor point falls inside a node's bbox is taken
             as that node's label (a minimal text-association pass).

Endpoint extraction reads the first and last absolute coordinate pair from the
path's `d` attribute. Valid for M/L/C/Q absolute commands, which is what
draw.io emits. Relative commands and arcs are a known gap (see README).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .model import BBox, Node

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _fnum(s):
    """Float or None. Rejects non-pixel values like '100%' that draw.io uses
    on its full-canvas background rect."""
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _path_endpoints(d: str) -> tuple[tuple[float, float], tuple[float, float]] | None:
    nums = [float(n) for n in _NUM.findall(d)]
    if len(nums) < 4:
        return None
    start = (nums[0], nums[1])
    end = (nums[-2], nums[-1])
    return start, end


def load(svg_text: str):
    """Return (nodes, raw_edges).

    nodes      : list[Node]
    raw_edges  : list[(edge_id, start_xy, end_xy)]
    """
    root = ET.fromstring(svg_text)

    # canvas size, used to recognise the full-bleed background rect
    vb = (root.get("viewBox") or "").split()
    canvas_w = float(vb[2]) if len(vb) == 4 else (_fnum(root.get("width")) or 1e9)
    canvas_h = float(vb[3]) if len(vb) == 4 else (_fnum(root.get("height")) or 1e9)

    shapes: list[tuple[str, BBox]] = []  # (auto_id, bbox)
    texts: list[tuple[float, float, str]] = []  # (x, y, label)
    raw_edges: list[tuple[str, tuple, tuple]] = []

    auto = 0
    for el in root.iter():
        name = _localname(el.tag)

        if name == "rect":
            x, y = _fnum(el.get("x", "0")), _fnum(el.get("y", "0"))
            w, h = _fnum(el.get("width")), _fnum(el.get("height"))
            if None in (x, y, w, h):
                continue  # e.g. width="100%" background rect
            if x == 0 and y == 0 and w >= canvas_w and h >= canvas_h:
                continue  # full-canvas background
            shapes.append((f"n{auto}", BBox(x, y, w, h)))
            auto += 1

        elif name == "ellipse":
            cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
            rx, ry = float(el.get("rx", 0)), float(el.get("ry", 0))
            shapes.append((f"n{auto}", BBox(cx - rx, cy - ry, 2 * rx, 2 * ry)))
            auto += 1

        elif name == "path" and (el.get("fill") == "none"):
            ep = _path_endpoints(el.get("d", ""))
            if ep:
                raw_edges.append((f"e{len(raw_edges)}", ep[0], ep[1]))

        elif name == "text":
            label = "".join(el.itertext()).strip()
            if label:
                texts.append((float(el.get("x", 0)), float(el.get("y", 0)), label))

    # associate each text anchor with the node whose bbox contains it
    nodes: list[Node] = []
    for nid, bbox in shapes:
        label = ""
        for tx, ty, t in texts:
            if bbox.distance_to(tx, ty) == 0.0:
                label = t
                break
        nodes.append(Node(id=nid, bbox=bbox, label=label))

    return nodes, raw_edges
