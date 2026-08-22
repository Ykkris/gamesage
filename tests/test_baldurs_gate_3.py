"""Tests for the Baldur's Gate 3 adapter (multi-game smoke test)."""

import pytest

from companion.api.analyze_json import run_analysis
from companion.api.capture_json import run_capture
from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameWindow,
    ProcessInfo,
    Rect,
    WindowInfo,
)
from companion.games.base import GameAdapter
from companion.games.baldurs_gate_3.adapter import BALDURS_GATE_3_GAME, BaldursGate3Game
from companion.games.baldurs_gate_3.detection import (
    EXECUTABLE_NAMES,
    is_game_window_title,
)
from companion.games.registry import get_game
from companion.vision.models import AnalysisResult


def bg3_process(exe: str = "bg3.exe", pid: int = 200) -> ProcessInfo:
    return ProcessInfo(pid=pid, exe_name=exe)


def bg3_window(hwnd: int = 7, pid: int = 200, title: str = "Baldur's Gate 3") -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        pid=pid,
        title=title,
        rect=Rect(0, 0, 2560, 1440),
        minimized=False,
    )


def echo_capture(window: GameWindow) -> CaptureResult:
    return CaptureResult(png=b"png", width=window.rect.width, height=window.rect.height)


class TestAdapter:
    def test_metadata(self):
        assert BALDURS_GATE_3_GAME.id == "baldurs_gate_3"
        assert BALDURS_GATE_3_GAME.display_name == "Baldur's Gate 3"

    def test_protocol_conformance(self):
        assert isinstance(BALDURS_GATE_3_GAME, GameAdapter)
        assert BaldursGate3Game().id == "baldurs_gate_3"

    def test_no_knowledge_packs_installed_for_bg3(self, tmp_path, monkeypatch):
        """BG3 with no installed packs: empty knowledge, vision-only answers."""
        from companion.knowledge.packs.registry import KnowledgePackRegistry

        # Hermetic: pin roots to empty directories so packs installed on
        # the developer's machine (e.g. a real community BG3 pack) don't
        # leak into the assertion.
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "absent-localappdata"))
        monkeypatch.setenv("GAMESAGE_KNOWLEDGE_PACKS", str(tmp_path / "empty-packs"))

        assert KnowledgePackRegistry().chunks_for_game("baldurs_gate_3") == ()

    def test_save_capture_uses_bg3_naming(self, tmp_path):
        path = BALDURS_GATE_3_GAME.save_capture(
            CaptureResult(png=b"png", width=8, height=4), tmp_path
        )

        assert path.parent == tmp_path
        assert path.name.startswith("bg3-")
        assert path.read_bytes() == b"png"


class TestDetectionRules:
    def test_executables_include_both_renderers(self):
        assert "bg3.exe" in EXECUTABLE_NAMES
        assert "bg3_dx11.exe" in EXECUTABLE_NAMES

    @pytest.mark.parametrize("exe", ["bg3.exe", "bg3_dx11.exe", "BG3.EXE"])
    def test_executable_matching(self, exe):
        window = BALDURS_GATE_3_GAME.detect_window(
            list_processes=lambda: [bg3_process(exe=exe)],
            list_visible_windows=lambda: [bg3_window()],
        )
        assert window.exe_name == exe

    def test_title_matching(self):
        assert is_game_window_title("Baldur's Gate 3")
        assert is_game_window_title("baldur's gate 3")
        assert is_game_window_title("Baldur\u2019s Gate 3")  # typographic apostrophe

    def test_title_mismatch(self):
        assert not is_game_window_title("Steam")
        assert not is_game_window_title("Baldur's Gate II")
        assert not is_game_window_title("")

    def test_window_detection_with_injected_fakes(self):
        window = BALDURS_GATE_3_GAME.detect_window(
            list_processes=lambda: [
                ProcessInfo(pid=1, exe_name="explorer.exe"),
                bg3_process(exe="bg3_dx11.exe", pid=200),
            ],
            list_visible_windows=lambda: [
                WindowInfo(
                    hwnd=99,
                    pid=1,
                    title="Explorer",
                    rect=Rect(0, 0, 100, 100),
                    minimized=False,
                ),
                bg3_window(hwnd=7, pid=200),
            ],
        )

        assert window.hwnd == 7
        assert window.pid == 200
        assert window.exe_name == "bg3_dx11.exe"
        assert window.rect == Rect(0, 0, 2560, 1440)

    def test_untitled_bg3_window_still_matches_by_process(self):
        window = BALDURS_GATE_3_GAME.detect_window(
            list_processes=lambda: [bg3_process()],
            list_visible_windows=lambda: [bg3_window(title="")],
        )
        assert window.hwnd == 7


