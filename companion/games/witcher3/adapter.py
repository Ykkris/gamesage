"""The Witcher 3 implementation of the generic GameAdapter interface.

Thin delegation to the existing game modules: detection rules, capture
naming, and the bundled knowledge corpus. All low-level capture and
retrieval logic stays in the generic layers.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameWindow,
    ProcessEnumerator,
    WindowEnumerator,
)
from companion.games.base import GameAdapter
from companion.knowledge.models import KnowledgeChunk

from .capture import save_capture
from .detection import GAME_ID, GAME_NAME, detect_window
from .knowledge.sources import load_corpus


class Witcher3Game(GameAdapter):
    """GameAdapter for The Witcher 3: Wild Hunt."""

    def __init__(self) -> None:
        self.id = GAME_ID
        self.display_name = GAME_NAME

    def detect_window(
        self,
        *,
        list_processes: ProcessEnumerator | None = None,
        list_visible_windows: WindowEnumerator | None = None,
    ) -> GameWindow:
        return detect_window(
            list_processes=list_processes,
            list_visible_windows=list_visible_windows,
        )

    def save_capture(
        self, result: CaptureResult, directory: Path | None = None
    ) -> Path:
        return save_capture(result, directory)

    def load_knowledge_corpus(self) -> tuple[KnowledgeChunk, ...]:
        return load_corpus()


#: Shared singleton (stateless adapter).
WITCHER3_GAME = Witcher3Game()
