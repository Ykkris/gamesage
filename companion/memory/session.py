"""Session Context v0 — runtime-only conversational context.

Holds the most recent successful interactions of the current GameSage
runtime, isolated per game_id, for prompt continuity ("what does 'her'
refer to?"). This is deliberately NOT long-term memory:

- nothing here is ever persisted to disk;
- restarting GameSage starts with empty session context;
- only bounded recent turns are kept;
- persistent memory is a future, separate milestone.

The desktop runtime owns the ephemeral turn list and transports it
explicitly to each one-shot Python analysis; this module is the trusted
side that validates, filters, bounds, and formats it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: Recent successful interactions kept per game (newest win).
MAX_TURNS = 4

#: Per-field character cap for question/answer values.
MAX_FIELD_CHARS = 1500

#: Total character budget for the formatted context block.
MAX_CONTEXT_CHARS = 4000


class SessionContextError(ValueError):
    """Supplied session context is malformed."""


@dataclass(frozen=True)
class SessionInteraction:
    """One successful question/answer turn for a game."""

    game_id: str
    question: str
    answer: str


def parse_session_context(raw: object) -> list[SessionInteraction]:
    """Validate raw (JSON-decoded) context data into interactions.

    Raises:
        SessionContextError: the payload is not a list of interaction
            objects with non-empty string fields.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SessionContextError("session context must be a JSON list of interactions.")
    interactions: list[SessionInteraction] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SessionContextError(
                f"session context entry {index} must be a JSON object."
            )
        fields = {}
        for name in ("game_id", "question", "answer"):
            value = entry.get(name)
            if not isinstance(value, str) or not value.strip():
                raise SessionContextError(
                    f"session context entry {index} needs a non-empty string {name!r}."
                )
            fields[name] = value.strip()
        interactions.append(SessionInteraction(**fields))
    return interactions


def filter_for_game(
    interactions: Iterable[SessionInteraction], game_id: str
) -> list[SessionInteraction]:
    """Drop interactions belonging to any other game (hard isolation).

    The analysis target's game_id is authoritative; cross-game entries
    never reach a prompt.
    """
    return [
        interaction
        for interaction in interactions
        if interaction.game_id == game_id
    ]


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def bound_interactions(
    interactions: Sequence[SessionInteraction],
    *,
    max_turns: int = MAX_TURNS,
    max_field_chars: int = MAX_FIELD_CHARS,
    max_context_chars: int = MAX_CONTEXT_CHARS,
) -> list[SessionInteraction]:
    """Deterministically bound context: newest turns win.

    Keeps the last ``max_turns`` interactions (chronological order),
    truncates over-long fields, then drops oldest turns until the sum of
    question+answer characters fits ``max_context_chars``.
    """
    bounded = [
        SessionInteraction(
            game_id=interaction.game_id,
            question=_truncate(interaction.question, max_field_chars),
            answer=_truncate(interaction.answer, max_field_chars),
        )
        for interaction in interactions[-max_turns:]
    ]
    while bounded and sum(
        len(item.question) + len(item.answer) for item in bounded
    ) > max_context_chars:
        bounded.pop(0)
    return bounded


def format_session_context(
    interactions: Sequence[SessionInteraction],
) -> str | None:
    """Render the labeled turn block, or None when there is no context.

    The block lists prior player questions and GameSage answers; the
    authority wording (prior model output, current screenshot
    authoritative, knowledge packs as grounding) lives with the provider
    prompt constants so it is never omitted.
    """
    if not interactions:
        return None
    lines = ["Recent session turns (chronological):"]
    for index, interaction in enumerate(interactions, start=1):
        lines.append(f"[{index}] player: {interaction.question}")
        lines.append(f"[{index}] GameSage: {interaction.answer}")
    return "\n".join(lines)


def prepare_session_context(raw: object, game_id: str) -> str | None:
    """Full pipeline: parse, filter to ``game_id``, bound, and format.

    Raises:
        SessionContextError: the payload is malformed.
    """
    interactions = bound_interactions(
        filter_for_game(parse_session_context(raw), game_id)
    )
    return format_session_context(interactions)
