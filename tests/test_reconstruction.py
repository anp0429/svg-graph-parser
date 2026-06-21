import pathlib

from svg_graph_parser import BBox, match_endpoint, parse_svg, truth_pairs
from svg_graph_parser.model import Node

SAMPLE = (pathlib.Path(__file__).parent / "samples" / "triangle.drawio.svg").read_text()


def test_distance_zero_inside_box():
    assert BBox(0, 0, 10, 10).distance_to(5, 5) == 0.0


def test_distance_outside_box():
    # point 3 to the right of a [0,10] box edge -> distance 3
    assert BBox(0, 0, 10, 10).distance_to(13, 5) == 3.0


def test_match_picks_nearest_node():
    nodes = [Node("left", BBox(0, 0, 10, 10)), Node("right", BBox(100, 0, 10, 10))]
    assert match_endpoint(5, 5, nodes) == "left"
    assert match_endpoint(105, 5, nodes) == "right"


def test_match_returns_none_when_too_far():
    nodes = [Node("a", BBox(0, 0, 10, 10))]
    assert match_endpoint(500, 500, nodes, max_dist=40) is None


def test_reconstruction_matches_ground_truth():
    graph = parse_svg(SAMPLE)
    assert graph.edge_pairs() == truth_pairs(SAMPLE)


def test_real_flowchart_connectivity():
    """Regression on a real draw.io export (36 nodes, 25 edges).

    Scored by node bbox, independent of label text. Recall must stay perfect;
    precision is allowed one false-positive edge until the decorative-stroke
    filter lands.
    """
    svg = (pathlib.Path(__file__).parent / "samples" / "flowchart.drawio.svg").read_text()
    g = parse_svg(svg)
    from svg_graph_parser import score
    r = score(g, svg)
    assert r["recall"] == 1.0
    assert r["precision"] >= 0.95

def test_geometry_stage1_on_real_export():
    """Stage 1: classify primitives and type arrowheads from geometry alone."""
    import re, xml.etree.ElementTree as ET
    from svg_graph_parser.geometry import classify_primitive, classify_arrowhead, Primitive, Head

    svg = (pathlib.Path(__file__).parent / "samples" / "flowchart.drawio.svg").read_text()
    root = ET.fromstring(svg)
    num = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
    ln = lambda t: t.rsplit("}", 1)[-1]

    prims = []
    for el in root.iter():
        if ln(el.tag) == "path":
            d = el.get("d", "")
            n = [float(x) for x in num.findall(d)]
            P = list(zip(n[0::2], n[1::2]))
            if len(P) < 2:
                continue
            prims.append({"pts": P, "filled": el.get("fill") not in (None, "none"),
                          "closed": ("Z" in d or "z" in d)})

    lines = [p for p in prims if classify_primitive(p["pts"], p["closed"], p["filled"]) == Primitive.LINE]
    shapes = [p for p in prims if classify_primitive(p["pts"], p["closed"], p["filled"]) == Primitive.SHAPE]
    assert len(lines) == 26 and len(shapes) == 24

    ends = [L["pts"][0] for L in lines] + [L["pts"][-1] for L in lines]
    attached = 0
    for s in shapes:
        best, bd = None, 1e9
        for v in s["pts"]:
            for e in ends:
                dd = (v[0] - e[0]) ** 2 + (v[1] - e[1]) ** 2
                if dd < bd:
                    bd, best = dd, e
        if classify_arrowhead(s["pts"], s["filled"], best, median_node_span=110.0) != Head.NONE:
            attached += 1
    assert attached == 24  # every arrowhead binds to a line, geometry only

def test_geometric_pipeline_wires_stage1():
    """The geometric pipeline routes through geometry.py and matches the oracle."""
    from svg_graph_parser import parse_svg_geometric, score
    svg = (pathlib.Path(__file__).parent / "samples" / "flowchart.drawio.svg").read_text()
    g = parse_svg_geometric(svg)
    r = score(g, svg)
    assert r["recall"] == 1.0 and r["precision"] >= 0.95
    assert sum(1 for e in g.edges if e.head_type and e.head_type != "none") >= 20