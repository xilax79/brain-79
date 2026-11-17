---
type: changelog
summary: historical record of internal development cycles (v1.0.0 through v2.0.2) prior to ADR-017 pre-GA recalibration
version: 2.0.2
date: 2026-11-04
last_updated: 2026-11-12
---

# Changelog — Historical internal development milestones (v1.0.0 through v2.0.2)

> **Historical notice**: This document consolidates the technical release logs from internal development cycles (Phases 1 through 5.5). Prior to ADR-017, internal architectural milestones were tracked under `1.x` and `2.0.x`. Under [ADR-017](../decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md) and SemVer 2.0.0 §4, the official package release tracking was recalibrated to `0.7.2` for pre-GA maturation leading to `1.0.0` General Availability.

---

## Version 2.0.2 — Defect backlog and agent protocol polish (2026-11-04)

Patch release addressing defects discovered during adversarial evaluation on greenfield projects, refining organizational linter atomicity heuristics, and aligning LLM agent efficiency protocols.

### Fixed
- **Root backlink normalization & broken link in general profile template (BUG-001)**:
  - Fixed `src/brain79/templates/SCHEMA_GENERAL.md` by replacing invalid upward traversal `[← Volver al Índice](../INDEX.md)` with `[← Volver al Índice](INDEX.md)`.
  - Hardened `normalize_backlink_footer` in `src/brain79/core/frontmatter.py` to rewrite root-level relative backlink traversals in tail lines outside code fences, preserving documentation examples inside code blocks in `SCHEMA.md`.
  - Added regression test verifying `brain79 init --profile general` produces a wiki that passes `brain79 lint --strict` with zero broken links out of the box.

- **Composite H2 atomicity heuristics & code-fence masking (BUG-002)**:
  - Masked code fences in `check_article_atomicity` (`src/brain79/core/lint_organizational.py`) so example headings inside markdown code blocks do not falsely trigger `article_not_atomic` warnings.
  - Implemented exact composite H2 threshold:
    - Structured checklists, roadmaps, backlogs, glossaries, or outlines: up to **15** H2 sections.
    - Compact articles (`<= 150` lines): up to **12** H2 sections.
    - Standard prose articles (`> 150` lines): up to **10** H2 sections.

- **Self-documenting tool receipts & navigation synchronization (INEF-001)**:
  - Updated receipts for `brain79_write`, `brain79_edit`, and `brain79_write_many` to return `Written: <path> · INDEX.md auto-synced · lint OK`, eliminating redundant `navigate` and `index` agent call loops.
  - Clarified tool docstrings in `src/brain79/server.py` and instructions in `AGENTS.md` regarding automated navigation synchronization.

- **Active schema summary in cold start (INEF-002)**:
  - Enhanced `brain79_orient` (`src/brain79/core/orient.py`) to include a compact `## 📐 Active Schema Summary` header showing the active ontology profile (`software` or `general`) and managed directories with required fields in a single call.

- **Formalized on-demand handoff policy (INEF-003)**:
  - Codified across `server.py` docstrings (`brain79_handoff_write`, `brain79_session_commit`) and `AGENTS.md` manifests that handoffs must only be written on explicit user request or upon autonomous headless sub-agent process termination, preventing per-turn handoff spam during interactive sessions.

---

## Version 2.0.1 — Obsolete integration fixture purge (2026-11-03)

Internal maintenance release eliminating obsolete legacy test fixtures and non-portable local paths.

### Removed
- **Obsolete Truco Arena snapshot fixture (`tests/test_truco_arena_integration.py` & `tests/fixtures/`)**:
  - Removed outdated 40+ file fixture snapshot dating from prototype v0.1 (August 2026) that required artificial test-time patching to pass modern linter rules.
  - Eliminated `refresh_truco_arena.sh` containing hardcoded absolute machine paths.
  - Test coverage for frontmatter migration and strict organizational linting remains 100% covered across `tests/test_migrate_frontmatter.py` and `tests/test_lint_organizational.py`.

---

## Version 2.0.0 — Two-call protocol and release governance (2026-11-03)

A milestone major release transitioning brain-79 from an MVP memory logger into an industrial-scale, mechanically governed AI memory operating system.

### Major paradigm shifts (v2.0.0)
- **Two-call session protocol (ADR-010, ADR-011)**:
  - Collapsed session cold start from 5+ sequential round-trips into a single turn with `brain79_orient` (`brain79 orient`), powered by a 3-signal deterministic context ranker (exact/glob path matches via `applies_to`, field-weighted TF-IDF, and 1-hop active ADR graph expansion).
  - Finalized sessions in 1 atomic turn with `brain79_session_commit` (`brain79 session-commit`), executing raw logs, article writes, simulated partial edits, and immutable handoffs with all-or-nothing rollback guarantees.
  - Added section-projected reads (`brain79_read` with `sections` and `brain79_read_batch`) saving up to 50% context window tokens.

