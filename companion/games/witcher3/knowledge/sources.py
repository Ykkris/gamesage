"""Access to the bundled Witcher 3 knowledge corpus."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from companion.knowledge.corpus import load_corpus_directory
from companion.knowledge.models import KnowledgeChunk

#: Directory holding the Markdown corpus entries.
CORPUS_DIR = Path(__file__).parent / "corpus"


@lru_cache(maxsize=1)
def load_corpus() -> tuple[KnowledgeChunk, ...]:
    """Load the Witcher 3 corpus, parsed once per process.

    The corpus only changes when files are edited, so in-process caching
    is safe; tests that need a fresh parse can call
    ``load_corpus.cache_clear()``.
    """
    return tuple(load_corpus_directory(CORPUS_DIR))
