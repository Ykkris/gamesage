"""Tests for the reusable game window detection logic."""

import pytest

from companion.capture.window_detection import (
    GameNotRunningError,
    GameWindow,
    NoVisibleWindowError,
    ProcessInfo,
    Rect,
    WindowInfo,
    WindowMinimizedError,
    find_game_window,
)

GAME_NAME = "Some Game"


def make_process(pid: int = 100, exe_name: str = "game.exe") -> ProcessInfo:
    return ProcessInfo(pid=pid, exe_name=exe_name)


def make_window(
    hwnd: int = 1,
    pid: int = 100,
    title: str = "Some Game",
    rect: Rect | None = None,
    minimized: bool = False,
) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        pid=pid,
        title=title,
        rect=rect or Rect(0, 0, 1280, 720),
        minimized=minimized,
    )


def finder(
    processes: list[ProcessInfo],
    windows: list[WindowInfo],
    title_matches=None,
):
    return find_game_window(
        {"game.exe"},
        game_name=GAME_NAME,
        title_matches=title_matches,
        list_processes=lambda: processes,
        list_visible_windows=lambda: windows,
    )


class TestRect:
    def test_dimensions_and_area(self):
        rect = Rect(10, 20, 110, 260)
        assert rect.width == 100
        assert rect.height == 240
        assert rect.area == 24000


class TestFindGameWindow:
    def test_returns_matching_window_with_bounds(self):
        result = finder([make_process()], [make_window(hwnd=7, title="Some Game")])

        assert isinstance(result, GameWindow)
        assert result.pid == 100
        assert result.exe_name == "game.exe"
        assert result.hwnd == 7
        assert result.title == "Some Game"
        assert result.rect == Rect(0, 0, 1280, 720)

    def test_exe_name_matching_is_case_insensitive(self):
        result = finder([make_process(exe_name="GAME.EXE")], [make_window()])

        assert result.exe_name == "GAME.EXE"

    def test_raises_game_not_running_when_no_process(self):
        with pytest.raises(GameNotRunningError) as excinfo:
            finder([make_process(pid=1, exe_name="other.exe")], [])

        assert GAME_NAME in str(excinfo.value)
        assert "does not appear to be running" in str(excinfo.value)

    def test_raises_no_visible_window_when_process_has_none(self):
        with pytest.raises(NoVisibleWindowError) as excinfo:
            finder([make_process()], [])

        assert "no visible game window" in str(excinfo.value)

    def test_raises_minimized_when_only_minimized_windows(self):
        with pytest.raises(WindowMinimizedError) as excinfo:
            finder([make_process()], [make_window(minimized=True)])

        assert "minimized" in str(excinfo.value)

    def test_prefers_visible_window_over_minimized(self):
        result = finder(
            [make_process()],
            [make_window(hwnd=1, minimized=True), make_window(hwnd=2)],
        )

        assert result.hwnd == 2

    def test_ignores_windows_of_other_processes(self):
        with pytest.raises(NoVisibleWindowError):
            finder(
                [make_process(pid=100)],
                [make_window(hwnd=1, pid=999, title="Some Game")],
            )

    def test_prefers_title_match_over_larger_unmatched_window(self):
        result = finder(
            [make_process()],
            [
                make_window(hwnd=1, title="Some Game", rect=Rect(0, 0, 800, 600)),
                make_window(hwnd=2, title="Unrelated", rect=Rect(0, 0, 1920, 1080)),
            ],
            title_matches=lambda t: t == "Some Game",
        )

        assert result.hwnd == 1

    def test_falls_back_to_largest_window_without_title_match(self):
        result = finder(
            [make_process()],
            [
                make_window(hwnd=1, title="First", rect=Rect(0, 0, 800, 600)),
                make_window(hwnd=2, title="Second", rect=Rect(0, 0, 1920, 1080)),
            ],
            title_matches=lambda t: t == "Some Game",
        )

        assert result.hwnd == 2

    def test_picks_largest_among_multiple_title_matches(self):
        result = finder(
            [make_process()],
            [
                make_window(hwnd=1, title="Some Game", rect=Rect(0, 0, 800, 600)),
                make_window(hwnd=2, title="Some Game", rect=Rect(0, 0, 1920, 1080)),
            ],
            title_matches=lambda t: t == "Some Game",
        )

        assert result.hwnd == 2

    def test_without_title_match_largest_window_wins(self):
        result = finder(
            [make_process()],
            [
                make_window(hwnd=1, title="Small", rect=Rect(0, 0, 640, 480)),
                make_window(hwnd=2, title="Big", rect=Rect(0, 0, 2560, 1440)),
            ],
        )

        assert result.hwnd == 2
