# svg-graph-parser

Reconstruct a **connection graph** (nodes + directed edges) from an SVG diagram
using geometry alone — then prove it's correct against the diagram's own
embedded ground truth.

Most tools that read draw.io files just parse the embedded `mxGraphModel` XML.
This one doesn't. It treats the rendered SVG as the only input a real-world
diagram gives you (a PDF export, a screenshot-to-SVG, a hand-authored file) and
**infers connectivity from shape and path positions**. The embedded XML, when
present, is used as a labeled oracle to score the inference — never as a
shortcut inside it.

## How it works

1. **Load** (`svg_loader.py`) — pull node shapes (`<rect>`, `<ellipse>`) and
   their text labels, plus edge paths (`<path fill="none">`) with endpoints.
2. **Match** (`matcher.py`) — for each edge endpoint, find the nearest node by
   clamped point-to-bbox distance, within a tolerance. This is the core.
3. **Assemble** (`parser.py`) — start endpoint → `source`, end endpoint →
   `target`, yielding a directed graph.
4. **Validate** (`oracle.py`) — parse the embedded `mxGraphModel` (if any) and
   score precision/recall of the reconstruction.

The core has **zero third-party dependencies**. Spatial matching is a linear
scan today; the interface is built so an R-tree drops in unchanged for
large diagrams.

## Quickstart

```bash
python3 examples/demo.py
# precision=100%  recall=100%  (3/3 edges recovered)  -- toy sample
python3 -m pytest -q
```

### Benchmark on a real export

On a real `app.diagrams.net` flowchart (36 nodes, 25 edges), scored by node
bounding box so connectivity is judged independently of label text:

```
recall=100%   precision=96%   (25/25 true edges recovered, 1 false positive)
```

Recall is perfect — every real connection is recovered from geometry alone.
The single false positive is a non-connector stroke that the edge filter
doesn't yet reject (tracked).

## Scope (current) and roadmap

Handles: axis-aligned rect/ellipse nodes, straight and orthogonal connectors,
absolute `M/L/C/Q` path data, single-line text labels by containment.

Known gaps, in priority order: **labels rendered in `<foreignObject>` HTML**
(draw.io's default for rich-text nodes — the geometric loader reads `<text>`
only, so these nodes reconstruct unlabelled; connectivity is unaffected);
one false-positive edge from an unfiltered decorative stroke; relative path
commands and arcs; rotated shapes; waypoint-aware routing for ambiguous
endpoints; grouped/nested shapes. Each is a tracked issue with a sample.

## Why this exists

A connection graph is the substrate for anything that has to *reason* about a
diagram rather than just display it — answering "what depends on what,"
"is this reachable," "where are the cycles." Repo two builds an MCP server on
top of this parser so an LLM agent can query a diagram's structure directly.
