"""OpenRouter provider preset (thin configuration over the shared client).

OpenRouter is an aggregator: the model is always user-selected, so
``OPENROUTER_MODEL`` is required rather than defaulted.
"""

from __future__ import annotations

from collections.abc import Mapping

from companion.vision.chat_completions import ChatCompletionsConfig, ChatCompletionsProvider
from companion.vision.errors import ProviderNotConfiguredError

PROVIDER_ID = "openrouter"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def from_env(env: Mapping[str, str]) -> ChatCompletionsProvider:
    """Build the OpenRouter provider from OPENROUTER_* environment variables."""
    api_key = (env.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise ProviderNotConfiguredError(
            "OpenRouter API key is not configured. Set OPENROUTER_API_KEY in "
            "the environment or in the repository .env file."
        )
    model = (env.get("OPENROUTER_MODEL") or "").strip()
    if not model:
        raise ProviderNotConfiguredError(
            "OpenRouter model is not configured. Set OPENROUTER_MODEL to a "
            "vision-capable model id from https://openrouter.ai/models."
        )
    base_url = (env.get("OPENROUTER_BASE_URL") or "").strip().rstrip("/")
    return ChatCompletionsProvider(
        ChatCompletionsConfig(
            base_url=base_url or DEFAULT_BASE_URL,
            model=model,
            api_key=api_key,
            provider_id=PROVIDER_ID,
            error_label="OpenRouter API",
        )
    )
