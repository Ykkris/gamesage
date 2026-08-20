"""OpenAI provider preset (thin configuration over the shared client)."""

from __future__ import annotations

from collections.abc import Mapping

from companion.vision.chat_completions import ChatCompletionsConfig, ChatCompletionsProvider
from companion.vision.errors import ProviderNotConfiguredError

PROVIDER_ID = "openai"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4.1-mini"


def from_env(env: Mapping[str, str]) -> ChatCompletionsProvider:
    """Build the OpenAI provider from OPENAI_* environment variables."""
    api_key = (env.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ProviderNotConfiguredError(
            "OpenAI API key is not configured. Set OPENAI_API_KEY in the "
            "environment or in the repository .env file."
        )
    base_url = (env.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
    model = (env.get("OPENAI_MODEL") or "").strip()
    return ChatCompletionsProvider(
        ChatCompletionsConfig(
            base_url=base_url or DEFAULT_BASE_URL,
            model=model or DEFAULT_MODEL,
            api_key=api_key,
            provider_id=PROVIDER_ID,
            error_label="OpenAI API",
        )
    )
