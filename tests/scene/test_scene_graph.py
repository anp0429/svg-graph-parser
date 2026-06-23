"""Scene graph lens tests, locked against the known-good Lamp and Flowgorithm graphs.

These assert the LENS behaviour, not the parser. If a future change to the
scene graph breaks traversal, direction, or root/sink logic, these fail.
"""

from pathlib import Path

from svg_graph_parser.scene.scene_graph import SceneGraph

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
LAMP = SAMPLES / "lamp_inkscape.svg"
FLOW = SAMPLES / "flowchart_world1.svg"


def _lamp():
    return SceneGraph.from_svg(str(LAMP))


def test_lamp_builds():
    g = _lamp()
    assert len(g.nodes) == 6
    assert len(g.edges) == 5
    # every Lamp edge is directed (all arrows detected on this clean file)
    assert all(e.directed for e in g.edges)


def test_lamp_successors_follow_arrows():
    g = _lamp()
    plugged = g.find_by_text("plugged in")
    assert len(plugged) == 1
    targets = {g.label(t) for t in g.successors(plugged[0].id)}
    assert targets == {"Bulb burned out?", "Plug in lamp"}


def test_lamp_single_root():
    g = _lamp()
    roots = [g.label(r) for r in g.roots()]
    assert roots == ["Lamp doesn't work"]


def test_lamp_three_sinks():
    g = _lamp()
    sinks = {g.label(s) for s in g.sinks()}
    assert sinks == {"Plug in lamp", "Replace bulb", "Repair lamp"}


def test_lamp_find_path():
    g = _lamp()
    src = g.find_by_text("Lamp doesn't work")[0].id
    dst = g.find_by_text("Repair lamp")[0].id
    path = g.find_path(src, dst)
    assert path is not None
    assert path[0] == src and path[-1] == dst
    # the route runs through the two decision diamonds
    labels = [g.label(n) for n in path]
    assert "Lamp plugged in?" in labels
    assert "Bulb burned out?" in labels


def test_flowchart_has_directed_spine():
    g = SceneGraph.from_svg(str(FLOW))
    assert len(g.nodes) == 10
    assert len(g.edges) == 10
    # Start is the single entry point
    starts = g.find_by_text("Start")
    assert len(starts) == 1
    assert starts[0].id in g.roots()


def test_ids_are_reproducible():
    # same file, two builds -> identical id->label mapping (geometry-sorted ids)
    a = _lamp(); b = _lamp()
    assert {i: n.label for i, n in a.nodes.items()} == \
           {i: n.label for i, n in b.nodes.items()}


def test_stable_root_under_rebuild():
    assert _lamp().roots() == _lamp().roots()
