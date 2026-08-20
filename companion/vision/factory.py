"""Vision provider selection from environment configuration.

Selection is explicit: ``GAMESAGE_AI_PROVIDER`` must name one of the
registered providers. No commercial provider is the architectural default.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from companion.vision.errors import ProviderNotConfiguredError
from companion.vision.provider import VisionProvider
from companion.vision.providers import openai, openai_compatible, openrouter, zai

PROVIDER_ENV_VAR = "GAMESAGE_AI_PROVIDER"

ProviderBuilder = Callable[[Mapping[str, str]], VisionProvider]

_BUILDERS: dict[str, ProviderBuilder] = {
    openai.PROVIDER_ID: openai.from_env,
    openrouter.PROVIDER_ID: openrouter.from_env,
    openai_compatible.PROVIDER_ID: openai_compatible.from_env,
    zai.PROVIDER_ID: zai.from_env,
}


def available_providers() -> str:
    """Comma-separated list of supported provider identifiers."""
    return ", ".join(sorted(_BUILDERS))


def create_provider(env: Mapping[str, str] | None = None) -> VisionProvider:
    """Build the provider selected by ``GAMESAGE_AI_PROVIDER``.

    Raises:
        ProviderNotConfiguredError: no provider selected, unknown provider
            id, or missing provider configuration (e.g. an API key).
    """
    source = os.environ if env is None else env
    provider_id = (source.get(PROVIDER_ENV_VAR) or "").strip().lower()
    if not provider_id:
        raise ProviderNotConfiguredError(
            f"No AI provider is configured. Set {PROVIDER_ENV_VAR} to one "
            f"of: {available_providers()}."
        )
    builder = _BUILDERS.get(provider_id)
    if builder is None:
        raise ProviderNotConfiguredError(
            f"The AI provider '{provider_id}' is not supported. Available "
            f"providers: {available_providers()}."
        )
    return builder(source)
