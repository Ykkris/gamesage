"""Generic vision-provider interface.

Any AI provider capable of answering questions about images implements
:class:`VisionProvider`. Provider-specific code lives under
``companion/vision/providers/``; nothing in this module may depend on a
concrete provider.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from .models import AnalysisResult

#: Minimal system instruction shared by all providers.
SYSTEM_PROMPT = (
    "You are GameSage, an AI gaming companion.\n"
    "The image is a screenshot from the game described in the context.\n"
    "Answer the user's question based primarily on what is visible in the "
    "screenshot.\n"
    "Do not invent quest consequences, statistics, or game facts that are "
    "not visible or clearly implied by the screenshot.\n"
    "If the screenshot does not contain enough information to answer, say "
    "so plainly.\n"
    "Keep the answer concise."
)

#: Additional instructions used when retrieved knowledge accompanies a request.
KNOWLEDGE_SYSTEM_PROMPT = (
    "Additional game knowledge retrieved for this question is provided "
    "below as numbered reference passages.\n"
    "Information visible in the screenshot takes precedence over retrieved "
    "knowledge.\n"
    "Clearly distinguish what is visible in the screenshot from what comes "
    "from the retrieved game knowledge.\n"
    "If the retrieved knowledge does not contain the needed information "
    "(for example quest consequences), say that the available knowledge is "
    "insufficient instead of guessing."
)

#: Additional instructions used when recent session context accompanies a
#: request. Prior GameSage answers are previous model output — the wording
#: keeps them from being treated as guaranteed facts.
SESSION_CONTEXT_SYSTEM_PROMPT = (
    "Recent conversation with the player from this session is provided "
    "below.\n"
    "Use it only to resolve references and continuity, for example what a "
    "phrase like 'her' or 'that quest' refers to.\n"
    "Earlier GameSage replies are previous model output, not guaranteed "
    "facts.\n"
    "The current screenshot is authoritative for what is visible now; do "
    "not claim something is visible because it appeared earlier.\n"
    "Retrieved game knowledge remains the preferred source for game facts."
)


class VisionProvider(Protocol):
    """A provider that can answer questions about a screenshot image."""

    id: str

    def analyze(
        self,
        image_path: Path,
        question: str,
        *,
        context: str | None = None,
        knowledge: Sequence[str] | None = None,
        session_context: str | None = None,
    ) -> AnalysisResult:
        """Answer ``question`` about the image at ``image_path``.

        ``context`` optionally names the game shown in the screenshot.
        ``knowledge`` optionally holds pre-formatted reference passages to
        ground the answer in retrieved game knowledge. ``session_context``
        optionally holds the formatted recent-turn block for conversational
        continuity.
        """
        ...


class HttpTransport(Protocol):
    """Minimal JSON-over-HTTP POST transport, injectable for tests."""

    def post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout: float,
    ) -> tuple[int, object]:
        """POST ``payload`` as JSON; return ``(status_code, parsed_body)``.

        Raises an ``OSError`` subclass on network failure. HTTP error
        statuses are returned, not raised, so callers can map them.
        """
        ...
