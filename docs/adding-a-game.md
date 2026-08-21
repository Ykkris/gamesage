# Adding a game

There are two ways to make GameSage support a game:

1. **Declarative Game Definition** — preferred for ordinary games.
   A data-only `game.toml` published as a community artifact; no GameSage
   source changes. See `docs/game-definitions-v1.md`.
2. **Native GameAdapter** — a Python adapter inside GameSage source
   code, required only for behavior a definition cannot express.

Start with a Game Definition. Only write a native adapter when the game
genuinely needs custom logic (unusual window selection, special capture
handling, game-specific behavior beyond declarative rules).

## Option 1: Declarative Game Definition

Create a directory with a `game.toml` declaring the game id,
display name, executable names, and window-title match values:

```toml
schema_version = 1
id = "kingdom_come_deliverance_3"
display_name = "Kingdom Come: Deliverance III"
definition_id = "someauthor.kcd3.windows"
version = "1.0.0"
author = "Some Author"
platform = "windows"
executables = ["KingdomCome3.exe"]
window_titles = ["Kingdom Come: Deliverance III"]
window_title_mode = "starts_with"
```

Install it into `game_definitions/` (development) or
`%LOCALAPPDATA%\GameSage\games\` (users). GameSage discovers,
validates, and exposes it through the unified registry — the desktop
selector, capture, and knowledge association work automatically through
the shared `game_id`. Validation tooling:

```
python -m tools.games validate path/to/definition
python -m tools.games inspect path/to/definition
```

Knowledge comes from Knowledge Packs declaring the same `game_id`
(`docs/knowledge-packs-v1.md`); a new game ships fine without any.

## Option 2: Native GameAdapter

The `GameAdapter` interface (`companion/games/base.py`):

| Member            | Purpose                                                  |
| ----------------- | -------------------------------------------------------- |
| `id`              | Stable machine id, e.g. `"witcher3"`                     |
| `display_name`    | Human name; used as vision context and in the UI         |
| `detect_window()` | Detect the game's visible window                         |
| `save_capture()`  | Save a capture with the game's file naming               |

Adapters compose their own rules with the generic layers; they do **not**
reimplement screen capture (GDI/mss lives in `companion/capture/`) or
retrieval (BM25 lives in `companion/knowledge/`). Knowledge is not part
of the adapter: installed Knowledge Packs associate with a game through
the `game_id` declared in their manifest (see
`docs/knowledge-packs-v1.md` and `companion/knowledge/packs/`).

### Steps

1. **Create the package** under `companion/games/<game_id>/`
   (e.g. `companion/games/baldursgate3/`).

2. **Keep detection rules game-side.** Define the game's executable names
   and window-title rules in the game package, then delegate to the generic
   `find_game_window(...)` in `companion/capture/window_detection.py`. See
   `witcher3/detection.py`.

3. **Knowledge comes from packs, not the adapter.** A new game needs no
   knowledge to ship (analysis degrades gracefully to vision-only). To
   provide starter knowledge, author a Knowledge Pack targeting the new
   `game_id` — see `docs/knowledge-packs-v1.md`. Preserve source/license
   metadata and spoiler hints; write original summaries rather than
   copying wikis.

4. **Implement the adapter.** A small class satisfying `GameAdapter` that
   delegates to the modules above. See `witcher3/adapter.py`.

5. **Register it** in `companion/games/registry.py` by adding the adapter
   instance to `_NATIVE_GAMES`. The registry is explicit — no plugin
   discovery, entry points, or package scanning. Native adapters take
   precedence over declarative definitions claiming the same game id.

6. **Add tests** covering adapter metadata, detection rules (with injected
   enumerators), and registry lookup. Existing games must keep passing:
   `pytest`, `cargo test`, `pnpm build`.

## What must NOT go into generic core modules

`companion/capture/`, `companion/knowledge/`, `companion/vision/`, and
`companion/api/` must stay game-agnostic:

- no game ids, executable names, or window titles;
- no imports of `companion.games.<game>`;
- no `if game == "..."` branching.

Games enter generic flows only through the unified registry
(`get_game(game_id)`) and the `GameAdapter` it returns — whether that
adapter is native or backed by a declarative Game Definition is
invisible to consumers.

## Desktop behavior

The desktop app asks `python -m companion.api games` at startup and
displays the registry metadata (including declarative games, marked
`origin: "community"`); capture and analysis pass the selected `game_id`
through the Rust bridge to the Python CLI. A screenshot belongs to the
game that produced it (`game_id` in the capture envelope), and analysis
always uses the capture's game id. New registered games appear in the
header selector automatically — nothing else changes.
