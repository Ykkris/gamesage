"""Loading of local knowledge corpora from marked Markdown files.

A knowledge document is a Markdown file whose first block is an HTML
comment starting with ``gamesage-knowledge`` containing ``key: value``
metadata lines; the rest of the file is the chunk text::

    <!-- gamesage-knowledge
    id: my-entry
    title: My Entry
    source: My Source
    url: https://example.com/entry
    license: ...
    section: ...
    spoiler: none
    -->

    Markdown body...

Files without the marker are ignored, so READMEs can live next to corpus
entries. ``id``, ``title``, and a non-empty body are required.
"""

from __future__ import annotations

from pathlib import Path

from .models import KnowledgeChunk

MARKER = "gamesage-knowledge"
_METADATA_FIELDS = ("id", "title", "source", "url", "license", "section", "spoiler")


class KnowledgeFormatError(ValueError):
    """A marked knowledge document is malformed."""


def parse_knowledge_markdown(content: str, *, origin: str = "<string>") -> KnowledgeChunk | None:
    """Parse one knowledge document; return None when it is not marked.

    Raises:
        KnowledgeFormatError: the document is marked but malformed.
    """
    text = content.lstrip("\ufeff").lstrip()
    if not text.startswith("<!--"):
        return None
    end = text.find("-->")
    if end == -1:
        return None
    header = text[4:end].strip()
    if not header.startswith(MARKER):
        return None
    body = text[end + 3 :].strip()

    metadata: dict[str, str] = {}
    for line in header[len(MARKER) :].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        if key in _METADATA_FIELDS:
            metadata[key] = value.strip()

    missing = [field for field in ("id", "title") if not metadata.get(field)]
    if missing or not body:
        missing_fields = ", ".join(missing) if missing else "body"
        raise KnowledgeFormatError(
            f"Knowledge document {origin} is missing required field(s): {missing_fields}."
        )
    return KnowledgeChunk(text=body, **metadata)  # type: ignore[arg-type]


def load_corpus_directory(directory: Path) -> list[KnowledgeChunk]:
    """Load all knowledge documents from ``directory`` (sorted by filename).

    A missing directory yields an empty corpus. Metadata marker, required
    fields, and id uniqueness are enforced; failures raise
    :class:`KnowledgeFormatError` with the offending file named.
    """
    if not directory.is_dir():
        return []
    chunks: list[KnowledgeChunk] = []
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise KnowledgeFormatError(f"Could not read knowledge file {path}: {error}") from error
        chunk = parse_knowledge_markdown(content, origin=str(path))
        if chunk is None:
            continue  # Not a knowledge document (e.g. corpus README).
        if chunk.id in seen_ids:
            raise KnowledgeFormatError(f"Duplicate knowledge id {chunk.id!r} in {path}.")
        seen_ids.add(chunk.id)
        chunks.append(chunk)
    return chunks
