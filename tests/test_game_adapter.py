"""Tests for the generic GameAdapter architecture and registry."""

import pytest

from companion.api.analyze_json import run_analysis
from companion.api.capture_json import run_capture
from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameNotRunningError,
    GameWindow,
    ProcessInfo,
    Rect,
    WindowInfo,
)
from companion.games.base import GameAdapter
from companion.games.registry import (
    UnknownGameError,
    available_game_ids,
    get_game,
)
from companion.games.witcher3.adapter import WITCHER3_GAME, Witcher3Game
from companion.vision.models import AnalysisResult


def witcher3_process() -> ProcessInfo:
    return ProcessInfo(pid=100, exe_name="witcher3.exe")


def witcher3_window() -> WindowInfo:
    return WindowInfo(
        hwnd=42,
        pid=100,
        title="The Witcher 3",
        rect=Rect(0, 0, 1920, 1080),
        minimized=False,
    )


class TestWitcher3Adapter:
    def test_metadata(self):
        assert WITCHER3_GAME.id == "witcher3"
        assert WITCHER3_GAME.display_name == "The Witcher 3: Wild Hunt"

    def test_implements_game_adapter_protocol(self):
        assert isinstance(WITCHER3_GAME, GameAdapter)

    def test_detect_window_composes_detection_rules(self):
        window = WITCHER3_GAME.detect_window(
            list_processes=lambda: [witcher3_process()],
            list_visible_windows=lambda: [witcher3_window()],
        )

        assert isinstance(window, GameWindow)
        assert window.hwnd == 42
        assert window.exe_name == "witcher3.exe"

    def test_save_capture_uses_game_naming(self, tmp_path):
        result = CaptureResult(png=b"png", width=10, height=5)

        path = WITCHER3_GAME.save_capture(result, tmp_path)

        assert path.parent == tmp_path
        assert path.name.startswith("witcher3-")
        assert path.read_bytes() == b"png"

    def test_load_knowledge_corpus_returns_witcher3_chunks(self):
        chunks = WITCHER3_GAME.load_knowledge_corpus()

        assert chunks
        assert all(chunk.id.startswith("witcher3-") for chunk in chunks)

    def test_fresh_instance_behaves_identically(self):
        assert Witcher3Game().id == WITCHER3_GAME.id


class TestRegistry:
    def test_get_game_by_id(self):
        assert get_game("witcher3") is WITCHER3_GAME

    def test_default_game_is_witcher3(self):
        assert get_game() is WITCHER3_GAME
        assert get_game("") is WITCHER3_GAME
        assert get_game(None) is WITCHER3_GAME

    def test_id_is_normalized(self):
        assert get_game("  WITCHER3  ") is WITCHER3_GAME

    def test_unknown_game_id_fails_clearly(self):
        with pytest.raises(UnknownGameError) as excinfo:
            get_game("baldursgate3")
        assert "'baldursgate3'" in str(excinfo.value)
        assert "witcher3" in str(excinfo.value)

    def test_available_game_ids(self):
        assert available_game_ids() == ["baldurs_gate_3", "witcher3"]


class TestCaptureThroughAdapter:
    def test_run_capture_with_explicit_game(self, tmp_path):
        payload = run_capture(
            tmp_path,
            game_id="witcher3",
            detect=lambda: GameWindow(
                pid=100,
                exe_name="witcher3.exe",
                hwnd=42,
                title="The Witcher 3",
                rect=Rect(0, 0, 800, 600),
                minimized=False,
            ),
            capture=lambda window: CaptureResult(
                png=b"png", width=window.rect.width, height=window.rect.height
            ),
        )

        assert payload["ok"] is True
        assert payload["game_id"] == "witcher3"
        assert payload["screenshot_path"].startswith(str(tmp_path))

    def test_run_capture_unknown_game_returns_error_envelope(self, tmp_path):
        payload = run_capture(tmp_path, game_id="halo")

        assert payload["ok"] is False
        assert payload["error"]["code"] == "unknown_game"
        assert "halo" in payload["error"]["message"]

    def test_run_capture_defaults_to_witcher3(self, tmp_path):
        payload = run_capture(
            tmp_path,
            detect=lambda: GameWindow(
                pid=1,
                exe_name="witcher3.exe",
                hwnd=1,
                title="The Witcher 3",
                rect=Rect(0, 0, 4, 4),
                minimized=False,
            ),
        )

        assert payload["game_id"] == "witcher3"

    def test_run_capture_default_detection_uses_adapter_rules(self, tmp_path, monkeypatch):
        # No injected detect: the adapter's real detection runs; with the game
        # window absent this must produce the standard not-running envelope.
        payload = run_capture(tmp_path)

        assert payload["ok"] is False
        assert payload["error"]["code"] in ("game_not_running", "no_visible_window")


class TestAnalysisReceivesGameMetadata:
    def test_provider_context_is_adapter_display_name(self):
        from companion.api.analyze_json import CONTEXT_EXTRACTION_QUESTION

        contexts = []

        class RecordingProvider:
            id = "fake"

            def analyze(self, image_path, question, *, context=None, knowledge=None):
                contexts.append(context)
                return AnalysisResult("scene", "fake", "m")

        run_analysis(
            "x.png",
            "What is this?",
            provider_factory=lambda: RecordingProvider(),
            knowledge_retriever=lambda query: [],
        )

        # Both stages (context extraction and grounded answer) receive it.
        assert contexts == ["The Witcher 3: Wild Hunt", "The Witcher 3: Wild Hunt"]

    def test_unknown_game_returns_error_envelope(self):
        payload = run_analysis(
            "x.png",
            "q",
            game_id="starfield",
            knowledge_retriever=lambda query: [],
        )

        assert payload["ok"] is False
        assert payload["error"]["code"] == "unknown_game"
