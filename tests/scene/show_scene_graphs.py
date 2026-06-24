"""Scene-graph inspection harness.

Not a pass/fail unit test -- a *readable* dump of the reconstructed scene graph
for every real sample SVG in the repo, viewed through every lens the SceneGraph
exposes. Run it to eyeball correctness across the whole corpus at once:

    python -m tests.scene.show_scene_graphs            # -> tests/scene/scene_graph_report.txt
    python -m tests.scene.show_scene_graphs --stdout   # print instead of saving
    python -m tests.scene.show_scene_graphs miro_erd   # only files matching a name
    python -m tests.scene.show_scene_graphs --out path # custom output file

Lenses shown per file:
  - SUMMARY        node / edge / directed counts
  - NODES          id, label, and visual encoding (fill / stroke / dashed)
  - CONNECTION     undirected adjacency (neighbors)
  - DIRECTED       edges src -> tgt, plus roots (sources) and sinks (terminals)
  - VISUAL-ENCODING edges grouped by stroke style (solid / dashed / dotted)
  - CONTAINMENT    nodes that sit inside a container, with the container label
  - REACHABILITY   a sample find_path between the first root and first sink
"""
import os
import pathlib
import sys
import traceback

from svg_graph_parser.scene.scene_graph import SceneGraph


def _repo_root():
    """Walk up until we find the project root (pyproject.toml or the package)."""
    here = pathlib.Path(__file__).resolve()
    for base in here.parents:
        if (base / "pyproject.toml").exists() or (base / "svg_graph_parser").exists():
            return base
    return here.parent.parent.parent


SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", "build", "dist"}


def samples(filter_substr=None):
    root = _repo_root()
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root):
        # prune skipped / hidden dirs in place so os.walk does not descend them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in sorted(filenames):
            if not fn.lower().endswith(".svg"):
                continue
            if fn.startswith("."):                     # hidden icon stubs
                continue
            if filter_substr and filter_substr.lower() not in fn.lower():
                continue
            key = fn.lower()
            if key in seen:                            # duplicate-encoded names
                continue
            seen.add(key)
            yield pathlib.Path(dirpath) / fn


def _list_tree(root, out, max_entries=60):
    """When nothing is found, show what IS under the root so we can see why."""
    print("  directory listing (dirs + any .svg), 2 levels deep:", file=out)
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 2:
            dirnames[:] = []
            continue
        svgs = [f for f in filenames if f.lower().endswith(".svg")]
        marker = f"  <-- {len(svgs)} svg" if svgs else ""
        print(f"    {rel}/{marker}", file=out)
        n += 1
        if n >= max_entries:
            print("    ...", file=out)
            return


def lab(g, nid):
    t = g.label(nid)
    return t if t else nid


def show(g, path, out=sys.stdout):
    def pr(s=""):
        print(s, file=out)

    nodes = g.nodes
    directed = [e for e in g.edges if e.directed]
    undirected = [e for e in g.edges if not e.directed]

    pr(f"\n{'='*78}\nFILE: {path.name}")
    pr(f"SUMMARY  nodes={len(nodes)}  edges={len(g.edges)}  "
       f"directed={len(directed)}  undirected={len(undirected)}")

    # NODES + visual encoding
    pr(f"\n  NODES ({len(nodes)}):")
    for nid, n in list(nodes.items())[:40]:
        enc = []
        if n.fill and n.fill not in ("none", ""):
            enc.append(f"fill={n.fill}")
        if n.stroke_style and n.stroke_style != "solid":
            enc.append(n.stroke_style)
        encs = ("  {" + ", ".join(enc) + "}") if enc else ""
        pr(f"    {nid:5s} {(n.label or '(no text)')[:40]:40s}{encs}")
    if len(nodes) > 40:
        pr(f"    ... (+{len(nodes)-40} more)")

    # CONNECTION lens (undirected adjacency)
    pr(f"\n  CONNECTION (neighbors):")
    shown = 0
    for nid in nodes:
        nb = g.neighbors(nid)
        if nb:
            pr(f"    {lab(g,nid)[:24]:24s} -- {', '.join(lab(g,x)[:18] for x in nb)}")
            shown += 1
        if shown >= 25:
            pr("    ...")
            break
    if shown == 0:
        pr("    (no connections)")

    # DIRECTED lens
    if directed:
        pr(f"\n  DIRECTED ({len(directed)}):")
        for e in directed[:30]:
            pr(f"    {lab(g,e.source)[:24]:24s} -> {lab(g,e.target)[:24]}")
        if len(directed) > 30:
            pr(f"    ... (+{len(directed)-30} more)")
        roots = g.roots()
        sinks = g.sinks()
        pr(f"    roots (sources): {', '.join(lab(g,r)[:18] for r in roots[:10]) or '(none)'}")
        pr(f"    sinks (terminals): {', '.join(lab(g,s)[:18] for s in sinks[:10]) or '(none)'}")

    # VISUAL-ENCODING lens
    styles = {}
    for e in g.edges:
        styles.setdefault(e.style or "solid", 0)
        styles[e.style or "solid"] += 1
    if len(styles) > 1 or (styles and "solid" not in styles):
        pr(f"\n  VISUAL-ENCODING (edges by style): "
           + ", ".join(f"{k}={v}" for k, v in sorted(styles.items())))

    # CONTAINMENT lens
    contained = []
    for nid, n in nodes.items():
        parent = getattr(getattr(n, "_shape", None), "parent", None)
        if parent is not None:
            ptext = (parent.text or "(unlabelled container)")[:24]
            contained.append((lab(g, nid)[:24], ptext))
    if contained:
        pr(f"\n  CONTAINMENT (node inside container):")
        for child, parent in contained[:15]:
            pr(f"    {child:24s}  <  {parent}")

    # REACHABILITY sample
    roots = g.roots()
    sinks = g.sinks()
    if roots and sinks:
        path_found = g.find_path(roots[0], sinks[0])
        if path_found:
            pr(f"\n  REACHABILITY  {lab(g,roots[0])[:16]} ... {lab(g,sinks[0])[:16]}: "
               + " -> ".join(lab(g, x)[:14] for x in path_found))


def main():
    args = [a for a in sys.argv[1:]]
    to_stdout = "--stdout" in args
    if to_stdout:
        args.remove("--stdout")
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        out_path = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    filt = args[0] if args else None

    if not to_stdout and out_path is None:
        # default: save next to this script
        out_path = str(pathlib.Path(__file__).parent / "scene_graph_report.txt")

    out = sys.stdout if to_stdout else open(out_path, "w")
    try:
        ok = bad = 0
        for p in samples(filt):
            try:
                g = SceneGraph.from_svg(str(p))
                show(g, p, out)
                ok += 1
            except Exception:
                bad += 1
                print(f"\n{'='*78}\nFILE: {p.name}\n  ERROR reconstructing:", file=out)
                traceback.print_exc(file=out)
        print(f"\n{'='*78}\nDONE  reconstructed={ok}  errored={bad}", file=out)
        if ok + bad == 0:
            print(f"  NO .svg FILES FOUND under repo root: {_repo_root()}", file=out)
            print(f"  (searched recursively, skipping {sorted(SKIP_DIRS)})", file=out)
            _list_tree(_repo_root(), out)
    finally:
        if not to_stdout:
            out.close()
            print(f"wrote {ok + bad} files' scene graphs to {out_path}")


if __name__ == "__main__":
    main()