"""Tests for Game Definition v1: schema, adapter, discovery, unified registry."""

import json

import pytest

from companion.api.analyze_json import run_analysis
from companion.api.games_json import run_games
from companion.capture.window_capture import CaptureResult
from companion.capture.window_detection import (
    GameWindow,
    ProcessInfo,
    Rect,
    WindowInfo,
)
from companion.games.base import GameAdapter
from companion.games.definitions.adapter import DeclarativeGameAdapter
from companion.games.definitions.discovery import (
    discover_definitions,
    load_definition,
)
from companion.games.definitions.schema import (
    make_title_matcher,
    parse_game_definition_file,
)
from companion.games.registry import (
    clear_discovery_cache,
    game_origin,
    get_game,
)
from companion.knowledge.packs.registry import KnowledgePackRegistry
from companion.vision.models import AnalysisResult


def write_definition(
    directory,
    game_id="kingdom_come_deliverance_3",
    display_name="Kingdom Come: Deliverance III",
    definition_id=None,
    version="1.0.0",
    schema_version=1,
    executables=None,
    window_titles=None,
    window_title_mode=None,
    platform="windows",
    extra="",
):
    if definition_id is None:
        definition_id = directory.name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        f"schema_version = {schema_version}",
        f'id = "{game_id}"',
        f'display_name = "{display_name}"',
        f'definition_id = "{definition_id}"',
        f'version = "{version}"',
        'author = "Community Author"',
        f'platform = "{platform}"',
        f"executables = {toml_list(executables if executables is not None else ['KingdomCome3.exe'])}",
        f"window_titles = {toml_list(window_titles or [display_name])}",
    ]
    if window_title_mode:
        lines.append(f'window_title_mode = "{window_title_mode}"')
    lines.append(extra)
    (directory / "game.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def toml_list(values):
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


def _clear_all_caches():
    """Reset process-wide discovery caches (games and knowledge packs)."""
    from companion.api import analyze_json

    clear_discovery_cache()
    analyze_json._default_registry.cache_clear()


def fake_process(exe, pid=300):
    return ProcessInfo(pid=pid, exe_name=exe)


def fake_window(pid=300, title="Kingdom Come: Deliverance III", hwnd=11):
    return WindowInfo(
        hwnd=hwnd, pid=pid, title=title, rect=Rect(0, 0, 1920, 1080), minimized=False
    )


class TestSchema:
    def test_valid_definition(self, tmp_path):
        write_definition(tmp_path / "community.kcd3.windows")
        result = load_definition(tmp_path / "community.kcd3.windows")
        assert result.status == "loaded"
        assert result.definition.id == "kingdom_come_deliverance_3"
        assert result.definition.definition_id == "community.kcd3.windows"

    def test_malformed_toml(self, tmp_path):
        directory = tmp_path / "author.game.windows"
        directory.mkdir()
        (directory / "game.toml").write_text("id = [unterminated\n", encoding="utf-8")
        problem = load_definition(directory)
        assert problem.status == "invalid"
        assert "invalid TOML" in problem.message

    def test_missing_game_toml(self, tmp_path):
        directory = tmp_path / "author.game.windows"
        directory.mkdir()
        problem = load_definition(directory)
        assert problem.status == "invalid"
        assert "game.toml" in problem.message

    def test_unsupported_schema_version(self, tmp_path):
        write_definition(tmp_path / "author.game.windows", schema_version=2)
        problem = load_definition(tmp_path / "author.game.windows")
        assert problem.status == "incompatible"
        assert "schema version" in problem.message

    def test_missing_required_fields(self, tmp_path):
        directory = tmp_path / "author.game.windows"
        directory.mkdir()
        (directory / "game.toml").write_text('schema_version = 1\nid = "x_y"\n', encoding="utf-8")
        problem = load_definition(directory)
        assert problem.status == "invalid"
        assert "display_name" in problem.message

    def test_invalid_definition_id(self, tmp_path):
        write_definition(tmp_path / "author.game.windows", definition_id="not-namespaced")
        problem = load_definition(tmp_path / "author.game.windows")
        assert problem.status == "invalid"
        assert "definition id" in problem.message

    def test_invalid_game_id(self, tmp_path):
        write_definition(tmp_path / "author.game.windows", game_id="Not A Game Id")
        problem = load_definition(tmp_path / "author.game.windows")
        assert problem.status == "invalid"
        assert "game id" in problem.message

    def test_executable_normalization_and_validation(self, tmp_path):
        write_definition(
            tmp_path / "author.game.windows",
            executables=["  Game.Exe  ", "Other.exe"],
        )
        result = load_definition(tmp_path / "author.game.windows")
        assert result.definition.executables == ("Game.Exe", "Other.exe")

        write_definition(tmp_path / "other.game.windows", definition_id="other.game.windows", executables=["game.bin"])
        problem = load_definition(tmp_path / "other.game.windows")
        assert problem.status == "invalid"
        assert ".exe" in problem.message

    def test_no_executables_is_invalid(self, tmp_path):
        write_definition(tmp_path / "author.game.windows", executables=[])
        problem = load_definition(tmp_path / "author.game.windows")
        assert problem.status == "invalid"
        assert "executable" in problem.message

    def test_unsupported_title_mode(self, tmp_path):
        write_definition(tmp_path / "author.game.windows", window_title_mode="regex")
        problem = load_definition(tmp_path / "author.game.windows")
        assert problem.status == "invalid"
        assert "window_title_mode" in problem.message

    def test_unsupported_platform(self, tmp_path):
        write_definition(tmp_path / "author.game.windows", platform="linux")
        problem = load_definition(tmp_path / "author.game.windows")
        assert problem.status == "invalid"
        assert "platform" in problem.message

    def test_compatibility_bounds(self, tmp_path):
        write_definition(
            tmp_path / "author.game.windows", extra='gamesage_min_version = "99.0.0"'
        )
        problem = load_definition(tmp_path / "author.game.windows")
        assert problem.status == "incompatible"
        assert "99.0.0" in problem.message

        write_definition(
            tmp_path / "other.game.windows",
            definition_id="other.game.windows",
            extra='gamesage_min_version = "0.0.1"',
        )
        assert load_definition(tmp_path / "other.game.windows").status == "loaded"


class TestTitleMatching:
    def test_exact(self):
        matcher = make_title_matcher(("Kingdom Come: Deliverance III",), "exact")
        assert matcher("kingdom come: deliverance iii")
        assert not matcher("Kingdom Come: Deliverance III — Main Menu")

    def test_starts_with(self):
        matcher = make_title_matcher(("Kingdom Come",), "starts_with")
        assert matcher("Kingdom Come: Deliverance III")
        assert not matcher("The Kingdom Come")

    def test_contains(self):
        matcher = make_title_matcher(("Deliverance",), "contains")
        assert matcher("*Untitled - Kingdom Come: Deliverance III")
        assert not matcher("Kingdom Come")

    def test_empty_never_matches(self):
        for mode in ("exact", "starts_with", "contains"):
            assert not make_title_matcher(("x",), mode)("   ")

    def test_no_regex_behavior(self):
        matcher = make_title_matcher(("a.b*c",), "contains")
        # A literal dot/asterisk must not act as regex metacharacters.
        assert not matcher("abc")
        assert matcher("za.b*cz")


class TestDeclarativeAdapter:
    def _adapter(self, tmp_path, **kwargs):
        write_definition(tmp_path / "community.game.windows", **kwargs)
        result = load_definition(tmp_path / "community.game.windows")
        return DeclarativeGameAdapter(result.definition)

    def test_protocol_conformance(self, tmp_path):
        assert isinstance(self._adapter(tmp_path), GameAdapter)

    def test_detection_with_injected_enumerators(self, tmp_path):
        adapter = self._adapter(
            tmp_path,
            executables=["Game.exe", "GameDX11.exe"],
            window_titles=["My Game"],
            window_title_mode="starts_with",
        )

        window = adapter.detect_window(
            list_processes=lambda: [
                ProcessInfo(pid=1, exe_name="explorer.exe"),
                fake_process("gamedx11.exe", pid=300),
            ],
            list_visible_windows=lambda: [
                fake_window(pid=1, title="Explorer", hwnd=99),
                fake_window(pid=300, title="My Game — Chapter 1", hwnd=11),
            ],
        )

        assert window.hwnd == 11
        assert window.exe_name == "gamedx11.exe"

    def test_pid_fallback_for_unmatched_titles(self, tmp_path):
        adapter = self._adapter(tmp_path, executables=["game.exe"], window_titles=["My Game"])

        window = adapter.detect_window(
            list_processes=lambda: [fake_process("game.exe", pid=300)],
            list_visible_windows=lambda: [fake_window(pid=300, title="")],
        )

        assert window.hwnd == 11

    def test_screenshot_naming_uses_game_id(self, tmp_path):
        adapter = self._adapter(tmp_path)

        path = adapter.save_capture(CaptureResult(png=b"png", width=4, height=2), tmp_path)

        assert path.name.startswith("kingdom_come_deliverance_3-")
        assert path.read_bytes() == b"png"


class TestDiscoveryAndRegistry:
    def test_discovers_external_definition_and_unified_lookup(self, tmp_path):
        write_definition(tmp_path / "community.kcd3.windows")

        definitions, statuses = discover_definitions([tmp_path])
        assert [d.id for d in definitions] == ["kingdom_come_deliverance_3"]
        assert statuses[0].status == "loaded"

    def test_multiple_roots(self, tmp_path):
        write_definition(tmp_path / "a" / "author.one.game1.windows", game_id="game_one")
        write_definition(tmp_path / "b" / "author.two.game2.windows", game_id="game_two")

        definitions, _ = discover_definitions([tmp_path / "a", tmp_path / "b"])
        assert {d.id for d in definitions} == {"game_one", "game_two"}

    def test_duplicate_definition_ids_conflict(self, tmp_path):
        write_definition(tmp_path / "one" / "dupe.game.windows", game_id="game_a")
        write_definition(tmp_path / "two" / "dupe.game.windows", game_id="game_b")

        definitions, statuses = discover_definitions([tmp_path / "one", tmp_path / "two"])
        assert {d.id for d in definitions} == {"game_a"}
        conflicts = [s for s in statuses if s.status == "conflict"]
        assert len(conflicts) == 1 and "duplicate definition id" in conflicts[0].message

    def test_duplicate_declarative_game_ids_conflict(self, tmp_path):
        write_definition(tmp_path / "author.one.game1.windows", game_id="game_x")
        write_definition(tmp_path / "author.two.game2.windows", game_id="game_x")

        definitions, statuses = discover_definitions([tmp_path])
        assert len(definitions) == 1
        conflicts = [s for s in statuses if s.status == "conflict"]
        assert len(conflicts) == 1 and "another definition" in conflicts[0].message

    def test_native_game_id_collision_reports_conflict(self, tmp_path):
        write_definition(tmp_path / "author.witcher3.fake", game_id="witcher3")

        definitions, statuses = discover_definitions(
            [tmp_path], reserved_game_ids=frozenset({"witcher3", "baldurs_gate_3"})
        )
        assert definitions == ()
        conflicts = [s for s in statuses if s.status == "conflict"]
        assert len(conflicts) == 1
        assert "native" in conflicts[0].message

    def test_broken_definition_does_not_break_valid_games(self, tmp_path):
        write_definition(tmp_path / "author.good.game1.windows", game_id="game_one")
        broken = tmp_path / "broken.game.windows"
        broken.mkdir()
        (broken / "game.toml").write_text("garbage = = =\n", encoding="utf-8")

        definitions, statuses = discover_definitions([tmp_path])
        assert [d.id for d in definitions] == ["game_one"]
        assert any(s.status == "invalid" and "broken.game.windows" == s.definition_id for s in statuses)

    def test_missing_roots_tolerated(self, tmp_path):
        assert discover_definitions([tmp_path / "absent"]) == ((), ())


class TestUnifiedRegistryIntegration:
    """External definitions enter the unified registry through env roots —
    no Python source registration — and caches are cleared per test."""

    @pytest.fixture(autouse=True)
    def _reset_caches(self, monkeypatch, tmp_path):
        # Neutralize the real user directories so only tmp roots are scanned.
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "absent-localappdata"))
        monkeypatch.setenv("GAMESAGE_GAME_DEFINITIONS", str(tmp_path / "games"))
        monkeypatch.setenv("GAMESAGE_KNOWLEDGE_PACKS", str(tmp_path / "packs"))
        _clear_all_caches()
        yield
        _clear_all_caches()

    def test_external_game_in_registry_and_api(self, tmp_path):
        write_definition(tmp_path / "games" / "community.kcd3.windows")

        game = get_game("kingdom_come_deliverance_3")
        assert isinstance(game, DeclarativeGameAdapter)
        assert game.display_name == "Kingdom Come: Deliverance III"
        assert "kingdom_come_deliverance_3" in [
            entry["id"] for entry in run_games()["games"]
        ]
        origins = {entry["id"]: entry["origin"] for entry in run_games()["games"]}
        assert origins["kingdom_come_deliverance_3"] == "community"
        assert origins["witcher3"] == "native"

    def test_native_games_unchanged_and_default(self):
        assert get_game() is get_game("witcher3")
        assert get_game("baldurs_gate_3").display_name == "Baldur's Gate 3"
        assert game_origin("witcher3") == "native"

    def test_capture_routes_through_declarative_adapter(self, tmp_path):
        from companion.api.capture_json import run_capture

        write_definition(tmp_path / "games" / "community.kcd3.windows")

        payload = run_capture(
            tmp_path / "shots",
            "kingdom_come_deliverance_3",
            detect=lambda: GameWindow(
                pid=300, exe_name="kingdomcome3.exe", hwnd=5,
                title="Kingdom Come: Deliverance III",
                rect=Rect(0, 0, 640, 480), minimized=False,
            ),
            capture=lambda window: CaptureResult(
                png=b"png", width=window.rect.width, height=window.rect.height
            ),
        )

        assert payload["ok"] is True
        assert payload["game_id"] == "kingdom_come_deliverance_3"
        assert "kingdom_come_deliverance_3-" in payload["screenshot_path"].replace("\\", "/")

    def test_declarative_game_without_knowledge_is_vision_only(self, tmp_path):
        write_definition(tmp_path / "games" / "community.kcd3.windows")

        class FakeProvider:
            id = "fake"

            def analyze(self, image_path, question, *, context=None, knowledge=None, session_context=None):
                return AnalysisResult("answer", "fake", "m")

        payload = run_analysis(
            "x.png", "What is this?", "kingdom_come_deliverance_3",
            provider_factory=lambda: FakeProvider(),
        )

        assert payload["ok"] is True
        assert "sources" not in payload


