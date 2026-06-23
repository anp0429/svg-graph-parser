"""World 1 geometry: bounding boxes for hand-drawn SVG primitives.

In a hand-drawn (World 1) flowchart a node is a <path>, not a <rect>, so we
cannot read width and height off attributes. We get the bbox from the path
geometry instead. Arcs and curves bulge past their control points, so naive
min/max of the path coordinates is wrong. We use svgpathtools, which computes
path bounding boxes (including arc extrema) analytically.

Connectors are <polyline> and arrowheads are <polygon>. Those are not paths.
Their geometry is just a list of numbers in the `points` attribute, so we read
those directly. No spec risk there.

This module is the front-end only. It turns SVG primitives into points and
boxes. The graph reconstruction (assembly, endpoint matching, topology) is not
here, because no SVG library does that. That part is the library's own work.
"""

from svgpathtools import parse_path


def path_bbox(d):
    """Return (xmin, ymin, xmax, ymax) for a path d-string.

    svgpathtools returns (xmin, xmax, ymin, ymax); we reorder to the
    (xmin, ymin, xmax, ymax) convention used across this package.
    """
    p = parse_path(d)
    xmin, xmax, ymin, ymax = p.bbox()
    return (xmin, ymin, xmax, ymax)


def parse_points(points_attr):
    """Parse a polyline/polygon `points` attribute into (x, y) tuples.

    Accepts comma or whitespace separated numbers, e.g.
    "425,200 425,261" or "425 200 425 261".
    """
    nums = [float(t) for t in points_attr.replace(",", " ").split()]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def points_bbox(points):
    """Bounding box for an explicit list of (x, y) points."""
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))