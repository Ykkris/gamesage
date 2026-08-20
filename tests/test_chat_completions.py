"""Tests for the shared OpenAI-compatible chat-completions client."""

import base64

import pytest

from companion.vision.chat_completions import (
    ChatCompletionsConfig,
    ChatCompletionsProvider,
    build_multimodal_payload,
    extract_answer,
    load_image_data_url,
)
from companion.vision.errors import (
    InvalidImageError,
    ProviderAuthError,
    ProviderEmptyResponseError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
)
from companion.vision.models import AnalysisResult


class FakeTransport:
    """Records calls; returns a canned response or raises."""

    def __init__(self, status: int = 200, body: object = None, error: Exception | None = None):
        self.status = status
        self.body = body
        self.error = error
        self.calls: list[tuple] = []

    def post_json(self, url, *, headers, payload, timeout):
        self.calls.append((url, dict(headers), payload, timeout))
        if self.error is not None:
            raise self.error
        return self.status, self.body


def ok_body(content: str = "A useful answer.") -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def make_config(**overrides) -> ChatCompletionsConfig:
    defaults: dict = dict(base_url="https://api.example.com/v1", model="vision-model")
    defaults.update(overrides)
    return ChatCompletionsConfig(**defaults)


def make_image(tmp_path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-data")
    return image


class TestBuildMultimodalPayload:
    def test_shape(self):
        payload = build_multimodal_payload(
            "vision-model", "What is this?", "data:image/png;base64,QUJD", None
        )

        assert payload["model"] == "vision-model"
        assert "thinking" not in payload
        system, user = payload["messages"]
        assert system["role"] == "system"
        assert "GameSage" in system["content"]
        assert "Do not invent" in system["content"]
        image_part, text_part = user["content"]
        assert image_part == {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
        assert text_part == {"type": "text", "text": "What is this?"}

    def test_context_is_appended_to_system_prompt(self):
        payload = build_multimodal_payload("m", "q", "data:", "The Witcher 3: Wild Hunt")

        assert "Game context: The Witcher 3: Wild Hunt." in payload["messages"][0]["content"]

    def test_payload_extensions_are_merged(self):
        payload = build_multimodal_payload(
            "m", "q", "data:", None, payload_extensions={"thinking": {"type": "disabled"}}
        )

        assert payload["thinking"] == {"type": "disabled"}


class TestLoadImage:
    def test_reads_file_as_base64_data_url(self, tmp_path):
        image = make_image(tmp_path)

        data_url = load_image_data_url(image)

        assert data_url.startswith("data:image/png;base64,")
        assert base64.b64decode(data_url.split(",", 1)[1]) == image.read_bytes()

    def test_missing_image_raises_invalid_image(self, tmp_path):
        with pytest.raises(InvalidImageError) as excinfo:
            load_image_data_url(tmp_path / "missing.png")

        assert "could not be read" in str(excinfo.value)


class TestProviderRequests:
    def test_authorization_header_with_api_key(self, tmp_path):
        transport = FakeTransport(body=ok_body())
        provider = ChatCompletionsProvider(make_config(api_key="secret"), transport=transport)

        provider.analyze(make_image(tmp_path), "q")

        url, headers, _, _ = transport.calls[0]
        assert url == "https://api.example.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer secret"

    def test_no_authorization_header_without_api_key(self, tmp_path):
        """Local endpoints must work without a Bearer token."""
        transport = FakeTransport(body=ok_body())
        provider = ChatCompletionsProvider(make_config(api_key=None), transport=transport)

        provider.analyze(make_image(tmp_path), "q")

        _, headers, _, _ = transport.calls[0]
        assert "Authorization" not in headers

    def test_extra_headers_are_sent(self, tmp_path):
        transport = FakeTransport(body=ok_body())
        provider = ChatCompletionsProvider(
            make_config(extra_headers={"X-Custom": "1"}), transport=transport
        )

        provider.analyze(make_image(tmp_path), "q")

        assert transport.calls[0][1]["X-Custom"] == "1"

    def test_base_url_trailing_slash_is_normalized(self):
        assert make_config(base_url="https://api.example.com/v1/").endpoint_url() == (
            "https://api.example.com/v1/chat/completions"
        )

    def test_image_bytes_are_sent_verbatim(self, tmp_path):
        transport = FakeTransport(body=ok_body())
        provider = ChatCompletionsProvider(make_config(), transport=transport)
        image = make_image(tmp_path)

        provider.analyze(image, "q")

        _, _, payload, _ = transport.calls[0]
        data_url = payload["messages"][1]["content"][0]["image_url"]["url"]
        assert base64.b64decode(data_url.split(",", 1)[1]) == image.read_bytes()

    def test_payload_extensions_from_config(self, tmp_path):
        transport = FakeTransport(body=ok_body())
        provider = ChatCompletionsProvider(
            make_config(payload_extensions={"thinking": {"type": "disabled"}}),
            transport=transport,
        )

        provider.analyze(make_image(tmp_path), "q")

        assert transport.calls[0][2]["thinking"] == {"type": "disabled"}


class TestProviderAnalysis:
    def test_success_returns_result_with_provider_id(self, tmp_path):
        provider = ChatCompletionsProvider(
            make_config(provider_id="openai_compatible"),
            transport=FakeTransport(body=ok_body("  Look at the map.  ")),
        )

        result = provider.analyze(make_image(tmp_path), "Where am I?")

        assert result == AnalysisResult(
            answer="Look at the map.", provider="openai_compatible", model="vision-model"
        )

    def test_network_failure_is_wrapped_with_label(self, tmp_path):
        provider = ChatCompletionsProvider(
            make_config(error_label="AI endpoint"),
            transport=FakeTransport(error=OSError("connection refused")),
        )

        with pytest.raises(ProviderRequestError) as excinfo:
            provider.analyze(make_image(tmp_path), "q")

        assert "AI endpoint request failed" in str(excinfo.value)
        assert "connection refused" in str(excinfo.value)


class TestExtractAnswer:
    def test_auth_errors(self):
        for status in (401, 403):
            with pytest.raises(ProviderAuthError) as excinfo:
                extract_answer(status, {"error": {"message": "bad key"}}, label="OpenAI API")
            assert "OpenAI API rejected the configured API key" in str(excinfo.value)

    def test_rate_limit(self):
        with pytest.raises(ProviderRateLimitError) as excinfo:
            extract_answer(429, {}, label="OpenRouter API")
        assert "OpenRouter API rate limit" in str(excinfo.value)

    def test_http_error_includes_server_message(self):
        with pytest.raises(ProviderRequestError) as excinfo:
            extract_answer(500, {"error": {"message": "upstream down"}}, label="Z.AI API")
        assert "upstream down" in str(excinfo.value)

    def test_http_error_without_server_message_shows_status(self):
        with pytest.raises(ProviderRequestError) as excinfo:
            extract_answer(503, {}, label="AI endpoint")
        assert "HTTP 503" in str(excinfo.value)

    def test_malformed_response(self):
        with pytest.raises(ProviderResponseError):
            extract_answer(200, {})

    def test_non_string_content_is_malformed(self):
        with pytest.raises(ProviderResponseError):
            extract_answer(200, {"choices": [{"message": {"content": None}}]})

    def test_empty_answer(self):
        with pytest.raises(ProviderEmptyResponseError):
            extract_answer(200, ok_body("   "))

    def test_answer_is_trimmed(self):
        assert extract_answer(200, ok_body("  answer  ")) == "answer"
