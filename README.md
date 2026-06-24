# svg-graph-parser

Reconstruct a connection graph (nodes and directed edges) from an SVG diagram
using geometry alone, then let an AI agent query that graph directly.

Most tools that read draw.io files just parse the embedded `mxGraphModel` XML.
This one does not. It treats the rendered SVG as the only input a real diagram
gives you (a PDF export, a screenshot turned to SVG, a hand-authored file) and
infers connectivity from shape and path positions. The embedded XML, when it
exists, is used only as a labeled oracle to score the inference, never as a
shortcut inside it.

On top of the parser sits a queryable **scene graph** and an **MCP server**, so
a language model can ask a diagram structural questions ("what depends on X",
"is there a path from A to B") and get answers walked from the real geometry.

## What works today

- **Tool-exported SVG (World 2):** on a real `app.diagrams.net` flowchart
  (36 nodes, 25 edges), 100% recall / 96% precision, scored against the
  embedded model.
- **Hand-drawn / general SVG (World 1):** full graphs reconstructed from
  geometry alone on real files — a Flowgorithm export (10 nodes, 10 edges,
  including the loop back-edge and both decision branches) and an Inkscape
  decision diagram (6 nodes, 5 edges, with `Yes`/`No` on the right branches,
  through `<use>` instancing, matrix rotation, and multilingual `<switch>` text).
- **Real-corpus robustness:** parses a set of 24 Wikimedia SVGs from different
  tools (Flowgorithm, Inkscape, dia, Illustrator) without crashing, producing
  high-confidence directed graphs on the clean flowcharts.