class TestCommunityDefinitionWithKnowledge:
    """Core acceptance test: an external Game Definition and an independent
    external Knowledge Pack associate purely through game_id, with no
    production source registration."""

    @pytest.fixture(autouse=True)
    def _install_external_content(self, monkeypatch, tmp_path):
        # Neutralize the real user directories so only tmp roots are scanned.
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "absent-localappdata"))
        monkeypatch.setenv("GAMESAGE_GAME_DEFINITIONS", str(tmp_path / "games"))
        monkeypatch.setenv("GAMESAGE_KNOWLEDGE_PACKS", str(tmp_path / "packs"))
        clear_discovery_cache()
        games_root = tmp_path / "games"
        packs_root = tmp_path / "packs"
        write_definition(
            games_root / "community.notepaddemo.windows",
            game_id="gamesage_notepad_demo",
            display_name="GameSage Notepad Demo",
            executables=["notepad.exe"],
            window_titles=["Notepad"],
            window_title_mode="contains",
        )
        pack_dir = packs_root / "community.notepaddemo.knowledge"
        pack_dir.mkdir(parents=True)
        (pack_dir / "manifest.toml").write_text(
            'schema_version = 1\n'
            'id = "community.notepaddemo.knowledge"\n'
            'game_id = "gamesage_notepad_demo"\n'
            'version = "1.0.0"\n'
            'name = "Notepad Demo Knowledge"\n'
            'author = "Community Author"\n',
            encoding="utf-8",
        )
        (pack_dir / "corpus.jsonl").write_text(
            json.dumps({
                "id": "gamesage_notepad_demo:mechanic:notepad:overview",
                "title": "Notepad mechanics",
                "text": "Notepad is a plain text editor for taking quick notes.",
            }) + "\n"
            + json.dumps({
                "id": "gamesage_notepad_demo:mechanic:shortcuts:overview",
                "title": "Notepad shortcuts",
                "text": "Notepad supports common shortcuts like control-s for saving the current text file.",
            }) + "\n",
            encoding="utf-8",
        )
        yield
        _clear_all_caches()

    def test_definition_and_pack_associate_through_game_id(self):
        game = get_game("gamesage_notepad_demo")
        assert isinstance(game, DeclarativeGameAdapter)

        chunks = KnowledgePackRegistry().chunks_for_game("gamesage_notepad_demo")
        assert [chunk.pack_id for chunk in chunks] == [
            "community.notepaddemo.knowledge",
            "community.notepaddemo.knowledge",
        ]

    def test_full_ask_pipeline_uses_associated_knowledge(self):
        from companion.knowledge.retrieval import retrieve

        chunks = KnowledgePackRegistry().chunks_for_game("gamesage_notepad_demo")
        hits = retrieve("plain text editor notes", chunks)
        assert hits and hits[0].chunk.pack_id == "community.notepaddemo.knowledge"

        class FakeProvider:
            id = "fake"

            def __init__(self):
                self.contexts = []

            def analyze(self, image_path, question, *, context=None, knowledge=None, session_context=None):
                self.contexts.append(context)
                return AnalysisResult("answer", "fake", "m")

        provider = FakeProvider()
        payload = run_analysis(
            "x.png",
            "What is this plain text editor?",
            "gamesage_notepad_demo",
            provider_factory=lambda: provider,
        )

        assert payload["ok"] is True
        assert payload["sources"] == [
            {
                "title": "Notepad mechanics",
                "source": "",
                "url": "",
            }
        ]
        assert provider.contexts[0] == "GameSage Notepad Demo"
