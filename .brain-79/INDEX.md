---
type: navigation
last_updated: 2026-11-13
---

# Project index

> **Read this first at the start of every session.**
> This is the automated routing table for the project wiki.

## Quick navigation

### Architecture
- [Architecture — CLI and MCP symmetry](architecture/symmetry.md) — enforces strict 1:1 symmetry between CLI subcommands and FastMCP server tools
- [Architecture — CLI dispatcher](architecture/dispatcher.md) — CLI argument parsing, closed-whitelist subcommand routing, and POSIX exit code mappings
- [Architecture — Defect backlog and live evaluation remediations](architecture/defect-backlog.md) — master defect backlog and forensic analysis for live evaluation findings on Grand Palace Casino (test-wiki)
- [Architecture — Industrial-scale roadmap and adoption evolution](architecture/roadmap-industrial-scale.md) — industrial-scale roadmap covering completed core protocol phases (0-6.8) and next-stage adoption and context guardrails (7-8)
- [Architecture — MCP server](architecture/mcp-server.md) — FastMCP server architecture, logging suppression, tool definitions, and lifecycle management
- [Architecture — System current state](architecture/current-state.md) — high-level overview of system architecture, active milestones, runtime invariants, and roadmap

### Changelog
- [Changelog — Historical internal development milestones (v1.0.0 through v2.0.2)](changelog/legacy-internal-releases.md) — historical record of internal development cycles (v1.0.0 through v2.0.2) prior to ADR-017 pre-GA recalibration
- [Changelog — Release 0.8.1: Living manuals, temporal decontamination, and codebase de-phasing](changelog/v0-8-1.md) — release v0.8.1 — living manuals, temporal decontamination, codebase de-phasing, and three-class document ontology
- [Changelog — Release 0.9.0: Project upgrade, multi-harness zero-config, and doctor diagnostics](changelog/v0-9-0.md) — release v0.9.0 — project protocol upgrader, delimited AGENTS.md blocks, multi-harness zero-config, and doctor diagnostics
- [Changelog — Version 0.7.2 — Pre-GA semantic calibration](changelog/v0-7-2.md) — semantic versioning recalibration to 0.7.2 for pre-GA maturation prior to public PyPI release
- [Changelog — Version 0.8.0 — Transitive drift and ripple guards](changelog/v0-8-0.md) — Phase 6.7 release — Merkle drift detection, transitive DAG propagation, Hard Session Ripple Gate, Anti-Sprawl Guard, and AST signature verification

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
- [ADR-016: Handoff freshness, provenance, and authority decay](decisions/adr-016-handoff-freshness-and-authority-decay.md) — treat handoffs as perishable transition notes with authority decaying based on deterministic workspace drift
- [ADR-017: Semantic versioning calibration for pre-GA maturation](decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md) — semantic versioning calibration to 0.7.2 for pre-GA maturation prior to public release
- [Decision — ADR-018: Living manuals, temporal decontamination, and the three-class document ontology](decisions/adr-018-living-manuals-and-temporal-decontamination.md) — architectural foundation for living manuals, temporal decontamination, Chesterton's Fence for ADRs, and epocal changelog consolidation

### Features
- [Feature — Cross-platform portability and centralized lock isolation](features/cross-platform-and-lock-isolation.md) — centralized .locks/ directory isolation, POSIX path and CRLF normalization, cross-platform Git hooks, and local Windows/Linux simulation tests
- [Feature — FastMCP integration](features/mcp-server.md) — Model Context Protocol server exposing wiki operations as JSON-RPC tools with token de-duplication
- [Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics](features/project-upgrade-and-multi-harness-doctor.md) — non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP setup, and brain79 doctor diagnostics
- [Feature — Session knowledge triage and research persistence](features/session-triage-and-research-persistence.md) — session knowledge triage (Amnesia Test), zero-code research persistence guard, profile-aware curation guide, path prefix normalization, and handoff schema ergonomics
- [Feature — Short-term handoff continuity, freshness, and lifecycle operations](features/handoff-continuity.md) — tactical session transitions, freshness evaluation, authority decay, anti-hallucination work tracking, and operational purge
- [Feature — Standalone CLI interface](features/cli.md) — deterministic CLI subcommands for managing wiki knowledge, executing linters, and managing handoffs
- [Feature — Transitive drift detection, holistic ripple gates, anti-sprawl guards, and unbounded governing context](features/transitive-drift-and-ripple-guards.md) — merkle leaf-manifest drift detection, multi-hop DAG propagation, hard session ripple gate, anti-sprawl guard, AST signature verification, and unbounded Signal 1 context
- [Feature — Versioning and release governance](features/version-governance.md) — single-source semantic versioning via Hatchling, MCP handshake version reporting, and automated changelog/badge parity checks
- [Feature — Wiki organizational enforcement](features/organizational-enforcement.md) — prevent organic wiki degradation through frontmatter schema validation, decision leakage detection, and navigation indexing

### Product
- [Brain-79 — Product vision](product/overview.md) — deterministic AI memory and mechanical documentation protocol designed to prevent organic wiki degradation in software repositories.
