"""Registry of installed Knowledge Packs.

Discovery walks configurable search roots (repository-local
``knowledge_packs/`` and the per-user GameSage directory), validates each
pack through the same loader used everywhere, groups packs by ``game_id``,
and exposes merged knowledge chunks per game.

Fault isolation: an invalid, incompatible, or conflicting pack is excluded
and reported through :meth:`KnowledgePackRegistry.statuses`; valid
unrelated packs stay usable. Conflicts are reported, never silently
overwritten — v1 has no load order or priority overrides.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from companion.knowledge.models import KnowledgeChunk

from .corpus import CorpusError, load_corpus_file
from .manifest import (
    ManifestError,
    PackManifest,
    SchemaVersionError,
    compatibility_problem,
    parse_manifest_file,
)

MANIFEST_FILENAME = "manifest.toml"
CORPUS_FILENAME = "corpus.jsonl"

STATUS_LOADED = "loaded"
STATUS_INVALID = "invalid"
STATUS_INCOMPATIBLE = "incompatible"
STATUS_CONFLICT = "conflict"


def default_pack_roots(env: dict[str, str] | None = None) -> tuple[Path, ...]:
    """Knowledge Pack search roots (deterministic order).

    Development: ``knowledge_packs/`` in the working directory (the Python
    core runs from the repository root). Users: ``%LOCALAPPDATA%\\GameSage\\
    knowledge-packs``. The ``GAMESAGE_KNOWLEDGE_PACKS`` environment
    variable adds extra os-pathsep-separated roots. Tests inject roots
    directly into the registry instead.
    """
    environment = os.environ if env is None else env
    roots = [Path("knowledge_packs")]
    local_app_data = environment.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(Path(local_app_data) / "GameSage" / "knowledge-packs")
    extra = environment.get("GAMESAGE_KNOWLEDGE_PACKS", "")
    roots.extend(Path(part) for part in extra.split(os.pathsep) if part.strip())
    return tuple(roots)


@dataclass(frozen=True)
class PackStatus:
    """Structured report about one discovered pack (future-UI ready)."""

    pack_id: str
    status: str  # loaded | invalid | incompatible | conflict
    message: str
    path: str


@dataclass(frozen=True)
class LoadedPack:
    """A pack that passed manifest and corpus validation."""

    manifest: PackManifest
    directory: Path
    records: tuple[KnowledgeChunk, ...]

    @property
    def status(self) -> str:
        return STATUS_LOADED


@dataclass(frozen=True)
class PackProblem:
    """A pack that failed validation; carries a status and diagnostic."""

    status: str  # invalid | incompatible
    message: str
    directory: Path
    pack_id: str


def load_pack(directory: Path) -> LoadedPack | PackProblem:
    """Validate and load a single pack directory.

    This is the one shared validation path — runtime discovery and the
    ``tools.knowledge`` CLI both call it; there is no privileged loader.
    """
    manifest_path = directory / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return PackProblem(
            status=STATUS_INVALID,
            message=f"missing {MANIFEST_FILENAME}",
            directory=directory,
            pack_id=directory.name,
        )
    try:
        manifest = parse_manifest_file(manifest_path)
    except SchemaVersionError as error:
        return PackProblem(
            status=STATUS_INCOMPATIBLE,
            message=str(error),
            directory=directory,
            pack_id=directory.name,
        )
    except ManifestError as error:
        return PackProblem(
            status=STATUS_INVALID,
            message=str(error),
            directory=directory,
            pack_id=directory.name,
        )
    incompatibility = compatibility_problem(manifest)
    if incompatibility is not None:
        return PackProblem(
            status=STATUS_INCOMPATIBLE,
            message=incompatibility,
            directory=directory,
            pack_id=manifest.id,
        )
    try:
        records = load_corpus_file(directory / CORPUS_FILENAME, manifest)
    except CorpusError as error:
        return PackProblem(
            status=STATUS_INVALID,
            message=str(error),
            directory=directory,
            pack_id=manifest.id,
        )
    return LoadedPack(manifest=manifest, directory=directory, records=records)


class KnowledgePackRegistry:
    """Installed Knowledge Packs, discovered from search roots."""

    def __init__(self, roots: Sequence[Path] | None = None) -> None:
        self._roots = tuple(roots) if roots is not None else default_pack_roots()
        self._statuses: list[PackStatus] = []
        self._packs_by_game: dict[str, list[LoadedPack]] = {}
        self._chunks_by_game: dict[str, tuple[KnowledgeChunk, ...]] = {}
        self._scan()

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def chunks_for_game(self, game_id: str) -> tuple[KnowledgeChunk, ...]:
        """Merged knowledge chunks from all usable packs for ``game_id``."""
        return self._chunks_by_game.get(game_id, ())

    def packs_for_game(self, game_id: str) -> tuple[PackManifest, ...]:
        """Manifests of the usable packs installed for ``game_id``."""
        return tuple(pack.manifest for pack in self._packs_by_game.get(game_id, []))

    def statuses(self) -> tuple[PackStatus, ...]:
        """One structured status per discovered pack directory."""
        return tuple(self._statuses)

    def _scan(self) -> None:
        candidates: list[Path] = []
        for root in self._roots:
            if not root.is_dir():
                continue
            for directory in sorted(root.iterdir()):
                if directory.is_dir():
                    candidates.append(directory)

        seen_pack_ids: set[str] = set()
        loaded: list[LoadedPack] = []
        for directory in candidates:
            result = load_pack(directory)
            if isinstance(result, PackProblem):
                self._statuses.append(
                    PackStatus(result.pack_id, result.status, result.message, str(directory))
                )
                continue
            if result.manifest.id in seen_pack_ids:
                self._statuses.append(
                    PackStatus(
                        result.manifest.id,
                        STATUS_CONFLICT,
                        f"duplicate pack id {result.manifest.id!r} is already installed; "
                        "this copy is ignored.",
                        str(directory),
                    )
                )
                continue
            seen_pack_ids.add(result.manifest.id)
            loaded.append(result)
            self._statuses.append(
                PackStatus(
                    result.manifest.id,
                    STATUS_LOADED,
                    f"{len(result.records)} records for game '{result.manifest.game_id}'",
                    str(directory),
                )
            )

        for pack in loaded:
            self._packs_by_game.setdefault(pack.manifest.game_id, []).append(pack)

        # Cross-pack record-id conflicts within a game: the first pack (in
        # deterministic scan order) wins; later ones are demoted to conflict.
        for game_id, packs in list(self._packs_by_game.items()):
            record_ids: set[str] = set()
            usable: list[LoadedPack] = []
            for pack in packs:
                collisions = [record.id for record in pack.records if record.id in record_ids]
                if collisions:
                    self._statuses.append(
                        PackStatus(
                            pack.manifest.id,
                            STATUS_CONFLICT,
                            f"record id {collisions[0]!r} already provided by another pack "
                            f"for game '{game_id}'; this pack is ignored.",
                            str(pack.directory),
                        )
                    )
                    continue
                record_ids.update(record.id for record in pack.records)
                usable.append(pack)
            self._packs_by_game[game_id] = usable
            self._chunks_by_game[game_id] = tuple(
                record for pack in usable for record in pack.records
            )

        for status in self._statuses:
            if status.status != STATUS_LOADED:
                # Diagnostics for the development console; never user-facing.
                print(
                    f"gamesage: knowledge pack {status.pack_id!r} ({status.status}): "
                    f"{status.message} [{status.path}]",
                    file=sys.stderr,
                )
