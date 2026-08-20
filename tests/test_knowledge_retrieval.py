"""Tests for the deterministic lexical retriever."""

from companion.knowledge.models import KnowledgeChunk
from companion.knowledge.retrieval import has_any_term, retrieve, tokenize

GRAFFIN = KnowledgeChunk(
    id="a-griffin",
    title="Griffin attacks",
    text="A griffin attacks travelers near the village. Blood trails and claw marks lead to the nest.",
)
SORCERESS = KnowledgeChunk(
    id="b-sorceress",
    title="Missing sorceress",
    text="The sorceress left camp following the scent of lilac. Her trail points toward the islands.",
)
COMBAT = KnowledgeChunk(
    id="c-combat",
    title="Sword fighting basics",
    text="Fast attacks suit humans; strong attacks pierce armor. Dodge and roll to avoid damage.",
)
CORPUS = [GRAFFIN, SORCERESS, COMBAT]


class TestTokenize:
    def test_normalizes_case_and_punctuation(self):
        assert tokenize("Griffin-attacks, TRAVELERS!") == ["griffin", "attacks", "travelers"]

    def test_drops_stopwords_and_short_tokens(self):
        assert tokenize("the is a of to it how and") == []

    def test_keeps_numbers_and_unicode(self):
        # Unicode letters are preserved as-is (consistent for query and docs).
        assert tokenize("3 witchers élixirs") == ["witchers", "élixirs"]


class TestRetrieve:
    def test_ranks_relevant_chunk_first(self):
        hits = retrieve("griffin attacking travelers", CORPUS)

        assert hits[0].chunk.id == "a-griffin"
        assert all(hit.score > 0 for hit in hits)

    def test_irrelevant_query_returns_no_results(self):
        assert retrieve("spaceship navigation tutorial", CORPUS) == []

    def test_stopword_only_query_returns_no_results(self):
        assert retrieve("the of and", CORPUS) == []

    def test_limit_restricts_result_count(self):
        wide_query = "attack sorceress sword"
        full = retrieve(wide_query, CORPUS, limit=10, min_score=0)
        limited = retrieve(wide_query, CORPUS, limit=1, min_score=0)

        assert len(full) >= 2
        assert [hit.chunk.id for hit in limited] == [full[0].chunk.id]
        assert limited[0].score == full[0].score

    def test_title_match_outranks_body_only_match(self):
        body_only = KnowledgeChunk(
            id="d-body",
            title="Unrelated title",
            text="The griffin appears only deep inside this long body text about other things.",
        )
        title_match = KnowledgeChunk(
            id="e-title",
            title="Griffin",
            text="Brief text.",
        )

        hits = retrieve("griffin", [body_only, title_match], min_score=0)

        assert hits[0].chunk.id == "e-title"

    def test_results_preserve_source_metadata(self):
        hits = retrieve("griffin attacks travelers near the village", CORPUS)

        assert hits, "strongly matching query must survive the score floor"
        top = hits[0].chunk
        assert top is GRAFFIN
        assert top.title == "Griffin attacks"

    def test_ties_are_deterministic(self):
        one = KnowledgeChunk(id="x", title="Same", text="alpha")
        two = KnowledgeChunk(id="y", title="Same", text="alpha")
        for _ in range(3):
            hits = retrieve("alpha", [two, one], min_score=0)
            assert [hit.chunk.id for hit in hits[:2]] == ["x", "y"]

    def test_empty_corpus_returns_no_results(self):
        assert retrieve("griffin", []) == []

    def test_scoring_favors_rare_terms(self):
        # "lilac" appears in one chunk; "attacks" in two. A rare-term query
        # must outscore a common-term one for the same chunk.
        rare = retrieve("lilac", CORPUS, min_score=0)[0].score
        common = retrieve("attacks", CORPUS, min_score=0)[0].score
        assert rare > common


class TestRelevanceGate:
    """The default score floor suppresses weak lexical coincidences."""

    def test_clearly_irrelevant_query_returns_no_hits(self):
        assert retrieve("How do I repair a spaceship?", CORPUS) == []

    def test_weak_accidental_token_overlap_returns_no_hits(self):
        # Only the common term "village" matches; the score stays under the floor.
        assert retrieve("spaceship engine village", CORPUS) == []

    def test_relevant_rare_single_term_query_still_works(self):
        # A distinctive single term must clear the floor on the real corpus.
        from companion.games.witcher3.knowledge.sources import load_corpus

        hits = retrieve("vesemir", load_corpus())

        assert hits[0].chunk.id == "witcher3-character-vesemir"

    def test_relevant_distinctive_term_query_still_works(self):
        assert retrieve("griffin", CORPUS)[0].chunk.id == "a-griffin"

    def test_floor_can_be_disabled_for_raw_ranking(self):
        assert retrieve("spaceship engine village", CORPUS, min_score=0) != []

    def test_witcher3_corpus_preserves_good_queries(self):
        from companion.games.witcher3.knowledge.sources import load_corpus

        corpus = load_corpus()
        assert (
            retrieve("How do Witcher Senses help me investigate tracks?", corpus)[0].chunk.id
            == "witcher3-mechanic-witcher-senses"
        )
        assert (
            retrieve("griffin attacking travelers", corpus)[0].chunk.id
            == "witcher3-quest-beast-of-white-orchard"
        )

    def test_witcher3_corpus_rejects_irrelevant_query(self):
        from companion.games.witcher3.knowledge.sources import load_corpus

        assert retrieve("How do I repair a spaceship?", load_corpus()) == []


class TestHasAnyTerm:
    def test_matches_on_title_or_text(self):
        assert has_any_term(GRAFFIN, ["griffin"])
        assert has_any_term(GRAFFIN, ["travelers", "nothing"])

    def test_no_match_returns_false(self):
        assert not has_any_term(GRAFFIN, ["spaceship"])

    def test_empty_terms_matches_everything(self):
        assert has_any_term(GRAFFIN, [])
