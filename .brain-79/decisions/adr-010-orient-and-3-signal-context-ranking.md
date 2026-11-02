---
type: decision
summary: 1-Call cold start orientation and deterministic 3-signal context ranking
status: accepted
date: 2026-11-02
deciders:
  - xilax
applies_to:
  - "src/brain79/core/orient.py"
  - "src/brain79/core/context.py"
  - "src/brain79/core/navigation.py"
related:
  - "decisions/adr-008-pure-index-routing-table.md"
  - "architecture/roadmap-industrial-scale.md"
last_updated: 2026-11-02
---

# ADR-010 — Two-Call Session Protocol: 1-Call Cold Start Orient and Deterministic 3-Signal Context Ranking

## Status

Accepted

## Context

Prior to Phase 2, an AI agent starting a session faced substantial latency and omission hazards:
1. **Turn Tax**: Cold start required 4 to 6 sequential LLM round-trips (`brain79_index` $\rightarrow$ `brain79_handoff_read` $\rightarrow$ `brain79_context` $\rightarrow$ multiple `brain79_read` calls), adding 20–40 seconds of round-trip latency.
2. **Vocabulary Mismatch & Context Omission**: Pure keyword search frequently missed governing decisions or architectural constraints when user queries used different vocabulary than ADR titles.
3. **Decoupled Handoff Banners**: Knowledge promotion warnings were easily overlooked if an agent skipped reading the full handoff text.

## Decision

We introduced the **1-Call Cold Start Protocol (`brain79_orient` / `brain79 orient`)** powered by a **3-Signal Deterministic Context Ranker**:

1. **Deterministic Path & Graph Metadata in Frontmatter**:
   - `applies_to`: Globs or paths in the workspace governed by the article.
   - `related`: Explicit cross-links to companion articles or governing ADRs.
   - `supersedes`: Explicit lineage tracking.
   - The navigation registry automatically extracts and indexes `applies_to`, `related`, and `outgoing_links`.

2. **3-Signal Context Ranking (`rank_context_articles`)**:
   - **Signal 1 (Path Matching - Highest Weight)**: Exact match or glob matching of `applies_to` against touched files.
   - **Signal 2 (Field-Weighted TF-IDF)**: Matches in `title` ($3\times$), `summary` ($2\times$), and body, deprioritizing `superseded` or `deprecated` articles.
   - **Signal 3 (1-Hop ADR Reference Expansion - Anti-Omission Guard)**: For top matched articles, active linked decisions in `decisions/` are automatically pulled into context so no agent touches a subsystem without seeing its governing decisions.

3. **Consolidated Cold-Start Response (`orient`)**:
   In a single tool call, returns:
   - Automated routing table (`INDEX.md`).
   - Active handoff state with promotion alerts.
   - Inlined full markdown content of the top governing articles.

## Consequences

- **Positive**: Cold-start latency drops from multiple rounds down to a single turn ($<20\text{ ms}$ local execution).
- **Positive**: Eliminates governing ADR omission when modifying bound source paths.
- **Positive**: Strict 1:1 symmetry preserved across MCP (`brain79_orient`) and CLI (`brain79 orient`).

---

[← Volver al Índice](../INDEX.md)
