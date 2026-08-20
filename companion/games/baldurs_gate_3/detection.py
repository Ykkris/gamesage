"""Baldur's Gate 3 window detection rules (Windows).

All BG3-specific knowledge used for detection lives here: executable names
and the window-title rule. The mechanics of process and window enumeration
are delegated to the reusable detection layer in
``companion.capture.window_detection``.
"""

from __future__ import annotations

from companion.capture.window_detection import (
    GameWindow,
    ProcessEnumerator,
    WindowEnumerator,
    find_game_window,
)

GAME_ID = "baldurs_gate_3"
GAME_NAME = "Baldur's Gate 3"

#: Executable base names (lowercase): bg3.exe renders with Vulkan,
#: bg3_dx11.exe with DirectX 11.
EXECUTABLE_NAMES = frozenset({"bg3.exe", "bg3_dx11.exe"})


def is_game_window_title(title: str) -> bool:
    """Whether a window title looks like the Baldur's Gate 3 main window."""
    normalized = title.strip().lower().replace("\u2019", "'")
    return normalized.startswith("baldur's gate 3")


def detect_window(
    *,
    list_processes: ProcessEnumerator | None = None,
    list_visible_windows: WindowEnumerator | None = None,
) -> GameWindow:
    """Detect the visible Baldur's Gate 3 window on this machine."""
    return find_game_window(
        EXECUTABLE_NAMES,
        game_name=GAME_NAME,
        title_matches=is_game_window_title,
        list_processes=list_processes,
        list_visible_windows=list_visible_windows,
    )
