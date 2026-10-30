---
type: decision
summary: Pure automated routing table architecture for INDEX.md and automated timestamp synchronization
status: accepted
date: 2026-10-30
deciders:
  - xilax
last_updated: 2026-10-30
---

# ADR-008 — Architecture — Pure Automated Routing Table for INDEX.md

## Status

Accepted

## Context

Previously, `INDEX.md` was treated as an executive summary document containing freeform text blocks (`## Project`, `## Current focus`, `## Known issues`, `## Roadmap`).

In real-world multi-session agent usage, this design led to critical knowledge drift:
1. When agents generated or updated specifications (e.g., adding `product/roadmap-aaa.md`), the static text in `INDEX.md` remained un-updated, creating two conflicting sources of truth.
2. Agents rarely edited the hardcoded prose, resulting in stale context during cold-starts.
3. The initial template placed unfilled placeholders and hardcoded `YYYY-MM-DD` dates in `INDEX.md`, causing linter warnings or outdated timestamps.

## Decision

We chose to transform `INDEX.md` into an exclusively automated routing table (*Pure Index Invariant*):

1. **Elimination of Freeform Prose Blocks**:
   - `INDEX.md` templates and canonical archetypes no longer include `## Current focus`, `## Known issues`, or `## Roadmap`.
   - Detailed specifications, roadmaps, and bug trackers belong strictly in their respective subdirectories (`architecture/`, `product/`, `decisions/`, `features/`) and are exposed through the index.
2. **Automated Timestamp Synchronization**:
   - During `brain79 init`, template placeholders (`YYYY-MM-DD`) are dynamically resolved to today's UTC ISO date.
   - `regenerate_index_navigation` automatically refreshes the `last_updated:` frontmatter field in `INDEX.md` on every regeneration, ensuring timestamps never lag behind wiki mutations.
3. **Pure Routing Structure**:
   - `INDEX.md` contains only frontmatter metadata, a single introductory lead block, and the mechanically generated `## Quick navigation` hierarchy.

## Consequences

- **Positive**: Eliminates knowledge drift between `INDEX.md` and domain specifications.
- **Positive**: Zero token waste during cold-start: agents ingest an exact routing table rather than stale text paragraphs.
- **Positive**: Clean initialization out of the box with zero unfilled template placeholder warnings.
- **Positive**: `last_updated` accurately reflects wiki modification activity automatically.

---

[← Volver al Índice](../INDEX.md)
