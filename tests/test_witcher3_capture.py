"""Tests for the Witcher 3 detect-and-capture pipeline (no game needed)."""

import pytest

from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameNotRunningError,
    ProcessInfo,
    Rect,
    WindowInfo,
    WindowMinimizedError,
)
from companion.games.witcher3 import capture as witcher3_capture


def witcher3_process(pid: int = 100) -> ProcessInfo:
    return ProcessInfo(pid=pid, exe_name="witcher3.exe")


def witcher3_window(hwnd: int = 42) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        pid=100,
        title="The Witcher 3: Wild Hunt",
        rect=Rect(0, 0, 2560, 1440),
        minimized=False,
    )


def echo_grab(rect: Rect) -> CaptureResult:
    return CaptureResult(png=b"witcher-png", width=rect.width, height=rect.height)


class TestCaptureGameWindow:
    def test_detects_then_captures_the_game_window(self):
        result = witcher3_capture.capture_game_window(
            list_processes=lambda: [witcher3_process()],
            list_visible_windows=lambda: [witcher3_window()],
            grab=echo_grab,
            is_minimized=lambda hwnd: False,
        )

        assert result.png == b"witcher-png"
        assert result.width == 2560
        assert result.height == 1440

    def test_raises_when_game_not_running(self):
        with pytest.raises(GameNotRunningError):
            witcher3_capture.capture_game_window(
                list_processes=lambda: [],
                list_visible_windows=lambda: [],
                grab=echo_grab,
            )

    def test_raises_when_window_minimized(self):
        minimized_window = WindowInfo(
            hwnd=42,
            pid=100,
            title="The Witcher 3: Wild Hunt",
            rect=Rect(-32000, -32000, -30000, -30800),
            minimized=True,
        )

        with pytest.raises(WindowMinimizedError):
            witcher3_capture.capture_game_window(
                list_processes=lambda: [witcher3_process()],
                list_visible_windows=lambda: [minimized_window],
                grab=echo_grab,
            )
