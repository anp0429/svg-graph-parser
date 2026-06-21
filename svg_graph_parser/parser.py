"""Orchestration: turn SVG text into a reconstructed connection Graph."""
from __future__ import annotations

from .model import Edge, Graph
from .matcher import match_endpoint
from .svg_loader import load


def parse_svg(svg_text: str, max_dist: float = 40.0) -> Graph:
    nodes, raw_edges = load(svg_text)
    g = Graph(nodes={n.id: n for n in nodes})
    for eid, start, end in raw_edges:
        src = match_endpoint(start[0], start[1], nodes, max_dist)
        tgt = match_endpoint(end[0], end[1], nodes, max_dist)
        g.edges.append(Edge(id=eid, start=start, end=end, source=src, target=tgt))
    return g
