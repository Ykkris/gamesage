"""Trusted adapter that realizes a validated Game Definition.

The definition supplies only data (executable names, window-title match
values); all behavior — process/window detection and screen capture — is
GameSage's own generic code. No code is generated or imported from
definition directories.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameWindow,
    ProcessEnumerator,
    WindowEnumerator,
    find_game_window,
)
from companion.games.base import GameAdapter

from .schema import GameDefinition, make_title_matcher


class DeclarativeGameAdapter(GameAdapter):
    """GameAdapter backed by a declarative Game Definition."""

    def __init__(self, definition: GameDefinition) -> None:
        self._definition = definition
        self.id = definition.id
        self.display_name = definition.display_name

    @property
    def definition(self) -> GameDefinition:
        """The validated definition backing this adapter (read-only)."""
        return self._definition

    def detect_window(
        self,
        *,
        list_processes: ProcessEnumerator | None = None,
        list_visible_windows: WindowEnumerator | None = None,
    ) -> GameWindow:
        return find_game_window(
            frozenset(name.lower() for name in self._definition.executables),
            game_name=self.display_name,
            title_matches=make_title_matcher(
                self._definition.window_titles,
                self._definition.window_title_mode,
            ),
            list_processes=list_processes,
            list_visible_windows=list_visible_windows,
        )

    def save_capture(
        self, result: CaptureResult, directory: Path | None = None
    ) -> Path:
        """Save a capture named after the game id (deterministic)."""
        target_dir = directory if directory is not None else Path("screenshots")
        target_dir.mkdir(exist_ok=True)
        stem = f"{self.id}-{datetime.now():%Y%m%d-%H%M%S-%f}"
        path = target_dir / f"{stem}.png"
        suffix = 1
        while path.exists():
            path = target_dir / f"{stem}-{suffix}.png"
            suffix += 1
        return result.save(path)
