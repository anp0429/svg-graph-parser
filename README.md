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

# World 1 README section (draft)

Paste this in place of the current "World 1: hand-drawn SVG (in progress)"
section. It is written to be confident AND precise: the strong claim is true,
and every limit a careful reader would probe is named before they have to ask.
All numbers come from the real test files and the Wikimedia batch run, not
estimates. Do not inflate them.

---

## World 1: hand-drawn and general SVG

World 2 reads nodes as `<rect>` and `<ellipse>`. Hand-drawn flowcharts draw
nodes as arbitrary `<path>` shapes (a rounded stadium, a decision diamond, a
slanted I/O parallelogram), so a tool-specific loader finds zero nodes on them.
World 1 is a separate pipeline that reconstructs the graph from path geometry
alone, with no reliance on grouping or embedded model data.

It reconstructs real flowcharts from geometry alone. On the test files it
recovers the full graph: a Flowgorithm export (10 nodes, 10 edges) including the
loop back-edge and both branches out of the decision diamond; a hand-authored
Inkscape decision diagram (6 nodes, 5 edges) with `Yes`/`No` correctly attached
to the right branches, reconstructed through `<use>` instancing, matrix
rotation, path connectors, and multilingual `<switch>` text.

### How it works

1. **Load** (`core/loader.py`). Walk the SVG once, composing the transform stack
   from the root down, resolving every `<use>` by re-walking its target. Every
   primitive type (`rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`,
   `path`) comes out with absolute, transform-applied points, so no later stage
   has to know about transforms or instancing. Robust to compact number
   notation, e.g. `matrix(.4778 0 0 .4778-76.05-55.02)` where negative signs are
   the only separators.
2. **Classify** (`world1/pipeline.py`). Tag each drawable as shape, connector, or
   arrowhead by primitive type and path closure, not by fill, so stroke-only
   boxes are still nodes.
3. **Containment** (`core/containment.py`). A shape whose bounding box fully
   contains other shapes is a group, not a node. The graph's nodes are the
   leaves.
4. **Match** (`core/point_match.py`). Match connector endpoints and arrowhead
   tips to shapes by real polygon containment (ray casting), not bounding box,
   so overlapping shapes (for example pie wedges, whose boxes overlap heavily)
   resolve to the correct shape. Every match carries a confidence: 1.0 inside a
   polygon, and a distance-based score, normalized by node size, when a point
   falls just outside one.
5. **Connect** (`world1/pipeline.py`). Build edges. Direction is read from the
   arrowhead tip via the connector's travel vector, so it holds for arrows
   pointing any way, touching or not. Each edge carries a per-endpoint
   confidence.

### Status on real Wikimedia files

Run against a set of 24 real Wikimedia SVGs exported by different tools
(Flowgorithm, Inkscape, dia, Illustrator), the pipeline parses all of them
without crashing and produces full, high-confidence directed graphs on the
clean flowcharts (for example a 9-node / 9-edge architecture flowchart
recovered from geometry alone).

This is early and honest about its edges. Known limits, by cause:

- **Direction depends on detached arrowheads.** Files whose arrows are drawn as
  a single fused glyph (shaft plus head in one path) currently produce
  *undirected* edges, because combined-arrow direction is detected
  (`world1/arrows.py`) but not yet wired into edge building. Connectivity is
  recovered; direction is pending.
- **Cycle / radial diagrams** whose arrows point tangentially (around the cycle)
  rather than between two shapes are not yet reconstructed: the relation they
  express is not "A connects to B".
- **Non-diagram SVGs** (illustrations, CAD drawings) produce spurious edges; the
  pipeline does not yet detect "this input is not a diagram".
- **Labels in `<foreignObject>` HTML** (draw.io's default for rich-text nodes)
  are skipped by the geometric loader, so those nodes reconstruct unlabelled
  while connectivity is unaffected.
- **Absolute pixel tolerances** in some stages still need scale-normalizing for
  diagrams at very different sizes. Endpoint matching is already scale-relative.

### Run it

```
uv run python -m svg_graph_parser.world1.pipeline tests/samples/flowchart_world1.svg
uv run python -m svg_graph_parser.world1.pipeline tests/samples/lamp_inkscape.svg
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

## License

  MIT. See LICENSE.