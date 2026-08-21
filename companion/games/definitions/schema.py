"""Game Definition v1 (game.toml) parsing and validation.

A Game Definition teaches GameSage to detect and capture a game using
declarative data only: executable names plus window-title match values.
``game.toml`` is authoritative; the directory name is not. Nothing from a
definition is ever executed.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from companion.specs import (
    GAMESAGE_VERSION,
    is_namespaced_id,
    version_within_bounds,
)

#: The Game Definition schema version implemented by this loader.
SCHEMA_VERSION = 1

GAME_FILENAME = "game.toml"

#: Stable GameSage game ids, e.g. "witcher3", "baldurs_gate_3".
GAME_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")

#: Supported declarative window-title matching modes (case-insensitive).
TITLE_MATCH_MODES = ("exact", "starts_with", "contains")
DEFAULT_TITLE_MATCH_MODE = "starts_with"

#: Supported platforms. v1 targets Windows only, like the rest of GameSage.
PLATFORMS = ("windows",)

_STRING_FIELDS = (
    "id",
    "display_name",
    "definition_id",
    "version",
    "author",
    "platform",
    "description",
    "homepage",
    "repository",
    "gamesage_min_version",
    "gamesage_max_version",
)


class DefinitionError(ValueError):
    """A game definition is missing, malformed, or invalid."""


class SchemaVersionError(DefinitionError):
    """The definition declares an unsupported schema version."""


def compatibility_problem(definition: GameDefinition) -> str | None:
    """Compatibility diagnostic for declared GameSage version bounds."""
    minimum = definition.gamesage_min_version
    maximum = definition.gamesage_max_version
    if not minimum and not maximum:
        return None
    try:
        if not version_within_bounds(GAMESAGE_VERSION, minimum, maximum):
            return (
                "requires GameSage"
                + (f" >= {minimum}" if minimum else "")
                + (f" <= {maximum}" if maximum else "")
                + f" (this is {GAMESAGE_VERSION})."
            )
    except ValueError as error:
        return f"unreadable version bound: {error}"
    return None


@dataclass(frozen=True)
class GameDefinition:
    """A validated declarative game definition."""

    schema_version: int
    id: str
    display_name: str
    definition_id: str
    version: str
    author: str
    platform: str
    executables: tuple[str, ...]
    window_titles: tuple[str, ...]
    window_title_mode: str = DEFAULT_TITLE_MATCH_MODE
    description: str = ""
    homepage: str = ""
    repository: str = ""
    gamesage_min_version: str = ""
    gamesage_max_version: str = ""


def parse_game_definition_file(path: Path) -> GameDefinition:
    """Read and validate ``game.toml``.

    Raises:
        DefinitionError: with a human-readable reason.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DefinitionError(f"could not read {GAME_FILENAME}: {error}") from error
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise DefinitionError(f"invalid TOML in {GAME_FILENAME}: {error}") from error

    for field in _STRING_FIELDS:
        value = data.get(field, "")
        if value is not None and not isinstance(value, str):
            raise DefinitionError(f"definition field {field!r} must be a string.")
        data[field] = (value or "").strip()

    required = ("id", "display_name", "definition_id", "version", "author")
    missing = [field for field in required if not data.get(field)]
    if missing:
        raise DefinitionError(f"missing required field(s): {', '.join(missing)}.")

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise DefinitionError("definition field 'schema_version' must be an integer.")
    if schema_version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"unsupported schema version {schema_version}; this GameSage supports "
            f"schema version {SCHEMA_VERSION}."
        )

    game_id = data["id"]
    if len(game_id) > 100 or not GAME_ID_PATTERN.match(game_id):
        raise DefinitionError(
            f"invalid game id {game_id!r}: use stable lowercase snake_case ids, "
            "e.g. 'kingdom_come_deliverance_3'."
        )

    if not is_namespaced_id(data["definition_id"]):
        raise DefinitionError(
            f"invalid definition id {data['definition_id']!r}: expected lowercase "
            "dot-separated segments, e.g. 'author.game.windows'."
        )

    platform = data.get("platform") or "windows"
    if platform not in PLATFORMS:
        raise DefinitionError(
            f"unsupported platform {platform!r}; supported: {', '.join(PLATFORMS)}."
        )

    executables = _string_tuple(data, "executables")
    if not executables:
        raise DefinitionError("at least one executable name is required.")
    if any(not name.lower().endswith(".exe") for name in executables):
        raise DefinitionError("executable names must end with '.exe'.")

    window_titles = _string_tuple(data, "window_titles")
    if not window_titles:
        raise DefinitionError("at least one window-title match value is required.")

    window_title_mode = data.get("window_title_mode") or DEFAULT_TITLE_MATCH_MODE
    if window_title_mode not in TITLE_MATCH_MODES:
        raise DefinitionError(
            f"unsupported window_title_mode {window_title_mode!r}; supported: "
            f"{', '.join(TITLE_MATCH_MODES)}."
        )

    return GameDefinition(
        schema_version=schema_version,
        id=game_id,
        display_name=data["display_name"],
        definition_id=data["definition_id"],
        version=data["version"],
        author=data["author"],
        platform=platform,
        executables=executables,
        window_titles=window_titles,
        window_title_mode=window_title_mode,
        description=data["description"],
        homepage=data["homepage"],
        repository=data["repository"],
        gamesage_min_version=data["gamesage_min_version"],
        gamesage_max_version=data["gamesage_max_version"],
    )


def _string_tuple(data: dict, field: str) -> tuple[str, ...]:
    value = data.get(field, [])
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DefinitionError(f"definition field {field!r} must be a list of strings.")
    return tuple(item.strip() for item in value if item.strip())


def make_title_matcher(
    values: tuple[str, ...], mode: str
) -> Callable[[str], bool]:
    """Build the declarative, case-insensitive window-title matcher.

    Deliberately free of regular expressions: v1 offers exact,
    starts_with, and contains modes only.
    """
    lowered = [value.lower() for value in values]

    def matches(title: str) -> bool:
        candidate = title.strip().lower()
        if not candidate:
            return False
        for value in lowered:
            if mode == "exact" and candidate == value:
                return True
            if mode == "starts_with" and candidate.startswith(value):
                return True
            if mode == "contains" and value in candidate:
                return True
        return False

    return matches
