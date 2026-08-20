"""The Witcher 3: Wild Hunt window detection rules (Windows).

All Witcher 3-specific knowledge used for detection lives here: executable
names and how to recognize the game window's title. The mechanics of process
and window enumeration are delegated to the reusable detection layer in
``companion.capture.window_detection``.
"""

from __future__ import annotations

from companion.capture.window_detection import (
    GameWindow,
    ProcessEnumerator,
    TitleMatcher,
    WindowEnumerator,
    find_game_window,
)

GAME_ID = "witcher3"
GAME_NAME = "The Witcher 3: Wild Hunt"

#: Executable base names (lowercase) used by the GOG and Steam releases.
EXECUTABLE_NAMES = frozenset({"witcher3.exe"})


def is_game_window_title(title: str) -> bool:
    """Whether a window title looks like The Witcher 3 main window."""
    return title.strip().lower().startswith("the witcher 3")


def detect_window(
    *,
    list_processes: ProcessEnumerator | None = None,
    list_visible_windows: WindowEnumerator | None = None,
) -> GameWindow:
    """Detect the visible Witcher 3 window on this machine.

    Enumerators are injectable for tests; by default the real Windows
    enumeration is used.

    Raises:
        GameNotRunningError: The Witcher 3 does not appear to be running.
        NoVisibleWindowError: the game runs but has no visible window.
        WindowMinimizedError: the game window exists but is minimized.
    """
    return find_game_window(
        EXECUTABLE_NAMES,
        game_name=GAME_NAME,
        title_matches=is_game_window_title,
        list_processes=list_processes,
        list_visible_windows=list_visible_windows,
    )
