"""Capture the currently detected The Witcher 3 game window (Windows).

Combines the game-specific detection rules with the generic capture layer:
detect the visible Witcher 3 window, then capture exactly its bounds.
"""

from __future__ import annotations

from companion.capture.window_capture import (
    CaptureResult,
    MinimizedCheck,
    RegionGrabber,
    capture_window,
)
from companion.capture.window_detection import (
    ProcessEnumerator,
    WindowEnumerator,
)

from .detection import detect_window


def capture_game_window(
    *,
    list_processes: ProcessEnumerator | None = None,
    list_visible_windows: WindowEnumerator | None = None,
    grab: RegionGrabber | None = None,
    is_minimized: MinimizedCheck | None = None,
) -> CaptureResult:
    """Detect The Witcher 3 window and capture its on-screen region.

    All system interactions are injectable for tests; by default the real
    Windows detection and capture are used.

    Raises:
        GameNotRunningError: The Witcher 3 does not appear to be running.
        NoVisibleWindowError: the game runs but has no visible window.
        WindowMinimizedError: the game window exists but is minimized.
        InvalidCaptureRegionError: the window bounds have no area.
        ScreenCaptureError: the OS screen grab failed.
    """
    window = detect_window(
        list_processes=list_processes,
        list_visible_windows=list_visible_windows,
    )
    return capture_window(window, grab=grab, is_minimized=is_minimized)
