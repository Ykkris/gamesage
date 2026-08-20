"""The Baldur's Gate 3 implementation of the generic GameAdapter interface.

Minimal multi-game smoke test: metadata, detection, capture naming, and an
intentionally empty knowledge corpus (no BG3 RAG yet).
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


class BaldursGate3Game(GameAdapter):
    """GameAdapter for Baldur's Gate 3."""

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
        """No BG3 knowledge corpus yet — deliberately empty."""
        return ()


#: Shared singleton (stateless adapter).
BALDURS_GATE_3_GAME = BaldursGate3Game()
