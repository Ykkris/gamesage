"""Typed representation of a knowledge document/chunk."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeChunk:
    """One retrievable knowledge entry with source and pack metadata.

    ``spoiler`` is a free-form hint for now (e.g. "none", "light",
    "moderate"); the full spoiler-preference system is a later feature.
    ``aliases`` (alternate names, e.g. localized titles) and ``tags``
    participate in lexical retrieval. ``pack_id`` records which Knowledge
    Pack supplied the chunk (empty for directly-constructed chunks).
    """

    id: str
    title: str
    text: str
    source: str = ""
    url: str = ""
    license: str = ""
    section: str = ""
    spoiler: str = ""
    language: str = ""
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    pack_id: str = ""
