"""Tests for the machine-readable analysis bridge (JSON envelope)."""

import json
from pathlib import Path

from companion.api.__main__ import load_env_file, main
from companion.api.analyze_json import (
    CONTEXT_EXTRACTION_QUESTION,
    error_code,
    run_analysis,
)
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
    def __init__(self, result=None, error=None, visual_context="A visible list."):
        self.result = result or AnalysisResult(
            answer="An answer.", provider="zai", model="glm-4.5v"
        )
        self.visual_context = visual_context
        self.error = error
        self.calls = []

    def analyze(self, image_path, question, *, context=None, knowledge=None):
        self.calls.append((image_path, question, context, knowledge))
        if self.error is not None:
            raise self.error
        if question == CONTEXT_EXTRACTION_QUESTION:
            return AnalysisResult(
                answer=self.visual_context, provider="zai", model="glm-4.5v"
            )
        return self.result


def no_knowledge(query: str):
    return []


class TestRunAnalysis:
    def test_success_envelope_without_knowledge(self, tmp_path):
        provider = FakeProvider()

        payload = run_analysis(
            tmp_path / "shot.png",
            "What is this?",
            provider_factory=lambda: provider,
            knowledge_retriever=no_knowledge,
        )

        assert payload == {
            "ok": True,
            "answer": "An answer.",
            "provider": "zai",
            "model": "glm-4.5v",
        }

    def test_two_stage_flow_extraction_then_grounded_answer(self, tmp_path):
        provider = FakeProvider()
        seen_queries = []

        def recording_retriever(query):
            seen_queries.append(query)
            return []

        run_analysis(
            Path("x.png"),
            "Where am I?",
            provider_factory=lambda: provider,
            knowledge_retriever=recording_retriever,
        )

        extraction_call, answer_call = provider.calls
        assert extraction_call[1] == CONTEXT_EXTRACTION_QUESTION
        assert extraction_call[3] is None  # no knowledge for extraction stage
        assert answer_call[1] == "Where am I?"
        assert answer_call[2] == GAME_NAME
        assert len(seen_queries) == 1

    def test_visual_context_feeds_retrieval_query(self, tmp_path):
        provider = FakeProvider(visual_context="Location: White Orchard. Quest: beast.")
        seen_queries = []

        def recording_retriever(query):
            seen_queries.append(query)
            return []

        run_analysis(
            Path("x.png"),
            "What quest is this?",
            provider_factory=lambda: provider,
            knowledge_retriever=recording_retriever,
        )

        query = seen_queries[0]
        assert "What quest is this?" in query
        assert "White Orchard" in query

    def test_empty_question_rejected(self, tmp_path):
        payload = run_analysis(
            tmp_path / "shot.png",
            "   ",
            provider_factory=lambda: FakeProvider(),
            knowledge_retriever=no_knowledge,
        )

        assert payload["error"]["code"] == "invalid_request"

    @classmethod
    def _error_payload(cls, error):
        provider = FakeProvider(error=error)
        return run_analysis(
            Path("x.png"),
            "q",
            provider_factory=lambda: provider,
            knowledge_retriever=no_knowledge,
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

        payload = run_analysis(
            Path("x.png"),
            "q",
            provider_factory=lambda: provider,
            knowledge_retriever=no_knowledge,
        )

        assert payload["error"]["code"] == "internal_error"
        assert "secret" not in json.dumps(payload)

    def test_error_code_fallback(self):
        assert error_code(RuntimeError("x")) == "internal_error"


class TestCliAnalyze:
    def test_prints_json_and_exits_zero(self, capsys):
        code = main(
            ["analyze", "--image", "shot.png", "--question", "What?"],
            run_analyze_command=lambda image, question, game_id: {
                "ok": True,
                "answer": "a",
                "provider": "zai",
                "model": "m",
            },
        )

        assert code == 0
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["ok"] is True

    def test_failure_envelope_exits_one(self, capsys):
        code = main(
            ["analyze", "--image", "shot.png", "--question", "What?"],
            run_analyze_command=lambda image, question, game_id: {
                "ok": False,
                "error": {"code": "provider_not_configured", "message": "m"},
            },
        )

        assert code == 1
        assert json.loads(capsys.readouterr().out)["ok"] is False

    def test_passes_explicit_game_id_through(self, capsys):
        seen = {}

        def fake_run(image, question, game_id):
            seen["game_id"] = game_id
            return {"ok": True}

        main(
            ["analyze", "--image", "shot.png", "--question", "q", "--game", "witcher3"],
            run_analyze_command=fake_run,
        )

        assert seen["game_id"] == "witcher3"


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
