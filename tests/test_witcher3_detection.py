"""Tests for The Witcher 3 detection rules (no game required)."""

import pytest

from companion.capture.window_detection import GameNotRunningError, ProcessInfo, Rect, WindowInfo
from companion.games.witcher3 import detection


class TestWitcher3Rules:
    def test_executable_names_include_known_binary(self):
        assert "witcher3.exe" in detection.EXECUTABLE_NAMES

    def test_accepts_main_window_title(self):
        assert detection.is_game_window_title("The Witcher 3: Wild Hunt")

    def test_title_match_is_case_and_whitespace_insensitive(self):
        assert detection.is_game_window_title("  the witcher 3  ")

    def test_rejects_other_titles(self):
        assert not detection.is_game_window_title("The Witcher 2")
        assert not detection.is_game_window_title("Steam")
        assert not detection.is_game_window_title("")


def witcher3_process(pid: int = 100) -> ProcessInfo:
    return ProcessInfo(pid=pid, exe_name="witcher3.exe")


def witcher3_window(hwnd: int = 1, **kwargs) -> WindowInfo:
    defaults = dict(
        pid=100,
        title="The Witcher 3: Wild Hunt",
        rect=Rect(0, 0, 1920, 1080),
        minimized=False,
    )
    defaults.update(kwargs)
    return WindowInfo(hwnd=hwnd, **defaults)


class TestDetectWindow:
    def test_returns_game_window_for_running_game(self):
        result = detection.detect_window(
            list_processes=lambda: [witcher3_process()],
            list_visible_windows=lambda: [witcher3_window(hwnd=42)],
        )

        assert result.hwnd == 42
        assert result.exe_name == "witcher3.exe"
        assert result.title == "The Witcher 3: Wild Hunt"
        assert result.rect == Rect(0, 0, 1920, 1080)

    def test_matches_real_executable_case_from_os(self):
        result = detection.detect_window(
            list_processes=lambda: [ProcessInfo(pid=100, exe_name="Witcher3.EXE")],
            list_visible_windows=lambda: [witcher3_window()],
        )

        assert result.pid == 100

    def test_raises_when_game_not_running(self):
        with pytest.raises(GameNotRunningError) as excinfo:
            detection.detect_window(
                list_processes=lambda: [ProcessInfo(pid=1, exe_name="explorer.exe")],
                list_visible_windows=lambda: [],
            )

        assert "Witcher 3" in str(excinfo.value)
