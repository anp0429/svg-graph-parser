"""Reconstruct the connection graph from geometry, then score it against
draw.io's own embedded ground truth."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from svg_graph_parser import parse_svg, truth_pairs  # noqa: E402

svg = (
    pathlib.Path(__file__).resolve().parents[1]
    / "tests" / "samples" / "triangle.drawio.svg"
).read_text()

graph = parse_svg(svg)

print("Reconstructed nodes:")
for n in graph.nodes.values():
    print(f"  {n.label or n.id:>4}  bbox=({n.bbox.x:.0f},{n.bbox.y:.0f},"
          f"{n.bbox.w:.0f},{n.bbox.h:.0f})")

print("\nReconstructed edges (from geometry alone):")
got = graph.edge_pairs()
for s, t in sorted(got):
    print(f"  {s} -> {t}")

truth = truth_pairs(svg)
print("\nGround truth (draw.io embedded mxGraphModel):")
for s, t in sorted(truth):
    print(f"  {s} -> {t}")

correct = got & truth
precision = len(correct) / len(got) if got else 0.0
recall = len(correct) / len(truth) if truth else 0.0
print(f"\nprecision={precision:.0%}  recall={recall:.0%}  "
      f"({len(correct)}/{len(truth)} edges recovered)")
