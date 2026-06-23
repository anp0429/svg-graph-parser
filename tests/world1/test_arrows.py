"""Tests for combined arrow glyph endpoint detection.

The sample is a radial cycle diagram: four wedges, a center circle, and four
self-contained arrow glyphs pointing clockwise. Each arrow's tip is known from
its position, so these need no oracle.

Run from the repo root:
  uv run pytest tests/world1/test_arrows.py -v
"""

import pathlib

from svg_graph_parser.core.loader import load
from svg_graph_parser.world1.arrows import arrow_endpoints, is_arrow_glyph

SAMPLE = pathlib.Path(__file__).parent.parent / "samples" / "cycle.svg"


def _arrows():
    els, _ = load(str(SAMPLE))
    return [e for e in els
            if e.tag == "path"
            and (e.bbox[2] - e.bbox[0]) < 70
            and (e.bbox[3] - e.bbox[1]) < 70]


def test_four_arrows_found():
    assert len(_arrows()) == 4


def test_tips_point_clockwise():
    # Known tips: top arrow points right, right points down, bottom points
    # left, left points up. We check each tip is on the expected side of its
    # own centroid.
    results = []
    for a in _arrows():
        tail, tip = arrow_endpoints(a.points)
        cx = (a.bbox[0] + a.bbox[2]) / 2
        cy = (a.bbox[1] + a.bbox[3]) / 2
        results.append((round(cx), round(cy), tip))
    # top arrow (cy smallest) tip should be to the right of its centroid
    top = min(results, key=lambda r: r[1])
    assert top[2][0] > top[0]
    # bottom arrow (cy largest) tip should be to the left of its centroid
    bottom = max(results, key=lambda r: r[1])
    assert bottom[2][0] < bottom[0]
    # right arrow (cx largest) tip should be below its centroid
    right = max(results, key=lambda r: r[0])
    assert right[2][1] > right[1]
    # left arrow (cx smallest) tip should be above its centroid
    left = min(results, key=lambda r: r[0])
    assert left[2][1] < left[1]


def test_is_arrow_glyph():
    arrows = _arrows()
    assert all(is_arrow_glyph(a, max_side=80) for a in arrows)