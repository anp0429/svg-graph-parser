"""MCP server exposing a diagram's structure as queryable tools.

This is the top layer of the stack:

    SVG  ->  reconstruct_universal  ->  SceneGraph (lenses)  ->  MCP tools  ->  agent

The agent never receives the whole graph as a blob. It loads a diagram, gets a
node index (id + label) to address by, then asks one structural question at a
time: what does X point to, is there a path from A to B, what are the entry
points. Each tool is one lens. The agent walks the graph; it does not reason
over a flat dump.

Run (stdio, for Claude Desktop and other local MCP clients):
    uv run python -m svg_graph_parser.mcp.server
"""

from mcp.server.fastmcp import FastMCP

from ..scene.scene_graph import SceneGraph

mcp = FastMCP("svg-graph-parser")

# cache parsed graphs by path so repeated queries do not re-parse the SVG
_CACHE: dict[str, SceneGraph] = {}


def _graph(path: str) -> SceneGraph:
    if path not in _CACHE:
        _CACHE[path] = SceneGraph.from_svg(path)
    return _CACHE[path]


def _node(g, nid):
    return {"id": nid, "label": g.label(nid) or "(no text)"}


import os

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")


def _approx_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Used only when the real count
    is unavailable (no API key / SDK)."""
    return len(text) // 4


def _real_tokens(text: str):
    """Exact token count from Claude's tokenizer via the count_tokens endpoint.

    No inference is run -- this only tokenizes. Returns an int, or None if the
    anthropic SDK or ANTHROPIC_API_KEY is missing, or the text is too large.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        r = anthropic.Anthropic().messages.count_tokens(
            model=MODEL, messages=[{"role": "user", "content": text}])
        return r.input_tokens
    except Exception:
        return None


def _scene_graph_text(g) -> str:
    """The compact serialization an agent would actually receive."""
    parts = []
    for n in g.nodes.values():
        if not (n.label or n.content):
            continue
        cols = "; ".join(" ".join(r) for r in n.content if r) if n.content else ""
        parts.append(f"{n.id}: {n.label}" + (f" [{cols}]" if cols else ""))
    for e in g.edges:
        a = g.label(e.source) or e.source
        b = g.label(e.target) or e.target
        st = f" ({e.style})" if e.style and e.style != "solid" else ""
        parts.append(f"{a} {'->' if e.directed else '--'} {b}{st}")
    return "\n".join(parts)


@mcp.tool()
def load_diagram(path: str) -> dict:
    """Parse an SVG diagram and return an overview plus the node index.

    Returns node/edge counts, the list of nodes (id + label) to address other
    queries by, the entry (root) and terminal (sink) node ids, and a token_cost
    comparison showing how much smaller the scene graph is than the raw SVG
    (why you query this instead of pasting the file). Call this first; use the
    returned ids in the other tools, and node_content for a node's detail.
    """
    _CACHE.pop(path, None)  # fresh parse on explicit load
    g = _graph(path)
    directed = sum(1 for e in g.edges if e.directed)
    try:
        raw_text = open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        raw_text = None
    sg_text = _scene_graph_text(g)

    # prefer the real tokenizer; fall back to chars/4 and say which was used
    sg_real = _real_tokens(sg_text)
    raw_real = _real_tokens(raw_text) if raw_text is not None else None
    if sg_real is not None:
        method = f"anthropic count_tokens, model={MODEL} (exact tokenizer)"
        sg_tokens = sg_real
        raw_tokens = raw_real  # may be None if raw too large to count
    else:
        method = "chars/4 (approximate — set ANTHROPIC_API_KEY for the exact count)"
        sg_tokens = _approx_tokens(sg_text)
        raw_tokens = _approx_tokens(raw_text) if raw_text is not None else None

    return {
        "nodes": len(g.nodes),
        "edges": len(g.edges),
        "directed_edges": directed,
        "undirected_edges": len(g.edges) - directed,
        "token_cost": {
            "method": method,
            "raw_svg_tokens": raw_tokens,
            "scene_graph_tokens": sg_tokens,
            "reduction": (f"{raw_tokens // max(sg_tokens,1)}x smaller"
                          if raw_tokens else "raw too large to fit/count"),
        },
        "node_index": [_node(g, nid) for nid in g.nodes],
        "roots": [_node(g, n) for n in g.roots()],
        "sinks": [_node(g, n) for n in g.sinks()],
    }


@mcp.tool()
def node_content(path: str, node_id: str) -> dict:
    """The full contents of a node's group, e.g. an ER table's columns.

    Each row is a list of cells, typically [key-flag, column-name, type]
    (PK / FK / NOT_NULL ...). Empty for a plain box that holds nothing. This is
    how an agent reads a table's schema, not just its title.
    """
    g = _graph(path)
    return {"id": node_id, "label": g.label(node_id) or "(no text)",
            "rows": g.content(node_id)}


@mcp.tool()
def node_children(path: str, node_id: str) -> list[dict]:
    """Boxes nested directly inside this node, from the lossless containment tree."""
    g = _graph(path)
    out = []
    for b in g.children(node_id):
        out.append({"text": (getattr(b, "text", None) or "").strip(),
                    "bbox": list(b.bbox)})
    return out


@mcp.tool()
def successors(path: str, node_id: str) -> list[dict]:
    """Nodes this node points TO, following arrow direction (its dependencies/next steps)."""
    g = _graph(path)
    return [_node(g, n) for n in g.successors(node_id)]


@mcp.tool()
def predecessors(path: str, node_id: str) -> list[dict]:
    """Nodes that point TO this node (what leads into it)."""
    g = _graph(path)
    return [_node(g, n) for n in g.predecessors(node_id)]


@mcp.tool()
def neighbors(path: str, node_id: str) -> list[dict]:
    """All connected nodes, ignoring direction."""
    g = _graph(path)
    return [_node(g, n) for n in g.neighbors(node_id)]


@mcp.tool()
def find_path(path: str, source_id: str, target_id: str) -> dict:
    """Shortest directed path from source to target. Returns the node sequence, or none."""
    g = _graph(path)
    p = g.find_path(source_id, target_id)
    return {"path": [_node(g, n) for n in p] if p else None,
            "reachable": p is not None,
            "hops": (len(p) - 1) if p else None}


@mcp.tool()
def find_nodes(path: str, text: str) -> list[dict]:
    """Find nodes whose label contains the given text (case-insensitive)."""
    g = _graph(path)
    return [_node(g, n.id) for n in g.find_by_text(text)]


@mcp.tool()
def edges_by_style(path: str, style: str) -> list[dict]:
    """Edges drawn in a given stroke style (e.g. 'dashed', 'dotted', 'solid').

    Reports the visual style only, not its meaning. The caller decides what a
    dashed edge signifies in this diagram.
    """
    g = _graph(path)
    out = []
    for e in g.edges_by_style(style):
        out.append({"source": g.label(e.source) or "(no text)",
                    "target": g.label(e.target) or "(no text)",
                    "style": e.style,
                    "directed": e.directed})
    return out


if __name__ == "__main__":
    mcp.run()