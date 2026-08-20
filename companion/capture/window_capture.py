"""Generic window capture logic.

Given a detected :class:`~companion.capture.window_detection.GameWindow`,
capture its on-screen region and return structured image data. The actual
screen grab is performed by an injectable region grabber; the default
implementation (Windows, mss-based) lives in
:mod:`companion.capture.screen_capture`.

This is screen-region capture: it reads the pixels currently visible at the
window's bounds, so windows fully hidden behind other windows are captured
as whatever is on top of them.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .window_detection import GameWindow, Rect, WindowMinimizedError

RegionGrabber = Callable[[Rect], "CaptureResult"]
MinimizedCheck = Callable[[int], bool]


@dataclass(frozen=True)
class CaptureResult:
    """A captured screenshot, PNG-encoded, with its pixel dimensions."""

    png: bytes
    width: int
    height: int

    def save(self, path: str | Path) -> Path:
        """Write the PNG to ``path`` (parent directories are not created)."""
        path = Path(path)
        path.write_bytes(self.png)
        return path


class WindowCaptureError(Exception):
    """Base class for window capture failures."""


class InvalidCaptureRegionError(WindowCaptureError):
    """The window region has no visible area to capture."""


class ScreenCaptureError(WindowCaptureError):
    """The screen region could not be captured from the OS."""


def capture_window(
    window: GameWindow,
    *,
    grab: RegionGrabber | None = None,
    is_minimized: MinimizedCheck | None = None,
) -> CaptureResult:
    """Capture the on-screen region of a detected game window.

    ``grab`` captures a physical-pixel screen region (defaults to the mss
    implementation). ``is_minimized`` optionally re-checks the window live,
    guarding against the window being minimized between detection and capture.

    Raises:
        WindowMinimizedError: the window is minimized.
        InvalidCaptureRegionError: the window bounds have no area.
        ScreenCaptureError: the OS screen grab failed.
    """
    if window.minimized:
        raise WindowMinimizedError(
            "The game window is minimized; restore it before capturing."
        )
    if window.rect.width <= 0 or window.rect.height <= 0:
        raise InvalidCaptureRegionError(
            f"The window region {window.rect} has no visible area to capture."
        )
    if is_minimized is None and sys.platform == "win32":
        from . import win32_api

        is_minimized = win32_api.is_minimized
    if is_minimized is not None and is_minimized(window.hwnd):
        raise WindowMinimizedError(
            "The game window was minimized after detection; restore it and try again."
        )
    if grab is None:
        from .screen_capture import capture_screen_region

        grab = capture_screen_region

    return grab(window.rect)
