"""Containment, clean-room.

Flowcharts are flat: no node sits inside another. Block diagrams and
architecture diagrams nest: an outer section box ("Causes", "Effects")
contains the real nodes. Treating every box as a node makes the container a
giant false node that also swallows every inner label.

The fix is the containment backbone: a shape whose bounding box fully contains
other shapes is a container, not a leaf. The graph's nodes are the leaves. The
containment chain (leaf, parent, grandparent) is kept as grouping context.

Containment requires FULL bbox containment, not mere overlap, so shapes that
overlap without nesting (for example pie-slice wedges) stay independent leaves.
"""


def bbox_contains(outer, inner, tol=1.0):
    """True if inner bbox sits fully inside outer bbox (within tol)."""
    return (outer[0] - tol <= inner[0] and outer[1] - tol <= inner[1]
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _area(b):
    return (b[2] - b[0]) * (b[3] - b[1])


def assign_containment(shapes, tol=1.0):
    """Set .parent and .is_container on each shape.

    parent = the smallest shape that strictly contains this one (or None).
    is_container = True if this shape contains at least one other shape.
    Returns (leaves, containers).
    """
    for s in shapes:
        s.parent = None
        s.is_container = False

    for s in shapes:
        best_parent, best_area = None, None
        for t in shapes:
            if t is s:
                continue
            if _area(t.bbox) <= _area(s.bbox):
                continue  # a parent must be strictly larger
            if bbox_contains(t.bbox, s.bbox, tol):
                a = _area(t.bbox)
                if best_area is None or a < best_area:
                    best_parent, best_area = t, a
        s.parent = best_parent
        if best_parent is not None:
            best_parent.is_container = True

    leaves = [s for s in shapes if not s.is_container]
    containers = [s for s in shapes if s.is_container]
    return leaves, containers