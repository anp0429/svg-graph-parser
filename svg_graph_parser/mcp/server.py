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


@mcp.tool()
def load_diagram(path: str) -> dict:
    """Parse an SVG diagram and return an overview plus the node index.

    Returns node/edge counts, the list of nodes (id + label) to address other
    queries by, and the entry (root) and terminal (sink) node ids. Call this
    first; use the returned ids in the other tools.
    """
    _CACHE.pop(path, None)  # fresh parse on explicit load
    g = _graph(path)
    directed = sum(1 for e in g.edges if e.directed)
    return {
        "nodes": len(g.nodes),
        "edges": len(g.edges),
        "directed_edges": directed,
        "undirected_edges": len(g.edges) - directed,
        "node_index": [_node(g, nid) for nid in g.nodes],
        "roots": [_node(g, n) for n in g.roots()],
        "sinks": [_node(g, n) for n in g.sinks()],
    }


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
