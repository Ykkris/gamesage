# AGENTS.md

## Project Overview

**GameSage** is an open-source AI gaming companion.

Its long-term goal is to understand what is happening in a game, retrieve relevant knowledge, and provide contextual help without forcing the player to leave the game.

The project begins deliberately small with **The Witcher 3: Wild Hunt** as the first supported game.

Current milestone:

**v0.1 — See & Ask**

The immediate goal is to build a reliable desktop pipeline before adding advanced AI features.

---

# Core Principles

## 1. Keep the prototype small

Do not overengineer the project.

Prefer the simplest implementation that satisfies the current milestone.

Do not introduce infrastructure for hypothetical future requirements unless it is required by the current feature.

Avoid adding technologies such as:

* Docker
* Kubernetes
* PostgreSQL
* Redis
* message queues
* LangChain
* large orchestration frameworks
* complex dependency injection frameworks
* microservices

unless explicitly requested and justified.

GameSage is currently a desktop application prototype, not a distributed platform.

---

## 2. Preserve the multi-game architecture

GameSage must not become hardcoded around The Witcher 3.

Game-specific behavior belongs under:

```text
companion/games/<game>/
```

The Witcher 3 code belongs under:

```text
companion/games/witcher3/
```

Reusable systems belong in the GameSage core.

Examples:

```text
companion/capture/
companion/vision/
companion/knowledge/
companion/llm/
companion/memory/
companion/api/
```

Do not add checks throughout the core such as:

```python
if game == "witcher3":
    ...
```

Prefer game adapters, interfaces, configuration, or game-specific implementations.

The architecture should make future support for games such as Baldur's Gate 3, Kingdom Come, Cyberpunk 2077, or others possible without rewriting the core.

---

## 3. Separate desktop UI from the Python companion core

The repository currently contains two main areas:

```text
apps/desktop/
```

Tauri 2 + React + TypeScript desktop application.

```text
companion/
```

Python GameSage core.

Do not move GameSage AI, retrieval, game knowledge, or capture logic into React unless there is a strong technical reason.

Do not place frontend UI concerns inside the Python core.

The boundary between both components should remain explicit.

---

# Current Architecture

```text
GameSage/
│
├── apps/
│   └── desktop/
│       ├── src/
│       └── src-tauri/
│
├── companion/
│   ├── api/
│   ├── capture/
│   ├── games/
│   │   └── witcher3/
│   ├── knowledge/
│   ├── llm/
│   ├── memory/
│   └── vision/
│
├── docs/
├── tests/
├── pyproject.toml
├── README.md
└── AGENTS.md
```

---

# Technology Stack

Current stack:

* Tauri 2
* React
* TypeScript
* Rust
* Python 3.12
* pnpm

Do not replace core technologies without explicit approval.

In particular:

* do not replace Tauri with Electron;
* do not replace React without a concrete reason;
* do not replace Python as the AI/game-companion core;
* do not introduce another JavaScript package manager.

Use **pnpm** for the desktop frontend.

GameSage currently targets Python:

```text
>=3.12,<3.13
```

Do not assume Python 3.13 or 3.14 compatibility.

---

# v0.1 Scope — See & Ask

The first milestone should evolve through small, testable steps.

Target pipeline:

```text
The Witcher 3 running
        ↓
Detect game window
        ↓
User presses hotkey
        ↓
Capture game window
        ↓
Display captured image
        ↓
Analyze context
        ↓
User asks a question
        ↓
Retrieve relevant game knowledge
        ↓
Generate contextual answer
        ↓
Display answer
```

The order matters.

Do not implement the entire pipeline at once.

---

# Current Development Priorities

Development should currently proceed approximately in this order:

1. Detect The Witcher 3 process/window.
2. Capture the game window on demand.
3. Add a configurable global hotkey.
4. Send/display the capture in the desktop application.
5. Define a generic vision-provider interface.
6. Add one initial vision provider.
7. Extract structured context from screenshots.
8. Introduce the first Witcher 3 knowledge source.
9. Implement simple retrieval.
10. Generate contextual answers.
11. Add session context.
12. Improve UX.

Voice, overlays, proactive monitoring, and multi-game support are later milestones.

---

# Explicitly Out of Scope for Early v0.1

Unless specifically requested, do not implement:

* continuous video capture;
* real-time 30/60 FPS vision analysis;
* DirectX hooking;
* DLL injection;
* game memory reading;
* game process manipulation;
* anti-cheat interaction;
* automatic gameplay;
* automated input;
* voice recognition;
* text-to-speech;
* ElevenLabs integration;
* complex overlays;
* cloud accounts;
* user authentication;
* multiplayer support;
* telemetry;
* analytics;
* remote databases.

