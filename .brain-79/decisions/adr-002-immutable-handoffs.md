---
type: decision
status: accepted
date: 2026-08-11
deciders: [xilax]
last_updated: 2026-08-11
---

# ADR-002 — Handoffs — Immutable Session Transition Records

## Status

Accepted

## Context

Short-term session transitions between AI agents are prone to state degradation when agents overwrite a single `handoff.md` file. Overwrites risk erasing pending tasks, obscuring historical lineage, and losing hard-won debugging context.

## Decision

We chose to enforce strict immutability for session handoffs:
- Each handoff is saved to a distinct timestamped file: `.brain-79/handoffs/handoff-%Y-%m-%d-%H%M%S-%f.md`.
- Handoff updates must create a new handoff document referencing the previous handoff's stem via `previous_handoff_ref`.
- Operational deletion is restricted to `brain79 handoff-purge`, which requires explicit `--apply` confirmation.

## Consequences

- **Positive**: Complete, tamper-proof audit trail of agent session transitions.
- **Positive**: Retains historical pending work items across multi-session tasks.
- **Negative**: Handoff files accumulate over time until explicitly purged via `brain79 handoff-purge`.

## Alternatives Considered

- **Single mutable `handoff.md` file**: Rejected due to frequent context loss and accidental overwrites during multi-turn sessions.
