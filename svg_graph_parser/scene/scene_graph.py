"""A queryable scene graph over the World 1 reconstruction.

This is a thin VIEW on top of reconstruct_universal. It does not re-parse or
re-infer anything. It takes the (shapes, edges) the pipeline already produces
and wraps them as nodes + directed/undirected edges with stable ids, plus a
set of "lenses": small query methods that answer one structural question each.

The lenses are the surface an MCP server exposes to an agent. The agent asks
"what does X point to?" and walks the graph one step at a time, instead of
being handed the whole graph as a blob. That is why the scene graph beats a
flat dump on connectivity questions.

Design rules carried from the rest of the project:
  - ids are derived from geometry (sorted by position), so they are
    reproducible across a re-parse, not dependent on list order.
  - nodes carry RAW attributes (text, bbox, fill, stroke, stroke_style).
    Meaning is never baked in here; lenses report structure, not semantics.
"""

from collections import deque

from ..world1.pipeline import reconstruct_universal, build_tree


def _structured_rows(runs):
    """Group a table's text runs into rows (by y) then columns (by x).

    An ER row reads like  [key-flag | column-name | type]; grouping by y band
    then sorting by x recovers exactly that, with no tool metadata.
    """
    if not runs:
        return []
    band = {}
    for r in runs:
        band.setdefault(round(r.anchor[1] / 6), []).append(r)
    rows = []
    for y in sorted(band):
        cells = [r.text for r in sorted(band[y], key=lambda r: r.anchor[0])]
        rows.append(cells)
    return rows


class Node:
    def __init__(self, nid, shape):
        self.id = nid
        self.label = (shape.text or "").strip()
        self.bbox = shape.bbox
        self.fill = getattr(shape, "fill", None)
        self.stroke = getattr(shape, "stroke", None)
        self.stroke_style = getattr(shape, "stroke_style", None)
        self._shape = shape
        # filled in from the lossless tree: structured contents of this node's
        # group (e.g. an ER table's columns). Empty for a plain flowchart box.
        self.content = []          # list[list[str]] rows of cells
        self.content_text = ""     # flat searchable text of the whole group

    def __repr__(self):
        return f"Node({self.id}, {self.label!r})"


class GraphEdge:
    def __init__(self, source_id, target_id, edge):
        self.source = source_id
        self.target = target_id
        self.directed = edge.directed
        self.label = edge.label
        self.style = edge.style
        self.source_confidence = edge.source_confidence
        self.target_confidence = edge.target_confidence


