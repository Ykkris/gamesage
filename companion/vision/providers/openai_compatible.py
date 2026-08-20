"""Generic OpenAI-compatible endpoint preset.

For any chat-completions endpoint the user supplies — including local
servers (LM Studio, vLLM, Ollama's OpenAI endpoint, ...) where the API key
is usually not required. GameSage only talks to the endpoint; it never
manages local model runtimes.
"""

from __future__ import annotations

from collections.abc import Mapping

from companion.vision.chat_completions import ChatCompletionsConfig, ChatCompletionsProvider
from companion.vision.errors import ProviderNotConfiguredError

PROVIDER_ID = "openai_compatible"


def from_env(env: Mapping[str, str]) -> ChatCompletionsProvider:
    """Build a provider from generic GAMESAGE_AI_* environment variables."""
    base_url = (env.get("GAMESAGE_AI_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise ProviderNotConfiguredError(
            "Custom endpoint base URL is not configured. Set "
            "GAMESAGE_AI_BASE_URL to your endpoint (e.g. http://127.0.0.1:1234/v1)."
        )
    model = (env.get("GAMESAGE_AI_MODEL") or "").strip()
    if not model:
        raise ProviderNotConfiguredError(
            "Custom endpoint model is not configured. Set GAMESAGE_AI_MODEL "
            "to the vision-capable model exposed by your endpoint."
        )
    # Optional: many local endpoints accept requests without authentication.
    api_key = (env.get("GAMESAGE_AI_API_KEY") or "").strip() or None
    return ChatCompletionsProvider(
        ChatCompletionsConfig(
            base_url=base_url,
            model=model,
            api_key=api_key,
            provider_id=PROVIDER_ID,
            error_label="AI endpoint",
        )
    )
