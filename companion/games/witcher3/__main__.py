"""Manual capture test for The Witcher 3.

Run from the repository root:

    python -m companion.games.witcher3

Detects the Witcher 3 window, captures it, and saves the PNG under
``screenshots/`` (git-ignored).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from companion.capture.window_capture import WindowCaptureError
from companion.capture.window_detection import WindowDetectionError

from .capture import capture_game_window

SCREENSHOTS_DIR = Path("screenshots")


def main() -> int:
    try:
        result = capture_game_window()
    except (WindowDetectionError, WindowCaptureError) as error:
        print(f"Capture failed: {error}", file=sys.stderr)
        return 1

    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    path = SCREENSHOTS_DIR / f"witcher3-{datetime.now():%Y%m%d-%H%M%S}.png"
    result.save(path)
    print(f"Saved {result.width}x{result.height} capture to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
