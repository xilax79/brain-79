---
type: decision
status: accepted
date: 2026-08-11
deciders: [xilax]
last_updated: 2026-08-11
---

# ADR-001 — Architecture — Dual-Mode Hybrid CLI & MCP Server Interface

## Status

Accepted

## Context

AI assistants (`agy`, `pi`, `opencode`, `claude`) interact with repository context via MCP over JSON-RPC stdio. However, developers, CI/CD pipelines, and git pre-commit hooks require deterministic, standard CLI execution without launching an MCP client harness.

Having separate tools for CLI and MCP would lead to code duplication, behavioral desynchronization, and higher maintenance overhead.

## Decision

We chose to implement `brain-79` as a dual-mode hybrid tool:
- When invoked without subcommands (e.g. `brain79 --project-root .`), it starts as a FastMCP server on standard IO.
- When invoked with a whitelisted subcommand (e.g. `brain79 read INDEX.md`), it positionally routes execution to standard CLI handlers in `dispatch.py`.

## Consequences

- **Positive**: 1:1 operational symmetry between CLI and MCP tool interfaces.
- **Positive**: Pre-commit hooks and CI scripts can execute `brain79 lint` directly.
- **Negative**: Entry point `__main__.py` must parse flags carefully to suppress MCP startup banners (`FASTMCP_SHOW_SERVER_BANNER=false`) when serving.

## Alternatives Considered

- **Separate CLI binary (`brain79-cli`)**: Rejected to avoid binary clutter and separate package entry points.
- **MCP-only interface**: Rejected because git hooks and terminal pipelines cannot interact with stdio JSON-RPC directly.
