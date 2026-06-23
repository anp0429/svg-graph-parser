# svg-graph-parser

Reconstruct a connection graph (nodes and directed edges) from an SVG diagram
using geometry alone, then prove it is correct against the diagram's own
embedded ground truth.

Most tools that read draw.io files just parse the embedded `mxGraphModel` XML.
This one does not. It treats the rendered SVG as the only input a real diagram
gives you (a PDF export, a screenshot turned to SVG, a hand-authored file) and
infers connectivity from shape and path positions. The embedded XML, when it
exists, is used only as a labeled oracle to score the inference. It is never a
shortcut inside it.

The project covers two cases. World 2 is tool-exported SVG, where an embedded
model exists and can score the result. World 1 is hand-drawn SVG, where nodes
are arbitrary `<path>` shapes and no embedded graph exists, so geometry is the
only signal.

## World 2: tool-exported SVG

### How it works

1. Load (`svg_loader.py`). Pull node shapes (`<rect>`, `<ellipse>`) and their
   text labels, plus edge paths (`<path fill="none">`) with endpoints.
2. Match (`matcher.py`). For each edge endpoint, find the nearest node by
   clamped point-to-bbox distance, within a tolerance. This is the core.
3. Assemble (`parser.py`). Start endpoint becomes source, end endpoint becomes
   target, yielding a directed graph.
4. Validate (`oracle.py`). Parse the embedded `mxGraphModel` if any, and score
   precision and recall of the reconstruction.

The World 2 core has zero third-party dependencies. Spatial matching is a
linear scan today; the interface is built so an R-tree drops in unchanged for
large diagrams.

### Benchmark on a real export

On a real `app.diagrams.net` flowchart (36 nodes, 25 edges), scored by node
bounding box so connectivity is judged independently of label text:

```
recall=100%   precision=96%   (25/25 true edges recovered, 1 false positive)
```

Recall is perfect. Every real connection is recovered from geometry alone. The
single false positive is a non-connector stroke that the edge filter does not
yet reject. It is a tracked gap, not a mystery.

Reproduce it:

```bash
uv run pytest
uv run python examples/demo.py
# precision=100%  recall=100%  (3/3 edges recovered)  -- toy sample
```

## World 1: hand-drawn SVG (in progress)

World 2 reads nodes as `<rect>` and `<ellipse>`. Hand-drawn flowcharts draw
nodes as `<path>` shapes (a rounded stadium, a decision diamond, a slanted
I/O parallelogram), so the World 2 loader finds zero nodes on them. World 1 is
a separate pipeline that reconstructs the graph from path geometry alone, with
no reliance on grouping, so it can extend to ungrouped files later.

Stages:

1. Geometry (`geometry_world1.py`). Bounding boxes from arbitrary path data,
   using svgpathtools for exact arc extrema, plus point readers for the
   `<polyline>` connectors and `<polygon>` arrowheads.
2. Parse (`parse_world1.py`). Classify shapes, connectors, arrowheads, and
   text. Associate each arrowhead to its line and each text run to its shape by
   containment. Drop decorations in two passes: a line grouped with a shape, or
   a line whose two ends sit inside one shape with no arrowhead.
3. Connect (`connect_world1.py`). Build directed edges. Direction is read from
   the arrowhead tip via the connector's travel vector, so it holds for arrows
   pointing any way, whether or not the arrowhead touches the shape.

On a real Flowgorithm export (10 nodes, 10 edges) the pipeline recovers the
full graph, including the loop back-edge and both branches out of the decision
diamond.

This is early. It is validated on one diagram, scored against a one-time hand
label rather than an embedded oracle, and not yet tested on curved connectors,
non-triangle arrowheads, or ungrouped decorations. Those are the next samples.

Run it:

```bash
uv run python -m svg_graph_parser.connect_world1 tests/samples/flowchart_world1.svg
```

## Scope and roadmap

World 2 handles axis-aligned `<rect>` and `<ellipse>` nodes, straight and
orthogonal connectors, absolute path data, and single-line text labels by
containment.

World 1 handles `<path>` node shapes including arcs, multi-bend `<polyline>`
connectors, detached `<polygon>` arrowheads, text by containment, and a
two-pass decoration filter.

Known gaps, in rough priority order: labels rendered in `<foreignObject>` HTML
(draw.io's default for rich-text nodes, which the geometric loader skips, so
those nodes reconstruct unlabelled while connectivity is unaffected); the
single false-positive edge in World 2; non-triangle arrowheads (chevron,
diamond, circle) untested in World 1; curved connectors; rotated shapes;
absolute pixel tolerances that need scale-normalizing for diagrams at very
different sizes.

## Why this exists

A connection graph is the substrate for anything that has to reason about a
diagram rather than display it: what depends on what, what is reachable, where
the cycles are. A later repo builds an MCP server on top of this parser so an
LLM agent can query a diagram's structure directly.