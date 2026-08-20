"""Global hotkey trigger for Witcher 3 capture (Windows).

Runs the existing detect-and-capture pipeline whenever the configured global
hotkey is pressed. The Windows hotkey mechanism itself is generic and lives
in ``companion/input/``; only the default shortcut and the capture handler
are Witcher 3 specific.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

from companion.capture.window_capture import CaptureResult, WindowCaptureError
from companion.capture.window_detection import WindowDetectionError
from companion.input.hotkey import Hotkey, HotkeyRegistrationError
from companion.input.win32_hotkey import GlobalHotkeyListener

from .capture import SCREENSHOTS_DIR, capture_game_window, save_capture

#: Default capture hotkey; kept in code for easy adjustment.
DEFAULT_HOTKEY = Hotkey.parse("ctrl+f8")


def handle_hotkey_press(
    screenshots_dir: Path = SCREENSHOTS_DIR,
    *,
    capture: Callable[[], CaptureResult] = capture_game_window,
) -> bool:
    """Run one capture request and report status; never raises.

    Returns True when a screenshot was saved, False when the capture failed
    (game not running, window minimized, capture error).
    """
    try:
        result = capture()
    except (WindowDetectionError, WindowCaptureError) as error:
        print(f"Capture failed: {error}", file=sys.stderr)
        return False
    path = save_capture(result, screenshots_dir)
    print(f"Saved {result.width}x{result.height} capture to {path}")
    return True


def run_hotkey_app(
    hotkey: Hotkey = DEFAULT_HOTKEY,
    screenshots_dir: Path = SCREENSHOTS_DIR,
    *,
    capture: Callable[[], CaptureResult] = capture_game_window,
) -> int:
    """Listen for the global hotkey until Ctrl+C; return an exit code."""
    print(f"Global hotkey: {hotkey}")
    print(
        f"Press {hotkey} to capture The Witcher 3 "
        f"(saved to {screenshots_dir}); press Ctrl+C to stop."
    )
    try:
        with GlobalHotkeyListener(
            hotkey,
            lambda: handle_hotkey_press(screenshots_dir, capture=capture),
        ):
            while True:
                time.sleep(0.2)
    except HotkeyRegistrationError as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
    return 0
