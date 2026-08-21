"""The Witcher 3 implementation of the generic GameAdapter interface.

Thin delegation to the game modules: detection rules and capture naming.
Knowledge for Witcher 3 comes from installed Knowledge Packs (see
``knowledge_packs/gamesage.witcher3.starter``), resolved by game id.
"""

from __future__ import annotations

from pathlib import Path

from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameWindow,
    ProcessEnumerator,
    WindowEnumerator,
)
from companion.games.base import GameAdapter

from .capture import save_capture
from .detection import GAME_ID, GAME_NAME, detect_window


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


#: Shared singleton (stateless adapter).
WITCHER3_GAME = Witcher3Game()
