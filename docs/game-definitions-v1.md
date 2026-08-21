# GameSage Game Definitions — Community Specification v1

A **Game Definition** is a data-only add-on that teaches GameSage to
detect and capture a game it does not know: executable names plus
window-title match values. For ordinary PC games, installing a definition
is enough — no GameSage source-code modification, recompilation, or
update is required, and compatible Knowledge Packs using the same
`game_id` work automatically.

Games needing behavior that declarative rules cannot express remain
native Python `GameAdapter`s inside GameSage (see
`docs/adding-a-game.md`).

This document is the public contract for Game Definition **schema
version 1**.

---

## The data-only security rule

Game Definitions are **declarative data**. A definition is a single
TOML file (plus optional notices):

```
<definition-directory>/
    game.toml     required — identity and detection rules
    NOTICE.md     optional — attribution, license, redistribution
```

A definition must never require or ask users to run Python, JavaScript,
Rust, DLLs, executables, or shell scripts, and it cannot contain
arbitrary commands or regular-expression code execution. GameSage's
trusted loader only parses `game.toml`; it never executes, imports, or
generates code from definition directories. Window matching uses fixed
declarative modes — exact, `starts_with`, `contains` — not regex. If a
"definition" asks you to run an installer or script, it is not a Game
Definition.

## Installation

Extract the definition folder into one of GameSage's games directories:

- **Development/repository**: `game_definitions/` next to the GameSage
  checkout.
- **Windows user directory**: `%LOCALAPPDATA%\GameSage\games\`
- Additional roots may be provided via the `GAMESAGE_GAME_DEFINITIONS`
  environment variable (Windows path list, `;`-separated).

The directory name is **not** the definition identity — `game.toml` is
authoritative. Discovery is automatic; restart GameSage and the game
appears in the same selector as built-in games. Uninstalling means
deleting the folder.

## game.toml

```toml
schema_version = 1

id = "kingdom_come_deliverance_3"
display_name = "Kingdom Come: Deliverance III"

definition_id = "community.kingdomcome3"
version = "1.0.0"
author = "Community Author"

platform = "windows"

executables = [
    "KingdomCome3.exe",
    "KingdomCome3DX11.exe",
]

window_titles = [
    "Kingdom Come: Deliverance III",
]
window_title_mode = "starts_with"
```

Required fields: `schema_version`, `id`, `display_name`,
`definition_id`, `version`, `author`, `executables`, `window_titles`.
Optional: `platform` (default `"windows"` — the only value in v1),
`window_title_mode` (default `"starts_with"`), `description`,
`homepage`, `repository`, `gamesage_min_version`,
`gamesage_max_version`.

### Two identities

- **`id`** — the stable GameSage **game id** that everything else links
  to (Knowledge Packs declare this same value). Lowercase snake_case,
  e.g. `kingdom_come_deliverance_3`.
- **`definition_id`** — the identity of *this particular definition*
  (yours). Namespaced lowercase dot-separated segments, e.g.
  `someauthor.kcd3.windows` — same convention as Knowledge Pack ids.
  Ownership is not verified in v1; pick a prefix you control.

### Detection rules

- **`executables`**: process image names, case-insensitive, `.exe`.
  Multiple entries cover alternate launchers/renderers. Detection uses
  GameSage's generic process/window enumeration (no new Win32 code).
- **`window_titles`**: match values, case-insensitive, combined with
  `window_title_mode`:
  - `exact` — the window title equals a value;
  - `starts_with` — the title begins with a value (recommended default;
    tolerant of suffixes like " — Main Menu");
  - `contains` — a value appears anywhere in the title (use for titles
    with changing prefixes such as "*Untitled - Notepad").
- If a game process is running but its visible windows do not match the
  declared titles, the generic PID-ownership fallback still selects the
  largest visible window of that process.

### Version compatibility

`schema_version` must be `1`. `gamesage_min_version` /
`gamesage_max_version` are optional `major.minor.patch` bounds checked
against the running GameSage (same philosophy as Knowledge Packs).

## Statuses, conflicts, and precedence

Each discovered definition gets one status:

- **loaded** — validated; the game appears in the registry and selector.
- **invalid** — malformed TOML or rule violations; the diagnostic names
  the reason.
- **incompatible** — unsupported `schema_version` or GameSage version
  bounds not satisfied.
- **conflict** — see below.

Conflict policy (detected and reported, never silently overridden):

- **Duplicate `definition_id`** — the first in deterministic scan order
  wins; later copies conflict.
- **Duplicate `game_id` between definitions** — first wins; the later
  definition conflicts.
- **Native game id collision** — a definition declaring a `game_id`
  already provided by a built-in native adapter (e.g. `witcher3`)
  conflicts and is ignored: **native adapters always take precedence**.
  Adapter overrides, load order, and priorities are future work.

Fault isolation: one broken definition never breaks the registry or
other games; diagnostics appear in the development console, and status
reports are exposed for a future management UI.

## Knowledge Pack association

Knowledge Packs link to a game through `game_id` — nothing else. If a
definition introduces `kingdom_come_deliverance_3` and an independently
installed Knowledge Pack declares the same `game_id`, GameSage
associates them automatically, regardless of who authored either. A
game with no packs works exactly like a native game without knowledge:
capture → vision answer → no Sources section.

## Validation commands

The developer CLI uses exactly the runtime validation rules — there is
no separate validator:

```
python -m tools.games validate path/to/your.definition
python -m tools.games inspect path/to/your.definition
```

## Example: a safe manual test

A temporary definition using an ordinary Windows application proves the
external-install flow without a new game:

```
%LOCALAPPDATA%\GameSage\games\gamesage.notepad.demo\game.toml
```

```toml
schema_version = 1
id = "gamesage_notepad_demo"
display_name = "GameSage Notepad Demo"
definition_id = "gamesage.notepad.demo"
version = "1.0.0"
author = "You"
platform = "windows"
executables = ["notepad.exe"]
window_titles = ["Notepad"]
window_title_mode = "contains"
```

Restart GameSage, select "GameSage Notepad Demo", and capture. Such a
demo definition must not be published as a real game.

## When a native GameAdapter is still required

Declarative definitions cover games whose support fits: executable
names + window titles + generic screen capture + knowledge packs. Write
a native adapter (in GameSage source code) when a game needs behavior
rules cannot express — custom window-selection heuristics, unusual
capture handling, or game-specific logic. See `docs/adding-a-game.md`.
