"""Knowledge Pack v1 developer CLI.

Usage (from the repository root):

    python -m tools.knowledge validate <pack-directory>
    python -m tools.knowledge inspect <pack-directory>
    python -m tools.knowledge query <pack-directory> "<query>"

Validation uses exactly the same loader as runtime discovery — there is no
separate rule set for pack authors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from companion.knowledge.packs.registry import LoadedPack, load_pack
from companion.knowledge.retrieval import retrieve


def _load(path: Path) -> LoadedPack | int:
    result = load_pack(path)
    if not isinstance(result, LoadedPack):
        print(f"{result.status}: {result.message}", file=sys.stderr)
        return 1
    return result


def validate(directory: Path) -> int:
    outcome = _load(directory)
    if isinstance(outcome, int):
        return outcome
    print(f"OK: {outcome.manifest.id} {outcome.manifest.version} "
          f"({len(outcome.records)} records for game '{outcome.manifest.game_id}')")
    return 0


def inspect_pack(directory: Path) -> int:
    outcome = _load(directory)
    if isinstance(outcome, int):
        return outcome
    manifest = outcome.manifest
    print(f"id:          {manifest.id}")
    print(f"game_id:     {manifest.game_id}")
    print(f"version:     {manifest.version}")
    print(f"name:        {manifest.name}")
    print(f"author:      {manifest.author}")
    if manifest.description:
        print(f"description: {manifest.description}")
    if manifest.languages:
        print(f"languages:   {', '.join(manifest.languages)}")
    print(f"records:     {len(outcome.records)}")
    for record in outcome.records:
        aliases = f"  aliases: {', '.join(record.aliases)}" if record.aliases else ""
        print(f"  - {record.id}  [{record.language or 'n/a'}] {record.title}{aliases}")
    return 0


def query(directory: Path, text: str) -> int:
    outcome = _load(directory)
    if isinstance(outcome, int):
        return outcome
    hits = retrieve(text, outcome.records, limit=5)
    if not hits:
        print("No matching records.")
        return 0
    for hit in hits:
        print(f"[{hit.score:6.2f}] {hit.chunk.title}  (spoiler: {hit.chunk.spoiler or 'n/a'})")
        print(f"          {hit.chunk.id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.knowledge",
        description="Validate, inspect, and query Knowledge Pack v1 directories.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate_parser = subcommands.add_parser("validate", help="validate a pack directory")
    validate_parser.add_argument("directory", type=Path)

    inspect_parser = subcommands.add_parser("inspect", help="show manifest and records")
    inspect_parser.add_argument("directory", type=Path)

    query_parser = subcommands.add_parser("query", help="run a retrieval query over a pack")
    query_parser.add_argument("directory", type=Path)
    query_parser.add_argument("query")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate(args.directory)
    if args.command == "inspect":
        return inspect_pack(args.directory)
    return query(args.directory, args.query)


if __name__ == "__main__":
    sys.exit(main())
