"""Manual retrieval test for the Witcher 3 knowledge corpus.

Run from the repository root:

    python -m companion.games.witcher3.knowledge "griffin attacks travelers"

Prints the ranked chunks with scores, spoiler levels, and sources.
"""

from __future__ import annotations

import argparse
import sys

from companion.knowledge.retrieval import retrieve

from .sources import load_corpus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m companion.games.witcher3.knowledge",
        description="Query the local Witcher 3 knowledge corpus.",
    )
    parser.add_argument("query", nargs="+", help="retrieval query terms")
    parser.add_argument("--limit", type=int, default=3, help="max results (default 3)")
    args = parser.parse_args(argv)

    chunks = load_corpus()
    if not chunks:
        print("The Witcher 3 knowledge corpus is empty.", file=sys.stderr)
        return 1

    hits = retrieve(" ".join(args.query), chunks, limit=args.limit)
    if not hits:
        print("No matching knowledge for this query.")
        return 0

    for hit in hits:
        chunk = hit.chunk
        spoiler = chunk.spoiler or "n/a"
        print(f"[{hit.score:6.2f}] {chunk.title}  (spoiler: {spoiler})")
        print(f"         source: {chunk.source}  id: {chunk.id}")
        summary = " ".join(chunk.text.split())[:110]
        print(f"         {summary}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