class TestRegistryAndApi:
    def test_registry_lists_both_games(self):
        assert get_game("baldurs_gate_3") is BALDURS_GATE_3_GAME
        assert get_game("witcher3") is get_game()

    def test_explicit_bg3_capture_routing(self, tmp_path):
        payload = run_capture(
            tmp_path,
            "baldurs_gate_3",
            detect=lambda: GameWindow(
                pid=200,
                exe_name="bg3.exe",
                hwnd=7,
                title="Baldur's Gate 3",
                rect=Rect(0, 0, 800, 600),
                minimized=False,
            ),
            capture=echo_capture,
        )

        assert payload["ok"] is True
        assert payload["game_id"] == "baldurs_gate_3"
        assert payload["screenshot_path"].startswith(str(tmp_path))
        assert "/bg3-" in payload["screenshot_path"].replace("\\", "/")


class FakeProvider:
    id = "fake"

    def __init__(self):
        self.calls = []

    def analyze(self, image_path, question, *, context=None, knowledge=None, session_context=None):
        self.calls.append((question, context, knowledge))
        return AnalysisResult("scene", "fake", "m")


class TestBg3Analysis:
    def test_analysis_routes_to_bg3_adapter(self):
        provider = FakeProvider()

        payload = run_analysis(
            "x.png",
            "What is happening on this screen?",
            "baldurs_gate_3",
            provider_factory=lambda: provider,
        )

        assert payload["ok"] is True
        extraction_call, answer_call = provider.calls
        assert extraction_call[1] == "Baldur's Gate 3"
        assert answer_call[1] == "Baldur's Gate 3"

    def test_empty_corpus_produces_vision_only_answer_without_sources(self):
        provider = FakeProvider()

        payload = run_analysis(
            "x.png",
            "What is happening on this screen?",
            "baldurs_gate_3",
            provider_factory=lambda: provider,
        )

        assert payload == {
            "ok": True,
            "answer": "scene",
            "provider": "fake",
            "model": "m",
        }
        assert "sources" not in payload
        # No knowledge passages were sent to the provider.
        assert all(call[2] is None for call in provider.calls)

    def test_capture_game_id_governs_analysis_adapter(self):
        """Screenshot ownership: analysis uses the capture's game id, so a
        BG3 capture is analyzed with BG3 metadata even while Witcher 3 is
        the default/selected game."""
        provider = FakeProvider()
        capture_payload = run_capture(
            None, "baldurs_gate_3", detect=lambda: GameWindow(
                pid=1, exe_name="bg3.exe", hwnd=1, title="Baldur's Gate 3",
                rect=Rect(0, 0, 4, 4), minimized=False,
            ), capture=lambda w: CaptureResult(png=b"p", width=4, height=4),
        )

        assert capture_payload["game_id"] == "baldurs_gate_3"

        run_analysis(
            "x.png",
            "What is this?",
            capture_payload["game_id"],  # the UI passes exactly this
            provider_factory=lambda: provider,
        )

        assert provider.calls[0][1] == "Baldur's Gate 3"
        assert get_game() is not BALDURS_GATE_3_GAME  # default stayed Witcher 3
