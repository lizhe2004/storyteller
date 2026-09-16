# Streaming Voice Matching Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start voice matching when the top-level `lines` field begins, then stream formal line text into voice-specific TTS sessions without waiting for the complete script.

**Architecture:** Extend the partial JSON stream with a raw top-level field boundary callback. The orchestrator starts voice matching in a worker once `lines` appears, buffers line deltas until the matching voice is available, and finalizes metadata/audio independently.

**Tech Stack:** Python 3.8+, partialjson, threading, pytest, existing WebSocket PCM publisher.

**Spec:** `docs/superpowers/specs/2026-09-14-llm-opening-streaming-tts-design.md`

## Global Constraints

- `characters` readiness means the ordered raw stream has reached the top-level `lines` field.
- `script_ready` waits for complete script data and voice matching, but not all audio sessions.
- `complete` waits for all formal line audio and final mixing.
- Opening and start_notice remain outside the final story audio.
- Existing fallback and CLI behavior remain intact.

### Task 1: Detect the top-level lines boundary

**Files:** `src/storyteller/core/story_generator.py`, `tests/unit/test_story_generator.py`

- [ ] Add a failing test proving `on_characters_ready` fires once when top-level `lines` begins, not when `characters` merely appears.
- [ ] Implement a JSON-string-aware top-level field detector over accumulated chunks.
- [ ] Run the focused story generator tests.

### Task 2: Start matching concurrently and expose line deltas

**Files:** `src/storyteller/core/story_generator.py`, `src/storyteller/web/streaming.py`, tests for generator/WebSocket orchestration

- [ ] Add failing tests for matching beginning before the final script response and line text delta callbacks preserving prefix order.
- [ ] Start one voice-matching worker at the characters boundary and synchronize its result with line processing.
- [ ] Buffer line deltas until the assigned voice is ready, then submit each suffix to the session.
- [ ] Preserve ordered audio publication and fallback behavior.

### Task 3: Verify metadata and audio completion boundaries

**Files:** relevant WebSocket tests and documentation if needed

- [ ] Assert `script_ready` follows complete script plus voice matching, while `complete` follows all formal audio.
- [ ] Run full Python and frontend verification.
