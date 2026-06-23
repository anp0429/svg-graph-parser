"""Tests for the universal World 1 pipeline on a real Inkscape structure.

The sample is a trimmed structural copy of LampFlowchart.svg (Inkscape): it
uses <use> instancing, matrix rotation, path connectors, path arrowheads, and
<switch> multi-language text. No embedded oracle, so expectations are a hand
label of the structure.

Run from the repo root:
  uv run pytest tests/world1/test_pipeline.py -v
"""

import pathlib

from svg_graph_parser.world1.pipeline import reconstruct_universal
from svg_graph_parser.core.text_reader import load_text

SAMPLE = pathlib.Path(__file__).parent.parent / "samples" / "lamp_inkscape.svg"


def test_runs_without_crashing():
    shapes, edges = reconstruct_universal(str(SAMPLE))
    assert shapes is not None and edges is not None


def test_finds_shapes_and_edges():
    shapes, edges = reconstruct_universal(str(SAMPLE))
    assert len(shapes) == 6
    assert len(edges) >= 4


def test_switch_picks_default_language():
    runs = load_text(str(SAMPLE))
    texts = {r.text for r in runs}
    # English default kept, Tagalog alternate dropped.
    assert "Lamp doesn't work" in texts
    assert "Di gumagana" not in texts


def test_node_labels_are_clean():
    # Branch words must not pollute node labels.
    shapes, edges = reconstruct_universal(str(SAMPLE))
    labels = {(s.text or "") for s in shapes}
    assert "Lamp plugged in?" in labels
    assert "Bulb burned out?" in labels
    assert not any(l.endswith("No") or l.endswith("Yes") for l in labels)


def test_edge_labels_attached():
    shapes, edges = reconstruct_universal(str(SAMPLE))
    labels = [e.label for e in edges if e.label]
    # Both branch words appear as edge labels, not node text.
    assert "Yes" in labels
    assert "No" in labels
    # The No branch out of the plugged-in diamond reaches Plug in lamp.
    plugged = next(s for s in shapes if s.text and "plugged in" in s.text)
    no_edges = [e for e in edges if e.source is plugged and e.label == "No"]
    assert no_edges
    assert any("Plug in lamp" in (e.target.text or "") for e in no_edges)


def test_decision_node_fans_out():
    shapes, edges = reconstruct_universal(str(SAMPLE))
    plugged = [s for s in shapes if s.text and "plugged in" in s.text]
    assert plugged
    out = [e for e in edges if e.source is plugged[0]]
    assert len(out) == 2


def test_spine_present():
    shapes, edges = reconstruct_universal(str(SAMPLE))
    labels = {(s.text or "") for s in shapes}
    assert any("Lamp doesn't work" in l for l in labels)
    assert any("plugged in" in l for l in labels)
    assert any("burned out" in l for l in labels)