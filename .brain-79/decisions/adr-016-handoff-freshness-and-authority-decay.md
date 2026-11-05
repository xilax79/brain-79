---
type: decision
summary: treat handoffs as perishable transition notes with authority decaying based on deterministic workspace drift
status: accepted
deciders: Team
date: 2026-11-05
last_updated: 2026-11-05
---

# ADR-016: Handoff freshness, provenance, and authority decay

## Status

Accepted

## Context

Prior to Phase 6.6, `brain79_orient` retrieved the lexicographically latest handoff file and rendered it directly under `## ⏱️ Active Handoff State` without evaluating its lifecycle or subsequent workspace activity.

Under the *On-demand handoff policy*, intermediate consultative or focused sessions do not necessarily write a handoff. If substantial work or wiki documentation occurred after a handoff without creating a new one, the next session received an obsolete handoff as if it were current, including an imperative boot instruction. This created the risk of executing already-completed tasks or reverting architecture decisions.

Conversely, consuming or deleting handoffs upon reading was unacceptable: it destroyed pending work context when sessions were interrupted, introduced write mutations into read operations, and caused race conditions across parallel agents and worktrees.

## Decision

Establish that **a handoff is a perishable transition note, not a permanent source of truth**. Authority strictly follows: `code and git > wiki > handoff`.

1. **Provenance capture in handoff frontmatter**: `write_handoff` captures `created_at`, `git_branch`, `git_head`, `wiki_digest`, and `code_digest`.
2. **Deterministic drift evaluation**: `compute_handoff_freshness` evaluates whether wiki articles or code files changed since the handoff, without relying on LLM guesswork.
3. **Authority decay states**:
   - `fresh`: no wiki or code modifications; rendered with active status.
   - `stale`: wiki or codebase modified; rendered with stale warning banner and relabeled historical boot instruction.
   - `foreign_branch`: handoff from another branch; omits pending work and boot instruction in `orient` to prevent cross-branch contamination.
   - `unverified`: legacy handoffs lacking digests; rendered with verification advisories.
4. **Branch-aware resolution**: `latest` resolution preferentially matches the active git branch before falling back to global newest.
5. **Aging pending work escalation**: advisory escalation surfaces when pending work remains unpromoted past configurable age or commit thresholds.
6. **English template standardization**: all handoff templates emit English section headings with colons outside bold formatting.

## Consequences

- Sessions cannot be misled by obsolete imperative boot instructions after intervening changes.
- Handoff reads remain pure, idempotent, and non-destructive.
- The on-demand handoff policy remains intact without forcing unneeded handoffs on every turn.
- Handoffs operate in full compliance with ADR-015 sentence case standards.

---

[← Volver al Índice](../INDEX.md)
