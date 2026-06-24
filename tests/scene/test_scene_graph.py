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


# ---- lossless tree + grouped-node tests (ER export) -----------------------
ERD = Path(__file__).resolve().parents[1] / "samples" / "miro1.svg"


def _erd():
    return _dense()


def test_grouped_table_is_single_node_with_columns():
    g = _erd()
    order = [n for n in g.nodes.values() if n.label == "ORDER"]
    assert len(order) == 1                      # the table is ONE node, not many
    cells = {c for row in order[0].content for c in row}
    assert {"order_id", "customer_id", "PK", "FK"} <= cells   # columns kept


def test_nothing_dropped_text_reachable_by_column_name():
    g = _erd()
    # an agent can locate a node by a column name, proving field text survived
    assert any(n.label == "ORDER" for n in g.find_by_text("customer_id"))


def test_relationships_stay_at_table_level():
    g = _erd()
    rels = {(g.label(e.source), g.label(e.target)) for e in g.edges if e.directed}
    assert ("CUSTOMER", "ORDER") in rels


# --- dense board: connector endpoints must roll up to the table node ---
DENSE = Path(__file__).resolve().parents[1] / "samples" / "miro_connectors.svg"


def _dense():
    import pytest
    if not DENSE.exists():
        pytest.skip("miro_connectors sample not present")
    return SceneGraph.from_svg(str(DENSE))


def test_dense_board_connector_rolls_up_to_table():
    """Regression: on a dense board a connector attaches at a tall table's bottom
    edge, far from its title. The endpoint must still resolve to the table node,
    not be dropped. Before the entity-box fix, successors(CUSTOMER) was empty."""
    g = _dense()
    ids = {n.label: nid for nid, n in g.nodes.items() if n.label}
    assert "ORDER" in [g.label(s) for s in g.successors(ids["CUSTOMER"])]
    assert "CUSTOMER" in [g.label(s) for s in g.predecessors(ids["ORDER"])]


def test_dense_board_all_nine_relationships_resolve():
    """Every ER relationship on the dense board resolves to a table->table edge,
    including EMPLOYEE->DESK_ASSIGNMENT (whose table titles the flat pass missed
    and which are recovered from the group's content)."""
    g = _dense()
    labels = {n.label for n in g.nodes.values()}
    assert "DESK_ASSIGNMENT" in labels
    assert "STUDENT_COURSE_ENROLLMENT" in labels
    ent = {"PERSON", "PASSPORT", "EMPLOYEE", "DESK_ASSIGNMENT", "CUSTOMER", "ORDER",
           "DEPARTMENT", "AUTHOR", "BOOK", "TEACHER", "STUDENT", "COURSE", "ACTOR",
           "MOVIE", "MANAGER"}
    er = {(g.label(e.source), g.label(e.target))
          for e in g.edges
          if g.label(e.source) in ent and g.label(e.target) in ent}
    expected = {("PERSON", "PASSPORT"), ("DEPARTMENT", "EMPLOYEE"),
                ("CUSTOMER", "ORDER"), ("EMPLOYEE", "DESK_ASSIGNMENT"),
                ("AUTHOR", "BOOK"), ("TEACHER", "STUDENT"), ("STUDENT", "COURSE"),
                ("ACTOR", "MOVIE"), ("MANAGER", "EMPLOYEE")}
    assert expected <= er, f"missing: {expected - er}"


def test_dense_board_dashed_relationships_complete():
    """Dashed ER relationships are all recovered, including STUDENT->COURSE."""
    g = _dense()
    ent = {"AUTHOR", "BOOK", "TEACHER", "STUDENT", "COURSE", "ACTOR", "MOVIE",
           "MANAGER", "EMPLOYEE"}
    dashed = {(g.label(e.source), g.label(e.target))
              for e in g.edges_by_style("dashed")
              if g.label(e.source) in ent and g.label(e.target) in ent}
    assert {("AUTHOR", "BOOK"), ("TEACHER", "STUDENT"), ("STUDENT", "COURSE"),
            ("ACTOR", "MOVIE"), ("MANAGER", "EMPLOYEE")} <= dashed