---
type: navigation
last_updated: 2026-11-05
---

# Project index

> **Read this first at the start of every session.**
> This is the automated routing table for the project wiki.

## Quick navigation

### Architecture
- [Architecture — CLI and MCP symmetry](architecture/symmetry.md) — enforces strict 1:1 symmetry between CLI subcommands and FastMCP server tools
- [Architecture — CLI dispatcher](architecture/dispatcher.md) — CLI argument parsing, closed-whitelist subcommand routing, and POSIX exit code mappings
- [Architecture — Defect backlog and agent efficiency deep dive](architecture/defect-backlog.md) — master defect backlog, forensic root-cause analysis, and specification for bug fixes, agent efficiency, and on-demand handoff policy
- [Architecture — Industrial-scale roadmap and adoption evolution](architecture/roadmap-industrial-scale.md) — industrial-scale roadmap covering completed core protocol phases (0-6.5) and next-stage handoff freshness, adoption, and context guardrails (6.6-8)
- [Architecture — MCP server](architecture/mcp-server.md) — FastMCP server architecture, logging suppression, tool definitions, and lifecycle management
- [Architecture — System current state](architecture/current-state.md) — high-level overview of system architecture, active milestones, runtime invariants, and roadmap

### Changelog
- [Changelog — Version 1.0.0](changelog/v1.md) — initial production release of brain-79 with mechanical organizational enforcement and handoff continuity
- [Changelog — Version 1.1.0 — Performance and session workflow optimization](changelog/v1-1.md) — performance and session workflow optimizations, partial edits, batch writes, and schema inspection
- [Changelog — Version 2.0.0 — Two-call protocol and release governance](changelog/v2-0.md) — major release 2.0.0 introducing Two-Call Session Protocol, declarative ontologies, deterministic drift detection, and release governance
- [Changelog — Version 2.0.1 — Purge obsolete integration fixture](changelog/v2-0-1.md) — remove obsolete legacy Truco Arena test fixture and decouple local development paths
- [Changelog — Version 2.0.2 — Defect backlog and agent protocol polish](changelog/v2-0-2.md) — defect backlog remediations, composite H2 atomicity thresholds, root backlink normalization, and agent protocol efficiency

### Decisions
- [ADR-001 — Architecture — Dual-mode hybrid CLI and MCP server interface](decisions/adr-001-hybrid-cli.md) — dual-mode hybrid binary combining standalone CLI dispatcher with FastMCP stdio server
- [ADR-002 — Handoffs — Immutable session transition records](decisions/adr-002-immutable-handoffs.md) — tactical handoff immutability via unique timestamped files to maintain audit trail and prevent context loss
- [ADR-003 — Migration — Progressive V3 migration with legacy status default](decisions/adr-003-v3-legacy-status.md) — assigning status legacy during progressive V3 migration to preserve semantic intent without blocking adoption
- [ADR-004 — Curation — Synchronous write-time frontmatter and location validation](decisions/adr-004-strict-write-validation.md) — synchronous write-time schema validation with multi-error reporting and deterministic field auto-fill
- [ADR-005 — Linter — Code fence masking for decision and debt leakage regex rules](decisions/adr-005-fence-mask-tracking.md) — enforcing code fence masking in organizational linter to eliminate false positives in documentation examples
- [ADR-006 — Architecture — Automatic navigation regeneration, inline health checks, and partial/batch operations](decisions/adr-006-auto-navigation-and-batch-operations.md) — automatic thread-safe navigation synchronization, inline write diagnostics, and partial/batch write operations
- [ADR-007 — Navigation — Explicit frontmatter summary and article backlinks](decisions/adr-007-frontmatter-summary-and-backlink-navigation.md) — standardize explicit frontmatter summary field and footer backlink navigation convention
- [ADR-008 — Architecture — Pure automated routing table for INDEX.md](decisions/adr-008-pure-index-routing-table.md) — pure automated routing table architecture for INDEX.md and automated timestamp synchronization
- [ADR-009 — Declarative schema loading and dual built-in ontologies (mechanism vs. policy)](decisions/adr-009-declarative-schema-and-dual-ontologies.md) — decoupling validation mechanism from ontology policy with dual built-in profiles and custom folder support
- [ADR-010 — Two-call session protocol: 1-call cold start orient and deterministic 3-signal context ranking](decisions/adr-010-orient-and-3-signal-context-ranking.md) — 1-call cold start orientation and deterministic 3-signal context ranking
- [ADR-011 — Two-call session protocol: 1-call atomic session commit and section-projected batch reading](decisions/adr-011-session-commit-and-batch-reading.md) — 1-call atomic session finalization and section-projected batch reading
- [ADR-012 — Structural article quality, auto-injected backlinks, and deterministic drift detection](decisions/adr-012-structural-quality-and-drift-detection.md) — section-level structural skeletons, auto-injected backlinks, and deterministic code-to-wiki drift detection
- [ADR-013 — Architecture — Single-source semantic versioning and mechanical release governance](decisions/adr-013-versioning-and-release-governance.md) — single-source semantic versioning via Hatchling, FastMCP version handshake exposure, and automated release parity testing
- [ADR-014: Centralized lock directory isolation and cross-platform I/O normalization](decisions/adr-014-centralized-locks-and-cross-platform-io.md) — centralize file locks in .brain-79/.locks/, enforce POSIX paths, strict LF I/O, and exact-case resolution
- [ADR-015: Sentence case first policy for documentation and wiki generation](decisions/adr-015-sentence-case-first-policy.md) — enforce sentence case first across all documentation, headings, lists, and wiki generation

### Features
- [Feature — Cross-platform portability and centralized lock isolation (Phase 6 specification)](features/cross-platform-and-lock-isolation.md) — centralized .locks/ directory isolation, POSIX path and CRLF normalization, cross-platform Git hooks, and local Windows/Linux simulation tests
- [Feature — FastMCP integration](features/mcp-server.md) — Model Context Protocol server exposing wiki operations as JSON-RPC tools with token de-duplication
- [Feature — Handoff purge operations](features/handoff-purge.md) — safe batch deletion of short-term handoffs with dry-run default guard and navigation registry cleanup
- [Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics (Phase 7 specification)](features/project-upgrade-and-multi-harness-doctor.md) — non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP setup, and brain79 doctor diagnostics
- [Feature — Session knowledge triage, research persistence guard and handoff ergonomics (Phase 6.5)](features/session-triage-and-research-persistence.md) — specification for Phase 6.5 — session knowledge triage (Amnesia Test), zero-code research persistence guard, profile-aware curation guide,path prefix normalization, and handoff schema ergonomics
- [Feature — Short-term handoff continuity](features/handoff-continuity.md) — tactical session transitions, immutable state snapshots, and anti-hallucination work tracking
- [Feature — Standalone CLI interface](features/cli.md) — deterministic CLI subcommands for managing wiki knowledge, executing linters, and managing handoffs
- [Feature — Versioning and release governance (Phase 5 specification)](features/version-governance.md) — single-source semantic versioning via Hatchling, MCP handshake version reporting, and automated changelog/badge parity checks
- [Feature — Wiki organizational enforcement](features/organizational-enforcement.md) — prevent organic wiki degradation through frontmatter schema validation, decision leakage detection, and navigation indexing

### Product
- [Brain-79 — Product vision](product/overview.md) — deterministic AI memory and mechanical documentation protocol designed to prevent organic wiki degradation in software repositories.
