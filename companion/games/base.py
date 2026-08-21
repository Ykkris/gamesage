"""Generic game adapter interface.

A game adapter represents the GAME: identity and detection rules composed
with the generic capture layer. Installed KNOWLEDGE is owned by the
Knowledge Pack registry (``companion/knowledge/packs/``), which resolves
packs by the adapter's ``game_id`` — adapters do not carry knowledge packs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameWindow,
    ProcessEnumerator,
    WindowEnumerator,
)


@runtime_checkable
class GameAdapter(Protocol):
    """A supported game."""

    id: str
    display_name: str

    def detect_window(
        self,
        *,
        list_processes: ProcessEnumerator | None = None,
        list_visible_windows: WindowEnumerator | None = None,
    ) -> GameWindow:
        """Detect the game's visible window on this machine."""
        ...

    def save_capture(
        self, result: CaptureResult, directory: Path | None = None
    ) -> Path:
        """Save a capture under ``directory`` with the game's naming."""
        ...