- **Declarative schemas & dual ontologies (ADR-009)**:
  - Decoupled validation engine (mechanism) from directory structure (policy) via `.brain-79/SCHEMA.md`.
  - Added native dual profiles (`software` and `general`) and custom folder extensions with nanosecond-cached schema loading.

- **Structural quality & deterministic drift detection (ADR-012)**:
  - Mandated section-level skeletons per document type (`## Status`, `## Context`, `## Decision`, `## Consequences` for decisions; `## Overview` for features).
  - Automated backlink injection (`[← Volver al Índice](../INDEX.md)`) across all subfolder articles.
  - Implemented Git-backed code-to-wiki drift detection alerting when workspace source code outpaces governing documentation.

- **Versioning & release governance (ADR-013)**:
  - Single source of truth semantic versioning via Hatchling dynamic version configuration.
  - Exposed accurate version in FastMCP server initialization handshake and CLI (`brain79 -v` / `--version`).
  - Automated release parity invariants verifying SemVer formatting, Hatchling configuration, README badges, and changelog presence.

- **CLI dispatcher hardening**:
  - Full POSIX-compliant global `-h/--help` and `help <cmd>` hierarchy with clear English subcommand descriptions.
  - Strict exit code 2 on unrecognized commands or flags.

---

## Version 1.1.0 — Performance and session workflow optimization (2026-10-29)

Notable improvements addressing end-of-session wiki update performance and tool usability.

### Added features
- **Schema exposure tool (`brain79 schema` / `brain79_schema`)**: inspect schema requirements and copy-paste YAML templates directly.
- **Partial edit tool (`brain79 edit` / `brain79_edit`)**: Targeted text replacement avoiding full article regeneration.
- **Batch write tool (`brain79 write-many` / `brain79_write_many`)**: Batch writes with upfront atomic all-or-nothing validation.
- **Automatic navigation synchronization**: Article writes auto-register and atomically regenerate `INDEX.md` Quick navigation.
- **Inline health checks**: write tools return immediate health check status without requiring separate lint invocations.
- **Deterministic field auto-fill**: Automatically infers type and updates timestamps, stripping hallucinated keys.

### Fixes and adjustments
- **Handoff navigation isolation**: Completely eliminated handoff entries from navigation registry and `INDEX.md`.
- **FastMCP output schema optimization**: Set `output_schema=None` to eliminate duplicated structuredContent payload.
- **Linter performance**: Optimized link resolution to avoid redundant filesystem calls.
- **Pure routing table architecture (ADR-008)**: Redesigned `INDEX.md` template removing static text blocks to prevent knowledge drift.
- **Automatic navigation timestamp updates**: Automated updating of `last_updated:` frontmatter on `INDEX.md` upon navigation sync.
- **Zero-modification idempotence (No-Op Rule)**: Formally mandated in `AGENTS.md` and `SCHEMA.md` to prevent synthetic wiki updates when no repository mutations occurred.
- **Static type safety resolution in test suite**: Resolved test-suite type annotations and submodule imports, achieving zero errors across `uv run mypy src tests`.

---

## Version 1.0.0 — Initial production release (2026-08-11)

All notable changes to `brain-79` v1.0.0 release cycle.

### Added features
- **`brain79 handoff-purge`**: Destructive command to wipe all handoff files and unregister them from navigation registry. CLI/MCP symmetric, defaults to `--dry-run` for safety.
- **Wiki organizational enforcement system**:
  - Mechanical YAML frontmatter schema validation and type-location consistency checking (`frontmatter.py`, `validation.py`).
  - Strict V5 structural decision and technical debt leakage regex rules with CommonMark code fence masking.
  - Thread-safe, lock-file backed auto-generated navigation registry (`navigation.py`).
  - Extended organizational health linter (`lint_organizational.py`) with `--strict`, `--suggest-extract`, `--format json`, and `check_unfilled_placeholders` checks.
  - Progressive V3 legacy wiki migration script (`migrate_frontmatter.py`) with `status: legacy` defaults and `--suggest-relocations`.
  - Bypassing validation via `force_validation_skip` flag / metadata (`force_skipped_article`).
  - Executable git pre-commit hook (`install_git_hooks`) automatically deployed during `brain79 init`.
  - State-aware dynamic curation guide generator (`curate.py`).
- **Self-wiki curation**: Dogfooding wiki population under `.brain-79/`.

### Fixes and adjustments
- CLI `brain79 migrate` now defaults to `--dry-run` for 1:1 symmetry with MCP `brain79_migrate()`. Use `--apply` to apply mutations explicitly.
- Unfilled HTML template placeholders in `INDEX.md` flagged as warnings via linter (BUG-11).

---

[← Volver al Índice](../INDEX.md)
