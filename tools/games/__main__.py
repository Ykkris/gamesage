"""Game Definition v1 developer CLI.

Usage (from the repository root):

    python -m tools.games validate <definition-directory>
    python -m tools.games inspect <definition-directory>

Validation uses exactly the same loader as runtime discovery — there is no
separate rule set for definition authors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from companion.games.definitions.discovery import (
    LoadedDefinition,
    load_definition,
)


def _load(path: Path) -> LoadedDefinition | int:
    result = load_definition(path)
    if not isinstance(result, LoadedDefinition):
        print(f"{result.status}: {result.message}", file=sys.stderr)
        return 1
    return result


def validate(directory: Path) -> int:
    outcome = _load(directory)
    if isinstance(outcome, int):
        return outcome
    definition = outcome.definition
    print(
        f"OK: {definition.definition_id} {definition.version} "
        f"(game '{definition.id}' — {definition.display_name})"
    )
    return 0


def inspect_definition(directory: Path) -> int:
    outcome = _load(directory)
    if isinstance(outcome, int):
        return outcome
    definition = outcome.definition
    print(f"id:               {definition.id}")
    print(f"display_name:     {definition.display_name}")
    print(f"definition_id:    {definition.definition_id}")
    print(f"version:          {definition.version}")
    print(f"author:           {definition.author}")
    print(f"platform:         {definition.platform}")
    if definition.description:
        print(f"description:      {definition.description}")
    print(f"executables:      {', '.join(definition.executables)}")
    print(f"window_titles:    {', '.join(definition.window_titles)}")
    print(f"title match mode: {definition.window_title_mode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.games",
        description="Validate and inspect Game Definition v1 directories.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate_parser = subcommands.add_parser("validate", help="validate a definition directory")
    validate_parser.add_argument("directory", type=Path)

    inspect_parser = subcommands.add_parser("inspect", help="show definition fields")
    inspect_parser.add_argument("directory", type=Path)

    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate(args.directory)
    return inspect_definition(args.directory)


if __name__ == "__main__":
    sys.exit(main())
