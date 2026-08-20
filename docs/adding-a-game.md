# Adding a game

How to add support for a new game to GameSage. The Witcher 3
(`companion/games/witcher3/`) is the reference implementation.

## The contract

A game is represented by a `GameAdapter` (see `companion/games/base.py`):

| Member               | Purpose                                                  |
| -------------------- | -------------------------------------------------------- |
| `id`                 | Stable machine id, e.g. `"witcher3"`                     |
| `display_name`       | Human name; used as vision context and in the UI         |
| `detect_window()`    | Detect the game's visible window                         |
| `save_capture()`     | Save a capture with the game's file naming               |
| `load_knowledge_corpus()` | The game's local knowledge chunks (may be empty)     |

Adapters compose their own rules with the generic layers; they do **not**
reimplement screen capture (GDI/mss lives in `companion/capture/`) or
retrieval (BM25 lives in `companion/knowledge/`).

## Steps

1. **Create the package** under `companion/games/<game_id>/`
   (e.g. `companion/games/baldursgate3/`).

2. **Keep detection rules game-side.** Define the game's executable names
   and window-title rules in the game package, then delegate to the generic
   `find_game_window(...)` in `companion/capture/window_detection.py`. See
   `witcher3/detection.py`.

3. **Expose a knowledge loader.** Put corpus entries (Markdown files with a
   `gamesage-knowledge` metadata block) under
   `companion/games/<game_id>/knowledge/corpus/` and expose a cached
   loader returning `KnowledgeChunk`s. See
   `witcher3/knowledge/sources.py`. Preserve source/license metadata and
   spoiler hints; write original summaries rather than copying wikis.

4. **Implement the adapter.** A small class satisfying `GameAdapter` that
   delegates to the modules above. See `witcher3/adapter.py`.

5. **Register it** in `companion/games/registry.py` by adding the adapter
   instance to `_GAMES`. The registry is explicit — no plugin discovery,
   entry points, or package scanning.

6. **Add tests** covering adapter metadata, detection rules (with injected
   enumerators), corpus loading, and registry lookup. Existing games must
   keep passing: `pytest`, `cargo test`, `pnpm build`.

## What must NOT go into generic core modules

`companion/capture/`, `companion/knowledge/`, `companion/vision/`, and
`companion/api/` must stay game-agnostic:

- no game ids, executable names, or window titles;
- no imports of `companion.games.<game>`;
- no `if game == "..."` branching.

Games enter generic flows only through the registry
(`get_game(game_id)`) and the `GameAdapter` it returns.

## Desktop behavior

The desktop app asks `python -m companion.api games` at startup and
displays the registry metadata; capture and analysis pass the selected
`game_id` through the Rust bridge to the Python CLI. A screenshot belongs
to the game that produced it (`game_id` in the capture envelope), and
analysis always uses the capture's game id. With a second registered game,
the header automatically renders a game selector — nothing else changes.
