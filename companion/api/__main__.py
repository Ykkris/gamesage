"""Machine-readable CLI for the GameSage desktop bridge.

Usage:

    python -m companion.api capture [--screenshots-dir PATH]
    python -m companion.api analyze --image PATH --question TEXT

Prints a single-line JSON envelope on stdout. Exit code is 0 on success and
1 on failure; the envelope itself always carries the error details.

A repository ``.env`` file (simple KEY=VALUE lines) is loaded first;
real environment variables always take precedence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from .analyze_json import run_analysis
from .capture_json import run_capture


def load_env_file(path: Path, *, environ: dict[str, str] | None = None) -> int:
    """Load simple KEY=VALUE lines from ``path`` into ``environ``.

    Existing variables are never overridden. Comments and blank lines are
    skipped. Returns the number of variables loaded.
    """
    target = os.environ if environ is None else environ
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    loaded = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in target:
            target[key] = value
            loaded += 1
    return loaded


def main(
    argv: list[str] | None = None,
    *,
    run_capture_command: Callable[[Path | None, str | None], dict] = run_capture,
    run_analyze_command: Callable[[Path, str, str | None], dict] = run_analysis,
) -> int:
    load_env_file(Path(".env"))

    parser = argparse.ArgumentParser(
        prog="python -m companion.api",
        description="Machine-readable GameSage core interface (desktop bridge).",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    capture = subcommands.add_parser(
        "capture", help="detect and capture the game window; print a JSON envelope"
    )
    capture.add_argument(
        "--screenshots-dir",
        type=Path,
        default=None,
        help="directory for saved screenshots (default: ./screenshots)",
    )
    capture.add_argument(
        "--game",
        default=None,
        help="game id (default: the currently supported game)",
    )

    analyze = subcommands.add_parser(
        "analyze", help="answer a question about a screenshot; print a JSON envelope"
    )
    analyze.add_argument("--image", type=Path, required=True, help="screenshot path (PNG)")
    analyze.add_argument("--question", required=True, help="question about the screenshot")
    analyze.add_argument(
        "--game",
        default=None,
        help="game id (default: the currently supported game)",
    )

    args = parser.parse_args(argv)
    if args.command == "capture":
        payload = run_capture_command(args.screenshots_dir, args.game)
    else:
        payload = run_analyze_command(args.image, args.question, args.game)
    print(json.dumps(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
