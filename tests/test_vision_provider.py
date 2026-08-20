"""Tests for provider presets and provider selection (no real API calls)."""

import pytest

from companion.vision.chat_completions import ChatCompletionsProvider
from companion.vision.errors import ProviderNotConfiguredError
from companion.vision.factory import (
    PROVIDER_ENV_VAR,
    available_providers,
    create_provider,
)
from companion.vision.providers import openai, openai_compatible, openrouter, zai


class TestOpenaiPreset:
    def test_missing_api_key(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            openai.from_env({})
        assert "OpenAI API key is not configured" in str(excinfo.value)

    def test_defaults(self):
        provider = openai.from_env({"OPENAI_API_KEY": "k"})

        assert isinstance(provider, ChatCompletionsProvider)
        assert provider.id == "openai"
        assert provider.config.base_url == openai.DEFAULT_BASE_URL
        assert provider.config.model == openai.DEFAULT_MODEL
        assert provider.config.api_key == "k"

    def test_overrides(self):
        provider = openai.from_env(
            {
                "OPENAI_API_KEY": "k",
                "OPENAI_MODEL": "gpt-4o",
                "OPENAI_BASE_URL": "https://proxy.example.com/v1/",
            }
        )

        assert provider.config.model == "gpt-4o"
        assert provider.config.base_url == "https://proxy.example.com/v1"
        assert provider.config.endpoint_url() == "https://proxy.example.com/v1/chat/completions"


class TestOpenrouterPreset:
    def test_missing_api_key(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            openrouter.from_env({"OPENROUTER_MODEL": "vendor/model"})
        assert "OpenRouter API key is not configured" in str(excinfo.value)

    def test_model_is_required(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            openrouter.from_env({"OPENROUTER_API_KEY": "k"})
        assert "OPENROUTER_MODEL" in str(excinfo.value)
        assert "openrouter.ai/models" in str(excinfo.value)

    def test_configuration(self):
        provider = openrouter.from_env(
            {"OPENROUTER_API_KEY": "k", "OPENROUTER_MODEL": "vendor/vision-model"}
        )

        assert provider.id == "openrouter"
        assert provider.config.base_url == "https://openrouter.ai/api/v1"
        assert provider.config.model == "vendor/vision-model"
        assert provider.config.api_key == "k"


class TestOpenaiCompatiblePreset:
    def test_missing_base_url(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            openai_compatible.from_env({"GAMESAGE_AI_MODEL": "local-model"})
        assert "GAMESAGE_AI_BASE_URL" in str(excinfo.value)

    def test_missing_model(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            openai_compatible.from_env({"GAMESAGE_AI_BASE_URL": "http://127.0.0.1:1234/v1"})
        assert "GAMESAGE_AI_MODEL" in str(excinfo.value)

    def test_api_key_is_optional_for_local_endpoints(self):
        provider = openai_compatible.from_env(
            {
                "GAMESAGE_AI_BASE_URL": "http://127.0.0.1:1234/v1",
                "GAMESAGE_AI_MODEL": "local-model",
            }
        )

        assert provider.id == "openai_compatible"
        assert provider.config.api_key is None

    def test_configuration_with_api_key(self):
        provider = openai_compatible.from_env(
            {
                "GAMESAGE_AI_BASE_URL": "https://gateway.example.com/v1/",
                "GAMESAGE_AI_MODEL": "custom-model",
                "GAMESAGE_AI_API_KEY": "k",
            }
        )

        assert provider.config.base_url == "https://gateway.example.com/v1"
        assert provider.config.model == "custom-model"
        assert provider.config.api_key == "k"


class TestZaiPreset:
    def test_missing_api_key(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            zai.from_env({})
        assert "Z.AI API key is not configured" in str(excinfo.value)

    def test_defaults_and_thinking_extension(self):
        provider = zai.from_env({"ZAI_API_KEY": "k"})

        assert provider.id == "zai"
        assert provider.config.base_url == zai.DEFAULT_BASE_URL
        assert provider.config.model == zai.DEFAULT_MODEL
        assert provider.config.payload_extensions == {"thinking": {"type": "disabled"}}
        assert provider.config.error_label == "Z.AI API"

    def test_overrides(self):
        provider = zai.from_env(
            {
                "ZAI_API_KEY": "k",
                "ZAI_BASE_URL": "https://custom.example.com/api/paas/v4/",
                "ZAI_VISION_MODEL": "glm-4.6v",
            }
        )

        assert provider.config.base_url == "https://custom.example.com/api/paas/v4"
        assert provider.config.model == "glm-4.6v"


class TestCreateProvider:
    @pytest.mark.parametrize(
        "provider_id",
        ["openai", "openrouter", "openai_compatible", "zai"],
    )
    def test_selects_each_registered_provider(self, provider_id):
        env = {
            "GAMESAGE_AI_PROVIDER": provider_id,
            "OPENAI_API_KEY": "k",
            "OPENROUTER_API_KEY": "k",
            "OPENROUTER_MODEL": "vendor/model",
            "GAMESAGE_AI_BASE_URL": "http://127.0.0.1:1234/v1",
            "GAMESAGE_AI_MODEL": "local-model",
            "ZAI_API_KEY": "k",
        }

        assert create_provider(env).id == provider_id

    def test_provider_id_is_normalized(self):
        provider = create_provider({"GAMESAGE_AI_PROVIDER": "  ZAI  ", "ZAI_API_KEY": "k"})
        assert provider.id == "zai"

    def test_no_provider_selected_lists_options(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            create_provider({})
        message = str(excinfo.value)
        assert PROVIDER_ENV_VAR in message
        for provider_id in ("openai", "openrouter", "openai_compatible", "zai"):
            assert provider_id in message

    def test_unknown_provider(self):
        with pytest.raises(ProviderNotConfiguredError) as excinfo:
            create_provider({"GAMESAGE_AI_PROVIDER": "hal9000"})
        assert "'hal9000'" in str(excinfo.value)
        assert available_providers() in str(excinfo.value)
