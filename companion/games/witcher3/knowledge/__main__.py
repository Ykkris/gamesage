"""Manual retrieval test for installed Witcher 3 knowledge packs.

Run from the repository root:

    python -m companion.games.witcher3.knowledge "griffin attacks travelers"

Prints the ranked chunks (from all installed packs for witcher3) with
scores, spoiler levels, and sources. For general pack tooling see
``python -m tools.knowledge``.
"""

from __future__ import annotations

import argparse
import sys

from companion.knowledge.packs.registry import KnowledgePackRegistry
from companion.knowledge.retrieval import retrieve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m companion.games.witcher3.knowledge",
        description="Query the installed Witcher 3 knowledge packs.",
    )
    parser.add_argument("query", nargs="+", help="retrieval query terms")
    parser.add_argument("--limit", type=int, default=3, help="max results (default 3)")
    args = parser.parse_args(argv)

    registry = KnowledgePackRegistry()
    chunks = registry.chunks_for_game("witcher3")
    if not chunks:
        print("No Witcher 3 knowledge is installed.", file=sys.stderr)
        return 1

    hits = retrieve(" ".join(args.query), chunks, limit=args.limit)
    if not hits:
        print("No matching knowledge for this query.")
        return 0

    for hit in hits:
        chunk = hit.chunk
        spoiler = chunk.spoiler or "n/a"
        pack = chunk.pack_id or "n/a"
        print(f"[{hit.score:6.2f}] {chunk.title}  (spoiler: {spoiler})")
        print(f"         source: {chunk.source}  pack: {pack}  id: {chunk.id}")
        summary = " ".join(chunk.text.split())[:110]
        print(f"         {summary}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
