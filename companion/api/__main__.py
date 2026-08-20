"""Machine-readable CLI for the GameSage desktop bridge.

Usage:

    python -m companion.api capture [--screenshots-dir PATH]

Prints a single-line JSON envelope on stdout. Exit code is 0 on success and
1 on failure; the envelope itself always carries the error details.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from .capture_json import run_capture


def main(
    argv: list[str] | None = None, *, run: Callable[[Path | None], dict] = run_capture
) -> int:
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

    args = parser.parse_args(argv)
    payload = run(args.screenshots_dir)
    print(json.dumps(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