- **AI access:** an MCP server exposes the scene graph as agent tools. A live
  agent can load a diagram and trace paths through it (see "Use with an AI
  agent" below).
- **Grouped ER tables (Miro):** on a Miro entity-relationship board, each table
  is reconstructed as one node carrying its columns as structured content, with
  connector endpoints rolled up through containment so a connector landing on any
  part of a tall table resolves to the table. On a dense 16-table board, all 9
  relationships resolve with correct foreign-key direction (crow's-foot geometry)
  and the full dashed/solid split (see "Benchmark" below).

## Package layout

```
svg_graph_parser/
  core/      world-agnostic foundation
    loader.py        universal SVG loader: all primitives, <use>, transform stack, paint
    transforms.py    SVG transform parsing (robust to compact number notation)
    geometry_world1.py
    text_reader.py   transform-aware text, <switch> default-language pick
    containment.py   shape-in-shape (bbox) containment: containers vs leaves
    point_match.py   point-in-polygon matching with confidence
    matcher.py
  world1/    hand-drawn / general SVG pipeline
    pipeline.py      load -> classify -> associate -> contain -> connect
    arrows.py        combined arrow glyph: tail/tip from barb flare
    connect.py  parse.py  constants.py
  world2/    tool-exported SVG (embedded model as scoring oracle)
    svg_loader.py  parser.py  matcher? (core)  oracle.py  evaluate.py  model.py
  scene/     queryable view over the reconstruction
    scene_graph.py   nodes + edges + lenses (neighbors, find_path, roots/sinks, by-style)
  mcp/       agent interface
    server.py        exposes the scene graph lenses as MCP tools (stdio)
```

## World 2: tool-exported SVG

1. Load (`world2/svg_loader.py`). Pull node shapes (`<rect>`, `<ellipse>`) and
   their text labels, plus edge paths (`<path fill="none">`) with endpoints.
2. Match (`core/matcher.py`). For each edge endpoint, find the nearest node by
   clamped point-to-bbox distance, within a tolerance.
3. Assemble (`world2/parser.py`). Start endpoint becomes source, end endpoint
   becomes target, yielding a directed graph.
4. Validate (`world2/oracle.py`). Parse the embedded `mxGraphModel` if any, and
   score precision and recall.

```
recall=100%   precision=96%   (25/25 true edges recovered, 1 false positive)
```

Every real connection is recovered from geometry alone. The single false
positive is a non-connector stroke the edge filter does not yet reject.

## World 1: hand-drawn and general SVG

World 2 reads nodes as `<rect>` and `<ellipse>`. Hand-drawn flowcharts draw
nodes as arbitrary `<path>` shapes, so a tool-specific loader finds zero nodes
on them. World 1 reconstructs the graph from path geometry alone.

Stages (`world1/pipeline.py`):

1. **Load** (`core/loader.py`). Walk the SVG once, composing the transform
   stack from the root down, resolving every `<use>`. Every primitive comes out
   with absolute, transform-applied points. Robust to compact number notation
   such as `matrix(.4778 0 0 .4778-76.05-55.02)` where minus signs are the only
   separators. Captures raw paint (fill, stroke, stroke style) per element.
2. **Classify.** Tag each drawable as shape, connector, or arrowhead by
   primitive type and path closure, not by fill, so stroke-only boxes are nodes.
3. **Contain** (`core/containment.py`). A shape whose bounding box fully
   contains others is a group, not a node. The nodes are the leaves.
4. **Match** (`core/point_match.py`). Match endpoints and arrowhead tips to
   shapes by real polygon containment (ray casting), not bounding box, so
   overlapping shapes (e.g. pie wedges) resolve correctly. Every match carries a
   confidence: 1.0 inside a polygon, a distance-based score (normalized by node
   size) just outside one.
5. **Connect.** Direction is read from the arrowhead tip via the connector's
   travel vector, so it holds for arrows pointing any way, touching or not. Each
   edge carries a per-endpoint confidence.

Known limits, by cause (honest about where it breaks):

- **Direction depends on detached arrowheads.** Files whose arrows are a single
  fused glyph currently produce *undirected* edges: connectivity is recovered,
  direction is pending (combined-arrow detection exists in `world1/arrows.py`
  but is not yet wired into edge building). This is the largest current
  limiter on real files.
- **Cycle / radial diagrams** whose arrows point tangentially (around the cycle)
  rather than between two shapes are not yet reconstructed.
- **Non-diagram SVGs** (illustrations, CAD drawings) produce spurious edges; the
  pipeline does not yet detect "this input is not a diagram".
- **`<foreignObject>` HTML labels** (draw.io rich text) are skipped by the
  geometric loader, so those nodes reconstruct unlabelled; connectivity is
  unaffected.
- **Absolute pixel tolerances** in some stages still need scale-normalizing;
  endpoint matching is already scale-relative.

Run it:

```bash
uv run python -m svg_graph_parser.world1.pipeline tests/samples/flowchart_world1.svg
uv run python -m svg_graph_parser.world1.pipeline tests/samples/lamp_inkscape.svg
```

## Scene graph

`scene/scene_graph.py` wraps a reconstruction into a queryable graph: nodes with
stable, geometry-derived ids; directed and undirected edges with style and
confidence; and lenses that each answer one structural question:

- `successors(id)` / `predecessors(id)` — follow arrow direction
- `neighbors(id)` — ignore direction
- `find_path(a, b)` — shortest directed path
- `roots()` / `sinks()` — entry and terminal nodes
- `find_by_text(s)` — locate nodes by label
- `edges_by_style(style)` — visual-encoding lens (reports style, not meaning)

```python
from svg_graph_parser.scene.scene_graph import SceneGraph
g = SceneGraph.from_svg("tests/samples/lamp_inkscape.svg")
g.successors(g.find_by_text("plugged in")[0].id)   # -> Bulb burned out?, Plug in lamp
```

## Use with an AI agent

`mcp/server.py` is a Model Context Protocol server (stdio) that exposes the
scene graph lenses as tools: `load_diagram`, `successors`, `predecessors`,
`neighbors`, `find_path`, `find_nodes`, `edges_by_style`, `node_content` (a
node's grouped contents, e.g. an ER table's columns), and `node_children`. An
agent loads a diagram once, then asks structural questions one tool call at a
time, instead of being handed the whole graph as a blob. `load_diagram` also
returns a `token_cost` block comparing the raw SVG size against the scene graph.

Install with the optional MCP dependency:

```bash
uv pip install -e ".[mcp]"   # or: pip install mcp
```

Register it with a stdio MCP client (here, project-scoped via `.mcp.json`):

```json
{
  "mcpServers": {
    "svg-graph-parser": {
      "type": "stdio",
      "command": "/abs/path/to/.venv/bin/python",
      "args": ["-m", "svg_graph_parser.mcp.server"]
    }
  }
}
```

Then ask, in plain language:

> Use the svg-graph-parser tools to load tests/samples/lamp_inkscape.svg and
> tell me every step from where the problem starts to "Repair lamp".

The agent calls `load_diagram`, `find_nodes`, then `find_path`, and answers from
the graph reconstructed from raw geometry:

```
Lamp doesn't work -> Lamp plugged in? -> Bulb burned out? -> Repair lamp
```

## Benchmark: scene graph vs. raw SVG for an agent

The point of the scene graph is to let an agent answer structural questions
about a diagram. A fair question is whether that earns its keep over simply
handing the raw SVG to a capable, tool-using agent. Tested on a dense Miro
entity-relationship board (`tests/samples/miro_connectors.svg`, 16 tables, ~307
KB), asking the same question both ways: *does ORDER reference CUSTOMER or the
reverse, which column is the foreign key, and which relationships are dashed?*

**Raw SVG.** The file does not fit comfortably in context, so the agent wrote
its own extraction script and asked for shell permission to run it. Its parser
keyed on Miro-specific markup (`data-widget-id` to split widgets,
`#LineHeadERD…` marker names for cardinality) and read a single `translate` per
element. It reached the correct answer, but only by leaning on the exporting
tool's metadata — the same shortcut that returns nothing on a Lucid, Inkscape,
or draw.io export — and after several script iterations, a shell-execution
approval, and noticeably higher latency.

**Scene graph (MCP).** The agent called `load_diagram` once, then `node_content`
and `predecessors`/`edges_by_style`. It answered correctly — `CUSTOMER → ORDER`,
foreign key `ORDER.customer_id`, all five dashed relationships — from bounded,
read-only tools, with no generated code and no shell access.

Measured in the same client (Claude Code `/context`, comparing the conversation
"Messages" only, since fixed system overhead is identical):

| | raw SVG + agent-written parser | scene graph (MCP) |
| --- | --- | --- |
| answer correct | yes (eventually) | yes |
| context used (messages) | ~36k tokens | ~10k tokens |
| code execution | wrote and ran a parser; needed approval | none — read-only tools |
| tool dependence | Miro `data-widget-id` / marker names | geometry only |

Two honest caveats. The `token_cost` figure in `load_diagram` is a `chars/4`
estimate (~70–80x reduction on this board); the exact tokenizer count requires
the Anthropic `count_tokens` endpoint and an API key. And `edges_by_style`
faithfully reports the board's legend sample arrows alongside the real
relationships; they carry empty labels and are trivially filtered.

For a board too large to load at all (a 2.8 MB Miro template, ~700k estimated
tokens raw), the raw approach simply does not fit any context window, while the
scene graph (~2.5k tokens) is queried normally. There, the scene graph is not an
optimization — it is the only option.

## Why this exists

A connection graph is the substrate for anything that has to reason about a
diagram rather than display it: what depends on what, what is reachable, where
the cycles are. The geometry stays the engine; the AI is the consumer of exact
output, never a component of the inference.

## Tests

```bash
uv run pytest -q
```

## License

MIT.