"""Manual capture tooling for The Witcher 3.

Run from the repository root:

    python -m companion.games.witcher3

Detects the Witcher 3 window, captures it, and saves the PNG under
``screenshots/`` (git-ignored). With ``--listen``, keeps running and
captures on the global hotkey (default Ctrl+F8) until Ctrl+C.
"""

from __future__ import annotations

import argparse
import sys

from companion.capture.window_capture import WindowCaptureError
from companion.capture.window_detection import WindowDetectionError

from .capture import capture_game_window, save_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m companion.games.witcher3",
        description="Detect and capture The Witcher 3 game window.",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="keep running and capture on the global hotkey (default: Ctrl+F8)",
    )
    args = parser.parse_args(argv)

    if args.listen:
        from .hotkey import run_hotkey_app

        return run_hotkey_app()

    try:
        result = capture_game_window()
    except (WindowDetectionError, WindowCaptureError) as error:
        print(f"Capture failed: {error}", file=sys.stderr)
        return 1
    path = save_capture(result)
    print(f"Saved {result.width}x{result.height} capture to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
