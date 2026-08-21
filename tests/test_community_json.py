"""Tests for the read-only Community Content API."""

import json

import pytest

from companion.api.__main__ import main
from companion.api.community_json import run_community_content
from companion.games.registry import clear_discovery_cache

from test_game_definitions import write_definition
from test_knowledge_packs import write_pack


@pytest.fixture(autouse=True)
def isolated_roots(monkeypatch, tmp_path):
    """External roots in tmp; the developer's LocalAppData is never read."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "absent-localappdata"))
    monkeypatch.setenv("GAMESAGE_GAME_DEFINITIONS", str(tmp_path / "games"))
    monkeypatch.setenv("GAMESAGE_KNOWLEDGE_PACKS", str(tmp_path / "packs"))
    clear_discovery_cache()
    yield
    clear_discovery_cache()


def entry_by_id(entries, key, value):
    return next(entry for entry in entries if entry[key] == value)


class TestGames:
    def test_native_games_with_origin(self):
        payload = run_community_content()

        witcher = entry_by_id(payload["games"], "id", "witcher3")
        bg3 = entry_by_id(payload["games"], "id", "baldurs_gate_3")
        assert witcher == {
            "id": "witcher3",
            "display_name": "The Witcher 3: Wild Hunt",
            "origin": "native",
        }
        assert bg3["origin"] == "native"

    def test_community_game_includes_definition_metadata(self, tmp_path):
        write_definition(
            tmp_path / "games" / "author.demo.windows",
            game_id="demo_game",
            display_name="Demo Game",
        )

        payload = run_community_content()

        game = entry_by_id(payload["games"], "id", "demo_game")
        assert game["origin"] == "community"
        assert game["definition_id"] == "author.demo.windows"
        assert game["version"] == "1.0.0"
        assert game["author"] == "Community Author"


class TestGameDefinitions:
    def test_loaded_definition(self, tmp_path):
        write_definition(tmp_path / "games" / "author.demo.windows", game_id="demo_game")

        entry = entry_by_id(
            run_community_content()["game_definitions"], "definition_id", "author.demo.windows"
        )

        assert entry["status"] == "loaded"
        assert entry["game_id"] == "demo_game"
        assert entry["display_name"] == "Kingdom Come: Deliverance III"
        assert entry["version"] == "1.0.0"
        assert entry["author"] == "Community Author"

    def test_invalid_definition_reports_diagnostic_and_null_metadata(self, tmp_path):
        broken = tmp_path / "games" / "broken.dir"
        broken.mkdir(parents=True)
        (broken / "game.toml").write_text("id = [unterminated\n", encoding="utf-8")

        entry = entry_by_id(
            run_community_content()["game_definitions"], "definition_id", "broken.dir"
        )

        assert entry["status"] == "invalid"
        assert "invalid TOML" in entry["message"]
        assert entry["game_id"] is None
        assert entry["display_name"] is None
        assert entry["version"] is None
        assert entry["author"] is None

    def test_incompatible_definition_keeps_identity(self, tmp_path):
        write_definition(
            tmp_path / "games" / "author.future.windows",
            game_id="future_game",
            extra='gamesage_min_version = "99.0.0"',
        )

        entry = entry_by_id(
            run_community_content()["game_definitions"],
            "definition_id",
            "author.future.windows",
        )

        assert entry["status"] == "incompatible"
        assert "99.0.0" in entry["message"]
        assert entry["game_id"] == "future_game"  # identity preserved

    def test_conflicting_definition_with_native_game(self, tmp_path):
        write_definition(tmp_path / "games" / "author.witcher3.fake", game_id="witcher3")

        entry = entry_by_id(
            run_community_content()["game_definitions"],
            "definition_id",
            "author.witcher3.fake",
        )

        assert entry["status"] == "conflict"
        assert "native" in entry["message"]
        # Native game unaffected.
        games = {game["id"]: game for game in run_community_content()["games"]}
        assert games["witcher3"]["origin"] == "native"


class TestKnowledgePacks:
    def test_loaded_pack_with_metadata_and_record_count(self, tmp_path):
        write_pack(
            tmp_path / "packs" / "author.witcher3.extra",
            pack_id="author.witcher3.extra",
            manifest_extra='languages = ["en", "fr"]\n',
            records=[
                {"id": "witcher3:mechanic:a:overview", "title": "A", "text": "alpha beta"},
                {"id": "witcher3:mechanic:b:overview", "title": "B", "text": "gamma delta"},
            ],
        )

        entry = entry_by_id(
            run_community_content()["knowledge_packs"], "pack_id", "author.witcher3.extra"
        )

        assert entry["status"] == "loaded"
        assert entry["game_id"] == "witcher3"
        assert entry["name"] == "Test Pack"
        assert entry["version"] == "1.0.0"
        assert entry["author"] == "Some Author"
        assert entry["languages"] == ["en", "fr"]
        assert entry["record_count"] == 2

    def test_invalid_pack_reports_diagnostic_and_keeps_known_metadata(self, tmp_path):
        write_pack(tmp_path / "packs" / "broken.pack")
        (tmp_path / "packs" / "broken.pack" / "corpus.jsonl").write_text(
            '{"id": "witcher3:x:a", "title": "t", "text": "ok"}\nnot json\n',
            encoding="utf-8",
        )

        entry = entry_by_id(
            run_community_content()["knowledge_packs"], "pack_id", "broken.pack"
        )

        assert entry["status"] == "invalid"
        assert "line 2" in entry["message"]
        assert entry["name"] == "Test Pack"  # manifest parsed; identity kept
        assert entry["record_count"] is None

    def test_incompatible_pack(self, tmp_path):
        write_pack(
            tmp_path / "packs" / "author.future.pack",
            pack_id="author.future.pack",
            schema_version=2,
        )

        entry = entry_by_id(
            run_community_content()["knowledge_packs"], "pack_id", "author.future.pack"
        )

        assert entry["status"] == "incompatible"
        assert "schema version" in entry["message"]

    def test_conflicting_pack(self, tmp_path, monkeypatch):
        write_pack(tmp_path / "packs-a" / "dupe.pack")
        write_pack(tmp_path / "packs-b" / "dupe.pack", pack_id="dupe.pack")
        import os

        monkeypatch.setenv(
            "GAMESAGE_KNOWLEDGE_PACKS",
            os.pathsep.join([str(tmp_path / "packs-a"), str(tmp_path / "packs-b")]),
        )

        payload = run_community_content()

        conflicts = [
            entry
            for entry in payload["knowledge_packs"]
            if entry["status"] == "conflict"
        ]
        assert len(conflicts) == 1
        assert "duplicate pack id" in conflicts[0]["message"]

    def test_pack_for_unknown_game_is_still_reported(self, tmp_path):
        write_pack(
            tmp_path / "packs" / "author.mystery.pack",
            pack_id="author.mystery.pack",
            game_id="not_installed_game",
        )

        entry = entry_by_id(
            run_community_content()["knowledge_packs"], "pack_id", "author.mystery.pack"
        )

        assert entry["status"] == "loaded"
        assert entry["game_id"] == "not_installed_game"
        game_ids = {game["id"] for game in run_community_content()["games"]}
        assert "not_installed_game" not in game_ids


class TestFaultIsolationAndRefresh:
    def test_invalid_content_does_not_suppress_valid_content(self, tmp_path):
        write_definition(tmp_path / "games" / "author.good.windows", game_id="good_game")
        broken = tmp_path / "games" / "broken.dir"
        broken.mkdir()
        (broken / "game.toml").write_text("garbage\n", encoding="utf-8")
        write_pack(tmp_path / "packs" / "author.good.pack")

        payload = run_community_content()

        assert any(g["id"] == "good_game" for g in payload["games"])
        assert any(
            d["status"] == "invalid" for d in payload["game_definitions"]
        )
        assert any(p["status"] == "loaded" for p in payload["knowledge_packs"])

    def test_refresh_rediscovers_changes_in_process(self, tmp_path):
        games_root = tmp_path / "games"
        write_definition(games_root / "author.demo.windows", game_id="demo_game")

        first = run_community_content()
        assert any(g["id"] == "demo_game" for g in first["games"])

        # Simulate the user removing the definition, then refreshing.
        import shutil

        shutil.rmtree(games_root / "author.demo.windows")
        second = run_community_content()
        assert not any(g["id"] == "demo_game" for g in second["games"])

        # And reinstalling it.
        write_definition(games_root / "author.demo.windows", game_id="demo_game")
        third = run_community_content()
        assert any(g["id"] == "demo_game" for g in third["games"])


class TestEnvelopeAndCli:
    def test_envelope_shape_and_serializability(self):
        payload = run_community_content()

        assert set(payload) == {"ok", "games", "game_definitions", "knowledge_packs"}
        assert payload["ok"] is True
        assert json.loads(json.dumps(payload)) == payload

    def test_starter_pack_present_without_external_roots(self, tmp_path):
        # The built-in starter pack lives in the repository pack root, which
        # is always scanned — no developer LocalAppData needed.
        payload = run_community_content()

        entry = entry_by_id(
            payload["knowledge_packs"], "pack_id", "gamesage.witcher3.starter"
        )
        assert entry["status"] == "loaded"
        assert entry["record_count"] == 5

    def test_cli_prints_json_and_exits_zero(self, capsys):
        exit_code = main(["community-content"])

        assert exit_code == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["ok"] is True
