"""Typed representation of a knowledge document/chunk."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeChunk:
    """One retrievable knowledge entry with source metadata.

    ``spoiler`` is a free-form hint for now (e.g. "none", "light",
    "moderate"); the full spoiler-preference system is a later feature.
    """

    id: str
    title: str
    text: str
    source: str = ""
    url: str = ""
    license: str = ""
    section: str = ""
    spoiler: str = ""