Initial screen capture should be user-triggered.

---

# Game Safety Boundary

GameSage is an informational companion.

The initial architecture must remain based on observing normal user-visible game information.

Do not implement cheats, memory manipulation, packet manipulation, game automation, or anti-cheat bypass functionality.

The initial target is single-player gameplay assistance.

---

# Capture System

Screen/window capture belongs under:

```text
companion/capture/
```

Game identification belongs either in a reusable game/window detection component or in the relevant game adapter.

The capture implementation should eventually expose a generic interface rather than being tied directly to Witcher 3.

Conceptually:

```python
class CaptureProvider:
    def capture(self, target):
        ...
```

Exact interfaces may evolve.

Avoid premature abstractions, but preserve clear boundaries.

For the first implementation, prioritize:

* reliability;
* correct game-window bounds;
* Windows support;
* low complexity;
* useful errors.

Do not optimize for high-frequency capture yet.

---

# Game Adapters

Each supported game exposes game-specific behavior through the established `GameAdapter` interface in:

```text
companion/games/base.py
```

with an explicit registry in:

```text
companion/games/registry.py
```

The current contract (id, display name, window detection, capture naming, knowledge corpus) and the steps for adding a new game are documented in:

```text
docs/adding-a-game.md
```

Generic modules (`companion/capture/`, `companion/knowledge/`, `companion/vision/`, `companion/api/`) must not import concrete games; they resolve adapters through the registry.

The first adapter is:

```text
companion/games/witcher3/
```

Potential Witcher 3 process/window names should be defined there rather than spread through unrelated modules.

---

# AI Provider Design

GameSage must not depend permanently on a single AI provider.

Future AI functionality should be implemented behind provider abstractions.

Potential providers may include:

* OpenAI
* Z.AI
* OpenRouter
* local models
* other compatible APIs

Do not hardcode API-specific behavior into the rest of the application.

Conceptual example:

```python
class VisionProvider:
    async def analyze(self, image, prompt):
        ...
```

and:

```python
class LLMProvider:
    async def complete(self, messages):
        ...
```

Exact APIs should remain simple and evolve from actual requirements.

---

# Secrets and Configuration

Never commit:

* API keys;
* access tokens;
* passwords;
* private endpoints;
* credentials.

Use environment variables or local configuration.

`.env` files must remain ignored by Git.

When configuration examples become necessary, use:

```text
.env.example
```

with placeholder values only.

Example:

```text
ZAI_API_KEY=
OPENAI_API_KEY=
```

Never place real credentials in tests, examples, documentation, or commits.

---

# Knowledge and Retrieval

Knowledge retrieval belongs under:

```text
companion/knowledge/
```

Game knowledge is delivered through **Knowledge Packs** — data-only,
community-authorable directories discovered from the knowledge-packs
search roots and associated with a game by the `game_id` declared in their
manifest:

```text
knowledge_packs/<pack-id>/manifest.toml + corpus.jsonl + NOTICE.md
%LOCALAPPDATA%\GameSage\knowledge-packs\<pack-id>\...
```

The pack loader/registry lives under `companion/knowledge/packs/`; the
public format specification is `docs/knowledge-packs-v1.md`. Game
adapters do not own knowledge packs. Packs must remain declarative data —
the loader never executes pack content.

Do not immediately introduce a vector database.

For the first usable retrieval prototype, prefer the simplest local solution capable of validating the concept.

A more complex retrieval system can be introduced when data volume justifies it.

---

# Spoilers

Spoiler awareness is an important future GameSage feature.

Architecture should avoid assuming that every answer should reveal all known consequences.

Future response modes may include:

* minimal;
* spoiler-free;
* contextual;
* full spoilers.

Do not build the complete spoiler engine during the initial capture work.

---

# Session Memory

Session/playthrough state belongs under:

```text
companion/memory/
```

Future examples include:

* romance preference;
* important quest decisions;
* preferred character outcomes;
* current quest context;
* previous GameSage questions.

Do not implement persistent memory before it is required by the current milestone.

---

# Frontend Guidelines

Frontend code lives under:

```text
apps/desktop/
```

Keep the interface functional and simple during the prototype.

Avoid spending significant development time on visual polish before the core pipeline works.

For early v0.1, prioritize:

* clear status;
* clear errors;
* screenshot preview;
* question input;
* response display;
* settings only when required.

Do not introduce a large UI component framework without need.

---

# Rust / Tauri Guidelines

Use Rust/Tauri for capabilities that genuinely benefit from native desktop integration.

