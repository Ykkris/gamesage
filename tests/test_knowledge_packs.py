"""Tests for Knowledge Pack v1: manifest, corpus, discovery, and conflicts."""

import json

import pytest

from companion.knowledge.packs.corpus import CorpusError, load_corpus_file
from companion.knowledge.packs.manifest import (
    ManifestError,
    compatibility_problem,
    parse_manifest_file,
    parse_version,
)
from companion.knowledge.packs.registry import (
    KnowledgePackRegistry,
    default_pack_roots,
    load_pack,
)
from companion.knowledge.retrieval import retrieve

STARTER_PACK_ID = "gamesage.witcher3.starter"

#: Standard test pack directory (valid namespaced id).
PACK_DIR = "someauthor.witcher3.extra"


def write_pack(
    directory,
    pack_id=None,
    game_id="witcher3",
    version="1.0.0",
    schema_version=1,
    records=None,
    manifest_extra="",
):
    directory.mkdir(parents=True, exist_ok=True)
    if pack_id is None:
        pack_id = directory.name  # convention: manifest id matches the folder
    manifest = (
        f'schema_version = {schema_version}\n'
        f'id = "{pack_id}"\n'
        f'game_id = "{game_id}"\n'
        f'version = "{version}"\n'
        f'name = "Test Pack"\n'
        f'author = "Some Author"\n'
        f'{manifest_extra}'
    )
    (directory / "manifest.toml").write_text(manifest, encoding="utf-8")
    if records is None:
        records = [
            {
                "id": f"{game_id}:mechanic:test:overview",
                "title": "Test Record",
                "text": "A test record about alchemy bombs and grenades.",
            }
        ]
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    (directory / "corpus.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestManifest:
    def test_valid_manifest(self, tmp_path):
        write_pack(tmp_path / PACK_DIR)
        manifest = parse_manifest_file(tmp_path / PACK_DIR / "manifest.toml")

        assert manifest.id == "someauthor.witcher3.extra"
        assert manifest.game_id == "witcher3"
        assert manifest.schema_version == 1

    def test_malformed_toml(self, tmp_path):
        (tmp_path / "manifest.toml").write_text("id = [unterminated\n", encoding="utf-8")
        with pytest.raises(ManifestError) as excinfo:
            parse_manifest_file(tmp_path / "manifest.toml")
        assert "invalid TOML" in str(excinfo.value)

    def test_missing_manifest_file(self, tmp_path):
        with pytest.raises(ManifestError):
            parse_manifest_file(tmp_path / "manifest.toml")

    def test_missing_required_fields(self, tmp_path):
        (tmp_path / "manifest.toml").write_text('schema_version = 1\nid = "a.b"\n', encoding="utf-8")
        with pytest.raises(ManifestError) as excinfo:
            parse_manifest_file(tmp_path / "manifest.toml")
        assert "game_id" in str(excinfo.value)

    @pytest.mark.parametrize("pack_id", ["witcher3", "Has Upper", "no-domain!", "a..b"])
    def test_invalid_pack_id_syntax(self, tmp_path, pack_id):
        write_pack(tmp_path / PACK_DIR, pack_id=pack_id)
        with pytest.raises(ManifestError) as excinfo:
            parse_manifest_file(tmp_path / PACK_DIR / "manifest.toml")
        assert "pack id" in str(excinfo.value)

    def test_unsupported_schema_version(self, tmp_path):
        write_pack(tmp_path / PACK_DIR, schema_version=2)
        problem = load_pack(tmp_path / PACK_DIR)
        assert problem.status == "incompatible"
        assert "schema version" in problem.message


class TestVersionCompatibility:
    def test_parse_version(self):
        assert parse_version("1.2.3") == (1, 2, 3)
        assert parse_version("0.1.0-rc.1") == (0, 1, 0)
        with pytest.raises(ValueError):
            parse_version("one.two")

    def test_min_version_above_current_is_incompatible(self, tmp_path):
        write_pack(tmp_path / PACK_DIR, manifest_extra='gamesage_min_version = "99.0.0"\n')
        problem = load_pack(tmp_path / PACK_DIR)
        assert problem.status == "incompatible"
        assert "99.0.0" in problem.message

    def test_min_version_below_current_is_compatible(self, tmp_path):
        write_pack(tmp_path / PACK_DIR, manifest_extra='gamesage_min_version = "0.0.1"\n')
        result = load_pack(tmp_path / PACK_DIR)
        assert result.status == "loaded"

    def test_compatibility_problem_none_when_unbounded(self, tmp_path):
        write_pack(tmp_path / PACK_DIR)
        manifest = parse_manifest_file(tmp_path / PACK_DIR / "manifest.toml")
        assert compatibility_problem(manifest) is None


class TestCorpus:
    def test_valid_records(self, tmp_path):
        write_pack(tmp_path / PACK_DIR, records=[
            {
                "id": "witcher3:item:bomb:overview",
                "game_id": "witcher3",
                "type": "item",
                "title": "Grapeshot",
                "text": "Grapeshot is a bomb.",
                "language": "en",
                "aliases": ["Petard à mitraille"],
                "tags": ["bomb", "alchemy"],
                "section": "Items",
                "spoiler": "none",
                "source": {"name": "Test", "url": "https://example.com", "license": "CC0"},
            }
        ])
        result = load_pack(tmp_path / PACK_DIR)

        assert result.status == "loaded"
        chunk = result.records[0]
        assert chunk.language == "en"
        assert chunk.aliases == ("Petard à mitraille",)
        assert chunk.tags == ("bomb", "alchemy")
        assert chunk.spoiler == "none"
        assert chunk.source == "Test"
        assert chunk.url == "https://example.com"
        assert chunk.license == "CC0"
        assert chunk.pack_id == "someauthor.witcher3.extra"

    def test_malformed_jsonl_reports_line_number(self, tmp_path):
        write_pack(tmp_path / PACK_DIR)
        (tmp_path / PACK_DIR / "corpus.jsonl").write_text(
            '{"id": "g:x:a", "title": "t", "text": "ok"}\nnot json\n', encoding="utf-8"
        )
        problem = load_pack(tmp_path / PACK_DIR)
        assert problem.status == "invalid"
        assert "line 2" in problem.message

    def test_missing_required_record_fields(self, tmp_path):
        write_pack(tmp_path / PACK_DIR, records=[{"id": "g:x:a", "title": "no text"}])
        problem = load_pack(tmp_path / PACK_DIR)
        assert problem.status == "invalid"
        assert "text" in problem.message

    def test_duplicate_record_ids_within_pack(self, tmp_path):
        write_pack(tmp_path / PACK_DIR, records=[
            {"id": "witcher3:mechanic:dup:overview", "title": "a", "text": "x"},
            {"id": "witcher3:mechanic:dup:overview", "title": "b", "text": "y"},
        ])
        problem = load_pack(tmp_path / PACK_DIR)
        assert problem.status == "invalid"
        assert "duplicate record id" in problem.message

    def test_record_game_id_mismatch(self, tmp_path):
        write_pack(tmp_path / PACK_DIR, records=[
            {"id": "witcher3:mechanic:x:overview", "title": "t", "text": "x", "game_id": "baldurs_gate_3"},
        ])
        problem = load_pack(tmp_path / PACK_DIR)
        assert problem.status == "invalid"
        assert "baldurs_gate_3" in problem.message and "witcher3" in problem.message

    def test_missing_corpus_file(self, tmp_path):
        write_pack(tmp_path / PACK_DIR)
        (tmp_path / PACK_DIR / "corpus.jsonl").unlink()
        problem = load_pack(tmp_path / PACK_DIR)
        assert problem.status == "invalid"
        assert "corpus.jsonl" in problem.message

    def test_load_corpus_file_with_manifest(self, tmp_path):
        write_pack(tmp_path / PACK_DIR)
        manifest = parse_manifest_file(tmp_path / PACK_DIR / "manifest.toml")
        chunks = load_corpus_file(tmp_path / PACK_DIR / "corpus.jsonl", manifest)
        assert len(chunks) == 1


class TestDiscovery:
    def test_discovers_valid_external_pack(self, tmp_path):
        write_pack(tmp_path / "community.witcher3.extra")

        registry = KnowledgePackRegistry(roots=[tmp_path])

        chunks = registry.chunks_for_game("witcher3")
        assert [chunk.pack_id for chunk in chunks] == ["community.witcher3.extra"]
        assert [chunk.id for chunk in chunks] == ["witcher3:mechanic:test:overview"]

    def test_multiple_search_roots(self, tmp_path):
        write_pack(tmp_path / "a" / "author.one.witcher3.a")
        write_pack(tmp_path / "b" / "author.two.witcher3.b", records=[
            {"id": "witcher3:mechanic:other:overview", "title": "Other", "text": "different terms"}
        ])

        registry = KnowledgePackRegistry(roots=[tmp_path / "a", tmp_path / "b"])

        pack_ids = sorted(m.id for m in registry.packs_for_game("witcher3"))
        assert pack_ids == ["author.one.witcher3.a", "author.two.witcher3.b"]
        assert len(registry.chunks_for_game("witcher3")) == 2

    def test_missing_roots_are_tolerated(self, tmp_path):
        registry = KnowledgePackRegistry(roots=[tmp_path / "absent"])
        assert registry.chunks_for_game("witcher3") == ()
        assert registry.statuses() == ()

    def test_duplicate_pack_ids_conflict(self, tmp_path):
        write_pack(tmp_path / "one" / "dupe.witcher3.pack")
        write_pack(tmp_path / "two" / "dupe.witcher3.pack")

        registry = KnowledgePackRegistry(roots=[tmp_path / "one", tmp_path / "two"])

        assert len(registry.chunks_for_game("witcher3")) == 1  # first root wins
        conflicts = [s for s in registry.statuses() if s.status == "conflict"]
        assert len(conflicts) == 1
        assert "duplicate pack id" in conflicts[0].message

    def test_record_id_collision_across_packs(self, tmp_path):
        write_pack(tmp_path / "author.one.witcher3.a", pack_id="author.one.witcher3.a")
        write_pack(tmp_path / "author.two.witcher3.b", pack_id="author.two.witcher3.b")
        # Same record id in both packs.

        registry = KnowledgePackRegistry(roots=[tmp_path])

        chunks = registry.chunks_for_game("witcher3")
        assert len(chunks) == 1
        assert chunks[0].pack_id == "author.one.witcher3.a"  # deterministic winner
        conflicts = [s for s in registry.statuses() if s.status == "conflict"]
        assert len(conflicts) == 1
        assert "another pack" in conflicts[0].message

    def test_invalid_pack_does_not_destroy_valid_unrelated_pack(self, tmp_path):
        write_pack(tmp_path / "author.bg3.good", game_id="baldurs_gate_3")
        write_pack(tmp_path / "broken.witcher3.pack", records=None)
        (tmp_path / "broken.witcher3.pack" / "manifest.toml").write_text(
            "not valid toml = = =\n", encoding="utf-8"
        )

        registry = KnowledgePackRegistry(roots=[tmp_path])

        assert len(registry.chunks_for_game("baldurs_gate_3")) == 1
        invalid = [s for s in registry.statuses() if s.status == "invalid"]
        assert len(invalid) == 1
        assert "broken.witcher3.pack" == invalid[0].pack_id

    def test_default_roots_include_repo_and_user_directories(self):
        roots = default_pack_roots(env={"LOCALAPPDATA": r"C:\Users\x\AppData\Local"})
        assert str(roots[0]) == "knowledge_packs"
        assert "GameSage" in str(roots[1]) and "knowledge-packs" in str(roots[1])

    def test_extra_roots_from_environment(self):
        roots = default_pack_roots(
            env={"LOCALAPPDATA": "", "GAMESAGE_KNOWLEDGE_PACKS": r"D:\extra;D:\more"}
        )
        assert str(roots[-2]) == r"D:\extra"
        assert str(roots[-1]) == r"D:\more"


class TestStarterPackMigration:
    def test_starter_pack_loads_through_standard_discovery(self):
        registry = KnowledgePackRegistry()
        chunks = registry.chunks_for_game("witcher3")

        assert len(chunks) == 5
        assert {chunk.pack_id for chunk in chunks} == {STARTER_PACK_ID}
        ids = {chunk.id for chunk in chunks}
        assert "witcher3:quest:beast-of-white-orchard:overview" in ids
        assert "witcher3:mechanic:witcher-senses:overview" in ids

    def test_original_text_preserved(self):
        registry = KnowledgePackRegistry()
        beast = next(
            chunk
            for chunk in registry.chunks_for_game("witcher3")
            if chunk.id == "witcher3:quest:beast-of-white-orchard:overview"
        )
        assert "griffin has been attacking travelers" in beast.text
        assert beast.source == "GameSage starter corpus"
        assert beast.url.startswith("https://witcher.fandom.com/wiki/")
        assert "CC BY-SA" in beast.license

    def test_starter_pack_status_is_loaded(self):
        statuses = {
            status.pack_id: status
            for status in KnowledgePackRegistry().statuses()
        }
        starter = statuses.get(STARTER_PACK_ID)
        assert starter is not None and starter.status == "loaded"
        assert "5 records" in starter.message


class TestAliasesInRetrieval:
    def test_french_alias_finds_english_record(self):
        registry = KnowledgePackRegistry()
        chunks = registry.chunks_for_game("witcher3")

        hits = retrieve("lilas et groseilles", chunks)

        assert hits, "localized alias query must retrieve the English record"
        assert hits[0].chunk.id == "witcher3:quest:lilac-and-gooseberries:overview"

    def test_alias_participates_in_anchor_gate(self):
        from companion.knowledge.retrieval import has_any_term, tokenize

        registry = KnowledgePackRegistry()
        chunk = next(
            c for c in registry.chunks_for_game("witcher3")
            if c.id == "witcher3:quest:lilac-and-gooseberries:overview"
        )
        assert has_any_term(chunk, tokenize("groseilles"))


class TestExternalPackAcceptance:
    """Core acceptance test: a third-party pack outside the repository pack
    directory is discovered, validated, associated, and retrievable — with
    no GameSage source-code registration."""

    def test_full_external_pack_flow(self, tmp_path):
        external_root = tmp_path / "downloads" / "unzipped-somewhere"
        write_pack(
            external_root / "someauthor.bg3.builds",
            pack_id="someauthor.bg3.builds",
            game_id="baldurs_gate_3",
            records=[
                {
                    "id": "bg3:build:fire-wizard:overview",
                    "type": "build",
                    "title": "Fire Wizard build",
                    "text": "A fire-damage evocation wizard build using fire bolt and fireball.",
                    "tags": ["build", "wizard"],
                }
            ],
        )

        registry = KnowledgePackRegistry(roots=[external_root])

        chunks = registry.chunks_for_game("baldurs_gate_3")
        assert [chunk.pack_id for chunk in chunks] == ["someauthor.bg3.builds"]

        hits = retrieve("fire wizard build fireball", chunks)
        assert hits and hits[0].chunk.id == "bg3:build:fire-wizard:overview"

    def test_starter_pack_uses_same_validation_as_community_packs(self, tmp_path):
        from companion.knowledge.packs.registry import default_pack_roots

        # The starter pack is loaded by the exact same load_pack() used for
        # the external community pack above — no special-cased path exists.
        repo_root = default_pack_roots()[0]
        write_pack(tmp_path / "x.y.z")
        starter = load_pack(repo_root / STARTER_PACK_ID)
        external = load_pack(tmp_path / "x.y.z")

        assert starter.status == external.status == "loaded"
