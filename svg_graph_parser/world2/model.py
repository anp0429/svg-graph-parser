"""Core data model for the reconstructed connection graph.

Zero third-party dependencies on purpose: the core stays portable and easy
to audit. Spatial acceleration (R-tree) is an optional upgrade in matcher.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class BBox:
    """Axis-aligned bounding box for a shape."""
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def distance_to(self, px: float, py: float) -> float:
        """Euclidean distance from point (px, py) to this box.

        Returns 0.0 if the point lies inside or on the boundary. This is the
        clamped point-to-rectangle distance: collapse the point onto the box
        on each axis independently, then take the hypotenuse of the overflow.
        """
        dx = max(self.x - px, 0.0, px - (self.x + self.w))
        dy = max(self.y - py, 0.0, py - (self.y + self.h))
        return (dx * dx + dy * dy) ** 0.5


@dataclass
class Node:
    id: str
    bbox: BBox
    label: str = ""


@dataclass
class Edge:
    id: str
    start: tuple[float, float]
    end: tuple[float, float]
    source: Optional[str] = None
    target: Optional[str] = None
    head_type: Optional[str] = None  # arrowhead type at the target end


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def edge_pairs(self) -> set[tuple[str, str]]:
        """Directed (source_label, target_label) pairs, for comparison."""
        out = set()
        for e in self.edges:
            if e.source is None or e.target is None:
                continue
            s = self.nodes[e.source].label or e.source
            t = self.nodes[e.target].label or e.target
            out.add((s, t))
        return out
