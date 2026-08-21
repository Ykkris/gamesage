"""Machine-readable JSON interface for screenshot question analysis.

Companion to :mod:`companion.api.capture_json`. The pipeline has two vision
stages plus local knowledge retrieval:

1. context extraction — a fixed internal question asks the provider to list
   what is visible in the screenshot (location/character/quest names, UI);
2. retrieval — the user question plus a capped slice of that visual context
   form the retrieval query over the selected game's local corpus;
3. grounded answer — the user question is answered with the screenshot and
   the retrieved passages, which the provider must distinguish from visible
   information.

Games are resolved through the adapter registry (``get_game``); nothing
here imports a concrete game.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path

from companion.games.registry import UnknownGameError, get_game
from companion.knowledge.models import KnowledgeChunk
from companion.knowledge.packs.registry import KnowledgePackRegistry
from companion.knowledge.retrieval import RetrievalHit, has_any_term, retrieve, tokenize
from companion.vision.errors import (
    InvalidImageError,
    ProviderAuthError,
    ProviderEmptyResponseError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
    VisionError,
)
from companion.vision.factory import create_provider
from companion.vision.models import AnalysisResult
from companion.vision.provider import VisionProvider

ProviderFactory = Callable[[], VisionProvider]
KnowledgeRetriever = Callable[[str], Sequence[RetrievalHit]]

#: Fixed internal question for the visual-context extraction stage.
CONTEXT_EXTRACTION_QUESTION = (
    "List concisely what is visible in this screenshot: location names, "
    "character names, quest or objective names, item names, and notable UI "
    "text. Plain list only, no commentary."
)

#: How much of the raw vision context feeds the retrieval query; the rest is
#: dropped to avoid turning the whole first answer into the query.
MAX_VISUAL_CONTEXT_CHARS = 400

#: Retrieved passages included in the final prompt.
KNOWLEDGE_LIMIT = 3

#: Known vision error types mapped to stable machine-readable codes.
_ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (ProviderNotConfiguredError, "provider_not_configured"),
    (InvalidImageError, "invalid_image"),
    (ProviderAuthError, "provider_auth_failed"),
    (ProviderRateLimitError, "provider_rate_limited"),
    (ProviderEmptyResponseError, "provider_empty_response"),
    (ProviderResponseError, "provider_response_invalid"),
    (ProviderRequestError, "provider_request_failed"),
)


def error_code(error: Exception) -> str:
    for error_type, code in _ERROR_CODES:
        if isinstance(error, error_type):
            return code
    return "internal_error"


def build_retrieval_query(
    question: str,
    visual_context: str,
    *,
    max_context_chars: int = MAX_VISUAL_CONTEXT_CHARS,
) -> str:
    """Combine the user question with a capped slice of visual context."""
    trimmed = visual_context.strip()[:max_context_chars]
    if not trimmed:
        return question.strip()
    return f"{question.strip()}\n{trimmed}"


def format_knowledge_passages(hits: Sequence[RetrievalHit]) -> list[str]:
    """Format retrieved chunks as numbered, attributed reference passages."""
    return [
        f"[{index}] {hit.chunk.title} ({hit.chunk.source})\n{hit.chunk.text.strip()}"
        for index, hit in enumerate(hits, start=1)
    ]


def build_knowledge_retriever(
    game_id: str, *, registry: KnowledgePackRegistry | None = None
) -> KnowledgeRetriever:
    """Build the default retriever over the game's installed packs."""
    packs = registry if registry is not None else default_pack_registry()
    chunks = packs.chunks_for_game(game_id)

    def retrieve_for_game(query: str) -> list[RetrievalHit]:
        if not chunks:
            return []
        return retrieve(query, chunks, limit=KNOWLEDGE_LIMIT)

    return retrieve_for_game


def _source_entries(hits: Sequence[RetrievalHit]) -> list[dict[str, str]]:
    return [
        {"title": hit.chunk.title, "source": hit.chunk.source, "url": hit.chunk.url}
        for hit in hits
    ]


def run_analysis(
    image_path: Path,
    question: str,
    game_id: str | None = None,
    *,
    provider_factory: ProviderFactory = create_provider,
    knowledge_retriever: KnowledgeRetriever | None = None,
) -> dict:
    """Answer ``question`` about the screenshot, grounded in local knowledge.

    ``game_id`` selects the adapter (default game when omitted); its
    ``display_name`` becomes the vision context and its corpus backs the
    default knowledge retriever.

    Returns ``{"ok": True, "answer", "provider", "model"}`` plus
    ``"sources"`` when retrieved knowledge was used, or
    ``{"ok": False, "error": {"code", "message"}}``. Unexpected exceptions
    are reported generically (details go to stderr), so raw stack traces
    never reach the desktop UI.
    """
    if not question.strip():
        return {
            "ok": False,
            "error": {"code": "invalid_request", "message": "A question is required."},
        }
    try:
        game = get_game(game_id)
        if knowledge_retriever is None:
            knowledge_retriever = build_knowledge_retriever(game.id)
        provider = provider_factory()
        visual_context = provider.analyze(
            image_path, CONTEXT_EXTRACTION_QUESTION, context=game.display_name
        ).answer
        retrieved: Sequence[RetrievalHit] = knowledge_retriever(
            build_retrieval_query(question, visual_context)
        )
        # Question-anchor rule: retrieved knowledge must share at least one
        # term with the user's question. Scene context alone cannot qualify
        # a source, so off-topic questions produce no Sources section even
        # when the visual context matches corpus entries strongly.
        question_terms = tokenize(question)
        if question_terms:
            retrieved = [hit for hit in retrieved if has_any_term(hit.chunk, question_terms)]
        knowledge = format_knowledge_passages(retrieved) or None
        result: AnalysisResult = provider.analyze(
            image_path, question, context=game.display_name, knowledge=knowledge
        )
    except UnknownGameError as error:
        return {
            "ok": False,
            "error": {"code": "unknown_game", "message": str(error)},
        }
    except VisionError as error:
        return {
            "ok": False,
            "error": {"code": error_code(error), "message": str(error)},
        }
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return {
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred while analyzing the screenshot.",
            },
        }

    payload: dict[str, object] = {
        "ok": True,
        "answer": result.answer,
        "provider": result.provider,
        "model": result.model,
    }
    if knowledge:
        payload["sources"] = _source_entries(retrieved)
    return payload


def default_pack_registry() -> KnowledgePackRegistry:
    """The process-wide pack registry (discovery runs once per process)."""
    return _default_registry()


@lru_cache(maxsize=1)
def _default_registry() -> KnowledgePackRegistry:
    return KnowledgePackRegistry()


def knowledge_chunks(game_id: str | None = None) -> Sequence[KnowledgeChunk]:
    """The selected game's installed pack chunks (diagnostics/tests)."""
    return default_pack_registry().chunks_for_game(get_game(game_id).id)