Do not move Python AI logic into Rust merely because Tauri uses Rust.

Rust may eventually handle:

* native window operations;
* application lifecycle;
* global shortcuts;
* desktop integration;
* communication with the Python process.

Keep Rust code small and focused.

---

# Python Guidelines

Prefer:

* Python standard library when practical;
* typed functions;
* small modules;
* explicit data structures;
* `pathlib`;
* clear exceptions;
* dataclasses or lightweight models when useful.

Avoid huge modules.

Avoid global mutable state.

Use type hints for public APIs.

Public functions should have short docstrings when behavior is not obvious.

---

# TypeScript Guidelines

Use:

* TypeScript strict typing where practical;
* functional React components;
* small components;
* clear state ownership.

Avoid:

* `any` unless justified;
* giant components;
* hidden side effects;
* unnecessary state-management libraries.

Do not introduce Redux or similar tooling unless state complexity actually requires it.

---

# Dependencies

Before adding a dependency:

1. Determine whether the standard library or existing dependency can solve the problem.
2. Confirm the package is actively maintained.
3. Prefer lightweight libraries.
4. Explain why the dependency is necessary.
5. Avoid installing large frameworks for one minor feature.

Do not add dependencies merely because they may be useful later.

---

# Testing

New core behavior should be testable where practical.

Python tests belong under:

```text
tests/
```

Use `pytest`.

Prioritize tests for:

* game detection logic;
* configuration parsing;
* data transformations;
* provider abstractions;
* retrieval logic.

OS-level integration code may require separate integration tests.

Do not mock every implementation detail.

Test observable behavior.

---

# Error Handling

GameSage must fail clearly.

Examples:

Instead of:

```text
Capture failed.
```

prefer errors that communicate useful state:

```text
The Witcher 3 process was detected, but no visible game window could be found.
```

or:

```text
The Witcher 3 does not appear to be running.
```

Do not silently swallow exceptions.

Avoid exposing raw stack traces to normal users in the desktop UI.

Logs may contain detailed diagnostic information.

---

# Logging

When logging is introduced, use standard structured logging practices.

Do not use large quantities of permanent `print()` statements.

Logs should help diagnose:

* process detection;
* window selection;
* capture;
* provider communication;
* retrieval;
* configuration.

Never log secrets.

---

# Git Practices

Keep commits focused.

Recommended commit prefixes:

```text
feat:
fix:
chore:
docs:
refactor:
test:
build:
```

Examples:

```text
feat: detect Witcher 3 game window
feat: capture selected game window
fix: handle minimized Witcher 3 window
docs: document local development setup
test: add Witcher 3 detection tests
```

Avoid giant commits containing unrelated changes.

---

# AI Coding Agent Behavior

When working as a coding agent on GameSage:

1. Read this file before making architectural changes.
2. Inspect existing code before generating replacements.
3. Preserve the existing project structure unless change is justified.
4. Prefer modifying existing files over creating parallel implementations.
5. Do not rewrite working modules without a concrete reason.
6. Do not add speculative features.
7. Do not silently add dependencies.
8. Do not silently change configuration formats.
9. Do not remove comments or documentation that still applies.
10. Keep patches scoped to the requested task.
11. Run relevant tests and type checks after changes.
12. Report what changed and what was verified.
13. Clearly mention anything that could not be tested.
14. Do not commit or push unless explicitly requested.

---

# Before Completing a Coding Task

Verify where relevant:

```text
Python tests
TypeScript type checking
Frontend build
Rust compilation
Tauri development build
```

Do not claim a command succeeded unless it was actually run successfully.

If a command cannot be run, state that clearly.

---

# Definition of Done

A feature is not finished merely because code exists.

For early GameSage features, done generally means:

* implementation is reasonably scoped;
* errors are handled;
* obvious edge cases are considered;
* code fits the architecture;
* relevant tests exist where practical;
* documentation is updated if behavior changed;
* project still builds.

---

# Current Next Feature

The next planned feature after initial project setup is:

```text
Detect The Witcher 3 game window.
```

The first implementation should target Windows.

The goal is only to reliably answer questions such as:

```text
Is The Witcher 3 currently running?

If so, which visible window belongs to it?

What are the window bounds?
```

Do not add screen capture, AI analysis, RAG, voice, or overlays as part of this task unless explicitly requested.

---

# Project Philosophy

GameSage should grow incrementally:

```text
See
↓
Understand
↓
Know
↓
Answer
↓
Remember
↓
Speak
↓
Assist proactively
```

Build each layer only when the previous layer is sufficiently reliable.