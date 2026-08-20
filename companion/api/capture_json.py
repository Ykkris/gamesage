"""Machine-readable JSON interface for the game capture pipeline.

This module is the desktop bridge: the Tauri layer invokes
``python -m companion.api capture`` and consumes the single-line JSON
envelope printed on stdout. Human-facing console output
(``python -m companion.games.witcher3``) stays separate.

Games are resolved through the adapter registry (``get_game``); nothing
here imports a concrete game.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from companion.capture.window_capture import CaptureResult, WindowCaptureError, capture_window
from companion.capture.window_detection import (
    GameNotRunningError,
    GameWindow,
    NoVisibleWindowError,
    WindowDetectionError,
    WindowMinimizedError,
)
from companion.games.base import GameAdapter
from companion.games.registry import UnknownGameError, get_game

Detector = Callable[[], GameWindow]
Captor = Callable[[GameWindow], CaptureResult]

#: Known error types mapped to stable machine-readable codes.
_ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (GameNotRunningError, "game_not_running"),
    (NoVisibleWindowError, "no_visible_window"),
    (WindowMinimizedError, "window_minimized"),
    (WindowCaptureError, "capture_failed"),
)


def error_code(error: Exception) -> str:
    """Stable code for a capture pipeline error, or ``internal_error``."""
    for error_type, code in _ERROR_CODES:
        if isinstance(error, error_type):
            return code
    return "internal_error"


def run_capture(
    screenshots_dir: Path | None = None,
    game_id: str | None = None,
    *,
    detect: Detector | None = None,
    capture: Captor = capture_window,
) -> dict:
    """Run the capture pipeline for a game and return a JSON envelope.

    ``game_id`` selects the adapter (default game when omitted). ``detect``
    defaults to the adapter's window detection; ``capture`` is the generic
    window capture and normally not replaced.

    Returns ``{"ok": True, ...capture details}`` or
    ``{"ok": False, "error": {"code", "message"}}``. Unexpected exceptions are
    reported generically (details go to stderr) so raw stack traces never
    reach the desktop UI.
    """
    try:
        game = get_game(game_id)
        if detect is None:
            detect = game.detect_window
        window = detect()
        result = capture(window)
        path = game.save_capture(result, screenshots_dir)
    except UnknownGameError as error:
        return {
            "ok": False,
            "error": {"code": "unknown_game", "message": str(error)},
        }
    except (WindowDetectionError, WindowCaptureError) as error:
        return {
            "ok": False,
            "error": {"code": error_code(error), "message": str(error)},
        }
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": (
                    "An unexpected error occurred while running the "
                    "GameSage capture pipeline."
                ),
            },
        }

    return {
        "ok": True,
        "game_id": game.id,
        "window_title": window.title,
        "width": result.width,
        "height": result.height,
        "screenshot_path": str(path.resolve()),
    }
