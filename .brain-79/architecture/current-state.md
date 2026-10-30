---
type: architecture
summary: High-level overview of system architecture, active milestones, runtime invariants, and roadmap
stability: stable
last_updated: 2026-10-30
---

# Architecture — System Current State

## Overview

This document maintains a high-level summary of the repository's current architecture, active capabilities, completed milestones, and immediate roadmap status as of version 1.1.0+.

## Completed Milestones & Merged Features

- **Phase 1 – Core MVP & MCP Server**: FastMCP 2.0 integration, dual-mode CLI/MCP architecture, atomic POSIX file writes, and initial wiki IO primitives (`read`, `write`, `list`, `search`).
- **Phase 1.5 & 1.7 – Handoff Continuity & Init**: Immutable short-term session handoffs (`handoff-write`, `handoff-read`), project protocol initializer (`init`), pre-commit hooks, and universal `AGENTS.md` manifest.
- **Phase 3, 4, 5, 6 – Context, Install & Bootstrap**: TF-IDF context ranking (`brain79_context`), standalone installer (`install.py`), self-updater (`brain79 update`), and repository bootstrapping (`brain79_bootstrap`).
- **Phase 7 – Organizational Enforcement**: 10-subphase linter engine (`lint_organizational.py`), YAML frontmatter schema validation, location consistency checks, decision leakage prevention, and navigation registry generation.
- **Phase 8 – Operational Handoff Purge**: Destructive short-term handoff purge subcommand (`brain79 handoff-purge`) with dry-run default guard.
- **Phase 9 – Performance & Session Workflow Optimization (v1.1.0)**: Output schema de-duplication (`output_schema=None`), multi-error validation reporting with templates, deterministic field auto-fill (ADR-004 amendment), automatic navigation synchronization and inline health checks on write (ADR-006), partial in-place edits (`brain79_edit`), batch write execution (`brain79_write_many`), schema inspection (`brain79_schema`), handoff navigation isolation, and linter path resolution optimization.
- **Phase 10 – Frontmatter Summary & Backlinks**: Frontmatter `summary` extraction in $O(1)$ for `INDEX.md`, hardened heuristic fallbacks against colon and subheading truncation, and standardized article backlink navigation (`[← Volver al Índice](../INDEX.md)`).
- **Phase 11 – Pure Routing Table Index (ADR-008)**: Transformed `INDEX.md` into a pure automated routing table, eliminating hardcoded prose drift and automating timestamp updates on navigation sync.
- **Phase 12 – Zero-Modification Idempotence & Static Type Compliance**: Formally mandated the Zero-Modification Rule across `AGENTS.md` and `SCHEMA.md` to prevent synthetic wiki updates without real repository mutations. Resolved static typing in test suites, achieving zero errors across `uv run mypy src tests`.
- **Self-Wiki Dogfooding (Phase A-D)**: Fully populated self-documenting `.brain-79/` wiki verified by `brain79 lint --strict`.

## System Invariants & Invariant Guards

- **Wiki Primacy**: Long-term wiki in `.brain-79/` is the absolute source of truth over tactical handoffs.
- **Zero-Modification Idempotence**: Wiki updates strictly require real repository mutations (code, tests, decisions); synthetic documentation churn is rejected.
- **Synchronous Write Validation**: Writes to `.brain-79/` are validated against schema rules prior to disk mutation.
- **Code Fence Masking**: Regex linter rules mask code blocks before scanning to eliminate false positive leakage errors.
- **1:1 CLI & MCP Symmetry**: Every operational subcommand has a matching `@mcp.tool()` equivalent in `server.py`.
- **Atomic File Mutexes**: Mutations to articles and `INDEX.md` use interprocess `.lock` files to prevent write corruption.

## Immediate Focus & Maintenance

- Maintenance of organizational linter rules and schema validation.
- Preservation of 100% test coverage and static type safety (`mypy --strict`, `ruff`).
- Preparation for PyPI packaging release (v1.1.0).

---

[← Volver al Índice](../INDEX.md)
