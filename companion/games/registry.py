"""Unified game registry: native GameAdapters plus declarative games.

Native adapters (maintained in GameSage code) and community Game
Definitions (data-only, discovered from search roots) are exposed through
one API: :func:`get_game` and :func:`available_game_ids`. Consumers never
need to know whether a game is native or declarative.

Native adapters always take precedence over a definition claiming the same
game id. No plugin discovery of Python code — definitions are declarative
data interpreted by trusted GameSage code.
"""

from __future__ import annotations

from functools import lru_cache

from companion.games.base import GameAdapter
from companion.games.baldurs_gate_3.adapter import BALDURS_GATE_3_GAME
from companion.games.definitions.adapter import DeclarativeGameAdapter
from companion.games.definitions.discovery import (
    DefinitionStatus,
    default_definition_roots,
    discover_definitions,
)
from companion.games.definitions.schema import GameDefinition
from companion.games.witcher3.adapter import WITCHER3_GAME

#: Game used when no explicit id is supplied (v0.1 default).
DEFAULT_GAME_ID = WITCHER3_GAME.id

#: Trusted adapters maintained in GameSage source code.
_NATIVE_GAMES: dict[str, GameAdapter] = {
    WITCHER3_GAME.id: WITCHER3_GAME,
    BALDURS_GATE_3_GAME.id: BALDURS_GATE_3_GAME,
}

ORIGIN_NATIVE = "native"
ORIGIN_COMMUNITY = "community"


class UnknownGameError(ValueError):
    """No adapter is registered for the requested game id."""


@lru_cache(maxsize=1)
def _declarative() -> tuple[tuple[DeclarativeGameAdapter, ...], tuple[DefinitionStatus, ...]]:
    """Discovery runs once per process; tests clear the cache explicitly."""
    definitions, statuses = discover_definitions(
        default_definition_roots(), reserved_game_ids=frozenset(_NATIVE_GAMES)
    )
    adapters = tuple(DeclarativeGameAdapter(definition) for definition in definitions)
    return adapters, statuses


def clear_discovery_cache() -> None:
    """Force re-discovery of Game Definitions on next registry use."""
    _declarative.cache_clear()


def available_game_ids() -> list[str]:
    """Sorted ids of all supported games (native and declarative)."""
    ids = set(_NATIVE_GAMES) | {adapter.id for adapter in _declarative()[0]}
    return sorted(ids)


def get_game(game_id: str | None = None) -> GameAdapter:
    """Resolve a game adapter by id (case-insensitive).

    ``None`` or an empty id selects the default game. Native adapters take
    precedence over declarative definitions with the same id.

    Raises:
        UnknownGameError: the id is not registered.
    """
    resolved = (game_id or DEFAULT_GAME_ID).strip().lower()
    native = _NATIVE_GAMES.get(resolved)
    if native is not None:
        return native
    for adapter in _declarative()[0]:
        if adapter.id == resolved:
            return adapter
    raise UnknownGameError(
        f"Unknown game id {resolved!r}. Available games: "
        f"{', '.join(available_game_ids())}."
    ) from None


def game_origin(game_id: str | None = None) -> str:
    """Whether a game comes from a native adapter or a community definition."""
    resolved = (game_id or DEFAULT_GAME_ID).strip().lower()
    if resolved in _NATIVE_GAMES:
        return ORIGIN_NATIVE
    return ORIGIN_COMMUNITY


def definition_statuses() -> tuple[DefinitionStatus, ...]:
    """Structured reports for all discovered Game Definitions."""
    return _declarative()[1]


def loaded_definitions() -> tuple["GameDefinition", ...]:
    """Validated definitions backing the active community games."""
    return tuple(adapter.definition for adapter in _declarative()[0])
