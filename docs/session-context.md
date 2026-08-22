# Session Context v0

Session Context gives consecutive questions during one GameSage runtime
conversational continuity: "And what about her?" can resolve "her"
against the previous question and answer instead of starting from
nothing.

## What it is — and is not

Session Context v0 is **runtime-only**:

- the recent-turn list lives in the desktop application's memory
  (per game), never on disk;
- restarting GameSage starts with empty context;
- only the **last 4 successful interactions** per game are kept
  (newest win), with a 4000-character total budget and 1500-character
  per-field caps — deterministic character-based bounds, no tokenizer;
- only successful answers become turns; failures (provider errors,
  cancelled requests) never pollute context.

It is deliberately **not** long-term Memory. Persistent memory —
romance preferences, quest decisions, cross-session playthrough state —
is a future milestone with its own design. Session Context is a
conversational sliding window, nothing more.

## Per-game isolation

Context is keyed by `game_id` and follows the same ownership rule as
Ask: a screenshot carries the `game_id` of the game that produced it,
and both the context sent with a question and the turn recorded after a
successful answer use that owner id — never the current selector.
Witcher context can never reach a Baldur's Gate 3 prompt or vice versa;
trusted Python (`companion/memory/session.py`) additionally filters
cross-game entries defensively, so the invariant holds even if a caller
misbehaves.

Each game keeps its own independent window: switching games preserves
the other game's context for the rest of the runtime.

## How it crosses the one-shot boundary

The Python core stays one-shot. The desktop transports the bounded turn
list explicitly with each analyze request: React → Tauri → structured
JSON over **stdin** to `python -m companion.api analyze --context -` →
JSON envelope back. No daemon, no files, no environment variables. CLI
use without `--context` behaves exactly as before.

## Prompt integration

Session context is formatted by trusted Python into a labeled
"Recent session turns" block delivered to both analysis stages (visual
context extraction and the final answer) as its **own system message**,
separate from Knowledge Pack evidence. The wording states that:

- earlier GameSage replies are previous model output, **not guaranteed
  facts**;
- they may be used only to resolve references and continuity;
- the **current screenshot is authoritative** for what is visible now;
- retrieved Knowledge Pack content remains the preferred source for
  game facts.

Retrieval itself is unchanged (BM25, score floor, anchor gate, coverage
rule) — session context improves the visual extraction, and the better
resolved current context improves retrieval indirectly. Session turns
never appear in the Sources UI; Sources remain Knowledge Pack
provenance only.

## Clearing

The Assistant view shows "Context: N recent turns" with a **Clear
context** action. It clears only the relevant game's turns — the
screenshot owner when a capture exists, otherwise the selected game.
