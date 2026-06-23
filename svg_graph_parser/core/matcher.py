"""Endpoint matching: the heart of the geometric reconstruction.

Given an edge endpoint and the set of nodes, decide which node (if any) that
endpoint connects to. The rule is nearest-bounding-box, with a tolerance so a
stray endpoint floating in empty space produces no false link.

The MVP uses a linear scan (O(nodes) per endpoint). For large diagrams swap in
an R-tree over node bboxes to get O(log n) queries -- see `match_endpoint`'s
note. The interface stays identical, so the upgrade is a drop-in.
"""
from __future__ import annotations

from typing import Optional

from ..world2.model import Node


def match_endpoint(
    px: float,
    py: float,
    nodes: list[Node],
    max_dist: float = 40.0,
) -> Optional[str]:
    """Return the id of the node nearest (px, py), or None if none is within
    `max_dist`. Distance is point-to-bbox, so an endpoint sitting on or inside
    a shape scores 0 and wins outright.

    `max_dist` accounts for draw.io's perimeter spacing -- connectors usually
    stop a few pixels short of the shape they attach to.
    """
    best_id: Optional[str] = None
    best_d = float("inf")
    for n in nodes:
        d = n.bbox.distance_to(px, py)
        if d < best_d:
            best_d = d
            best_id = n.id
    if best_id is None or best_d > max_dist:
        return None
    return best_id
