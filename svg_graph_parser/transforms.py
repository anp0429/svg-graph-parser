"""SVG transforms, clean-room from the spec.

An SVG transform attribute is a list of primitives: translate, scale, rotate,
matrix, skewX, skewY. Each is a 2D affine transform. We represent one as a
2x3 matrix (a, b, c, d, e, f) meaning:

    x' = a*x + c*y + e
    y' = b*x + d*y + f

To place an element we compose the transforms from the root down to it, in
order, then apply the result to the element's local coordinates. Without this,
a rotated or translated shape lands in the wrong place and gets the wrong
bounding box, and a <use> instance cannot be positioned at all.
"""

import math
import re

# identity
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

_FUNC = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")


def _nums(s):
    return [float(t) for t in re.split(r"[\s,]+", s.strip()) if t]


def multiply(m1, m2):
    """Compose two 2x3 matrices: result applies m1 then m2 in user space.

    Standard SVG nesting: a parent transform m1 with child m2 gives points
    transformed by m1 * m2 (parent outermost). We return m1 then m2 applied
    as m1 composed with m2.
    """
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def parse_transform(attr):
    """Parse a transform attribute string into a single 2x3 matrix."""
    if not attr:
        return IDENTITY
    m = IDENTITY
    for name, args in _FUNC.findall(attr):
        n = _nums(args)
        if name == "matrix":
            t = (n[0], n[1], n[2], n[3], n[4], n[5])
        elif name == "translate":
            tx = n[0]
            ty = n[1] if len(n) > 1 else 0.0
            t = (1, 0, 0, 1, tx, ty)
        elif name == "scale":
            sx = n[0]
            sy = n[1] if len(n) > 1 else sx
            t = (sx, 0, 0, sy, 0, 0)
        elif name == "rotate":
            ang = math.radians(n[0])
            cos, sin = math.cos(ang), math.sin(ang)
            if len(n) == 3:
                cx, cy = n[1], n[2]
                # translate(cx,cy) rotate translate(-cx,-cy)
                t = multiply((1, 0, 0, 1, cx, cy),
                             multiply((cos, sin, -sin, cos, 0, 0),
                                      (1, 0, 0, 1, -cx, -cy)))
            else:
                t = (cos, sin, -sin, cos, 0, 0)
        elif name == "skewX":
            t = (1, 0, math.tan(math.radians(n[0])), 1, 0, 0)
        elif name == "skewY":
            t = (1, math.tan(math.radians(n[0])), 0, 1, 0, 0)
        else:
            t = IDENTITY
        m = multiply(m, t)
    return m


def apply(m, point):
    """Apply a 2x3 matrix to an (x, y) point."""
    a, b, c, d, e, f = m
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def apply_many(m, points):
    return [apply(m, p) for p in points]
