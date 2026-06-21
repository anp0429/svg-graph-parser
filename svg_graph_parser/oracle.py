"""Ground-truth extractor.

draw.io can embed the original diagram as escaped mxGraphModel XML in the root
<svg content="..."> attribute. We parse that to get the TRUE connectivity and
use it only to score the geometric reconstruction -- never as a shortcut inside
the reconstruction path itself.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET


def truth_pairs(svg_text: str) -> set[tuple[str, str]] | None:
    """Return the true directed (source_label, target_label) edge set, or None
    if the SVG carries no embedded mxGraphModel.
    """
    root = ET.fromstring(svg_text)
    content = root.get("content")
    if not content:
        return None

    model = ET.fromstring(content)
    labels: dict[str, str] = {}
    edges: list[tuple[str, str]] = []

    for cell in model.iter("mxCell"):
        cid = cell.get("id")
        if cell.get("vertex") == "1":
            labels[cid] = cell.get("value", cid) or cid
        elif cell.get("edge") == "1":
            s, t = cell.get("source"), cell.get("target")
            if s and t:
                edges.append((s, t))

    return {(labels.get(s, s), labels.get(t, t)) for s, t in edges}


def truth_graph(svg_text: str):
    """Richer ground truth for label-independent scoring.

    Returns (vertex_bboxes, vertex_labels, edge_ids) where edges are keyed by
    mxCell id, not label -- so we can score connectivity even when the rendered
    labels live in foreignObject HTML that the geometric loader can't read yet.
    """
    from .model import BBox

    root = ET.fromstring(svg_text)
    content = root.get("content")
    if not content:
        return None

    model = ET.fromstring(content)
    vboxes: dict[str, BBox] = {}
    vlabels: dict[str, str] = {}
    edges: set[tuple[str, str]] = set()

    for cell in model.iter("mxCell"):
        cid = cell.get("id")
        if cell.get("vertex") == "1":
            geo = cell.find("mxGeometry")
            if geo is not None and geo.get("width"):
                vboxes[cid] = BBox(
                    float(geo.get("x", 0)), float(geo.get("y", 0)),
                    float(geo.get("width")), float(geo.get("height")),
                )
                vlabels[cid] = cell.get("value", "") or ""
        elif cell.get("edge") == "1":
            s, t = cell.get("source"), cell.get("target")
            if s and t:
                edges.add((s, t))

    return vboxes, vlabels, edges
