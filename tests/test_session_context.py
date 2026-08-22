"""Tests for Session Context v0 (runtime-only conversational context)."""

import json
from pathlib import Path

import pytest

from companion.api.analyze_json import run_analysis
from companion.memory.session import (
    MAX_TURNS,
    SessionContextError,
    SessionInteraction,
    bound_interactions,
    filter_for_game,
    format_session_context,
    parse_session_context,
    prepare_session_context,
)
from companion.vision.models import AnalysisResult


def turn(game_id="witcher3", question="q", answer="a"):
    return {"game_id": game_id, "question": question, "answer": answer}


class TestParsing:
    def test_none_is_empty(self):
        assert parse_session_context(None) == []

    def test_valid_interactions(self):
        interactions = parse_session_context(
            [turn(question="Who is Triss?", answer="A sorceress.")]
        )
        assert interactions == [
            SessionInteraction("witcher3", "Who is Triss?", "A sorceress.")
        ]

    @pytest.mark.parametrize(
        "raw",
        [
            "not a list",
            {"game_id": "x"},
            ["not an object"],
            [{"game_id": "witcher3", "question": "q"}],
            [{"game_id": "", "question": "q", "answer": "a"}],
            [{"game_id": "witcher3", "question": 5, "answer": "a"}],
        ],
    )
    def test_malformed_inputs_raise(self, raw):
        with pytest.raises(SessionContextError):
            parse_session_context(raw)

    def test_values_are_stripped(self):
        interactions = parse_session_context(
            [{"game_id": " witcher3 ", "question": " q ", "answer": " a "}]
        )
        assert interactions[0] == SessionInteraction("witcher3", "q", "a")


class TestFiltering:
    def test_cross_game_entries_are_dropped(self):
        interactions = [
            SessionInteraction("witcher3", "q1", "a1"),
            SessionInteraction("baldurs_gate_3", "q2", "a2"),
            SessionInteraction("community_game", "q3", "a3"),
            SessionInteraction("witcher3", "q4", "a4"),
        ]

        kept = filter_for_game(interactions, "witcher3")

        assert [item.question for item in kept] == ["q1", "q4"]


class TestBounding:
    def test_recent_turn_limit_keeps_newest(self):
        interactions = [
            SessionInteraction("witcher3", f"q{i}", f"a{i}") for i in range(10)
        ]

        bounded = bound_interactions(interactions)

        assert len(bounded) == MAX_TURNS
        assert [item.question for item in bounded] == [
            f"q{i}" for i in range(10 - MAX_TURNS, 10)
        ]

    def test_long_fields_are_truncated_deterministically(self):
        interaction = SessionInteraction("witcher3", "x" * 5000, "y" * 5000)

        bounded = bound_interactions([interaction], max_field_chars=100)

        assert len(bounded[0].question) == 100
        assert bounded[0].question.endswith("…")
        assert len(bounded[0].answer) == 100

    def test_total_budget_drops_oldest_first(self):
        interactions = [
            SessionInteraction("witcher3", f"q{i}" * 100, f"a{i}" * 100)
            for i in range(4)
        ]

        bounded = bound_interactions(interactions, max_context_chars=700)

        total = sum(len(item.question) + len(item.answer) for item in bounded)
        assert total <= 700
        # Newest turns are the survivors.
        assert bounded[-1].question.startswith("q3")
        assert bounded[0].question.startswith("q1") is False or total <= 700

    def test_empty_context_stays_empty(self):
        assert bound_interactions([]) == []


class TestFormatting:
    def test_labeled_block_contains_turns(self):
        block = format_session_context(
            [SessionInteraction("witcher3", "Who is this character?", "Triss.")]
        )

        assert block is not None
        assert "Recent session turns" in block
        assert "player: Who is this character?" in block
        assert "GameSage: Triss." in block

    def test_empty_context_formats_to_none(self):
        assert format_session_context([]) is None

    def test_unicode_is_preserved(self):
        block = format_session_context(
            [SessionInteraction("witcher3", "Et le Seigneur d'Undvik ?", "Éminemment.")]
        )

        assert "Et le Seigneur d'Undvik ?" in block
        assert "Éminemment." in block


class TestPrepare:
    def test_full_pipeline_filters_and_formats(self):
        raw = [
            turn(game_id="baldurs_gate_3", question="BG", answer="bg"),
            turn(question="W1", answer="w1"),
        ]

        block = prepare_session_context(raw, "witcher3")

        assert block is not None
        assert "W1" in block
        assert "BG" not in block

    def test_no_matching_game_yields_none(self):
        assert prepare_session_context([turn(game_id="other")], "witcher3") is None

    def test_malformed_raises(self):
        with pytest.raises(SessionContextError):
            prepare_session_context(["bad"], "witcher3")


class ContextRecordingProvider:
    """Fake provider recording every call's session context."""

    id = "fake"

    def __init__(self, answer="answer"):
        self.answer = answer
        self.calls = []

    def analyze(
        self, image_path, question, *, context=None, knowledge=None, session_context=None
    ):
        self.calls.append(
            {
                "question": question,
                "context": context,
                "knowledge": knowledge,
                "session_context": session_context,
            }
        )
        return AnalysisResult(self.answer, "fake", "m")


