"""True token cost: raw SVG vs scene graph, using Anthropic's real tokenizer.

This calls the count_tokens endpoint -- it returns the exact input_tokens Claude
would see, WITHOUT running the model. No inference, no completion cost.
(The chars/4 number in the MCP server is only an estimate; this is the real one.)

Setup:  export ANTHROPIC_API_KEY=sk-...
        pip install anthropic
Run:    python -m examples.count_tokens tests/samples/miro_erd.svg
        python -m examples.count_tokens tests/samples/ai_playground.svg

Model matters: the Opus 4.7+ tokenizer counts ~30% higher than older models for
the same text, so pass the model you actually query with.
"""
import os
import sys

import anthropic

from svg_graph_parser.scene.scene_graph import SceneGraph

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")


def scene_graph_text(g):
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


def count(client, text):
    """Exact input_tokens from Claude's tokenizer. None if the call fails."""
    try:
        r = client.messages.count_tokens(
            model=MODEL,
            messages=[{"role": "user", "content": text}],
        )
        return r.input_tokens
    except Exception as e:
        return f"[error: {e}]"


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("set ANTHROPIC_API_KEY first")
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/samples/miro_erd.svg"
    raw = open(path).read()
    sg = scene_graph_text(SceneGraph.from_svg(path))

    client = anthropic.Anthropic()
    print(f"file:  {os.path.basename(path)}")
    print(f"model: {MODEL}  (true count_tokens, not an estimate)\n")

    sg_tok = count(client, sg)
    print(f"  scene graph : {sg_tok:>9,} tokens" if isinstance(sg_tok, int)
          else f"  scene graph : {sg_tok}")

    raw_tok = count(client, raw)
    if isinstance(raw_tok, int):
        print(f"  raw SVG     : {raw_tok:>9,} tokens")
        if isinstance(sg_tok, int):
            print(f"\n  reduction   : {raw_tok / max(sg_tok,1):.0f}x smaller (real tokenizer)")
    else:
        # huge boards may exceed the request limit -- which is itself the point
        print(f"  raw SVG     : {raw_tok}")
        print(f"\n  (raw SVG too large to count/send -- the scene graph is what fits)")


if __name__ == "__main__":
    main()
