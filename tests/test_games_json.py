"""Tests for the supported-games machine-readable API."""

import json

from companion.api.__main__ import main
from companion.api.games_json import run_games
from companion.games.registry import available_game_ids, get_game


class TestRunGames:
    def test_envelope_shape(self):
        payload = run_games()

        assert payload == {
            "ok": True,
            "games": [{"id": "witcher3", "display_name": "The Witcher 3: Wild Hunt"}],
            "default_game": "witcher3",
        }

    def test_registry_is_the_single_source(self):
        payload = run_games()

        listed_ids = [game["id"] for game in payload["games"]]
        assert listed_ids == available_game_ids()
        for entry in payload["games"]:
            adapter = get_game(entry["id"])
            assert entry["display_name"] == adapter.display_name

    def test_default_game_is_listed_with_metadata(self):
        payload = run_games()

        default_entry = next(
            game for game in payload["games"] if game["id"] == payload["default_game"]
        )
        assert default_entry["display_name"] == get_game().display_name

    def test_envelope_is_json_serializable(self):
        assert json.loads(json.dumps(run_games())) == run_games()


class TestGamesCli:
    def test_prints_json_and_exits_zero(self, capsys):
        exit_code = main(["games"])

        assert exit_code == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["ok"] is True
        assert payload["default_game"] == "witcher3"
