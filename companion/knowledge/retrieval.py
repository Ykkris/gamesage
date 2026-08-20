"""Deterministic lexical retrieval (BM25-style) over small local corpora.

No embeddings, no external services: normalized term matching with
idf-weighted scoring and length normalization, suited to corpora of tens
to hundreds of chunks. Title terms are counted twice so matches on a
document's title rank above body-only matches.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from .models import KnowledgeChunk

_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)

_STOPWORDS = frozenset(
    """a an and are as at be but by for from has have how i in is it its of on
    or that the this to was what when where which who will with you your do
    does did can could should would about""".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercased alphanumeric tokens, without stopwords/short tokens."""
    return [
        token
        for token in (match.group(0).lower() for match in _TOKEN_PATTERN.finditer(text))
        if len(token) > 2 and token not in _STOPWORDS
    ]


#: Default BM25 floor. Calibrated on the starter corpus: accidental matches
#: on a single common term (e.g. one generic scene word) score around
#: 1.1-1.3, while distinctive-term matches score >= ~1.8. Anything under
#: the floor is treated as a weak lexical coincidence and dropped.
DEFAULT_MIN_SCORE = 1.5


class RetrievalHit:
    """One scored retrieval result; keeps full source metadata."""

    __slots__ = ("chunk", "score")

    def __init__(self, chunk: KnowledgeChunk, score: float) -> None:
        self.chunk = chunk
        self.score = score

    def __repr__(self) -> str:
        return f"RetrievalHit(chunk={self.chunk.id!r}, score={self.score:.3f})"


def retrieve(
    query: str,
    chunks: Sequence[KnowledgeChunk],
    *,
    limit: int = 3,
    k1: float = 1.5,
    b: float = 0.75,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[RetrievalHit]:
    """Return the top ``limit`` chunks ranked by BM25 relevance to ``query``.

    Chunks scoring below ``min_score`` are dropped, so weak lexical
    coincidences (an accidental single common term) yield no results; pass
    ``min_score=0`` to observe raw ranking. Ties are broken by chunk id so
    results are fully deterministic.
    """
    query_terms = tokenize(query)
    if not query_terms or not chunks:
        return []

    documents = [tokenize(chunk.title) * 2 + tokenize(chunk.text) for chunk in chunks]
    total = len(documents)
    lengths = [len(doc) for doc in documents]
    average_length = sum(lengths) / total

    document_frequency: dict[str, int] = {}
    for document in documents:
        for term in set(document):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    scored: list[tuple[float, str, int]] = []
    for index, document in enumerate(documents):
        term_frequency = _count_terms(document)
        score = 0.0
        for term in query_terms:
            tf = term_frequency.get(term, 0)
            if tf == 0:
                continue
            df = document_frequency.get(term, 0)
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            length_norm = k1 * (1 - b + b * lengths[index] / average_length)
            score += idf * tf * (k1 + 1) / (tf + length_norm)
        if score >= min_score:
            scored.append((score, chunks[index].id, index))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [RetrievalHit(chunks[index], score) for score, _, index in scored[:limit]]


def has_any_term(chunk: KnowledgeChunk, terms: Sequence[str]) -> bool:
    """Whether ``chunk`` (title or text) contains any of ``terms``.

    ``terms`` must already be tokenized (see :func:`tokenize`). Used to
    anchor retrieval results to a specific question so that scene context
    alone cannot qualify a source.
    """
    if not terms:
        return True
    chunk_terms = set(tokenize(chunk.title)) | set(tokenize(chunk.text))
    return any(term in chunk_terms for term in terms)


def _count_terms(document: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for term in document:
        counts[term] = counts.get(term, 0) + 1
    return counts
