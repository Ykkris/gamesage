"""Shared client for OpenAI-compatible chat-completions vision endpoints.

Every provider whose API follows the OpenAI chat-completions shape with
multimodal ``image_url`` content (OpenAI, OpenRouter, Z.AI, local servers
such as LM Studio or vLLM) shares this implementation. Provider modules
under ``companion/vision/providers/`` are thin configuration presets and
only customize base URL, authentication, model, headers, and payload
extensions.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from companion.vision.errors import (
    InvalidImageError,
    ProviderAuthError,
    ProviderEmptyResponseError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
)
from companion.vision.http import UrllibTransport
from companion.vision.models import AnalysisResult
from companion.vision.provider import (
    KNOWLEDGE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    HttpTransport,
)

DEFAULT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class ChatCompletionsConfig:
    """Configuration for one OpenAI-compatible endpoint.

    ``api_key`` may be None for endpoints that do not require
    authentication (typically local servers); no Bearer header is sent
    then. ``payload_extensions`` are merged into the request payload
    (e.g. Z.AI's ``thinking`` flag).
    """

    base_url: str
    model: str
    api_key: str | None = None
    provider_id: str = "openai_compatible"
    error_label: str = "AI endpoint"
    payload_extensions: Mapping[str, object] = field(default_factory=dict)
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def endpoint_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class ChatCompletionsProvider:
    """Vision provider for any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self, config: ChatCompletionsConfig, *, transport: HttpTransport | None = None
    ) -> None:
        self._config = config
        self._transport: HttpTransport = (
            transport if transport is not None else UrllibTransport()
        )

    @property
    def id(self) -> str:
        return self._config.provider_id

    @property
    def config(self) -> ChatCompletionsConfig:
        """Read-only configuration (useful for diagnostics and tests)."""
        return self._config

    def analyze(
        self,
        image_path: Path,
        question: str,
        *,
        context: str | None = None,
        knowledge: Sequence[str] | None = None,
    ) -> AnalysisResult:
        image_data_url = load_image_data_url(image_path)
        payload = build_multimodal_payload(
            self._config.model,
            question,
            image_data_url,
            context,
            payload_extensions=self._config.payload_extensions,
            knowledge=knowledge,
        )
        status, body = self._request(payload)
        answer = extract_answer(status, body, label=self._config.error_label)
        return AnalysisResult(answer=answer, provider=self.id, model=self._config.model)

    def _request(self, payload: Mapping[str, object]) -> tuple[int, object]:
        headers = dict(self._config.extra_headers)
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        headers["Accept"] = "application/json"
        try:
            return self._transport.post_json(
                self._config.endpoint_url(),
                headers=headers,
                payload=payload,
                timeout=self._config.timeout_seconds,
            )
        except OSError as error:
            raise ProviderRequestError(
                f"The {self._config.error_label} request failed: {error}"
            ) from error


def load_image_data_url(image_path: Path) -> str:
    """Read a PNG screenshot as a base64 data URL."""
    try:
        data = Path(image_path).read_bytes()
    except OSError as error:
        raise InvalidImageError(
            f"The screenshot could not be read: {image_path}"
        ) from error
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def build_multimodal_payload(
    model: str,
    question: str,
    image_data_url: str,
    context: str | None,
    *,
    payload_extensions: Mapping[str, object] | None = None,
    knowledge: Sequence[str] | None = None,
) -> dict[str, object]:
    """Build the image + text chat-completions payload.

    When ``knowledge`` passages are given, they ride in a second system
    message carrying the screenshot-precedence instructions.
    """
    system_content = SYSTEM_PROMPT
    if context:
        system_content += f"\nGame context: {context}."
    messages: list[dict[str, object]] = [{"role": "system", "content": system_content}]
    if knowledge:
        messages.append(
            {
                "role": "system",
                "content": KNOWLEDGE_SYSTEM_PROMPT
                + "\n\nRetrieved game knowledge:\n\n"
                + "\n\n".join(knowledge),
            }
        )
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url}},
                {"type": "text", "text": question},
            ],
        }
    )
    payload: dict[str, object] = {"model": model, "messages": messages}
    if payload_extensions:
        payload.update(payload_extensions)
    return payload


def extract_answer(status: int, body: object, *, label: str = "AI endpoint") -> str:
    """Validate the response and return the answer text.

    Raises the appropriate typed error for authentication failures, rate
    limits, HTTP/server errors, malformed bodies, and empty answers.
    """
    if status in (401, 403):
        raise ProviderAuthError(f"The {label} rejected the configured API key.")
    if status == 429:
        raise ProviderRateLimitError(
            f"The {label} rate limit was reached; try again shortly."
        )
    if status >= 400:
        message = _server_error_message(body) or f"HTTP {status}"
        raise ProviderRequestError(f"The {label} request failed: {message}")

    try:
        content = body["choices"][0]["message"]["content"]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        raise ProviderResponseError(
            f"The {label} returned an unreadable response."
        ) from None
    if not isinstance(content, str) or not content.strip():
        raise ProviderEmptyResponseError(f"The {label} returned an empty answer.")
    return content.strip()


def _server_error_message(body: object) -> str | None:
    """Best-effort extraction of the provider's own error message."""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return None
