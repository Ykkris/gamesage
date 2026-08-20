"""Generic game adapter interface.

A game adapter composes the game's own detection rules and knowledge with
the generic capture/knowledge layers — it does not reimplement low-level
screen capture or retrieval. The smallest seams needed today are identity,
window detection, capture naming, corpus access, and the display name used
as vision context.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameWindow,
    ProcessEnumerator,
    WindowEnumerator,
)
from companion.knowledge.models import KnowledgeChunk


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

    def load_knowledge_corpus(self) -> Sequence[KnowledgeChunk]:
        """The game's local knowledge corpus (may be empty)."""
        ...
