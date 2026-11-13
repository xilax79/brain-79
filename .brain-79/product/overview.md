---
type: product
summary: deterministic AI memory and mechanical documentation protocol designed to prevent organic wiki degradation in software repositories.
last_updated: 2026-11-12
applies_to:
  - .brain-79/SCHEMA.md
  - .brain-79/features/*.md
  - src/brain79/__init__.py
applies_to_digest: "sha256:816c48996468956a"
applies_to_count: 11
---

# Brain-79 — Product vision

Deterministic AI memory and mechanical documentation protocol designed to prevent organic wiki degradation in software repositories.

## Problem

LLMs maintain wikis that degrade organically:
- They prefer writing to `INDEX.md` (visible) instead of creating articles in subfolders (correct).
- They inline decisions and technical debt instead of structuring them in dedicated folders.
- They lose history and context between development sessions.
- Manual documentation validation is tedious, error-prone, and inconsistent.

## Solution

`brain-79` is an **AI memory protocol** that enforces mechanical organization:

1. **Cold start (`brain79_orient`)**: The agent retrieves the routing table (`INDEX.md`), active handoff state with authority decay diagnostics, and inlined governing articles in a single call.
2. **Two-call session protocol**: Cold start orientation followed by single-call atomic session finalization (`brain79_session_commit`), validating transitive drift and ripple gates.
3. **Write-time validation**: Mechanical write operations validate frontmatter schemas, file locations, and target existence.
4. **Pre-commit hook**: Direct editing bypasses are mechanically blocked before commit via `brain79 lint --strict`.
5. **Handoff continuity**: Ephemeral tactical transitions with cryptographic freshness tracking and operational purge (`brain79 handoff-purge`).
6. **Organizational enforcement**: Mechanical linter detecting structural quality violations, unanchored governance, and target sprawl.

## Target users

- Development projects where an AI agent works in recurring sessions.
- Knowledge wikis with `INDEX.md` that grows uncontrollably or without structure.
- Teams that require mechanical and deterministic validation of project documentation.

---

[← Volver al Índice](../INDEX.md)
