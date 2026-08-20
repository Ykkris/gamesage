"""Tests for the machine-readable analysis bridge (JSON envelope)."""

import json
from pathlib import Path

from companion.api.__main__ import load_env_file, main
from companion.api.analyze_json import error_code, run_analysis
from companion.games.witcher3.detection import GAME_NAME
from companion.vision.errors import (
    InvalidImageError,
    ProviderAuthError,
    ProviderEmptyResponseError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderResponseError,
)
from companion.vision.models import AnalysisResult


class FakeProvider:
    def __init__(self, result=None, error=None):
        self.result = result or AnalysisResult(answer="An answer.", provider="zai", model="glm-4.5v")
        self.error = error
        self.calls = []

    def analyze(self, image_path, question, *, context=None):
        self.calls.append((image_path, question, context))
        if self.error is not None:
            raise self.error
        return self.result


class TestRunAnalysis:
    def test_success_envelope(self, tmp_path):
        provider = FakeProvider()

        payload = run_analysis(
            tmp_path / "shot.png", "What is this?", provider_factory=lambda: provider
        )

        assert payload == {
            "ok": True,
            "answer": "An answer.",
            "provider": "zai",
            "model": "glm-4.5v",
        }

    def test_game_context_passed_to_provider(self, tmp_path):
        provider = FakeProvider()

        run_analysis(tmp_path / "shot.png", "q", provider_factory=lambda: provider)

        image, question, context = provider.calls[0]
        assert image == tmp_path / "shot.png"
        assert question == "q"
        assert context == GAME_NAME

    def test_empty_question_rejected(self, tmp_path):
        payload = run_analysis(
            tmp_path / "shot.png", "   ", provider_factory=lambda: FakeProvider()
        )

        assert payload["error"]["code"] == "invalid_request"

    @classmethod
    def _error_payload(cls, error):
        provider = FakeProvider(error=error)
        return run_analysis(
            Path("x.png"), "q", provider_factory=lambda: provider
        )

    def test_provider_error_codes(self):
        cases = [
            (ProviderNotConfiguredError("Z.AI API key is not configured."), "provider_not_configured"),
            (InvalidImageError("The screenshot could not be read: x"), "invalid_image"),
            (ProviderAuthError("rejected"), "provider_auth_failed"),
            (ProviderRateLimitError("slow down"), "provider_rate_limited"),
            (ProviderEmptyResponseError("empty"), "provider_empty_response"),
            (ProviderResponseError("unreadable"), "provider_response_invalid"),
            (ProviderRequestError("network"), "provider_request_failed"),
        ]
        for error, expected_code in cases:
            payload = self._error_payload(error)
            assert payload["ok"] is False
            assert payload["error"]["code"] == expected_code
            assert payload["error"]["message"] == str(error)

    def test_unexpected_error_is_generic(self):
        provider = FakeProvider(error=ValueError("secret token xyz"))

        payload = run_analysis(Path("x.png"), "q", provider_factory=lambda: provider)

        assert payload["error"]["code"] == "internal_error"
        assert "secret" not in json.dumps(payload)

    def test_error_code_fallback(self):
        assert error_code(RuntimeError("x")) == "internal_error"


class TestCliAnalyze:
    def test_prints_json_and_exits_zero(self, capsys):
        provider = FakeProvider()

        code = main(
            ["analyze", "--image", "shot.png", "--question", "What?"],
            run_analyze_command=lambda image, question: (
                provider.analyze(image, question) and {}  # never runs
            )
            or {"ok": True, "answer": "a", "provider": "zai", "model": "m"},
        )

        assert code == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["ok"] is True

    def test_failure_envelope_exits_one(self, capsys):
        code = main(
            ["analyze", "--image", "shot.png", "--question", "What?"],
            run_analyze_command=lambda image, question: {
                "ok": False,
                "error": {"code": "provider_not_configured", "message": "m"},
            },
        )

        assert code == 1
        assert json.loads(capsys.readouterr().out)["ok"] is False


class TestLoadEnvFile:
    def test_loads_values_and_skips_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# comment\n"
            "\n"
            "ZAI_API_KEY='key-value'\n"
            'GAMESAGE_AI_PROVIDER="zai"\n'
            "INVALID LINE WITHOUT EQUALS\n",
            encoding="utf-8",
        )
        target: dict[str, str] = {}

        loaded = load_env_file(env_file, environ=target)

        assert loaded == 2
        assert target == {"ZAI_API_KEY": "key-value", "GAMESAGE_AI_PROVIDER": "zai"}

    def test_existing_values_are_not_overridden(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("ZAI_API_KEY=from-file\n", encoding="utf-8")
        target = {"ZAI_API_KEY": "from-env"}

        load_env_file(env_file, environ=target)

        assert target["ZAI_API_KEY"] == "from-env"

    def test_missing_file_is_silent(self, tmp_path):
        assert load_env_file(tmp_path / "absent.env", environ={}) == 0
