"""Explicit registry of supported game adapters.

No dynamic discovery: adapters are registered here by import. Resolving an
unknown id fails clearly; omitting the id yields the v0.1 default game.
"""

from __future__ import annotations

from companion.games.base import GameAdapter
from companion.games.witcher3.adapter import WITCHER3_GAME

#: Game used when no explicit id is supplied (v0.1 single-game default).
DEFAULT_GAME_ID = WITCHER3_GAME.id

_GAMES: dict[str, GameAdapter] = {WITCHER3_GAME.id: WITCHER3_GAME}


class UnknownGameError(ValueError):
    """No adapter is registered for the requested game id."""


def available_game_ids() -> list[str]:
    """Sorted ids of all registered games."""
    return sorted(_GAMES)


def get_game(game_id: str | None = None) -> GameAdapter:
    """Resolve a game adapter by id (case-insensitive).

    ``None`` or an empty id selects the default game.

    Raises:
        UnknownGameError: the id is not registered.
    """
    resolved = (game_id or DEFAULT_GAME_ID).strip().lower()
    try:
        return _GAMES[resolved]
    except KeyError:
        available = ", ".join(available_game_ids())
        raise UnknownGameError(
            f"Unknown game id {resolved!r}. Available games: {available}."
        ) from None
