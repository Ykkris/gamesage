# GameSage Knowledge Packs — Community Specification v1

A **Knowledge Pack** is a data-only add-on that teaches GameSage about a
game: quests, characters, locations, mechanics, builds, walkthrough
knowledge, mod notes, or localized names. Anyone can author and publish a
pack (for example on Nexus Mods); users drop it into a knowledge-packs
directory and GameSage picks it up. **No GameSage source-code modification,
recompilation, or update is required.**

This document is the public contract for Knowledge Pack **schema version 1**.

---

## The data-only security rule

Knowledge Packs are **declarative data**. A valid pack consists only of
text files:

```
<pack-directory>/
    manifest.toml    required — identity and compatibility
    corpus.jsonl     required — the knowledge records
    NOTICE.md        optional — attribution, license, redistribution
```

A pack must never require or ask users to run Python, JavaScript, Rust,
DLLs, executables, or shell scripts. GameSage's loader **never executes
pack content** — it only parses `manifest.toml` (TOML) and `corpus.jsonl`
(JSON Lines). If a "pack" asks you to run an installer or script, it is
not a Knowledge Pack.

Pack licensing is independent of the GameSage code license. Use
`NOTICE.md` for attribution, license, and redistribution terms; GameSage
does not interpret it, it just travels with the pack.

## Installation

Extract the pack folder into one of GameSage's knowledge-packs
directories:

- **Development/repository**: `knowledge_packs/` next to the GameSage
  checkout.
- **Windows user directory**: `%LOCALAPPDATA%\GameSage\knowledge-packs\`
- Additional roots may be provided via the `GAMESAGE_KNOWLEDGE_PACKS`
  environment variable (os-pathsep-separated).

The directory name is **not** the pack identity — `manifest.toml` is
authoritative. Discovery is automatic on the next GameSage run.

## manifest.toml

```toml
schema_version = 1
id = "someauthor.witcher3.quests"
game_id = "witcher3"
version = "1.2.0"

name = "Some Author's Witcher 3 Quest Knowledge"
author = "Some Author"
description = "Quest walkthroughs with spoiler levels."

# Optional:
homepage = "https://example.com/pack"
repository = "https://github.com/someauthor/pack"
languages = ["en"]
gamesage_min_version = "0.1.0"
gamesage_max_version = "1.0.0"
```

Required fields: `schema_version`, `id`, `game_id`, `version`, `name`,
`author`.

- **`schema_version`** must be `1`. Packs declaring other versions are
  reported as *incompatible*, not loaded.
- **`id`** must be globally distinguishable and stable. Use a namespaced
  convention `author.game.pack` with at least two dot-separated
  lowercase segments (letters, digits, `-`, `_`), e.g.
  `gamesage.witcher3.starter`, `community.bg3.builds`. Ownership is not
  verified in v1 — pick a prefix you control.
- **`game_id`** targets exactly one registered GameSage game, e.g.
  `witcher3` or `baldurs_gate_3`. This is how packs associate with games;
  the game adapter itself owns no packs.
- **`version`** is your pack's version, for humans and future tooling.
- **`gamesage_min_version` / `gamesage_max_version`** are optional
  `major.minor.patch` compatibility bounds; a pack outside the bounds is
  reported as *incompatible*.

## corpus.jsonl

One JSON object per line; blank lines are ignored. Each record:

```json
{"id": "witcher3:quest:lilac-and-gooseberries:overview", "game_id": "witcher3", "type": "quest", "title": "Lilac and Gooseberries", "text": "Lilac and Gooseberries is an early main quest...", "language": "en", "aliases": ["Lilas et groseilles"], "tags": ["quest", "main-quest"], "section": "Main quests", "spoiler": "moderate", "source": {"name": "My Pack sources", "url": "https://example.com/page", "license": "CC BY-SA 4.0"}}
```

| Field | Required | Notes |
| --- | --- | --- |
| `id` | yes | Stable, meaningful record id (see below) |
| `title` | yes | Display title |
| `text` | yes | The knowledge text (plain text; line breaks allowed) |
| `game_id` | no | If present, must equal the manifest `game_id` |
| `type` | no | e.g. `quest`, `character`, `location`, `mechanic`, `item`, `build` |
| `language` | no | Language tag of `title`/`text`, e.g. `en`, `fr` |
| `aliases` | no | Alternate/localized names; they participate in search |
| `tags` | no | Searchable topic tags |
| `section` | no | Grouping hint, e.g. "Main quests" |
| `spoiler` | no | Hint such as `none`, `light`, `moderate`, `heavy` |
| `source` | no | Provenance object: `name`, `url`, `license` |

The `source` block preserves attribution. The schema deliberately keeps
out provider-specific fields and embeddings.

### Stable record ids

Use deterministic, meaningful ids with colon-separated aspects:

```
witcher3:quest:lord-undvik:overview
witcher3:character:vesemir:overview
bg3:mechanic:advantage:overview
bg3:build:fire-wizard:overview
```

Lowercase letters, digits, and `:-_.` only; no random UUIDs. Ids must be
unique within a pack and across packs for the same game (see conflicts).

### Multilingual support

Records carry `language`, and `aliases` let one record be found under its
localized names — an English corpus can answer a French game interface:

```json
{"title": "The Lord of Undvik", "aliases": ["Le Seigneur d'Undvik"], "language": "en", ...}
```

Aliases are boosted in search exactly like titles. GameSage performs no
machine translation.

## Discovery, validation, and status

GameSage scans the knowledge-packs directories, validates every pack, and
groups it under its declared `game_id`. Each discovered pack gets one
status:

- **loaded** — validated and contributing records to its game.
- **invalid** — malformed manifest/corpus; the diagnostic names the file
  and, for corpus errors, the offending line number.
- **incompatible** — unsupported `schema_version` or GameSage version
  bounds not satisfied.
- **conflict** — duplicate pack id, or a record id already provided by
  another pack for the same game.

Fault isolation: one broken pack never breaks GameSage or other packs;
it is excluded and reported (diagnostics appear in the development
console). Status reports are exposed for a future management UI.

## Conflict policy (v1)

Conflicts are **detected and reported, never silently overwritten**:

- the first pack (in deterministic search order) wins;
- later duplicates are marked *conflict* and excluded.

There is no load order, priority, or override mechanism in v1 —
determinism over flexibility. Uninstalling a pack means deleting its
folder.

## Validating your pack

The developer CLI validates with exactly the rules runtime discovery
uses (there is no second validator):

```
python -m tools.knowledge validate path/to/your.pack
python -m tools.knowledge inspect path/to/your.pack
python -m tools.knowledge query path/to/your.pack "griffin attacks travelers"
```

`validate` prints `OK` with the record count, or the reason and corpus
line number on failure.

## Reference pack

`knowledge_packs/gamesage.witcher3.starter/` in the GameSage repository
is a complete v1 example. It passes through the same loader as any
community pack — GameSage-authored packs get no privileged path.
