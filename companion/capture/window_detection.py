"""Reusable game window detection built on pluggable system enumerators.

This module holds the game-agnostic detection logic: match running processes
by executable name, find their visible top-level windows, and pick the most
likely game window. Platform-specific enumeration (Windows) lives in
:mod:`companion.capture.win32_api` and is used by default.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

ProcessEnumerator = Callable[[], "list[ProcessInfo]"]
WindowEnumerator = Callable[[], "list[WindowInfo]"]
TitleMatcher = Callable[[str], bool]


@dataclass(frozen=True)
class Rect:
    """Integer window bounds in screen pixel coordinates."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class ProcessInfo:
    """A running process, identified by PID and lowercase executable name."""

    pid: int
    exe_name: str


@dataclass(frozen=True)
class WindowInfo:
    """A visible top-level window.

    ``rect`` of a minimized window holds the OS-reported values (typically
    off-screen coordinates); consumers should rely on ``minimized`` instead.
    """

    hwnd: int
    pid: int
    title: str
    rect: Rect
    minimized: bool


@dataclass(frozen=True)
class GameWindow:
    """The game window that was detected, with everything capture needs."""

    pid: int
    exe_name: str
    hwnd: int
    title: str
    rect: Rect


class WindowDetectionError(Exception):
    """Base class for game window detection failures."""


class GameNotRunningError(WindowDetectionError):
    """No process matching the game's executable names is running."""


class NoVisibleWindowError(WindowDetectionError):
    """The game process is running but exposes no visible window."""


class WindowMinimizedError(WindowDetectionError):
    """The game process has a window, but it is currently minimized."""


def _default_enumerators() -> tuple[ProcessEnumerator, WindowEnumerator]:
    from . import win32_api  # Imported lazily so logic tests run on any OS.

    return win32_api.list_processes, win32_api.list_visible_windows


def find_game_window(
    process_exe_names: Iterable[str],
    *,
    game_name: str,
    title_matches: TitleMatcher | None = None,
    list_processes: ProcessEnumerator | None = None,
    list_visible_windows: WindowEnumerator | None = None,
) -> GameWindow:
    """Find the visible window of a running game.

    ``process_exe_names`` is the set of executable base names (any case) that
    identify the game. Among the visible, non-minimized windows owned by those
    processes, windows whose title satisfies ``title_matches`` are preferred;
    otherwise the largest window is used as a fallback. When several windows
    qualify, the largest one wins.

    Raises:
        GameNotRunningError: no matching process is running.
        NoVisibleWindowError: a matching process runs but has no visible window.
        WindowMinimizedError: the game window exists but is minimized.
    """
    if list_processes is None or list_visible_windows is None:
        default_processes, default_windows = _default_enumerators()
        if list_processes is None:
            list_processes = default_processes
        if list_visible_windows is None:
            list_visible_windows = default_windows

    wanted = {name.lower() for name in process_exe_names}
    processes = [p for p in list_processes() if p.exe_name.lower() in wanted]
    if not processes:
        raise GameNotRunningError(f"{game_name} does not appear to be running.")

    pid_to_exe = {p.pid: p.exe_name for p in processes}
    windows = [w for w in list_visible_windows() if w.pid in pid_to_exe]
    if not windows:
        raise NoVisibleWindowError(
            f"{game_name} is running, but no visible game window could be found."
        )
    if all(w.minimized for w in windows):
        raise WindowMinimizedError(
            f"{game_name} is running, but its game window is minimized."
        )

    active = [w for w in windows if not w.minimized]
    candidates = (
        [w for w in active if title_matches(w.title)]
        if title_matches is not None
        else []
    )
    pool = candidates or active
    best = max(pool, key=lambda w: w.rect.area)

    return GameWindow(
        pid=best.pid,
        exe_name=pid_to_exe[best.pid],
        hwnd=best.hwnd,
        title=best.title,
        rect=best.rect,
    )
