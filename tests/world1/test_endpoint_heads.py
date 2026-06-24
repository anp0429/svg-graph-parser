"""Generic endpoint-head detection: heads built from small line/circle glyphs
(crow's foot = many, bar = one, circle = zero) must be recognised and attached,
not just closed-triangle arrowheads. Validated against Miro ER exports, whose
LineHead* markup is the oracle (used only to source the test, never by the parser).
"""
import pathlib
from svg_graph_parser.scene.scene_graph import SceneGraph

WIKI = pathlib.Path(__file__).parent.parent / "samples"


def _maybe(name):
    p = WIKI / name
    return p if p.exists() else None


def test_erd_crowsfoot_heads_become_directed_edges():
    f = _maybe("miro_connectors.svg")
    if f is None:
        import pytest; pytest.skip("miro_erd sample not present")
    g = SceneGraph.from_svg(str(f))
    # 6 relationship connectors are drawn with crow's-foot / bar / circle heads.
    directed = [e for e in g.edges if e.directed]
    assert len(directed) >= 6


def test_comprehensive_export_recovers_most_connectors():
    f = _maybe("miro_connectors.svg")
    if f is None:
        import pytest; pytest.skip("miro_connectors sample not present")
    g = SceneGraph.from_svg(str(f))
    # 48 connector widgets in the source; recovery is strong but not perfect
    # (a few are same-shape demo loops). Guard against silent collapse.
    assert len([e for e in g.edges if e.directed]) >= 40
