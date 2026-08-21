"""Tests for knowledge-grounded analysis (sources in the JSON envelope)."""

from companion.api.analyze_json import (
    build_knowledge_retriever,
    build_retrieval_query,
    format_knowledge_passages,
    run_analysis,
)
from companion.games.registry import get_game
from companion.knowledge.retrieval import RetrievalHit
from companion.vision.models import AnalysisResult

from test_analyze_json import FakeProvider


def make_hit(chunk_id: str, title: str, source: str = "GameSage starter corpus") -> RetrievalHit:
    from companion.knowledge.models import KnowledgeChunk

    chunk = KnowledgeChunk(
        id=chunk_id,
        title=title,
        text=f"Passage about {title}.",
        source=source,
        url="https://example.com/page",
        license="original",
        section="Tests",
        spoiler="none",
    )
    return RetrievalHit(chunk, score=1.25)


class TestBuildRetrievalQuery:
    def test_combines_question_and_visual_context(self):
        query = build_retrieval_query("What quest?", "Location: White Orchard.")

        assert query == "What quest?\nLocation: White Orchard."

    def test_caps_visual_context(self):
        long_context = "x" * 1000

        query = build_retrieval_query("q", long_context, max_context_chars=100)

        assert query == "q\n" + "x" * 100

    def test_empty_context_uses_question_only(self):
        assert build_retrieval_query("q", "   ") == "q"


class TestFormatKnowledgePassages:
    def test_passages_are_numbered_and_attributed(self):
        passages = format_knowledge_passages([make_hit("a", "Alpha"), make_hit("b", "Beta")])

        assert passages[0].startswith("[1] Alpha (GameSage starter corpus)\nPassage about Alpha.")
        assert passages[1].startswith("[2] Beta (GameSage starter corpus)")

    def test_no_hits_yield_no_passages(self):
        assert format_knowledge_passages([]) == []


class TestRunAnalysisWithKnowledge:
    def test_sources_included_when_knowledge_used(self):
        provider = FakeProvider()
        hits = [make_hit("witcher3-quest-beast", "The Beast of White Orchard (quest)")]

        payload = run_analysis(
            "x.png",
            "How do I beat the beast?",
            provider_factory=lambda: provider,
            knowledge_retriever=lambda query: hits,
        )

        assert payload["ok"] is True
        assert payload["sources"] == [
            {
                "title": "The Beast of White Orchard (quest)",
                "source": "GameSage starter corpus",
                "url": "https://example.com/page",
            }
        ]
        # The grounded call received the formatted passage.
        answer_call = provider.calls[-1]
        assert answer_call[3] == ["[1] The Beast of White Orchard (quest) (GameSage starter corpus)\nPassage about The Beast of White Orchard (quest)."]

    def test_offtopic_question_drops_context_matched_hits(self):
        """The reported bug: scene context matches strongly, the question
        shares no term with any chunk — no Sources may be attached."""
        provider = FakeProvider(
            visual_context="White Orchard village visible, quest objective: the griffin"
        )
        hits = [
            make_hit("witcher3-quest-beast", "The Beast of White Orchard (quest)"),
            make_hit("witcher3-location", "White Orchard (location)"),
        ]

        payload = run_analysis(
            "x.png",
            "How do I repair a spaceship?",
            provider_factory=lambda: provider,
            knowledge_retriever=lambda query: hits,
        )

        assert payload["ok"] is True
        assert "sources" not in payload
        answer_call = provider.calls[-1]
        assert answer_call[3] is None  # no knowledge passages sent

    def test_sources_omitted_without_hits(self):
        payload = run_analysis(
            "x.png",
            "q",
            provider_factory=lambda: FakeProvider(),
            knowledge_retriever=lambda query: [],
        )

        assert payload["ok"] is True
        assert "sources" not in payload

    def test_retriever_receives_query_with_visual_context(self):
        provider = FakeProvider(visual_context="Visible: griffin, White Orchard")
        seen = []

        run_analysis(
            "x.png",
            "What now?",
            provider_factory=lambda: provider,
            knowledge_retriever=lambda query: seen.append(query) or [],
        )

        assert "griffin" in seen[0]
        assert "What now?" in seen[0]

    def test_default_retriever_uses_installed_packs(self):
        retriever = build_knowledge_retriever(get_game().id)

        hits = retriever("griffin attacks travelers near the village")

        assert hits, "expected a hit from the installed starter pack"
        assert all(hit.chunk.pack_id == "gamesage.witcher3.starter" for hit in hits)

    def test_analysis_with_default_retriever_includes_sources(self):
        provider = FakeProvider(visual_context="Griffin attacking travelers near White Orchard village")

        payload = run_analysis(
            "x.png",
            "How do I deal with the griffin?",
            provider_factory=lambda: provider,
        )

        assert payload["ok"] is True
        assert payload.get("sources"), "expected sources from the real local corpus"
        assert any("White Orchard" in source["title"] or "Beast" in source["title"]
                   for source in payload["sources"])