class SceneGraph:
    def __init__(self, shapes, edges):
        # stable ids: sort shapes by position, assign n0, n1, ...
        ordered = sorted(shapes, key=lambda s: (s.bbox[1], s.bbox[0]))
        self._id_of = {id(s): f"n{i}" for i, s in enumerate(ordered)}
        self.nodes = {self._id_of[id(s)]: Node(self._id_of[id(s)], s) for s in ordered}

        self.edges = []
        # _out/_in: TRUE arrow direction only. roots/sinks/find_path use these.
        self._out = {nid: [] for nid in self.nodes}
        self._in = {nid: [] for nid in self.nodes}
        # _adj: undirected adjacency, includes BOTH directed and undirected edges.
        # neighbors() uses this. An undirected edge contributes to reachability
        # but never invents a direction it does not have.
        self._adj = {nid: set() for nid in self.nodes}
        for e in edges:
            sid = self._id_of.get(id(e.source))
            tid = self._id_of.get(id(e.target))
            if sid is None or tid is None:
                continue
            ge = GraphEdge(sid, tid, e)
            self.edges.append(ge)
            self._adj[sid].add(tid)
            self._adj[tid].add(sid)
            if e.directed:
                self._out[sid].append(tid)
                self._in[tid].append(sid)
            # undirected edges deliberately do NOT populate _out/_in:
            # a line with no arrowhead has no source or target.

    # ---- construction ----
    @classmethod
    def from_svg(cls, path):
        shapes, edges = reconstruct_universal(path)
        g = cls(shapes, edges)
        g._attach_tree(path)
        return g

    def _attach_tree(self, path):
        """Build the lossless containment tree and fold each group's full text
        (an ER table's columns, a container's members) onto the node that
        represents it, so grouped boxes stay ONE node but keep all their detail.
        """
        boxes = build_tree(path)
        self.tree = boxes

        # the outermost frames (top-level containers) are scaffolding, not tables
        frame_ids = {id(b) for b in boxes
                     if b.parent is None and getattr(b, "is_container", False)}

        def entity(b):
            """The group box this box belongs to: climb to the outermost
            ancestor that is not a top-level frame."""
            cur, p = b, b.parent
            while p is not None and id(p) not in frame_ids:
                cur, p = p, p.parent
            return cur

        def subtree_runs(root):
            out = list(getattr(root, "runs", []))
            for b in boxes:
                anc = b.parent
                while anc is not None:
                    if anc is root:
                        out.extend(getattr(b, "runs", []))
                        break
                    anc = anc.parent
            return out

        # map a flat node (from the flat graph) to its tree box by geometry,
        # then to its entity, and fold the entity's whole subtree text onto it
        by_bbox = {}
        for b in boxes:
            by_bbox.setdefault(tuple(round(x) for x in b.bbox), b)

        for node in self.nodes.values():
            tb = by_bbox.get(tuple(round(x) for x in node.bbox))
            if tb is None:
                continue
            ent = entity(tb)
            runs = subtree_runs(ent)
            node.content = _structured_rows(runs)
            node.content_text = " ".join(r.text for r in runs)

    # ---- lenses (the MCP query surface) ----
    def successors(self, nid):
        """Nodes this node points TO (follows arrow direction)."""
        return list(dict.fromkeys(self._out.get(nid, [])))

    def predecessors(self, nid):
        """Nodes that point TO this node."""
        return list(dict.fromkeys(self._in.get(nid, [])))

    def neighbors(self, nid):
        """All connected nodes, ignoring direction."""
        return sorted(self._adj.get(nid, set()))

    def find_path(self, a, b):
        """Shortest directed path a -> b, as a list of node ids, or None."""
        if a not in self.nodes or b not in self.nodes:
            return None
        if a == b:
            return [a]
        seen = {a}
        q = deque([[a]])
        while q:
            path = q.popleft()
            for nxt in self._out.get(path[-1], []):
                if nxt == b:
                    return path + [nxt]
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(path + [nxt])
        return None

    def find_by_text(self, substr):
        """Nodes whose label OR folded content contains substr (case-insensitive).
        Searching content means an agent can locate a node by a column name
        (e.g. 'customer_id'), not only by its title."""
        s = substr.lower()
        return [n for n in self.nodes.values()
                if s in n.label.lower() or s in n.content_text.lower()]

    def content(self, nid):
        """Containment lens: the structured contents of a node's group, as rows
        of cells. For an ER table this is its columns: [[key, name, type], ...].
        Empty for a plain box that contains nothing."""
        n = self.nodes.get(nid)
        return n.content if n else []

    def children(self, nid):
        """The boxes nested directly inside this node, from the lossless tree."""
        n = self.nodes.get(nid)
        if n is None:
            return []
        out = []
        for b in getattr(self, "tree", []):
            if getattr(b, "parent", None) is n._shape:
                out.append(b)
        return out

    def roots(self):
        """Entry points: have outgoing direction, no incoming. Nodes with only
        undirected or no edges are neither roots nor sinks."""
        return [nid for nid in self.nodes
                if self._out.get(nid) and not self._in.get(nid)]

    def sinks(self):
        """Terminal points: have incoming direction, no outgoing."""
        return [nid for nid in self.nodes
                if self._in.get(nid) and not self._out.get(nid)]

    def edges_by_style(self, style):
        """Visual-encoding lens: edges with a given stroke style (e.g. 'dashed')."""
        return [e for e in self.edges if e.style == style]

    def label(self, nid):
        n = self.nodes.get(nid)
        return n.label if n else None

    def __repr__(self):
        d = sum(1 for e in self.edges if e.directed)
        return f"SceneGraph(nodes={len(self.nodes)}, edges={len(self.edges)}, directed={d})"