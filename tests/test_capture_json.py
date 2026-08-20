"""Tests for the machine-readable capture bridge (JSON envelope)."""

import json

from companion.api.__main__ import main
from companion.api.capture_json import error_code, run_capture
from companion.capture.window_capture import (
    CaptureResult,
    InvalidCaptureRegionError,
    ScreenCaptureError,
)
from companion.capture.window_detection import (
    GameNotRunningError,
    GameWindow,
    NoVisibleWindowError,
    Rect,
    WindowMinimizedError,
)


def fake_window() -> GameWindow:
    return GameWindow(
        pid=100,
        exe_name="witcher3.exe",
        hwnd=42,
        title="The Witcher 3",
        rect=Rect(0, 0, 2560, 1440),
        minimized=False,
    )


def fake_capture(window: GameWindow) -> CaptureResult:
    return CaptureResult(png=b"png-bytes", width=window.rect.width, height=window.rect.height)


class TestRunCaptureSuccess:
    def test_returns_full_success_envelope(self, tmp_path):
        payload = run_capture(
            tmp_path, detect=fake_window, capture=fake_capture
        )

        assert payload["ok"] is True
        assert payload["game_id"] == "witcher3"
        assert payload["window_title"] == "The Witcher 3"
        assert payload["width"] == 2560
        assert payload["height"] == 1440

        saved = tmp_path / payload["screenshot_path"]
        assert saved.is_absolute()
        assert saved.exists()
        assert saved.read_bytes() == b"png-bytes"

    def test_envelope_is_json_serializable(self, tmp_path):
        payload = run_capture(tmp_path, detect=fake_window, capture=fake_capture)

        assert json.loads(json.dumps(payload)) == payload


class TestRunCaptureErrors:
    def test_game_not_running(self, tmp_path):
        def not_running() -> GameWindow:
            raise GameNotRunningError("The Witcher 3: Wild Hunt does not appear to be running.")

        payload = run_capture(tmp_path, detect=not_running, capture=fake_capture)

        assert payload == {
            "ok": False,
            "error": {
                "code": "game_not_running",
                "message": "The Witcher 3: Wild Hunt does not appear to be running.",
            },
        }

    def test_no_visible_window(self, tmp_path):
        def no_window() -> GameWindow:
            raise NoVisibleWindowError("...no visible game window...")

        payload = run_capture(tmp_path, detect=no_window, capture=fake_capture)

        assert payload["error"]["code"] == "no_visible_window"

    def test_window_minimized(self, tmp_path):
        def minimized() -> GameWindow:
            raise WindowMinimizedError("...minimized...")

        payload = run_capture(tmp_path, detect=minimized, capture=fake_capture)

        assert payload["error"]["code"] == "window_minimized"

    def test_capture_failure(self, tmp_path):
        def failing_capture(window: GameWindow) -> CaptureResult:
            raise ScreenCaptureError("Capturing screen region failed.")

        payload = run_capture(
            tmp_path, detect=fake_window, capture=failing_capture
        )

        assert payload["error"]["code"] == "capture_failed"

    def test_unexpected_error_is_generic_without_stack_trace(self, tmp_path):
        def exploding_detect() -> GameWindow:
            raise ValueError("secret internal detail")

        payload = run_capture(
            tmp_path, detect=exploding_detect, capture=fake_capture
        )

        assert payload["error"]["code"] == "internal_error"
        assert "secret internal detail" not in json.dumps(payload)
        assert "unexpected error" in payload["error"]["message"]


class TestErrorCodeMapping:
    def test_invalid_region_is_capture_failed(self):
        assert error_code(InvalidCaptureRegionError("x")) == "capture_failed"

    def test_unknown_exception_is_internal_error(self):
        assert error_code(RuntimeError("x")) == "internal_error"


class TestCliMain:
    def test_prints_single_json_line_and_exits_zero(self, tmp_path, capsys):
        def fake_run(directory):
            return {"ok": True, "screenshot_path": str(directory)}

        exit_code = main(["capture", "--screenshots-dir", str(tmp_path)], run=fake_run)

        assert exit_code == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == {"ok": True, "screenshot_path": str(tmp_path)}

    def test_failure_envelope_exits_one(self, tmp_path, capsys):
        def failing_run(directory):
            return {"ok": False, "error": {"code": "game_not_running", "message": "m"}}

        exit_code = main(["capture"], run=failing_run)

        assert exit_code == 1
        assert json.loads(capsys.readouterr().out)["ok"] is False
