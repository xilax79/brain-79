---
type: decision
summary: Section-level structural skeletons, auto-injected backlinks, and deterministic code-to-wiki drift detection
status: accepted
date: 2026-11-03
deciders:
  - xilax
applies_to:
  - src/brain79/core/frontmatter.py
  - src/brain79/core/validation.py
  - src/brain79/core/drift.py
  - src/brain79/core/lint_organizational.py
  - src/brain79/core/orient.py
  - src/brain79/core/wiki.py
related:
  - decisions/adr-007-frontmatter-summary-and-backlink-navigation.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
  - architecture/roadmap-industrial-scale.md
last_updated: 2026-11-03
---

# ADR-012 — Structural Article Quality, Auto-Injected Backlinks, and Deterministic Drift Detection

## Status

Accepted

## Context

Prior to Phase 4 of the Industrial-Scale Roadmap, three documentation degradation risks remained:
1. **Unstructured Walls of Text**: While frontmatter schema was strictly validated, document bodies lacked section structure requirements. Agents occasionally generated valid frontmatter followed by unorganized prose without standard headings (e.g. ADRs missing `Consequences` or features missing `Overview`).
2. **Backlink Forgetfulness**: ADR-007 mandated that all subfolder articles conclude with a backlink (`[← Volver al Índice](../INDEX.md)`), but enforcement relied on agent and human memory, occasionally leading to missing navigation footers.
3. **Silent Code-to-Wiki Drift**: When source code evolved in the repository, governing architecture documents and ADRs silently decayed without any automated indication that the code had moved ahead of the documentation.

## Decision

We implemented **Phase 4: Structural Article Quality & Deterministic Drift Detection**:

1. **Section-Level Structural Skeletons & Schema Validation**:
   - `ActiveSchema` defines type-specific `required_sections` (e.g. `decision` requires `## Status`, `## Context`, `## Decision`, `## Consequences`; `feature` requires `## Overview`; `architecture` requires `## Overview` or `## General Description` or `## State`).
   - Skeletons support alternatives and synonyms while masking fenced code blocks to prevent false positive heading matches.
   - `brain79_schema()` and `get_schema_documentation()` expose full markdown document skeletons (frontmatter, H1 title, H2 headings, and backlink footer).
   - `check_article_structural_sections` flags missing structural sections with rule `article_missing_required_sections` (severity `warning`).
   - `check_file_health` provides inline write-time warnings for missing structural sections without hard-aborting saves.

2. **Automatic Backlink Invariant Normalization**:
   - Write normalization (`validate_article_content`, `write_article`, `edit_article`, `commit_session`, and `migrate_wiki`) automatically verifies and injects the standard backlink navigation footer (`[← Volver al Índice](../INDEX.md)`) for any article in a subfolder.
   - The injection is completely idempotent: files already possessing the backlink remain untouched without redundant delimiters.
   - Root files (`INDEX.md`, `SCHEMA.md`), `_raw/`, and `handoffs/` are strictly excluded.
   - `check_article_backlinks` enforces this invariant across the wiki.

3. **Deterministic Code-to-Wiki Drift Detection (`applies_to` + Git)**:
   - Built a dedicated drift engine in `src/brain79/core/drift.py`.
   - Compares the `last_updated` date of any article declaring `applies_to` against the last modification date of governed workspace files (via `git log -1 --format=%cs` with working tree mtime fallback).
   - If a governed workspace file has been modified after the article's `last_updated` date, flags rule `documentation_drift_suspected` in `brain79 lint`.
   - `brain79_orient` / `brain79 orient` automatically checks drift for inlined governing articles and renders an immediate alert banner before the agent begins code modification.

## Consequences

- **Positive**: 100% elimination of manual backlink authoring overhead through automatic write normalization.
- **Positive**: Consistent structural document layout across ADRs and feature specifications.
- **Positive**: Early detection of stale documentation when underlying source files change.
- **Positive**: Full document skeletons accessible directly in `brain79_schema()`.
- **Positive**: Zero performance penalty; drift inspection only evaluates articles with explicit `applies_to` bindings.

---

[← Volver al Índice](../INDEX.md)