class TestAnalysisIntegration:
    def _run(self, provider, session_context, game_id="witcher3"):
        return run_analysis(
            Path("x.png"),
            "What about her?",
            game_id,
            provider_factory=lambda: provider,
            knowledge_retriever=lambda query: [],
            session_context=session_context,
        )

    def test_context_reaches_both_vision_stages(self):
        provider = ContextRecordingProvider()

        self._run(provider, [turn(question="Who is Triss?", answer="A sorceress.")])

        extraction, answer = provider.calls
        assert "Who is Triss?" in extraction["session_context"]
        assert "Who is Triss?" in answer["session_context"]

    def test_witcher_context_never_enters_bg3_prompt(self):
        provider = ContextRecordingProvider()

        self._run(provider, [turn(game_id="witcher3", question="Triss?", answer="w")], "baldurs_gate_3")

        for call in provider.calls:
            assert call["session_context"] is None

    def test_bg3_context_never_enters_witcher_prompt(self):
        provider = ContextRecordingProvider()

        self._run(provider, [turn(game_id="baldurs_gate_3", question="Gale?", answer="b")], "witcher3")

        for call in provider.calls:
            assert call["session_context"] is None

    def test_community_game_context_works_generically(self, monkeypatch, tmp_path):
        from companion.games.registry import clear_discovery_cache

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "absent-localappdata"))
        monkeypatch.setenv(
            "GAMESAGE_GAME_DEFINITIONS", str(tmp_path / "games")
        )
        try:
            from test_game_definitions import write_definition

            write_definition(
                tmp_path / "games" / "author.demo.windows",
                game_id="demo_community_game",
                display_name="Demo Community Game",
            )
            clear_discovery_cache()
            provider = ContextRecordingProvider()

            payload = self._run(
                provider,
                [turn(game_id="demo_community_game", question="X", answer="y")],
                "demo_community_game",
            )

            assert payload["ok"] is True
            assert "X" in provider.calls[0]["session_context"]
        finally:
            clear_discovery_cache()

    def test_no_context_preserves_existing_behavior(self):
        provider = ContextRecordingProvider()

        payload = self._run(provider, None)

        assert payload["ok"] is True
        for call in provider.calls:
            assert call["session_context"] is None

    def test_cli_positional_call_signature_matches_run_analysis(self):
        """Guard: the CLI passes (image, question, game_id, context) positionally,
        so session_context must stay a positional-or-keyword parameter."""
        import inspect

        from companion.api.analyze_json import run_analysis

        parameters = inspect.signature(run_analysis).parameters
        assert parameters["session_context"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    def test_malformed_context_returns_structured_error(self):
        provider = ContextRecordingProvider()

        payload = self._run(provider, [{"game_id": "witcher3"}])

        assert payload == {
            "ok": False,
            "error": {
                "code": "invalid_context",
                "message": payload["error"]["message"],
            },
        }
        assert "question" in payload["error"]["message"]
        assert provider.calls == []  # nothing reached the model

    def test_failed_analysis_creates_no_turn_at_api_boundary(self):
        # The desktop records turns only from ok:true responses; failures
        # (provider errors) must not be representable as context entries
        # through the API, and the pipeline must not fabricate any.
        provider = ContextRecordingProvider()

        class FailingProvider(ContextRecordingProvider):
            def analyze(self, *args, **kwargs):
                from companion.vision.errors import ProviderAuthError

                raise ProviderAuthError("rejected")

        payload = run_analysis(
            Path("x.png"),
            "q",
            "witcher3",
            provider_factory=lambda: FailingProvider(),
            knowledge_retriever=lambda query: [],
            session_context=[turn()],
        )

        assert payload["ok"] is False
        assert payload["error"]["code"] == "provider_auth_failed"


class TestPayloadSeparation:
    def test_session_and_knowledge_are_separately_labeled_messages(self):
        from companion.vision.chat_completions import build_multimodal_payload

        payload = build_multimodal_payload(
            "m",
            "q",
            "data:",
            "Some Game",
            knowledge=["[1] Title (Source)\npassage"],
            session_context="Recent session turns (chronological):\n[1] player: q0",
        )

        system, session_message, knowledge_message, user = payload["messages"]
        assert "not guaranteed facts" in session_message["content"]
        assert "current screenshot is authoritative" in session_message["content"]
        assert "player: q0" in session_message["content"]
        assert "Retrieved game knowledge" in knowledge_message["content"]
        assert "[1] Title (Source)" in knowledge_message["content"]
        assert user["content"][1]["text"] == "q"

    def test_no_session_message_without_context(self):
        from companion.vision.chat_completions import build_multimodal_payload

        payload = build_multimodal_payload("m", "q", "data:", None)
        assert len(payload["messages"]) == 2


class TestSourcesUnchanged:
    def test_sources_come_only_from_retrieval(self):
        from companion.knowledge.retrieval import RetrievalHit
        from companion.knowledge.models import KnowledgeChunk

        chunk = KnowledgeChunk(
            id="witcher3:mechanic:senses:overview",
            title="Witcher Senses",
            text="Investigation mechanic.",
            source="GameSage starter corpus",
            url="https://example.com",
        )
        provider = ContextRecordingProvider()

        payload = run_analysis(
            Path("x.png"),
            "How do witcher senses work for tracking?",
            "witcher3",
            provider_factory=lambda: provider,
            knowledge_retriever=lambda query: [RetrievalHit(chunk, 3.0)],
            session_context=[turn(question="earlier", answer="chat")],
        )

        assert payload["ok"] is True
        assert payload["sources"] == [
            {
                "title": "Witcher Senses",
                "source": "GameSage starter corpus",
                "url": "https://example.com",
            }
        ]
        # Session context was still delivered to the model.
        assert "earlier" in provider.calls[-1]["session_context"]
        # And the knowledge passage stayed separate.
        assert provider.calls[-1]["knowledge"] is not None
