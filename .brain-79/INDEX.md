---
type: navigation
last_updated: 2026-08-11
---

# Project index

> **Read this first at the start of every session.**
> This is the entry point to the project's wiki. It reflects the current state of the project.

---

## Project

**Name:** Brain-79
**Purpose:** AI memory protocol with mechanical validation for project wikis.
**Status:** Production (v1.0.0) — stable

---

## Current focus

- Maintenance of the organizational enforcement feature.
- Stabilization of `brain79_handoff_purge` and `brain79_migrate`.
- Full self-documentation of the wiki (dogfooding).

---


## Known issues

- None reported currently. Minor cosmetic issues are tracked on GitHub.

---

## Roadmap

- PyPI publication (v1.1.0) — next iteration.
- Optional auto-fix support for broken markdown links (future).

## Quick navigation

### Architecture
- [Architecture — CLI & MCP Symmetry](architecture/symmetry.md) — `brain-79` enforces strict 1:1 symmetry between CLI subcommands and MCP server tools. Any capability available to a human user in the terminal via `brain79 \<subcommand\>` is equally accessible to an AI agent via `brain79\_\<tool\>()`.
- [Architecture — CLI Dispatcher](architecture/dispatcher.md) — The CLI dispatcher system in `brain-79` is responsible for parsing global command-line flags and routing user invocations to deterministic CLI subcommands or launching the MCP server fallback.
- [Architecture — MCP Server](architecture/mcp-server.md) — The Model Context Protocol (MCP) server integration in `brain-79` enables AI assistants (such as Antigravity, Pi, OpenCode, Claude, Cursor) to interact with repository memory via standard JSON-RPC tools.
- [Architecture — System Current State](architecture/current-state.md) — This document maintains a high-level summary of the repository's current architecture, active capabilities, completed milestones, and immediate roadmap status as of version 1.0.0.

### Changelog
- [Changelog — Version 1.0.0](changelog/v1.md) — All notable changes to `brain-79` v1.0.0 release cycle.

### Decisions
- [ADR-001 — Architecture — Dual-Mode Hybrid CLI & MCP Server Interface](decisions/adr-001-hybrid-cli.md) — Accepted
- [ADR-002 — Handoffs — Immutable Session Transition Records](decisions/adr-002-immutable-handoffs.md) — Accepted
- [ADR-003 — Migration — Progressive V3 Migration with Legacy Status Default](decisions/adr-003-v3-legacy-status.md) — Accepted
- [ADR-004 — Curation — Synchronous Write-Time Frontmatter and Location Validation](decisions/adr-004-strict-write-validation.md) — Accepted
- [ADR-005 — Linter — Code Fence Masking for Decision and Debt Leakage Regex Rules](decisions/adr-005-fence-mask-tracking.md) — Accepted

### Features
- [Feature — FastMCP Integration](features/mcp-server.md) — The Model Context Protocol (MCP) server feature exposes `brain-79` operations as structured tools over JSON-RPC over stdio, integrating seamlessly with AI clients such as Antigravity, Pi, OpenCode, Claude Desktop, and Cursor.
- [Feature — Handoff Purge Operations](features/handoff-purge.md) — `brain79 handoff-purge` provides an explicit operational exception to handoff immutability. It allows developers and agents to clean up tactical short-term handoffs (`.brain-79/handoffs/handoff-\*.md`) upon completing sprint iterations, resetting demo repositories, or purging legacy session history.
- [Feature — Short-Term Handoff Continuity](features/handoff-continuity.md) — The Short-Term Handoff feature provides tactical transition management between AI development sessions. Unlike long-term wiki knowledge stored in subfolders, handoffs are immutable, timestamped state snapshots stored in `.brain-79/handoffs/handoff-%Y-%m-%d-%H%M%S-%f.md`.
- [Feature — Standalone CLI Interface](features/cli.md) — The Standalone CLI interface provides 13 deterministic command-line subcommands for managing the repository wiki, executing organizational linter checks, performing handoffs, and initializing memory protocols without requiring an active MCP host connection.
- [Feature — Wiki Organizational Enforcement](features/organizational-enforcement.md) — The Organizational Enforcement system prevents organic quality degradation of repository wikis. It automatically enforces frontmatter metadata schemas, checks type-location consistency, blocks structural decision leakage in non-decision folders, detects oversized or non-atomic articles, and identifies unfilled template placeholders in `INDEX.md`.

### Product
- [Brain-79 — Product Vision](product/overview.md) — LLMs maintain wikis that degrade organically:
