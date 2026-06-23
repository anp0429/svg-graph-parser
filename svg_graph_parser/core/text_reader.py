"""Text extraction for World 1, transform-aware and switch-aware.

The universal loader skips <text> because text is not an outline. But node
labels live in <text>, and real files (Inkscape) wrap each label in a
<switch> holding several language variants. The default branch is the <text>
with no systemLanguage attribute; the others are alternates we must drop, or a
label comes out as "Tagalog English" mashed together.

Each text anchor is transformed by the same composed matrix as everything
else, so labels land in the right place for containment matching.
"""

import xml.etree.ElementTree as ET

from .transforms import parse_transform, multiply, apply, IDENTITY


def _tag(el):
    return el.tag.split("}")[-1]


def _num(a, k, d=0.0):
    v = a.get(k)
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


class TextRun:
    def __init__(self, text, anchor):
        self.text = text
        self.anchor = anchor


def _text_content(text_el):
    return " ".join(t.strip() for t in text_el.itertext() if t.strip())


def load_text(svg_path):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    out = []

    def emit(text_el, matrix):
        x = _num(text_el.attrib, "x")
        y = _num(text_el.attrib, "y")
        anchor = apply(matrix, (x, y))
        content = _text_content(text_el)
        if content:
            out.append(TextRun(content, anchor))

    def walk(el, matrix):
        tag = _tag(el)
        m = multiply(matrix, parse_transform(el.attrib.get("transform")))

        if tag == "switch":
            # Pick the child <text> with no systemLanguage (the default).
            texts = [c for c in el if _tag(c) == "text"]
            default = None
            for t in texts:
                if "systemLanguage" not in t.attrib:
                    default = t
                    break
            if default is None and texts:
                default = texts[0]
            if default is not None:
                emit(default, m)
            return

        if tag == "text":
            emit(el, m)
            return

        for child in el:
            walk(child, m)

    walk(root, IDENTITY)
    return out


if __name__ == "__main__":
    import sys
    for r in load_text(sys.argv[1]):
        print("  %-30s @ (%6.1f,%6.1f)" % (r.text[:30], r.anchor[0], r.anchor[1]))
