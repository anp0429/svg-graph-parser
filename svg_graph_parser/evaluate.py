"""Score a reconstructed Graph against draw.io ground truth.

Connectivity is scored independently of labels: each reconstructed node is
mapped to the true vertex whose centre is closest (within tolerance), then
edges are compared by those true ids. This isolates the question that matters
-- did the geometry recover the right connections -- from the separate problem
of reading node labels out of foreignObject HTML.
"""
from __future__ import annotations

from .model import Graph
from .oracle import truth_graph


def score(graph: Graph, svg_text: str, center_tol: float = 30.0) -> dict:
    tg = truth_graph(svg_text)
    if tg is None:
        return {"precision": None, "recall": None, "reason": "no embedded ground truth"}
    vboxes, _vlabels, truth_edges = tg

    def closest_vertex(bb):
        best, bd = None, float("inf")
        for vid, vb in vboxes.items():
            d = ((bb.cx - vb.cx) ** 2 + (bb.cy - vb.cy) ** 2) ** 0.5
            if d < bd:
                bd, best = d, vid
        return best if bd <= center_tol else None

    node_to_vid = {nid: closest_vertex(n.bbox) for nid, n in graph.nodes.items()}

    got: set[tuple[str, str]] = set()
    for e in graph.edges:
        if e.source is None or e.target is None:
            continue
        s, t = node_to_vid.get(e.source), node_to_vid.get(e.target)
        if s and t:
            got.add((s, t))

    correct = got & truth_edges
    precision = len(correct) / len(got) if got else 0.0
    recall = len(correct) / len(truth_edges) if truth_edges else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "true_edges": len(truth_edges),
        "recovered": len(got),
        "correct": len(correct),
    }
