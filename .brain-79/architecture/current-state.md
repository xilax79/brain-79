---
type: architecture
summary: high-level overview of system architecture, active milestones, runtime invariants, and roadmap
stability: stable
last_updated: 2026-11-27
applies_to:
  - README.md
  - USER_GUIDE.md
  - ARCHITECTURE.md
  - .brain-79/decisions/adr-*.md
  - .brain-79/features/*.md
  - src/brain79/__init__.py
  - src/brain79/core/__init__.py
related:
  - architecture/roadmap-industrial-scale.md
  - decisions/adr-023-external-drift-lockfile.md
---

# Architecture — System current state

## Overview

This document maintains a high-level summary of the repository's current architecture, active capabilities, completed milestones, and immediate roadmap status as of version 0.18.0.

## Active subsystem topology

| Subsystem | Core modules | Governing documentation |
|---|---|---|
| **CLI & Dispatcher** | `src/brain79/cli/dispatch.py`, `src/brain79/__main__.py` | [Feature — Standalone CLI interface](../features/cli.md), [Architecture — CLI dispatcher](dispatcher.md) |
| **FastMCP Server** | `src/brain79/server.py` | [Feature — FastMCP integration](../features/mcp-server.md), [Architecture — MCP server](mcp-server.md) |
| **3-Signal Context & Orient** | `src/brain79/core/orient.py`, `src/brain79/core/context.py` | [ADR-010](../decisions/adr-010-orient-and-3-signal-context-ranking.md), [Feature — Transitive drift detection](../features/transitive-drift-and-ripple-guards.md) |
| **Transactional Session Commit & Ripple Gate** | `src/brain79/core/session_commit.py`, `src/brain79/core/curate.py` | [ADR-011](../decisions/adr-011-session-commit-and-batch-reading.md), [Feature — Transitive drift detection](../features/transitive-drift-and-ripple-guards.md) |
| **External Drift Lockfile & AST Guards** | `src/brain79/core/drift.py`, `src/brain79/core/drift_merge.py`, `src/brain79/core/ast_guards/` | [Feature — Transitive drift detection](../features/transitive-drift-and-ripple-guards.md), [ADR-023](../decisions/adr-023-external-drift-lockfile.md) |
| **Centralized Git Layer & Team Collaboration** | `src/brain79/core/git_ops.py`, `src/brain79/core/auto_map.py`, `src/brain79/core/navigation.py`, `src/brain79/core/drift_merge.py` | [Feature — Team-safe Git collaboration and low-friction onboarding](../features/team-collaboration-and-onboarding.md) |
| **Organizational Linter & Schema Engine** | `src/brain79/core/lint.py`, `src/brain79/core/lint_organizational.py`, `src/brain79/core/validation.py`, `src/brain79/core/frontmatter.py` | [Feature — Wiki organizational enforcement](../features/organizational-enforcement.md), [ADR-018](../decisions/adr-018-living-manuals-and-temporal-decontamination.md) |
| **CI PR Gate & Lifecycle Hooks** | `src/brain79/core/ci_check.py`, `src/brain79/core/harnesses/lifecycle_hooks.py`, `action.yml` | [Feature — Passive lifecycle hooks and CI PR gate](../features/lifecycle-hooks-and-ci-gate.md), [ADR-021](../decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md) |
| **Polyglot AST Guards & Context Stats** | `src/brain79/core/ast_guards/treesitter_inspector.py`, `src/brain79/core/ast_guards/polyglot.py`, `src/brain79/core/stats.py` | [Feature — Polyglot AST guards and context budget telemetry](../features/polyglot-ast-guards-and-stats.md), [ADR-022](../decisions/adr-022-polyglot-ast-guards-and-context-stats.md) |
| **Cross-Platform Lock & Scoped Context** | `src/brain79/core/locks.py`, `src/brain79/config.py` | [Feature — Cross-platform portability and centralized lock isolation](../features/cross-platform-and-lock-isolation.md), [ADR-014](../decisions/adr-014-centralized-locks-and-cross-platform-io.md) |
| **Handoff Continuity & Freshness** | `src/brain79/core/handoff.py`, `src/brain79/core/handoff_freshness.py` | [Feature — Short-term handoff continuity](../features/handoff-continuity.md), [ADR-016](../decisions/adr-016-handoff-freshness-and-authority-decay.md) |
| **Project Protocol Upgrade & Harness Registry** | `src/brain79/core/init_project.py`, `src/brain79/core/doctor.py`, `src/brain79/core/harnesses/`, `src/brain79/core/migration.py` | [Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics](../features/project-upgrade-and-multi-harness-doctor.md) |

> For the historical sequence of developmental milestones and releases, refer to [Architecture — Industrial-scale roadmap and adoption evolution](roadmap-industrial-scale.md) and [Changelog — Historical internal development milestones](../changelog/legacy-internal-releases.md).

## System invariants and invariant guards

- **Wiki primacy**: long-term wiki in `.brain-79/` is the absolute source of truth over tactical handoffs (guarded by `index_desync` and disk-reconciled `.navigation_registry.json`).
- **External drift lockfile & hash-free Markdown**: machine-managed `digest`, `count`, and leaf `targets` live in Git-tracked `.brain-79/drift.lock` (`version: "2.0"`), protected by `brain79 merge-drift-lock` (`ADR-023`), while Markdown frontmatter remains hash-free.
- **Zero-modification idempotence**: wiki updates strictly require real repository mutations; synthetic documentation churn is rejected.
- **Synchronous write validation**: writes to `.brain-79/` are validated against schema rules prior to disk mutation.
- **Code fence masking**: regex linter rules mask code blocks before scanning to eliminate false positive leakage errors.
- **MCP-subset / CLI-superset symmetry**: `MCP_TOOLS` (9 focused hot-path MCP tools) is a strict subset of `WHITELIST` (27 CLI subcommands) per ADR-020.
- **Centralized lock isolation**: file mutexes are strictly isolated into `.brain-79/.locks/` (`_transaction.lock -> _registry.lock -> _drift_lock.lock -> _drift_manifest.lock -> INDEX.md.lock`).
- **Cross-platform determinism**: strict POSIX path serialization (`.as_posix()`), pure LF (`\n`) line endings, and segment-by-segment character casing parity across macOS, Linux, and Windows.
- **Hard Session Ripple Gate**: commits modifying code or intra-wiki targets must atomically update or verify all impacted leaf and umbrella articles.
- **Lifecycle hook fail-open & loop immunity**: `--lifecycle-hook` always exits `0`, emits ASCII-safe JSON, caps `stdin` at `1 MB`, and short-circuits on active continuation or non-normal termination signals.

## Immediate focus and maintenance

- **Shipped (`v0.18.0`)**: Phase 17 (`SPEC-017`, `ADR-023`) external `.brain-79/drift.lock`, hash-free Markdown frontmatter, `brain79 merge-drift-lock` 3-way merge driver, zero-diff `verified_articles`, Guard C two-pass baseline resolver, zero-masking migration, and CI matrix reliability.
- **Upcoming (`v0.19.0`)**: Phase 18 automated PyPI Trusted Publishers release (unblocked by Phase 16 `PASS` and Phase 17).

---

[← Back to Index](../INDEX.md)
