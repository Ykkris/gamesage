"""Discovery of installed Game Definitions from search roots.

Fault isolation mirrors the Knowledge Pack system: a broken definition is
excluded with a structured status while valid unrelated definitions (and
native games) remain usable. Conflicts are reported, never silently
overwritten: native adapters always take precedence over a definition
claiming the same game id, and duplicate declarative ids or game ids
conflict in deterministic scan order.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .schema import (
    GAME_FILENAME,
    CompatibilityError,
    DefinitionError,
    GameDefinition,
    SchemaVersionError,
    parse_game_definition_file,
)

STATUS_LOADED = "loaded"
STATUS_INVALID = "invalid"
STATUS_INCOMPATIBLE = "incompatible"
STATUS_CONFLICT = "conflict"


def default_definition_roots(env: dict[str, str] | None = None) -> tuple[Path, ...]:
    """Game Definition search roots (deterministic order).

    Development: ``game_definitions/`` in the working directory (the Python
    core runs from the repository root). Users:
    ``%LOCALAPPDATA%\\GameSage\\games``. The
    ``GAMESAGE_GAME_DEFINITIONS`` environment variable adds extra
    os-pathsep-separated roots (``;`` on Windows). Tests inject roots
    directly into discovery instead.
    """
    environment = os.environ if env is None else env
    roots = [Path("game_definitions")]
    local_app_data = environment.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(Path(local_app_data) / "GameSage" / "games")
    extra = environment.get("GAMESAGE_GAME_DEFINITIONS", "")
    roots.extend(Path(part) for part in extra.split(os.pathsep) if part.strip())
    return tuple(roots)


@dataclass(frozen=True)
class DefinitionStatus:
    """Structured report about one discovered definition (future-UI ready)."""

    definition_id: str
    status: str  # loaded | invalid | incompatible | conflict
    message: str
    path: str


@dataclass(frozen=True)
class LoadedDefinition:
    """A definition that passed validation."""

    definition: GameDefinition
    directory: Path

    @property
    def status(self) -> str:
        return STATUS_LOADED


@dataclass(frozen=True)
class DefinitionProblem:
    """A definition that failed validation."""

    status: str  # invalid | incompatible
    message: str
    directory: Path
    definition_id: str


def load_definition(directory: Path) -> LoadedDefinition | DefinitionProblem:
    """Validate and load a single definition directory.

    The one shared validation path — runtime discovery and the
    ``tools.games`` CLI both call it; there is no separate validator.
    """
    definition_path = directory / GAME_FILENAME
    if not definition_path.is_file():
        return DefinitionProblem(
            status=STATUS_INVALID,
            message=f"missing {GAME_FILENAME}",
            directory=directory,
            definition_id=directory.name,
        )
    try:
        definition = parse_game_definition_file(definition_path)
    except (SchemaVersionError, CompatibilityError) as error:
        return DefinitionProblem(
            status=STATUS_INCOMPATIBLE,
            message=str(error),
            directory=directory,
            definition_id=directory.name,
        )
    except DefinitionError as error:
        return DefinitionProblem(
            status=STATUS_INVALID,
            message=str(error),
            directory=directory,
            definition_id=directory.name,
        )
    return LoadedDefinition(definition=definition, directory=directory)


def discover_definitions(
    roots: Sequence[Path],
    *,
    reserved_game_ids: frozenset[str] = frozenset(),
) -> tuple[tuple[GameDefinition, ...], tuple[DefinitionStatus, ...]]:
    """Walk ``roots`` and return validated definitions plus status reports.

    ``reserved_game_ids`` (the native game ids) take precedence: a
    definition claiming one is reported as a conflict and excluded.
    Duplicate definition ids and duplicate declarative game ids likewise
    conflict in deterministic scan order.
    """
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for directory in sorted(root.iterdir()):
            if directory.is_dir():
                candidates.append(directory)

    definitions: list[GameDefinition] = []
    statuses: list[DefinitionStatus] = []
    seen_definition_ids: set[str] = set()
    seen_game_ids: set[str] = set()

    for directory in candidates:
        result = load_definition(directory)
        if isinstance(result, DefinitionProblem):
            statuses.append(
                DefinitionStatus(
                    result.definition_id, result.status, result.message, str(directory)
                )
            )
            continue
        definition = result.definition
        if definition.definition_id in seen_definition_ids:
            statuses.append(
                DefinitionStatus(
                    definition.definition_id,
                    STATUS_CONFLICT,
                    f"duplicate definition id {definition.definition_id!r} is already "
                    "installed; this copy is ignored.",
                    str(directory),
                )
            )
            continue
        if definition.id in reserved_game_ids:
            statuses.append(
                DefinitionStatus(
                    definition.definition_id,
                    STATUS_CONFLICT,
                    f"game id {definition.id!r} is already provided by a built-in "
                    "native game; native adapters take precedence and this "
                    "definition is ignored.",
                    str(directory),
                )
            )
            continue
        if definition.id in seen_game_ids:
            statuses.append(
                DefinitionStatus(
                    definition.definition_id,
                    STATUS_CONFLICT,
                    f"another definition already provides game id {definition.id!r}; "
                    "this definition is ignored.",
                    str(directory),
                )
            )
            continue
        seen_definition_ids.add(definition.definition_id)
        seen_game_ids.add(definition.id)
        definitions.append(definition)
        statuses.append(
            DefinitionStatus(
                definition.definition_id,
                STATUS_LOADED,
                f"game '{definition.id}' ({definition.display_name})",
                str(directory),
            )
        )

    for status in statuses:
        if status.status != STATUS_LOADED:
            # Diagnostics for the development console; never user-facing.
            print(
                f"gamesage: game definition {status.definition_id!r} "
                f"({status.status}): {status.message} [{status.path}]",
                file=sys.stderr,
            )
    return tuple(definitions), tuple(statuses)
