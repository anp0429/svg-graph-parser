"""Tests for stage 2 (World 1) parsing on the real Flowgorithm flowchart.

This file has no embedded oracle (it is not draw.io), so the expected values
are a one-time hand label of the diagram: 10 shapes, 10 connectors,
10 arrowheads, 2 inner decoration lines.

Run from the repo root:
  uv run pytest tests/test_parse_world1.py -v
"""

import pathlib

from svg_graph_parser.world1.parse import parse_world1

SAMPLE = pathlib.Path(__file__).parent.parent / "samples" / "flowchart_world1.svg"


def _parse():
    return parse_world1(str(SAMPLE))


def test_counts():
    shapes, connectors, arrowheads, decorations = _parse()
    assert len(shapes) == 10
    assert len(connectors) == 10
    assert len(arrowheads) == 10
    assert len(decorations) == 2


def test_every_connector_has_a_head():
    _, connectors, _, _ = _parse()
    assert all(c.head is not None for c in connectors)


def test_every_shape_has_text():
    shapes, _, _, _ = _parse()
    assert all(s.text and s.text.strip() for s in shapes)


def test_start_and_end_present():
    shapes, _, _, _ = _parse()
    labels = {(s.text or "").strip().split()[0] for s in shapes if s.text}
    assert "Start" in labels
    assert "End" in labels


def test_decorations_are_inside_a_shape():
    # Each dropped decoration must have both ends inside one shape bbox.
    shapes, _, _, decorations = _parse()
    for d in decorations:
        a, b = d.points[0], d.points[-1]
        ok = False
        for s in shapes:
            inside = (s.bbox[0] <= a[0] <= s.bbox[2] and s.bbox[1] <= a[1] <= s.bbox[3]
                      and s.bbox[0] <= b[0] <= s.bbox[2] and s.bbox[1] <= b[1] <= s.bbox[3])
            if inside:
                ok = True
                break
        assert ok, "decoration not contained in any shape"
