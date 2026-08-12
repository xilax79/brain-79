---
type: architecture
stability: stable
last_updated: 2026-08-11
---

# Architecture — System Current State

## Overview

This document maintains a high-level summary of the repository's current architecture, active capabilities, completed milestones, and immediate roadmap status as of version 1.0.0.

## Completed Milestones & Merged Features

- **Phase 1 – Core MVP & MCP Server**: FastMCP 2.0 integration, dual-mode CLI/MCP architecture, atomic POSIX file writes, and initial wiki IO primitives (`read`, `write`, `list`, `search`).
- **Phase 1.5 & 1.7 – Handoff Continuity & Init**: Immutable short-term session handoffs (`handoff-write`, `handoff-read`), project protocol initializer (`init`), pre-commit hooks, and universal `AGENTS.md` manifest.
- **Phase 3, 4, 5, 6 – Context, Install & Bootstrap**: TF-IDF context ranking (`brain79_context`), standalone installer (`install.py`), self-updater (`brain79 update`), and repository bootstrapping (`brain79_bootstrap`).
- **Phase 7 – Organizational Enforcement**: 10-subphase linter engine (`lint_organizational.py`), YAML frontmatter schema validation, location consistency checks, decision leakage prevention, and navigation registry generation.
- **Phase 8 – Operational Handoff Purge**: Destructive short-term handoff purge subcommand (`brain79 handoff-purge`) with dry-run default guard.
- **Self-Wiki Dogfooding (Phase A-D)**: Fully populated self-documenting `.brain-79/` wiki verified by `brain79 lint --strict`.

## System Invariants & Invariant Guards

- **Wiki Primacy**: Long-term wiki in `.brain-79/` is the absolute source of truth over tactical handoffs.
- **Synchronous Write Validation**: Writes to `.brain-79/` are validated against schema rules prior to disk mutation.
- **Code Fence Masking**: Regex linter rules mask code blocks before scanning to eliminate false positive leakage errors.
- **1:1 CLI & MCP Symmetry**: Every operational subcommand has a matching `@mcp.tool()` equivalent in `server.py`.

## Immediate Focus & Maintenance

- Maintenance of organizational linter rules and schema validation.
- Preservation of 100% test coverage and static type safety (`mypy --strict`, `ruff`).
- Preparation for PyPI packaging release (v1.1.0).
