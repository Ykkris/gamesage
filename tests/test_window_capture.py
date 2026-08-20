"""Tests for the generic window capture logic (no real screen needed)."""

import pytest

from companion.capture.window_capture import (
    CaptureResult,
    InvalidCaptureRegionError,
    capture_window,
)
from companion.capture.window_detection import GameWindow, Rect, WindowMinimizedError


def make_window(rect: Rect | None = None, minimized: bool = False) -> GameWindow:
    return GameWindow(
        pid=100,
        exe_name="game.exe",
        hwnd=42,
        title="Some Game",
        rect=rect or Rect(0, 0, 1920, 1080),
        minimized=minimized,
    )


def echo_grab(rect: Rect) -> CaptureResult:
    return CaptureResult(png=b"fake-png", width=rect.width, height=rect.height)


class TestCaptureWindow:
    def test_returns_result_matching_the_window_region(self):
        result = capture_window(make_window(), grab=echo_grab)

        assert result.png == b"fake-png"
        assert result.width == 1920
        assert result.height == 1080

    def test_raises_when_window_is_minimized(self):
        with pytest.raises(WindowMinimizedError) as excinfo:
            capture_window(make_window(minimized=True), grab=echo_grab)

        assert "minimized" in str(excinfo.value)

    def test_raises_when_window_minimized_after_detection(self):
        with pytest.raises(WindowMinimizedError) as excinfo:
            capture_window(
                make_window(),
                grab=echo_grab,
                is_minimized=lambda hwnd: True,
            )

        assert "minimized after detection" in str(excinfo.value)

    def test_captures_when_live_check_says_not_minimized(self):
        checked = []

        result = capture_window(
            make_window(),
            grab=echo_grab,
            is_minimized=lambda hwnd: checked.append(hwnd) or False,
        )

        assert checked == [42]
        assert result.width == 1920

    def test_raises_when_region_has_no_width(self):
        with pytest.raises(InvalidCaptureRegionError) as excinfo:
            capture_window(make_window(rect=Rect(10, 10, 10, 100)), grab=echo_grab)

        assert "no visible area" in str(excinfo.value)

    def test_raises_when_region_has_no_height(self):
        with pytest.raises(InvalidCaptureRegionError):
            capture_window(make_window(rect=Rect(10, 10, 100, 10)), grab=echo_grab)


class TestCaptureResult:
    def test_save_writes_png_bytes_and_returns_path(self, tmp_path):
        result = CaptureResult(png=b"png-data", width=4, height=2)
        target = tmp_path / "shot.png"

        saved = result.save(target)

        assert saved == target
        assert target.read_bytes() == b"png-data"
