"""Tests for stage 3 (World 1) connection reconstruction.

No embedded oracle (not draw.io), so the expected edges are a one-time hand
label of the flowchart logic: a for-loop that reads five numbers, sums them,
and prints the average. 10 nodes, 10 directed edges, including the loop
back-edge and both branches out of the decision diamond.

Run from the repo root:
  uv run pytest tests/test_connect_world1.py -v
"""

import pathlib

from svg_graph_parser.connect_world1 import reconstruct

SAMPLE = pathlib.Path(__file__).parent / "samples" / "flowchart_world1.svg"


def _key(text):
    """Short stable label from a shape's text, for edge comparison."""
    t = (text or "").replace("\n", " ").replace("\t", " ")
    return " ".join(t.split())[:18]


def _edge_set():
    shapes, edges = reconstruct(str(SAMPLE))
    return {(_key(s.text), _key(d.text)) for s, d in edges}, shapes, edges


EXPECTED = {
    ("Start", "Integer currentNum"),
    ("Integer currentNum", "currentSum = 0"),
    ("currentSum = 0", "i = 1 to 5"),
    ("i = 1 to 5", 'Output "Please ent'),
    ('Output "Please ent', "Input currentNumbe"),
    ("Input currentNumbe", "currentSum = curre"),
    ("currentSum = curre", "i = 1 to 5"),
    ("i = 1 to 5", "average = currentS"),
    ("average = currentS", 'Output "Average is'),
    ('Output "Average is', "End"),
}


def test_node_and_edge_counts():
    _, shapes, edges = _edge_set()
    assert len(shapes) == 10
    assert len(edges) == 10


def test_exact_edge_set():
    got, _, _ = _edge_set()
    assert got == EXPECTED


def test_loop_back_edge_present():
    # The accumulate step must point back up into the decision diamond.
    got, _, _ = _edge_set()
    assert ("currentSum = curre", "i = 1 to 5") in got


def test_diamond_has_two_out_edges():
    # The decision diamond fans out: loop body and loop exit.
    got, _, _ = _edge_set()
    out = [d for s, d in got if s == "i = 1 to 5"]
    assert len(out) == 2


def test_start_has_no_incoming():
    got, _, _ = _edge_set()
    assert all(d != "Start" for _, d in got)


def test_end_has_no_outgoing():
    got, _, _ = _edge_set()
    assert all(s != "End" for s, _ in got)
