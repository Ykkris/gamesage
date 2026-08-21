"""Knowledge Pack v1 manifest parsing and validation.

The manifest (``manifest.toml``) is the authoritative pack identity; the
directory name is not. Parsing is pure data handling — nothing from a pack
is ever executed.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

#: The Knowledge Pack schema version implemented by this loader.
SCHEMA_VERSION = 1

#: GameSage version used for ``gamesage_min_version``/``max_version`` checks.
#: Kept in sync with pyproject.toml for the development prototype.
GAMESAGE_VERSION = "0.1.0"

_REQUIRED_FIELDS = ("id", "game_id", "version", "name", "author")

#: Pack ids: dot-separated namespaced segments, e.g. "author.game.pack".
_PACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")

_STRING_FIELDS = (
    "id",
    "game_id",
    "version",
    "name",
    "author",
    "description",
    "homepage",
    "repository",
    "gamesage_min_version",
    "gamesage_max_version",
)


class ManifestError(ValueError):
    """A pack manifest is missing, malformed, or invalid."""


class SchemaVersionError(ManifestError):
    """The manifest declares an unsupported Knowledge Pack schema version."""


@dataclass(frozen=True)
class PackManifest:
    """Validated manifest data for one Knowledge Pack."""

    schema_version: int
    id: str
    game_id: str
    version: str
    name: str
    author: str
    description: str = ""
    homepage: str = ""
    repository: str = ""
    languages: tuple[str, ...] = ()
    gamesage_min_version: str = ""
    gamesage_max_version: str = ""


def parse_manifest_file(path: Path) -> PackManifest:
    """Read and validate ``manifest.toml``.

    Raises:
        ManifestError: with a human-readable reason.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ManifestError(f"could not read manifest.toml: {error}") from error
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(f"invalid TOML in manifest.toml: {error}") from error

    for field in _STRING_FIELDS:
        value = data.get(field, "")
        if value is not None and not isinstance(value, str):
            raise ManifestError(f"manifest field {field!r} must be a string.")
        data[field] = (value or "").strip()

    missing = [field for field in _REQUIRED_FIELDS if not data.get(field)]
    if missing:
        raise ManifestError(f"missing required manifest field(s): {', '.join(missing)}.")

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ManifestError("manifest field 'schema_version' must be an integer.")
    if schema_version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"unsupported schema version {schema_version}; this GameSage supports "
            f"schema version {SCHEMA_VERSION}."
        )

    pack_id = data["id"]
    if len(pack_id) > 200 or not _PACK_ID_PATTERN.match(pack_id):
        raise ManifestError(
            f"invalid pack id {pack_id!r}: expected lowercase dot-separated "
            "segments with at least a namespace and a name, e.g. 'author.game.pack'."
        )

    languages = data.get("languages", [])
    if not isinstance(languages, list) or not all(isinstance(item, str) for item in languages):
        raise ManifestError("manifest field 'languages' must be a list of strings.")
    if any(not item.strip() for item in languages):
        raise ManifestError("manifest field 'languages' must not contain empty entries.")

    return PackManifest(
        schema_version=schema_version,
        id=pack_id,
        game_id=data["game_id"],
        version=data["version"],
        name=data["name"],
        author=data["author"],
        description=data["description"],
        homepage=data["homepage"],
        repository=data["repository"],
        languages=tuple(language.strip() for language in languages),
        gamesage_min_version=data["gamesage_min_version"],
        gamesage_max_version=data["gamesage_max_version"],
    )


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


def compatibility_problem(manifest: PackManifest) -> str | None:
    """Compatibility diagnostic for declared GameSage version bounds.

    Returns a message when the pack declares bounds this GameSage does not
    satisfy; otherwise None.
    """
    try:
        current = parse_version(GAMESAGE_VERSION)
        minimum = parse_version(manifest.gamesage_min_version) if manifest.gamesage_min_version else None
        maximum = parse_version(manifest.gamesage_max_version) if manifest.gamesage_max_version else None
    except ValueError as error:
        return f"unreadable version bound: {error}"
    if minimum is not None and current < minimum:
        return (
            f"requires GameSage >= {manifest.gamesage_min_version} "
            f"(this is {GAMESAGE_VERSION})."
        )
    if maximum is not None and current > maximum:
        return (
            f"requires GameSage <= {manifest.gamesage_max_version} "
            f"(this is {GAMESAGE_VERSION})."
        )
    return None
