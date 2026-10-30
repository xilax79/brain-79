---
type: navigation
last_updated: 2026-10-29
---

# Project index

> **Read this first at the start of every session.**
> This is the entry point to the project's wiki. It reflects the current state of the project.

---

## Project

**Name:** Brain-79
**Purpose:** AI memory protocol with mechanical validation for project wikis.
**Status:** Production (v1.1.0) — stable

---

## Current focus

- **Active branch**: Stabilization and UAT for frontmatter summaries and backlink navigation (`feat/frontmatter-summary-and-backlinks`).
- **Immediate milestone**: Decoupling schema validation to support arbitrary knowledge domains (`--profile presets`).

---

## Known issues

- None reported currently. Issues and discussions are tracked on GitHub.

---

## Roadmap

The authoritative, long-term engineering roadmap is maintained in:
👉 [**Industrial-Scale Roadmap & Performance Evolution**](architecture/roadmap-industrial-scale.md)

Key upcoming milestones:
1. **Universal Knowledge Domains (`--profile`)**: Research, writing, and custom domain schemas.
2. **Sub-Second Session Finalization**: Atomic `brain79_session_commit` in a single tool turn.
3. **High-Concurrency Storage**: SQLite WAL transactional registry (`.cache.db`).
4. **Embedded Local Semantic Search**: Hybrid BM25 and `sqlite-vec` engine.

## Quick navigation

### Architecture
- [Architecture — CLI & MCP Symmetry](architecture/symmetry.md) — Enforces strict 1:1 symmetry between CLI subcommands and FastMCP server tools
- [Architecture — CLI Dispatcher](architecture/dispatcher.md) — CLI argument parsing, closed-whitelist subcommand routing, and POSIX exit code mappings
- [Architecture — Industrial-Scale Roadmap & Performance Evolution](architecture/roadmap-industrial-scale.md) — Strategic roadmap for enterprise-grade scalability, concurrency, sub-second session commits, and local semantic retrieval
- [Architecture — MCP Server](architecture/mcp-server.md) — FastMCP server architecture, logging suppression, tool definitions, and lifecycle management
- [Architecture — System Current State](architecture/current-state.md) — High-level overview of system architecture, active milestones, runtime invariants, and roadmap

### Changelog
- [Changelog — Version 1.0.0](changelog/v1.md) — Initial production release of brain-79 with mechanical organizational enforcement and handoff continuity
- [Changelog — Version 1.1.0 — Performance & Session Workflow Optimization](changelog/v1-1.md) — Performance and session workflow optimizations, partial edits, batch writes, and schema inspection

### Decisions
- [ADR-001 — Architecture — Dual-Mode Hybrid CLI & MCP Server Interface](decisions/adr-001-hybrid-cli.md) — Dual-mode hybrid binary combining standalone CLI dispatcher with FastMCP stdio server
- [ADR-002 — Handoffs — Immutable Session Transition Records](decisions/adr-002-immutable-handoffs.md) — Tactical handoff immutability via unique timestamped files to maintain audit trail and prevent context loss
- [ADR-003 — Migration — Progressive V3 Migration with Legacy Status Default](decisions/adr-003-v3-legacy-status.md) — Assigning status legacy during progressive V3 migration to preserve semantic intent without blocking adoption
- [ADR-004 — Curation — Synchronous Write-Time Frontmatter and Location Validation](decisions/adr-004-strict-write-validation.md) — Synchronous write-time schema validation with multi-error reporting and deterministic field auto-fill
- [ADR-005 — Linter — Code Fence Masking for Decision and Debt Leakage Regex Rules](decisions/adr-005-fence-mask-tracking.md) — Enforcing code fence masking in organizational linter to eliminate false positives in documentation examples
- [ADR-006 — Architecture — Automatic Navigation Regeneration, Inline Health Checks, and Partial/Batch Operations](decisions/adr-006-auto-navigation-and-batch-operations.md) — Automatic thread-safe navigation synchronization, inline write diagnostics, and partial/batch write operations
- [ADR-007 — Navigation — Explicit Frontmatter Summary and Article Backlinks](decisions/adr-007-frontmatter-summary-and-backlink-navigation.md) — Standardize explicit frontmatter summary field and footer backlink navigation convention

### Features
- [Feature — FastMCP Integration](features/mcp-server.md) — Model Context Protocol server exposing wiki operations as JSON-RPC tools with token de-duplication
- [Feature — Handoff Purge Operations](features/handoff-purge.md) — Safe batch deletion of short-term handoffs with dry-run default guard and navigation registry cleanup
- [Feature — Short-Term Handoff Continuity](features/handoff-continuity.md) — Tactical session transitions, immutable state snapshots, and anti-hallucination work tracking
- [Feature — Standalone CLI Interface](features/cli.md) — Deterministic CLI subcommands for managing wiki knowledge, executing linters, and managing handoffs
- [Feature — Wiki Organizational Enforcement](features/organizational-enforcement.md) — Prevent organic wiki degradation through frontmatter schema validation, decision leakage detection, and navigation indexing

### Product
- [Brain-79 — Product Vision](product/overview.md) — Deterministic AI memory and mechanical documentation protocol designed to prevent organic wiki degradation in software repositories.
