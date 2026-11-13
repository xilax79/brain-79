---
type: architecture
summary: high-level overview of system architecture, active milestones, runtime invariants, and roadmap
stability: stable
last_updated: 2026-11-13
applies_to:
  - .brain-79/decisions/adr-*.md
  - .brain-79/features/*.md
  - src/brain79/__init__.py
  - src/brain79/core/__init__.py
related:
  - architecture/roadmap-industrial-scale.md
applies_to_digest: "sha256:40f4acbc9a5e42c2"
applies_to_count: 29
---

# Architecture — System current state

## Overview

This document maintains a high-level summary of the repository's current architecture, active capabilities, completed milestones, and immediate roadmap status as of version 0.8.1.

## Active subsystem topology

| Subsystem | Core Modules | Governing Documentation |
|---|---|---|
| **CLI & Dispatcher** | `src/brain79/cli/dispatch.py`, `src/brain79/__main__.py` | [Feature — Standalone CLI interface](../features/cli.md), [Architecture — CLI dispatcher](dispatcher.md) |
| **FastMCP Server** | `src/brain79/server.py` | [Feature — FastMCP integration](../features/mcp-server.md), [Architecture — MCP server](mcp-server.md) |
| **3-Signal Context & Orient** | `src/brain79/core/orient.py`, `src/brain79/core/context.py` | [ADR-010](../decisions/adr-010-orient-and-3-signal-context-ranking.md), [Feature — Transitive drift detection](../features/transitive-drift-and-ripple-guards.md) |
| **Transactional Session Commit & Ripple Gate** | `src/brain79/core/session_commit.py`, `src/brain79/core/curate.py` | [ADR-011](../decisions/adr-011-session-commit-and-batch-reading.md), [Feature — Transitive drift detection](../features/transitive-drift-and-ripple-guards.md) |
| **Merkle Drift Engine** | `src/brain79/core/drift.py` | [Feature — Transitive drift detection](../features/transitive-drift-and-ripple-guards.md), [ADR-012](../decisions/adr-012-structural-quality-and-drift-detection.md) |
| **Organizational Linter & Schema Engine** | `src/brain79/core/lint_organizational.py`, `src/brain79/core/validation.py`, `src/brain79/core/frontmatter.py` | [Feature — Wiki organizational enforcement](../features/organizational-enforcement.md), [ADR-018](../decisions/adr-018-living-manuals-and-temporal-decontamination.md) |
| **Cross-Platform Lock & I/O Layer** | `src/brain79/core/locks.py`, `src/brain79/config.py` | [Feature — Cross-platform portability and centralized lock isolation](../features/cross-platform-and-lock-isolation.md), [ADR-014](../decisions/adr-014-centralized-locks-and-cross-platform-io.md) |
| **Handoff Continuity & Freshness** | `src/brain79/core/handoff.py`, `src/brain79/core/handoff_freshness.py` | [Feature — Short-term handoff continuity](../features/handoff-continuity.md), [ADR-016](../decisions/adr-016-handoff-freshness-and-authority-decay.md) |

> For the historical sequence of developmental milestones and releases, refer to [Architecture — Industrial-scale roadmap and adoption evolution](roadmap-industrial-scale.md) and [Changelog — Historical internal development milestones](../changelog/legacy-internal-releases.md).

## System invariants and invariant guards

- **Wiki Primacy**: Long-term wiki in `.brain-79/` is the absolute source of truth over tactical handoffs.
- **Zero-Modification Idempotence**: Wiki updates strictly require real repository mutations (code, tests, decisions); synthetic documentation churn is rejected.
- **Synchronous Write Validation**: Writes to `.brain-79/` are validated against schema rules prior to disk mutation.
- **Code Fence Masking**: Regex linter rules mask code blocks before scanning to eliminate false positive leakage errors.
- **1:1 CLI & MCP Symmetry**: Every operational subcommand has a matching `@mcp.tool()` equivalent in `server.py` (22 subcommands, 20 MCP tools).
- **Centralized Lock Isolation**: File mutexes are strictly isolated into `.brain-79/.locks/`, maintaining 100% clean content directories.
- **Cross-Platform Determinism**: Strict POSIX path serialization (`.as_posix()`), pure LF (`\n`) line endings, and segment-by-segment character casing parity across macOS, Linux, and Windows.
- **Hard Session Ripple Gate**: Commits modifying code or intra-wiki targets must atomically update or verify all impacted leaf and umbrella articles.

## Immediate focus and maintenance

- Execution of Phase 7: Project Protocol Upgrade (`brain79 update-project`), Legacy Wiki Conditioning, Multi-Harness Setup, and `brain79 doctor` Diagnostics.

---

[← Volver al Índice](../INDEX.md)
