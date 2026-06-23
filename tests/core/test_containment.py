"""Tests for containment: nested boxes become container plus leaf nodes.

The sample is a synthetic block diagram: an outer "Causes" box containing three
inner boxes, plus a standalone box. Leaves are the graph nodes; the container
is not a node and must not swallow inner labels.

Run from the repo root:
  uv run pytest tests/core/test_containment.py -v
"""

import pathlib

from svg_graph_parser.core.loader import load
from svg_graph_parser.core.containment import assign_containment, bbox_contains
from svg_graph_parser.world1.pipeline import classify, reconstruct_universal

SAMPLE = pathlib.Path(__file__).parent.parent / "samples" / "block_diagram.svg"


def test_bbox_contains():
    outer = (0, 0, 100, 100)
    inner = (10, 10, 50, 50)
    assert bbox_contains(outer, inner)
    assert not bbox_contains(inner, outer)
    # overlap without containment
    assert not bbox_contains((0, 0, 50, 50), (40, 40, 90, 90))


def test_container_and_leaves():
    els, canvas = load(str(SAMPLE))
    classify(els, canvas)
    shapes = [e for e in els if e.role == "shape"]
    leaves, containers = assign_containment(shapes)
    assert len(containers) == 1
    assert len(leaves) == 4


def test_container_excluded_from_nodes():
    shapes, edges = reconstruct_universal(str(SAMPLE))
    # 4 leaf nodes, the Causes container is not among them
    assert len(shapes) == 4
    texts = {(s.text or "") for s in shapes}
    assert "Water vapor" in texts
    assert "CO2" in texts
    # the container label must not pollute a node
    assert not any("Causes" in t for t in texts)


def test_flat_flowchart_unaffected():
    # A flat flowchart has no nesting, so every shape stays a leaf.
    flat = SAMPLE.parent / "flowchart_world1.svg"
    els, canvas = load(str(flat))
    classify(els, canvas)
    shapes = [e for e in els if e.role == "shape"]
    leaves, containers = assign_containment(shapes)
    assert len(containers) == 0
    assert len(leaves) == len(shapes)