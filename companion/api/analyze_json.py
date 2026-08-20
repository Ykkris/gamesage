"""Machine-readable JSON interface for screenshot question analysis.

Companion to :mod:`companion.api.capture_json`: runs the configured vision
provider against a saved screenshot and returns a JSON envelope for the
desktop bridge. The game context is wired here (v0.1 composition root,
single supported game).
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from companion.games.witcher3.detection import GAME_NAME
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


def run_analysis(
    image_path: Path,
    question: str,
    *,
    provider_factory: ProviderFactory = create_provider,
    context: str | None = GAME_NAME,
) -> dict:
    """Answer ``question`` about the screenshot at ``image_path``.

    Returns ``{"ok": True, "answer", "provider", "model"}`` or
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
        provider = provider_factory()
        result: AnalysisResult = provider.analyze(image_path, question, context=context)
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

    return {
        "ok": True,
        "answer": result.answer,
        "provider": result.provider,
        "model": result.model,
    }
