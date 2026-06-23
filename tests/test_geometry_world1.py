"""Tests for World 1 geometry. Geometry has a known answer, so these need no
oracle. Each expected bbox is worked out by hand from the shape.

Run from the repo root:  uv run pytest tests/test_geometry_world1.py -v
"""

from svg_graph_parser.geometry_world1 import path_bbox, parse_points, points_bbox

TOL = 0.5


def approx(box, expected, tol=TOL):
    return all(abs(a - b) <= tol for a, b in zip(box, expected))


def test_box_rectangle():
    d = "M 150,275 L 150,450 L 700,450 L 700,275 Z"
    assert approx(path_bbox(d), (150, 275, 700, 450))


def test_diamond():
    d = "M 425,700 L 250,800 L 425,900 L 600,800 Z"
    assert approx(path_bbox(d), (250, 700, 600, 900))


def test_parallelogram_io():
    d = "M 650,975 L 575,1125 L 1150,1125 L 1225,975 Z"
    assert approx(path_bbox(d), (575, 975, 1225, 1125))


def test_stadium_arc_bulge():
    # Arcs bulge LEFT and RIGHT past the M/L coords. Left arc center
    # (325,150) r=50 reaches x=275; right arc center (525,150) reaches x=575.
    # Naive min/max of path coords would wrongly give 325..525.
    d = "M 325,100 A 50,50 0 0,0 325,200 L 525,200 A 50,50 0 0,0 525,100 Z"
    assert approx(path_bbox(d), (275, 100, 575, 200))


def test_parse_points_comma():
    assert parse_points("425,200 425,261") == [(425.0, 200.0), (425.0, 261.0)]


def test_parse_points_space():
    assert parse_points("425 200 425 261") == [(425.0, 200.0), (425.0, 261.0)]


def test_points_bbox():
    pts = [(425, 275), (438, 250), (411, 250)]  # an arrowhead triangle
    assert points_bbox(pts) == (411, 250, 438, 275)