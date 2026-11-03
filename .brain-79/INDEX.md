---
type: navigation
last_updated: 2026-11-03
---

# Project index

> **Read this first at the start of every session.**
> This is the automated routing table for the project wiki.

## Quick navigation

### Architecture
- [Architecture — CLI & MCP Symmetry](architecture/symmetry.md) — Enforces strict 1:1 symmetry between CLI subcommands and FastMCP server tools
- [Architecture — CLI Dispatcher](architecture/dispatcher.md) — CLI argument parsing, closed-whitelist subcommand routing, and POSIX exit code mappings
- [Architecture — Industrial-Scale Roadmap & Adoption Evolution](architecture/roadmap-industrial-scale.md) — Industrial-scale roadmap covering completed core protocol phases (0-4) and next-stage adoption, portability, and release governance (5-8)
- [Architecture — MCP Server](architecture/mcp-server.md) — FastMCP server architecture, logging suppression, tool definitions, and lifecycle management
- [Architecture — System Current State](architecture/current-state.md) — High-level overview of system architecture, active milestones, runtime invariants, and roadmap

### Changelog
- [Changelog — Version 1.0.0](changelog/v1.md) — Initial production release of brain-79 with mechanical organizational enforcement and handoff continuity
- [Changelog — Version 1.1.0 — Performance & Session Workflow Optimization](changelog/v1-1.md) — Performance and session workflow optimizations, partial edits, batch writes, and schema inspection
- [Changelog — Version 2.0.0 — Two-Call Protocol & Release Governance](changelog/v2-0.md) — Major release 2.0.0 introducing Two-Call Session Protocol, declarative ontologies, deterministic drift detection, and release governance
- [Changelog — Version 2.0.1 — Purge Obsolete Integration Fixture](changelog/v2-0-1.md) — Remove obsolete legacy Truco Arena test fixture and decouple local development paths

### Decisions
- [ADR-001 — Architecture — Dual-Mode Hybrid CLI & MCP Server Interface](decisions/adr-001-hybrid-cli.md) — Dual-mode hybrid binary combining standalone CLI dispatcher with FastMCP stdio server
- [ADR-002 — Handoffs — Immutable Session Transition Records](decisions/adr-002-immutable-handoffs.md) — Tactical handoff immutability via unique timestamped files to maintain audit trail and prevent context loss
- [ADR-003 — Migration — Progressive V3 Migration with Legacy Status Default](decisions/adr-003-v3-legacy-status.md) — Assigning status legacy during progressive V3 migration to preserve semantic intent without blocking adoption
- [ADR-004 — Curation — Synchronous Write-Time Frontmatter and Location Validation](decisions/adr-004-strict-write-validation.md) — Synchronous write-time schema validation with multi-error reporting and deterministic field auto-fill
- [ADR-005 — Linter — Code Fence Masking for Decision and Debt Leakage Regex Rules](decisions/adr-005-fence-mask-tracking.md) — Enforcing code fence masking in organizational linter to eliminate false positives in documentation examples
- [ADR-006 — Architecture — Automatic Navigation Regeneration, Inline Health Checks, and Partial/Batch Operations](decisions/adr-006-auto-navigation-and-batch-operations.md) — Automatic thread-safe navigation synchronization, inline write diagnostics, and partial/batch write operations
- [ADR-007 — Navigation — Explicit Frontmatter Summary and Article Backlinks](decisions/adr-007-frontmatter-summary-and-backlink-navigation.md) — Standardize explicit frontmatter summary field and footer backlink navigation convention
- [ADR-008 — Architecture — Pure Automated Routing Table for INDEX.md](decisions/adr-008-pure-index-routing-table.md) — Pure automated routing table architecture for INDEX.md and automated timestamp synchronization
- [ADR-009 — Declarative Schema Loading & Dual Built-In Ontologies (Mechanism vs. Policy)](decisions/adr-009-declarative-schema-and-dual-ontologies.md) — Decoupling validation mechanism from ontology policy with dual built-in profiles and custom folder support
- [ADR-010 — Two-Call Session Protocol: 1-Call Cold Start Orient and Deterministic 3-Signal Context Ranking](decisions/adr-010-orient-and-3-signal-context-ranking.md) — 1-Call cold start orientation and deterministic 3-signal context ranking
- [ADR-011 — Two-Call Session Protocol: 1-Call Atomic Session Commit & Section-Projected Batch Reading](decisions/adr-011-session-commit-and-batch-reading.md) — 1-Call atomic session finalization and section-projected batch reading
- [ADR-012 — Structural Article Quality, Auto-Injected Backlinks, and Deterministic Drift Detection](decisions/adr-012-structural-quality-and-drift-detection.md) — Section-level structural skeletons, auto-injected backlinks, and deterministic code-to-wiki drift detection
- [ADR-013 — Architecture — Single-Source Semantic Versioning and Mechanical Release Governance](decisions/adr-013-versioning-and-release-governance.md) — Single-source semantic versioning via Hatchling, FastMCP version handshake exposure, and automated release parity testing

### Features
- [Feature — Cross-Platform Portability & Centralized Lock Isolation (Phase 6 Specification)](features/cross-platform-and-lock-isolation.md) — Centralized .locks/ directory isolation, POSIX path and CRLF normalization, cross-platform Git hooks, and local Windows/Linux simulation tests
- [Feature — FastMCP Integration](features/mcp-server.md) — Model Context Protocol server exposing wiki operations as JSON-RPC tools with token de-duplication
- [Feature — Handoff Purge Operations](features/handoff-purge.md) — Safe batch deletion of short-term handoffs with dry-run default guard and navigation registry cleanup
- [Feature — Short-Term Handoff Continuity](features/handoff-continuity.md) — Tactical session transitions, immutable state snapshots, and anti-hallucination work tracking
- [Feature — Standalone CLI Interface](features/cli.md) — Deterministic CLI subcommands for managing wiki knowledge, executing linters, and managing handoffs
- [Feature — Versioning & Release Governance (Phase 5 Specification)](features/version-governance.md) — Single-source semantic versioning via Hatchling, MCP handshake version reporting, and automated changelog/badge parity checks
- [Feature — Wiki Organizational Enforcement](features/organizational-enforcement.md) — Prevent organic wiki degradation through frontmatter schema validation, decision leakage detection, and navigation indexing

### Product
- [Brain-79 — Product Vision](product/overview.md) — Deterministic AI memory and mechanical documentation protocol designed to prevent organic wiki degradation in software repositories.
