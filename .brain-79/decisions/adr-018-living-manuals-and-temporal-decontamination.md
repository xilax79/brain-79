---
type: decision
summary: architectural foundation for living manuals, temporal decontamination, Chesterton's Fence for ADRs, and epocal changelog consolidation
status: accepted
date: 2026-11-13
deciders:
  - Lead Architect
  - Core Engineering Team
last_updated: 2026-11-13
---

# Decision — ADR-018: Living manuals, temporal decontamination, and the three-class document ontology

## Status

Accepted.

## Context

During iterative, multi-phase software development, AI coding agents and human engineers naturally organize work around temporal milestones: *"Phase 2"*, *"Phase 4"*, *"Phase 6.7"*, *"Sprint 12"*, *"Defect 4"*. When unconstrained by mechanical governance, these ephemeral project management tags bleed into permanent engineering artifacts:
1. Living manuals (`features/`, `architecture/`, `product/`) accumulate obsolete phase numbers in titles and overview sections (e.g., `# Feature — Versioning (Phase 5 specification)`).
2. Production code comments and docstrings in `src/brain79/` fossilize historical ticket identifiers (`(Phase 2)`, `(Defect 1)`, `(P1.1)`), confusing LLMs and human auditors.
3. Changelog files proliferate with every patch, risking index line-budget exhaustion.
4. Conversely, naive proposals to "purge" older articles risk destroying past decision rationale (violating Chesterton's Fence).

## Decision

We establish a formal three-class document ontology, Chesterton's Fence governance for ADRs, mechanical linter rules for temporal decontamination in living manuals, and an epocal changelog consolidation policy:

### 1. The three-class document ontology
Documentation in Brain-79 is partitioned into three distinct lifecycles:
- **Class 1: Immutable audit trail (`decisions/`, `changelog/`, `_raw/`)**:
  - Strictly append-only. Past rationale and release notes are never rewritten or purged.
  - Phase and milestone references are legitimate historical context here.
  - Authority decays via status transitions (`accepted` $\rightarrow$ `superseded` or `archived`).
  - Superseded ADRs incur zero daily token cost because `INACTIVE_STATUSES` excludes them from Signal 1 and Signal 2 context ranking by default.
- **Class 2: Living system truth (`architecture/`, `features/`, `product/`)**:
  - Evergreen and mutable in-situ. Must describe how the software operates today.
  - Prohibited from containing temporal project management markers (`Phase X`, `Sprint Y`, `Milestone Z`, `WIP`) in titles, summaries, or opening overview paragraphs.
  - Shipped features are living manuals, not "specifications".
- **Class 3: Ephemeral transition notes (`handoffs/`)**:
  - Highly perishable operational handover state.
  - Purged actively via `brain79 handoff-purge` when closing major milestones.

### 2. Chesterton's Fence invariant for ADRs
Architectural Decision Records must **never be deleted or compacted into oblivion**. An old ADR explains *why* an alternative was rejected or why a non-obvious constraint (like mutex lock isolation) was created. An ADR is only superseded by a newer ADR, transitioning its status to `superseded`.

### 3. Mechanical temporal decontamination rule
`lint_organizational.py` enforces rule `temporal_contamination_in_title` on living manual ontologies (`features/`, `architecture/`, `product/`). Roadmap files (`roadmap*.md`) and immutable audit folders are exempt.

### 4. Epocal changelog consolidation policy
Standalone changelog articles (`vX-Y-Z.md`) are maintained for active releases within the current minor epoch (`v0.8.x`). When transitioning between major milestones (e.g. at `v1.0.0`), older minor release logs are consolidated into canonical archive compendiums (`changelog/releases-v0-pre-ga.md`), maintaining `INDEX.md` within its 150-line budget without losing historical Git commits.

## Consequences

### Positive
- Living manuals remain timeless, clear, and evergreen.
- LLM context windows in `orient()` are not polluted by obsolete milestone names.
- Historical decision rationale is permanently preserved without token bloat.
- Eliminates wiki sprawl and redundant specification files.

### Negative
- Requires ongoing mechanical linting to prevent agents from reintroducing phase markers in living titles.

---

[← Volver al Índice](../INDEX.md)
