"""Knowledge Pack v1 corpus (corpus.jsonl) loading.

One JSON object per line; parsing is pure data handling. Errors carry the
offending line number for pack authors.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from companion.knowledge.models import KnowledgeChunk

from .manifest import PackManifest

#: Record ids: stable, meaningful, lowercase with ``:``-separated aspects,
#: e.g. "witcher3:quest:lord-undvik:overview". No random UUIDs.
_RECORD_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_-]*$")

_STRING_FIELDS = ("id", "game_id", "type", "title", "text", "language", "section", "spoiler")


class CorpusError(ValueError):
    """A corpus record (or the file as a whole) is invalid."""


def load_corpus_file(path: Path, manifest: PackManifest) -> tuple[KnowledgeChunk, ...]:
    """Load and validate ``corpus.jsonl`` for a pack.

    Raises:
        CorpusError: with ``corpus.jsonl line N`` context on the first
            invalid record.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise CorpusError(f"could not read corpus.jsonl: {error}") from error

    chunks: list[KnowledgeChunk] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise CorpusError(f"corpus.jsonl line {line_number}: invalid JSON: {error}") from error
        if not isinstance(record, dict):
            raise CorpusError(f"corpus.jsonl line {line_number}: record must be a JSON object.")
        try:
            chunk = _record_to_chunk(record, manifest)
        except CorpusError as error:
            raise CorpusError(f"corpus.jsonl line {line_number}: {error}") from error
        if chunk.id in seen_ids:
            raise CorpusError(
                f"corpus.jsonl line {line_number}: duplicate record id {chunk.id!r} within this pack."
            )
        seen_ids.add(chunk.id)
        chunks.append(chunk)
    return tuple(chunks)


def _record_to_chunk(record: dict, manifest: PackManifest) -> KnowledgeChunk:
    for field in _STRING_FIELDS:
        value = record.get(field, "")
        if value is not None and not isinstance(value, str):
            raise CorpusError(f"field {field!r} must be a string.")
        record[field] = (value or "").strip()

    missing = [field for field in ("id", "title", "text") if not record.get(field)]
    if missing:
        raise CorpusError(f"missing required field(s): {', '.join(missing)}.")

    record_id = record["id"]
    if len(record_id) > 200 or not _RECORD_ID_PATTERN.match(record_id):
        raise CorpusError(
            f"invalid record id {record_id!r}: use stable lowercase ids with ':' "
            "aspects, e.g. 'witcher3:quest:lord-undvik:overview'."
        )

    record_game_id = record.get("game_id", "")
    if record_game_id and record_game_id != manifest.game_id:
        raise CorpusError(
            f"record declares game_id {record_game_id!r} but the pack targets "
            f"{manifest.game_id!r}."
        )

    aliases = _string_list(record, "aliases")
    tags = _string_list(record, "tags")

    source = record.get("source", {})
    if source is None:
        source = {}
    if not isinstance(source, dict):
        raise CorpusError("field 'source' must be an object with name/url/license.")
    for key in source:
        if key not in ("name", "url", "license"):
            raise CorpusError(f"unknown source field {key!r}.")
    if not all(isinstance(source[key], str) for key in source):
        raise CorpusError("source fields must be strings.")

    return KnowledgeChunk(
        id=record_id,
        title=record["title"],
        text=record["text"],
        source=source.get("name", ""),
        url=source.get("url", ""),
        license=source.get("license", ""),
        section=record["section"],
        spoiler=record["spoiler"],
        language=record["language"],
        aliases=aliases,
        tags=tags,
        pack_id=manifest.id,
    )


def _string_list(record: dict, field: str) -> tuple[str, ...]:
    value = record.get(field, [])
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CorpusError(f"field {field!r} must be a list of strings.")
    return tuple(item.strip() for item in value if item.strip())
