---
type: decision
status: accepted
date: 2026-10-29
deciders:
  - xilax
last_updated: 2026-10-29
---

# ADR-006 — Architecture — Automatic Navigation Regeneration, Inline Health Checks, and Partial/Batch Operations

## Status

Accepted

## Context

End-of-session wiki updates previously required 6–10 round trips per session (`ingest` → `read` → `write` ×N → `navigate --regenerate` → `lint` → `handoff-write`).
Furthermore, handoff transitional files were being mistakenly registered into `.navigation_registry.json`, polluting `INDEX.md` Quick navigation and pushing it towards the 150-line limit. Writes were full-file only, causing massive token regeneration for minor changes.

## Decision

1. **Automatic Navigation Sync on Write**:
   - Every successful non-bypass write of an article in a wiki section automatically updates `.navigation_registry.json` and regenerates `INDEX.md` Quick navigation.
   - `regenerate_index_navigation` is atomic (write to temporary file and rename) and synchronized with `INDEX.md.lock`.
   - Handoff files (`handoffs/*.md`) are strictly excluded from navigation registration and navigation generation. Legacy handoff entries are pruned automatically upon regeneration.
2. **Inline Health Checks**:
   - `brain79_write` and `brain79_edit` return an immediate health check (`· lint OK` or specific warnings), eliminating the need for a separate `brain79_lint` call after each write.
3. **Partial Edits (`brain79_edit`)**:
   - Allows targeted text replacements (`[{old_text, new_text}]`), validating the resulting content and atomic write without having to re-emit the entire file.
4. **Batch Writes (`brain79_write_many`)**:
   - Accepts multiple articles in a single call, validating all articles upfront (all-or-nothing), writing them in batch, and regenerating navigation once.
5. **Output Schema De-duplication**:
   - All MCP tools define `output_schema=None` to prevent FastMCP wrapping results in redundant `structuredContent`, halving token consumption in AI harnesses like Pi.

## Consequences

- **Positive**: Reduces typical session update flow from 8–15 tool calls down to 2–4 calls.
- **Positive**: Drastically cuts input and output token consumption for end-of-session wiki curation.
- **Positive**: Completely stops handoff pollution of `INDEX.md`.
- **Positive**: Prevents race conditions during index navigation updates through `INDEX.md.lock`.
- **Neutral**: `write_article` now modifies `INDEX.md` as an atomic side-effect.
