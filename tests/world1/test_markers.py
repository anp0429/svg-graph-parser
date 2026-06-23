"""Marker-based direction and symbol/use instancing.

Two real-file regressions are locked here:
  - SVG <marker> arrows: connectors carry marker-end (often in the style
    string). Direction must be read from that, producing directed edges, even
    though no detached arrowhead glyph exists on the canvas.
  - <symbol>+<use> instancing: definition blocks must be skipped where defined
    but rendered where a <use> references them. A blunt "skip all symbols"
    breaks instanced diagrams.
"""

from pathlib import Path

from svg_graph_parser.scene.scene_graph import SceneGraph

WIKI = Path(__file__).resolve().parents[1].parent / "wiki_samples"


def _maybe(path):
    p = WIKI / path
    return p if p.exists() else None


def test_marker_edges_are_directed():
    f = _maybe("Basic_e-cigarette_operation_flowchart.svg")
    if f is None:
        import pytest; pytest.skip("wiki sample not present")
    g = SceneGraph.from_svg(str(f))
    assert len(g.edges) > 0
    # this file's arrows are SVG markers; every edge must be directed
    assert all(e.directed for e in g.edges)
    # and it must form a real flow: one entry, at least one terminal
    assert len(g.roots()) >= 1
    assert len(g.sinks()) >= 1


def test_symbol_use_instancing_renders():
    # Algebra1 uses <symbol> + <use>. Skipping symbols on descent must NOT
    # remove instanced content; the graph still reconstructs.
    f = _maybe("Algebra1_fnz_fig031_alg.svg")
    if f is None:
        import pytest; pytest.skip("wiki sample not present")
    g = SceneGraph.from_svg(str(f))
    assert len(g.nodes) >= 4
    assert len(g.edges) >= 4


def test_defs_not_parsed_as_nodes():
    # marker definitions live in <defs> and must not become phantom nodes.
    f = _maybe("Basic_e-cigarette_operation_flowchart.svg")
    if f is None:
        import pytest; pytest.skip("wiki sample not present")
    g = SceneGraph.from_svg(str(f))
    # 19 real rect nodes; no marker-definition glyphs leaking in
    assert len(g.nodes) == 19


def test_degenerate_rect_not_a_node():
    # An editor's empty zero-size "backgroundrect" must not become a phantom node.
    f = _maybe("2PP_counting_flowchart.svg")
    if f is None:
        import pytest; pytest.skip("wiki sample not present")
    g = SceneGraph.from_svg(str(f))
    # no node may have zero area
    for n in g.nodes.values():
        w = n.bbox[2] - n.bbox[0]; h = n.bbox[3] - n.bbox[1]
        assert w > 0 and h > 0, f"zero-area node leaked in: {n.id}"


def test_axis_aligned_connectors_survive():
    # Guard against the regression we hit: a zero-dimension guard must NOT delete
    # straight (axis-aligned) connectors. Lamp's directed edges must stay intact.
    g = SceneGraph.from_svg(str(SAMPLES_LAMP))
    assert len(g.edges) == 5
    assert all(e.directed for e in g.edges)


SAMPLES_LAMP = Path(__file__).resolve().parents[1] / "samples" / "lamp_inkscape.svg"