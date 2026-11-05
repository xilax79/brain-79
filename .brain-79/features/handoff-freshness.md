---
type: feature
summary: specification for Phase 6.6 — handoff freshness, provenance digests, authority decay, branch-aware resolution, and aging escalation
status: shipped
version: 2.0.4
applies_to:
  - src/brain79/core/handoff_freshness.py
  - src/brain79/core/handoff.py
  - src/brain79/core/orient.py
  - src/brain79/core/session_commit.py
  - src/brain79/server.py
related:
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
  - features/handoff-continuity.md
  - architecture/roadmap-industrial-scale.md
last_updated: 2026-11-05
---

# Feature — Handoff freshness, provenance, and authority decay (Phase 6.6)

## Overview

In multi-session workflows where agents operate under the *On-demand handoff policy*, subsequent sessions often perform consultations or code edits without generating a new handoff. Prior to Phase 6.6, `brain79_orient` always rendered the latest handoff verbatim under `## ⏱️ Active Handoff State`.

This created a major hazard: an obsolete handoff with an imperative boot instruction could lead a newly initialized agent to re-implement already completed work or reverse decisions.

Phase 6.6 establishes deterministic handoff lifecycle management:
1. **Provenance capture**: recording git commit SHA, branch, ISO 8601 UTC timestamp, and independent sha256 digests of wiki content and codebase tree.
2. **Deterministic drift calculation**: classifying handoffs into `fresh`, `stale`, `foreign_branch`, or `unverified` without agent guesswork.
3. **Authority decay rendering**: displaying warning banners, relabeling historical boot instructions, and suppressing cross-branch task bleed in `orient()`.
4. **Branch-aware resolution**: resolving `latest` within the active git branch before falling back to global newest.
5. **Aging pending work escalation**: surfacing advisory notices when pending tasks remain unpromoted past age or commit thresholds.
6. **English template standardization**: emitting English headings with colons outside bold formatting.

---

## Technical architecture

### 1. Provenance frontmatter

Every generated handoff stores metadata in its YAML frontmatter:
```yaml
---
type: handoff
session_type: feature
previous_ref: latest
created_at: 2026-11-05T21:15:00Z
last_updated: 2026-11-05
git_branch: main
git_head: 22206e2a9b6c4f0...
wiki_digest: a3b7c9...
code_digest: f81d4c...
schema_version: 1
---
```

- `wiki_digest`: sha256 computed over sorted `(path, sha256(bytes))` pairs across permanent articles, excluding `handoffs/`, `_raw/`, `.locks/`, `INDEX.md`, and `.navigation_registry.json`. Pure Python and immune to mtime touching.
- `code_digest`: git-aware sha256 over tracked and untracked files outside `.brain-79/`. Commit-independent (committing the same tree does not alter the digest).

### 2. State classification

`compute_handoff_freshness(handoff_path)` evaluates states in strict precedence order:
1. `foreign_branch`: handoff branch differs from current branch.
2. `stale`: wiki content or codebase modified since the handoff.
3. `unverified`: legacy handoffs lacking digests, or git failures.
4. `fresh`: all content digests match.

### 3. Rendering and projection

- **Fresh handoffs**: rendered with confirmation banner (`> Fresh: written <age> ago on '<branch>'; no wiki or code changes since.`).
- **Stale handoffs**: rendered with warning banner detailing reasons, commit count, and changed articles. In rendered projection, `## Boot instruction` is renamed to `## Boot instruction (historical: verify against current state)`.
- **Foreign branch handoffs**: in `orient()`, only immediate context is projected. Pending work and boot instructions are omitted to avoid cross-branch contamination, with a hint directing the user to `brain79_handoff_read` for complete inspection.

---

[← Volver al Índice](../INDEX.md)
