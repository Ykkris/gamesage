"""Machine-readable JSON interface for the game registry.

The registry (``companion/games/registry.py``) is the single source of
truth; this module only serializes it.
"""

from __future__ import annotations

from companion.games.registry import DEFAULT_GAME_ID, available_game_ids, get_game


def run_games() -> dict:
    """List registered games with the default game id.

    Returns ``{"ok": True, "games": [{"id", "display_name"}], "default_game"}``.
    """
    games = [get_game(game_id) for game_id in available_game_ids()]
    return {
        "ok": True,
        "games": [{"id": game.id, "display_name": game.display_name} for game in games],
        "default_game": DEFAULT_GAME_ID,
    }
