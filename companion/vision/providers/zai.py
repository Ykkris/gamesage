"""Z.AI provider preset (thin configuration over the shared client).

Uses the normal Z.AI API (https://api.z.ai/api/paas/v4). The Z.AI Coding
Plan endpoint must not be used as GameSage's runtime backend. The only
Z.AI-specific behavior beyond configuration is disabling the model's
``thinking`` mode for quick prototype answers.
"""

from __future__ import annotations

from collections.abc import Mapping

from companion.vision.chat_completions import ChatCompletionsConfig, ChatCompletionsProvider
from companion.vision.errors import ProviderNotConfiguredError

PROVIDER_ID = "zai"
DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_MODEL = "glm-4.5v"


def from_env(env: Mapping[str, str]) -> ChatCompletionsProvider:
    """Build the Z.AI provider from ZAI_* environment variables."""
    api_key = (env.get("ZAI_API_KEY") or "").strip()
    if not api_key:
        raise ProviderNotConfiguredError(
            "Z.AI API key is not configured. Set ZAI_API_KEY in the "
            "environment or in the repository .env file."
        )
    base_url = (env.get("ZAI_BASE_URL") or "").strip().rstrip("/")
    model = (env.get("ZAI_VISION_MODEL") or "").strip()
    return ChatCompletionsProvider(
        ChatCompletionsConfig(
            base_url=base_url or DEFAULT_BASE_URL,
            model=model or DEFAULT_MODEL,
            api_key=api_key,
            provider_id=PROVIDER_ID,
            error_label="Z.AI API",
            payload_extensions={"thinking": {"type": "disabled"}},
        )
    )
