---
type: architecture
summary: high-level overview of system architecture, active milestones, runtime invariants, and roadmap
stability: stable
last_updated: 2026-11-04
---

# Architecture — System current state

## Overview

This document maintains a high-level summary of the repository's current architecture, active capabilities, completed milestones, and immediate roadmap status as of version 2.1.0.

## Completed milestones and merged features

- **Phase 1 – Core MVP & MCP Server**: FastMCP 2.0 integration, dual-mode CLI/MCP architecture, atomic POSIX file writes, and initial wiki IO primitives (`read`, `write`, `list`, `search`).
- **Phase 1.5 & 1.7 – Handoff Continuity & Init**: Immutable short-term session handoffs (`handoff-write`, `handoff-read`), project protocol initializer (`init`), pre-commit hooks, and universal `AGENTS.md` manifest.
- **Phase 3, 4, 5, 6 – Context, Install & Bootstrap**: TF-IDF context ranking (`brain79_context`), standalone installer (`install.py`), self-updater (`brain79 update`), and repository bootstrapping (`brain79_bootstrap`).
- **Phase 7 – Organizational Enforcement**: 10-subphase linter engine (`lint_organizational.py`), YAML frontmatter schema validation, location consistency checks, decision leakage prevention, and navigation registry generation.
- **Phase 8 – Operational Handoff Purge**: Destructive short-term handoff purge subcommand (`brain79 handoff-purge`) with dry-run default guard.
- **Phase 9 – Performance & Session Workflow Optimization (v1.1.0)**: Output schema de-duplication (`output_schema=None`), multi-error validation reporting with templates, deterministic field auto-fill (ADR-004 amendment), automatic navigation synchronization and inline health checks on write (ADR-006), partial in-place edits (`brain79_edit`), batch write execution (`brain79_write_many`), schema inspection (`brain79_schema`), handoff navigation isolation, and linter path resolution optimization.
- **Phase 10 – Frontmatter Summary & Backlinks**: Frontmatter `summary` extraction in $O(1)$ for `INDEX.md`, hardened heuristic fallbacks against colon and subheading truncation, and standardized article backlink navigation (`[← Volver al Índice](../INDEX.md)`).
- **Phase 11 – Pure Routing Table Index (ADR-008)**: Transformed `INDEX.md` into a pure automated routing table, eliminating hardcoded prose drift and automating timestamp updates on navigation sync.
- **Phase 12 – Zero-Modification Idempotence & Static Type Compliance**: Formally mandated the Zero-Modification Rule across `AGENTS.md` and `SCHEMA.md` to prevent synthetic wiki updates without real repository mutations. Resolved static typing in test suites, achieving zero errors across `uv run mypy src tests`.
- **Phase 13 – Phase 0: Core Bug Fixes & Invariant Alignment**: Achieved 100% validator-linter parity via `check_frontmatter_consistency`, enforced strict ADR-008 (`INDEX_ALLOWED_H2` restricted to `Quick navigation`), aligned `brain79_bootstrap` seed manifests with schema validation, mandated `summary` across indexable articles with deterministic sanitization (`sanitize_summary`), added YAML frontmatter to `_raw/sessions/`, and repaired legacy migration edge cases.
- **Phase 14 – Phase 1: Declarative Schema & Dual Ontology**: Decoupled validation engine (mechanism) from ontology policy via `load_active_schema` with nanosecond mtime caching. Added support for dual built-in profiles (`software` and `general`) via `brain79 init --profile [software|general]`, allowing non-code directories to manage knowledge seamlessly (`context/`, `topics/`, `decisions/`, `log/`) without semver or tech debt leakage friction. Added arbitrary custom folder declarations via `.brain-79/SCHEMA.md` frontmatter.
- **Phase 15 – Phase 2: Deterministic Pre-Work Context & Graph-Augmented Cold Start**: Collapsed cold-start orientation into a 1-call tool (`brain79_orient` / `brain79 orient`) powered by a 3-signal deterministic ranker (exact/glob path matches via `applies_to`, field-weighted TF-IDF with H1/H2 weighting, and 1-hop active ADR graph expansion). Documented in [ADR-010](../decisions/adr-010-orient-and-3-signal-context-ranking.md).
- **Phase 16 – Phase 3: Zero-Turn Session Execution**: Completed the Two-Call Session Protocol with 1-call atomic session finalization (`brain79_session_commit` / `brain79 session-commit`) guaranteeing all-or-nothing rollback across writes, in-memory simulated edits, and handoffs, and section-projected batch reading (`brain79_read_batch`, `brain79_read` with `sections`). Documented in [ADR-011](../decisions/adr-011-session-commit-and-batch-reading.md).
- **Phase 17 – Phase 4: Structural Article Quality & Deterministic Drift Detection**: Enforced document structural integrity with section skeletons per document type, automatic idempotent backlink footer normalization on write (`[← Volver al Índice](../INDEX.md)`), and deterministic code-to-wiki drift detection via `applies_to` frontmatter against git commit timestamps and filesystem mtimes, surfacing alerts in `brain79 lint` and `brain79_orient`. Documented in [ADR-012](../decisions/adr-012-structural-quality-and-drift-detection.md).
- **Phase 18 – Phase 5: Versioning & Release Governance (v2.0.0)**: Single-source semantic versioning via Hatchling dynamic metadata resolution (`__version__ = "2.0.0"` in `src/brain79/__init__.py`), FastMCP server initialization version handshake exposure, and automated test-enforced release parity across SemVer syntax, Hatchling dynamic build settings, README badges, and changelog presence. Documented in [ADR-013](../decisions/adr-013-versioning-and-release-governance.md).
- **Phase 19 – Phase 5.5: Defect Backlog Remediations & Agent Protocol Polish (v2.0.2)**: Resolved broken general profile root backlink (`BUG-001`), composite H2 atomicity thresholds (`BUG-002`), self-documenting write receipts with auto-synced navigation confirmation (`INEF-001`), active schema summary block in cold start (`INEF-002`), and formalized On-Demand Handoff Policy across engine and manifests (`INEF-003`). Documented in [Architecture — Defect Backlog](defect-backlog.md).
- **Phase 20 – Phase 6: Centralized Lock Isolation & Cross-Platform OS Portability**: Isolated inter-process mutex locks into `.brain-79/.locks/` (eliminating `.md.lock` visual clutter), added automatic legacy lock purge, enforced Linux `ext4` segment-by-segment case sensitivity on macOS APFS (`has_exact_case_path`), enforced strict POSIX paths across all registries, added `atomic_replace_with_retry` for NTFS `PermissionError` resilience, and guaranteed strict LF (`\n`) I/O. Documented in [ADR-014](../decisions/adr-014-centralized-locks-and-cross-platform-io.md).
- **Self-Wiki Dogfooding (Phase A-D)**: Fully populated self-documenting `.brain-79/` wiki verified by `brain79 lint --strict`.

## System invariants and invariant guards

- **Wiki Primacy**: Long-term wiki in `.brain-79/` is the absolute source of truth over tactical handoffs.
- **Zero-Modification Idempotence**: Wiki updates strictly require real repository mutations (code, tests, decisions); synthetic documentation churn is rejected.
- **Synchronous Write Validation**: Writes to `.brain-79/` are validated against schema rules prior to disk mutation.
- **Code Fence Masking**: Regex linter rules mask code blocks before scanning to eliminate false positive leakage errors.
- **1:1 CLI & MCP Symmetry**: Every operational subcommand has a matching `@mcp.tool()` equivalent in `server.py`.
- **Centralized Lock Isolation**: File mutexes are strictly isolated into `.brain-79/.locks/`, maintaining 100% clean content directories.
- **Cross-Platform Determinism**: Strict POSIX path serialization (`.as_posix()`), pure LF (`\n`) line endings, and segment-by-segment character casing parity across macOS, Linux, and Windows.

## Immediate focus and maintenance

- Execution of Phase 7: Project Protocol Upgrade (`brain79 update-project`), Legacy Wiki Conditioning, Multi-Harness Setup, and `brain79 doctor` Diagnostics.

---

[← Volver al Índice](../INDEX.md)
