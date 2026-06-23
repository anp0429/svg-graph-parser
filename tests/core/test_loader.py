"""Tests for the transform engine and the universal loader.

Transforms have known answers (geometry), so no oracle is needed. The loader
test uses a trimmed structural copy of a real Inkscape file that relies on
<use> instancing and matrix rotation, the two things the first loader could
not do.

Run from the repo root:
  uv run pytest tests/test_universal_loader.py -v
"""

import math
import pathlib

from svg_graph_parser.core.transforms import parse_transform, apply, multiply, IDENTITY
from svg_graph_parser.core.loader import load

SAMPLE = pathlib.Path(__file__).parent.parent / "samples" / "lamp_inkscape.svg"


def approx(a, b, tol=0.01):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_translate():
    m = parse_transform("translate(10, 20)")
    assert approx(apply(m, (0, 0)), (10, 20))
    assert approx(apply(m, (5, 5)), (15, 25))


def test_translate_single_arg():
    m = parse_transform("translate(10)")
    assert approx(apply(m, (0, 0)), (10, 0))


def test_scale():
    m = parse_transform("scale(2, 3)")
    assert approx(apply(m, (4, 5)), (8, 15))


def test_rotate_90_about_origin():
    m = parse_transform("rotate(90)")
    assert approx(apply(m, (1, 0)), (0, 1))


def test_rotate_about_center():
    m = parse_transform("rotate(180, 5, 5)")
    assert approx(apply(m, (5, 0)), (5, 10))


def test_matrix():
    m = parse_transform("matrix(1, 0, 0, 1, 7, 8)")
    assert approx(apply(m, (0, 0)), (7, 8))


def test_nested_composition():
    parent = parse_transform("translate(-3, 1)")
    child = parse_transform("translate(0, 5)")
    m = multiply(parent, child)
    assert approx(apply(m, (10, 10)), (7, 16))


def test_loader_resolves_use_instances():
    # The connector group is cloned 4 times; nodes via use twice. The first
    # loader would see far fewer. We expect 16 drawables resolved.
    els, _ = load(str(SAMPLE))
    assert len(els) == 16


def test_loader_applies_rotation():
    # Two connectors are placed with matrix(0,-1,1,0,...), a 90 deg rotation.
    # A connector that is vertical in local space must become horizontal.
    els, _ = load(str(SAMPLE))
    fill_none = [e for e in els if "none" in (e.attrib.get("style", "")
                                              + e.attrib.get("fill", ""))]
    widths = [round(e.bbox[2] - e.bbox[0], 1) for e in fill_none]
    heights = [round(e.bbox[3] - e.bbox[1], 1) for e in fill_none]
    # At least one connector vertical (w==0) and at least one horizontal (h==0).
    assert any(w == 0.0 for w in widths)
    assert any(h == 0.0 for h in heights)


def test_loader_reads_rects_and_paths():
    els, _ = load(str(SAMPLE))
    tags = {e.tag for e in els}
    assert "rect" in tags
    assert "path" in tags


def test_load_returns_canvas():
    els, canvas = load(str(SAMPLE))
    assert canvas is not None
    assert canvas[0] > 0 and canvas[1] > 0