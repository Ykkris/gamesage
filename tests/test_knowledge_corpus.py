"""Tests for knowledge corpus parsing and the Witcher 3 starter corpus."""

import pytest

from companion.games.witcher3.knowledge import sources as witcher3_sources
from companion.knowledge.corpus import (
    KnowledgeFormatError,
    load_corpus_directory,
    parse_knowledge_markdown,
)

VALID_DOCUMENT = """<!-- gamesage-knowledge
id: test-entry
title: Test Entry
source: Test Source
url: https://example.com/test
license: Test License
section: Tests
spoiler: none
-->

Some body text about griffins.
"""


class TestParseKnowledgeMarkdown:
    def test_parses_metadata_and_body(self):
        chunk = parse_knowledge_markdown(VALID_DOCUMENT)

        assert chunk is not None
        assert chunk.id == "test-entry"
        assert chunk.title == "Test Entry"
        assert chunk.text == "Some body text about griffins."
        assert chunk.source == "Test Source"
        assert chunk.url == "https://example.com/test"
        assert chunk.license == "Test License"
        assert chunk.section == "Tests"
        assert chunk.spoiler == "none"

    def test_optional_fields_default_to_empty(self):
        minimal = "<!-- gamesage-knowledge\nid: x\ntitle: X\n-->\n\nBody."
        chunk = parse_knowledge_markdown(minimal)

        assert chunk is not None
        assert chunk.source == ""
        assert chunk.url == ""
        assert chunk.spoiler == ""

    def test_unmarked_document_returns_none(self):
        assert parse_knowledge_markdown("# Just markdown\n\nNo marker.") is None

    def test_comment_without_marker_returns_none(self):
        assert parse_knowledge_markdown("<!-- some other comment -->\nbody") is None

    def test_unknown_metadata_keys_are_ignored(self):
        document = (
            "<!-- gamesage-knowledge\nid: x\ntitle: X\nfuture-field: value\n-->\n\nBody."
        )
        chunk = parse_knowledge_markdown(document)
        assert chunk is not None and chunk.title == "X"

    def test_missing_id_raises(self):
        with pytest.raises(KnowledgeFormatError) as excinfo:
            parse_knowledge_markdown("<!-- gamesage-knowledge\ntitle: T\n-->\n\nBody.")
        assert "id" in str(excinfo.value)

    def test_missing_title_raises(self):
        with pytest.raises(KnowledgeFormatError):
            parse_knowledge_markdown("<!-- gamesage-knowledge\nid: x\n-->\n\nBody.")

    def test_empty_body_raises(self):
        with pytest.raises(KnowledgeFormatError):
            parse_knowledge_markdown("<!-- gamesage-knowledge\nid: x\ntitle: T\n-->\n\n  ")


class TestLoadCorpusDirectory:
    def test_loads_marked_files_in_sorted_order(self, tmp_path):
        (tmp_path / "b-entry.md").write_text(VALID_DOCUMENT, encoding="utf-8")
        (tmp_path / "a-entry.md").write_text(
            VALID_DOCUMENT.replace("test-entry", "a-entry"), encoding="utf-8"
        )
        (tmp_path / "README.md").write_text("# not knowledge", encoding="utf-8")

        chunks = load_corpus_directory(tmp_path)

        assert [chunk.id for chunk in chunks] == ["a-entry", "test-entry"]

    def test_missing_directory_yields_empty_corpus(self, tmp_path):
        assert load_corpus_directory(tmp_path / "absent") == []

    def test_duplicate_ids_raise(self, tmp_path):
        (tmp_path / "one.md").write_text(VALID_DOCUMENT, encoding="utf-8")
        (tmp_path / "two.md").write_text(VALID_DOCUMENT, encoding="utf-8")

        with pytest.raises(KnowledgeFormatError) as excinfo:
            load_corpus_directory(tmp_path)
        assert "Duplicate" in str(excinfo.value)

    def test_malformed_file_names_the_offender(self, tmp_path):
        (tmp_path / "broken.md").write_text(
            "<!-- gamesage-knowledge\nid: x\n-->\n\n", encoding="utf-8"
        )

        with pytest.raises(KnowledgeFormatError) as excinfo:
            load_corpus_directory(tmp_path)
        assert "broken.md" in str(excinfo.value)


class TestWitcher3Corpus:
    def test_loads_starter_corpus(self):
        chunks = witcher3_sources.load_corpus()

        assert len(chunks) >= 5
        ids = [chunk.id for chunk in chunks]
        assert len(ids) == len(set(ids)), "corpus ids must be unique"
        assert all(chunk.id.startswith("witcher3-") for chunk in chunks)

    def test_entries_carry_source_metadata(self):
        for chunk in witcher3_sources.load_corpus():
            assert chunk.title, chunk.id
            assert chunk.text.strip(), chunk.id
            assert chunk.source, f"{chunk.id} must name its source"
            assert chunk.license, f"{chunk.id} must record licensing"
            assert chunk.spoiler, f"{chunk.id} must declare a spoiler level"

    def test_covers_expected_topics(self):
        titles = " ".join(chunk.title for chunk in witcher3_sources.load_corpus()).lower()
        assert "white orchard" in titles
        assert "witcher senses" in titles
        assert "vesemir" in titles

    def test_corpus_loads_quickly_and_is_cached(self):
        first = witcher3_sources.load_corpus()
        second = witcher3_sources.load_corpus()
        assert first is second  # lru_cache: one parse per process
