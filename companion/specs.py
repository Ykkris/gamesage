"""Shared helpers for GameSage community specification formats.

Common conventions used by both Knowledge Packs and Game Definitions:
namespaced ids, semantic-ish version parsing, and GameSage version
compatibility bounds. Trusted GameSage code only — these helpers never
execute content from community files.
"""

from __future__ import annotations

import re

#: GameSage version used for community-format compatibility bounds.
#: Kept in sync with pyproject.toml for the development prototype.
GAMESAGE_VERSION = "0.1.0"

#: Namespaced ids for community-authored artifacts, e.g.
#: "author.game.pack" or "author.game.windows". At least two dot-separated
#: lowercase segments; letters, digits, ``-`` and ``_``.
NAMESPACED_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")


def is_namespaced_id(candidate: str) -> bool:
    """Whether ``candidate`` is a valid namespaced community id."""
    return len(candidate) <= 200 and bool(NAMESPACED_ID_PATTERN.match(candidate))


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a ``major.minor.patch``-style version into comparable ints.

    Pre-release/build suffixes (``-rc.1``, ``+meta``) are ignored — enough
    for v1 compatibility bounds without a dependency.
    """
    core = version.strip().split("-", 1)[0].split("+", 1)[0]
    parts = []
    for segment in core.split("."):
        if not segment.isdigit():
            raise ValueError(f"invalid version {version!r}")
        parts.append(int(segment))
    if not parts:
        raise ValueError(f"invalid version {version!r}")
    return tuple(parts)


def version_within_bounds(
    current: str, minimum: str = "", maximum: str = ""
) -> bool:
    """Whether ``current`` satisfies optional min/max version bounds."""
    parsed_current = parse_version(current)
    if minimum:
        if parsed_current < parse_version(minimum):
            return False
    if maximum:
        if parsed_current > parse_version(maximum):
            return False
    return True
