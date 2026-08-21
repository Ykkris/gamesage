"""Machine-readable Community Content API (read-only view).

Exposes what the existing registries already know: supported games from
the unified registry, all discovered Game Definitions with statuses, and
all discovered Knowledge Packs with statuses. No second scanners or
validators — this module only serializes the existing systems.

Each call performs fresh discovery (the CLI process is one-shot anyway),
so a Refresh is just another invocation.
"""

from __future__ import annotations

from companion.games.registry import (
    available_game_ids,
    clear_discovery_cache,
    definition_statuses,
    game_origin,
    get_game,
    loaded_definitions,
)
from companion.knowledge.packs.registry import KnowledgePackRegistry


def run_community_content(*, packs_registry: KnowledgePackRegistry | None = None) -> dict:
    """Report supported games plus all discovered community content.

    Returns ``{"ok": True, "games", "game_definitions", "knowledge_packs"}``.
    Metadata fields are None when the underlying artifact could not be
    parsed far enough to know them; values are never fabricated.
    """
    # Fresh discovery through the registries' own cache invalidation.
    clear_discovery_cache()
    definitions_by_game = {
        definition.id: definition for definition in loaded_definitions()
    }

    games: list[dict[str, object]] = []
    for game_id in available_game_ids():
        adapter = get_game(game_id)
        entry: dict[str, object] = {
            "id": adapter.id,
            "display_name": adapter.display_name,
            "origin": game_origin(adapter.id),
        }
        definition = definitions_by_game.get(adapter.id)
        if definition is not None:
            entry["definition_id"] = definition.definition_id
            entry["version"] = definition.version
            entry["author"] = definition.author
        games.append(entry)

    game_definitions = [
        {
            "definition_id": status.definition_id,
            "status": status.status,
            "message": status.message,
            "game_id": status.game_id,
            "display_name": status.display_name,
            "version": status.version,
            "author": status.author,
        }
        for status in definition_statuses()
    ]

    registry = packs_registry if packs_registry is not None else KnowledgePackRegistry()
    knowledge_packs = [
        {
            "pack_id": status.pack_id,
            "status": status.status,
            "message": status.message,
            "game_id": status.game_id,
            "name": status.name,
            "version": status.version,
            "author": status.author,
            "languages": list(status.languages) if status.languages else None,
            "record_count": status.record_count,
        }
        for status in registry.statuses()
    ]

    return {
        "ok": True,
        "games": games,
        "game_definitions": game_definitions,
        "knowledge_packs": knowledge_packs,
    }
