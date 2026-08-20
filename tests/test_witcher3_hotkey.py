"""Tests for the Witcher 3 hotkey handler and defaults (no OS hotkeys)."""

from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import GameNotRunningError, WindowMinimizedError
from companion.games.witcher3 import hotkey as witcher3_hotkey
from companion.input.hotkey import Hotkey


def fake_capture() -> CaptureResult:
    return CaptureResult(png=b"png-bytes", width=320, height=240)


class TestDefaultHotkey:
    def test_default_is_ctrl_f8(self):
        assert witcher3_hotkey.DEFAULT_HOTKEY == Hotkey(key="f8", modifiers=frozenset({"ctrl"}))


class TestHandleHotkeyPress:
    def test_saves_capture_and_reports_success(self, tmp_path, capsys):
        result = witcher3_hotkey.handle_hotkey_press(tmp_path, capture=fake_capture)

        assert result is True
        output = capsys.readouterr().out
        assert "Saved 320x240 capture" in output

        saved = list(tmp_path.glob("witcher3-*.png"))
        assert len(saved) == 1
        assert saved[0].read_bytes() == b"png-bytes"

    def test_reports_game_not_running_without_raising(self, tmp_path, capsys):
        def not_running() -> CaptureResult:
            raise GameNotRunningError("The Witcher 3: Wild Hunt does not appear to be running.")

        result = witcher3_hotkey.handle_hotkey_press(tmp_path, capture=not_running)

        assert result is False
        error = capsys.readouterr().err
        assert "Capture failed" in error
        assert "running" in error

    def test_reports_minimized_window_without_raising(self, tmp_path, capsys):
        def minimized() -> CaptureResult:
            raise WindowMinimizedError("The game window is minimized; restore it before capturing.")

        result = witcher3_hotkey.handle_hotkey_press(tmp_path, capture=minimized)

        assert result is False
        assert "minimized" in capsys.readouterr().err

    def test_repeated_presses_create_separate_files(self, tmp_path):
        assert witcher3_hotkey.handle_hotkey_press(tmp_path, capture=fake_capture)
        assert witcher3_hotkey.handle_hotkey_press(tmp_path, capture=fake_capture)

        assert len(list(tmp_path.glob("witcher3-*.png"))) == 2
