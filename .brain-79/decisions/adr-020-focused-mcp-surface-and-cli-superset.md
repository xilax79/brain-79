---
type: decision
summary: prune redundant MCP wrappers and dual-profile branching to formalize a focused 9-tool MCP surface as a strict subset of the 24-command CLI
status: accepted
date: 2026-11-23
deciders:
  - xilax
related:
  - decisions/adr-001-hybrid-cli.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
last_updated: 2026-11-23
---

# ADR-020 — Focused MCP surface and CLI superset

## Status

Accepted (2026-11-23; supersedes the 1:1 22-tool symmetry policy of ADR-001 and dual-profile routing from v0.11.0–v0.13.1).

## Context

Under ADR-001, `brain-79` exposed 22 FastMCP tools mirroring 22 of 24 CLI subcommands, later split into `core` (8 tools) and `full` (22 tools) via `--mcp-profile` and `BRAIN79_MCP_PROFILE`. Thirteen of those tools were either subsumed by the two-call session protocol (`brain79_orient` and `brain79_session_commit` per ADR-010 and ADR-011) or were sporadic terminal maintenance commands (`migrate`, `doctor`, `update-project`, `navigate`, `handoff-purge`). Maintaining 13 redundant MCP wrappers and dual-profile branching inflated `src/brain79/server.py`, duplicated test surfaces, and added configuration complexity before PyPI publication.

## Decision

1. **Single fixed 9-tool MCP surface (`MCP_TOOLS`)**: `src/brain79/server.py` exposes only `brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, and `brain79_bootstrap` (retained so shell-less MCP clients can bootstrap empty wikis).
2. **CLI superset preserved**: all 24 CLI subcommands in `WHITELIST` (`src/brain79/cli/dispatch.py`) remain intact. Future administrative and CI commands (such as `ci-check` and `stats`) default to CLI-only.
3. **Profile flag removal**: `--mcp-profile` is removed from `src/brain79/__main__.py` (passing it emits a migration error to `stderr` and exits with code `2`). Legacy `BRAIN79_MCP_PROFILE` environment variables are silently ignored during MCP stdio startup so strict MCP hosts never drop the handshake.
4. **Subset symmetry invariant**: `tests/test_symmetry.py` enforces `MCP_TOOLS` ⊂ `WHITELIST` and parameter parity for retained MCP tools.

## Consequences

- **Positive**: cuts `src/brain79/server.py` roughly in half, eliminates dual-profile branching and stale tool drift, and establishes a clear boundary between hot-path MCP session tools and full CLI operations.
- **Negative**: users whose MCP client configs passed `--mcp-profile full` must remove that flag and invoke administrative commands via `brain79 <command>` CLI.

---

[← Back to Index](../INDEX.md)
