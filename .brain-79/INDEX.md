---
type: navigation
last_updated: 2026-11-27
---

# Project index

> **Read this first at the start of every session.**
> This is the automated routing table for the project wiki.

## Quick navigation

### Architecture
- [Architecture — CLI and MCP symmetry](architecture/symmetry.md) — enforces MCP-subset / CLI-superset symmetry between the 9 focused FastMCP tools and 26 CLI subcommands
- [Architecture — CLI dispatcher](architecture/dispatcher.md) — CLI argument parsing, closed-whitelist subcommand routing across 26 commands, and POSIX exit code mappings
- [Architecture — Defect backlog and live evaluation remediations](architecture/defect-backlog.md) — master defect backlog and forensic analysis for live evaluation findings on Grand Palace Casino (test-wiki)
- [Architecture — Industrial-scale roadmap and adoption evolution](architecture/roadmap-industrial-scale.md) — project roadmap covering completed foundation (phases 0-16 and v0.17.0) and prioritized evolution (phase 17 PyPI release and phase 18 external drift lockfile)
- [Architecture — MCP server](architecture/mcp-server.md) — FastMCP server architecture, logging suppression, focused 9-tool surface, and lifecycle management
- [Architecture — System current state](architecture/current-state.md) — high-level overview of system architecture, active milestones, runtime invariants, and roadmap

### Changelog
- [Changelog — Historical internal development milestones (v1.0.0 through v2.0.2)](changelog/legacy-internal-releases.md) — historical record of internal development cycles (v1.0.0 through v2.0.2) prior to ADR-017 pre-GA recalibration
- [Changelog — Release 0.8.1: Living manuals, temporal decontamination, and codebase de-phasing](changelog/v0-8-1.md) — release v0.8.1 — living manuals, temporal decontamination, codebase de-phasing, and three-class document ontology
- [Changelog — Release 0.9.0: Project upgrade, multi-harness zero-config, and doctor diagnostics](changelog/v0-9-0.md) — release v0.9.0 — project protocol upgrader, delimited AGENTS.md blocks, multi-harness zero-config, and doctor diagnostics
- [Changelog — Release 0.9.1: Antigravity plugin, progressive disclosure, and root walk](changelog/v0-9-1.md) — release v0.9.1 — Antigravity native plugin, progressive AGENTS.md disclosure, and ancestor root walk
- [Changelog — Release 0.9.2: Zero-clone installation, CLI/Python 3.11+ alignment, and 3-layer Diátaxis documentation](changelog/v0-9-2.md) — release v0.9.2 — zero-clone installation, CLI/Python 3.11+ alignment, and 3-layer Diátaxis documentation
- [Changelog — Version 0.7.2 — Pre-GA semantic calibration](changelog/v0-7-2.md) — semantic versioning recalibration to 0.7.2 for pre-GA maturation prior to public PyPI release
- [Changelog — Version 0.8.0 — Transitive drift and ripple guards](changelog/v0-8-0.md) — phase 6.7 release — Merkle drift detection, transitive DAG propagation, Hard Session Ripple Gate, Anti-Sprawl Guard, and AST signature verification
- [Changelog — release 0.10.0: automated battle-testing, chaos fuzzing, and multi-repo gauntlet](changelog/v0-10-0.md) — release v0.10.0 — automated battle-testing, chaos fuzzing, and multi-repo gauntlet
- [Changelog — v0.12.0](changelog/v0-12-0.md) — release notes for v0.12.0 (Phase 11 public release readiness, English backlinks, native harnesses, core MCP default, and Windows CI latency recovery)
- [Changelog — v0.13.0](changelog/v0-13-0.md) — release notes for v0.13.0 (Phase 12 team-safe Git collaboration, INDEX.md merge driver, bootstrap --auto-map, and configurable enforcement tiers)
- [Changelog — v0.13.1](changelog/v0-13-1.md) — release notes for v0.13.1 (BUG-008 navigation registry disk reconciliation, BUG-009 index\_desync lint rule, and BUG-010 symmetric version skew detection)
- [Changelog — v0.14.0](changelog/v0-14-0.md) — release notes for v0.14.0 (Phase 13 MCP surface pruning, focused 9-tool MCP\_TOOLS, CLI superset, and --mcp-profile removal)
- [Changelog — v0.15.0](changelog/v0-15-0.md) — release notes for v0.15.0 (Phase 14 passive lifecycle hooks, read-only CI PR gate, composite GitHub Action, and 25-command CLI)
- [Changelog — v0.16.0](changelog/v0-16-0.md) — release notes for v0.16.0 (polyglot AST Guard C via brain79\[polyglot\], read-only brain79 stats, doctor diagnostics, and language-agnostic docs)
- [Changelog — v0.17.0](changelog/v0-17-0.md) — release notes for v0.17.0 (phase 16 longitudinal anti-rot release gate PASS 7/7 and SPEC-202611 agent ergonomics, strict pre-flight parity, and batch-read normalization)
- [Release v0.11.0 — Core refactoring and hardening](changelog/v0-11-0.md) — core architectural refactoring, concurrency hardening, centralized Git layer, security fixes, and modular decomposition

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
- [ADR-020 — Focused MCP surface and CLI superset](decisions/adr-020-focused-mcp-surface-and-cli-superset.md) — prune redundant MCP wrappers and dual-profile branching to formalize a focused 9-tool MCP surface as a strict subset of the 24-command CLI
- [ADR-021 — Passive lifecycle hooks and CI PR gate](decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md) — adopt opt-in native lifecycle hooks backed by a read-only CLI CI gate and composite GitHub Action with dual-tier enforcement
- [ADR-022 — Polyglot AST guards and context budget telemetry](decisions/adr-022-polyglot-ast-guards-and-context-stats.md) — isolate optional Tree-sitter polyglot AST guards behind brain79\[polyglot\] and ship read-only brain79 stats telemetry
- [Decision — ADR-018: Living manuals, temporal decontamination, and the three-class document ontology](decisions/adr-018-living-manuals-and-temporal-decontamination.md) — architectural foundation for living manuals, temporal decontamination, Chesterton's Fence for ADRs, and epocal changelog consolidation
- [Decision — ADR-019: External feature specifications and requirements standard](decisions/adr-019-external-specs-and-requirements-standard.md) — isolate repository feature specifications in specs/ outside .brain-79/ using EARS, BDD Given/When/Then, explicit non-goals, and CI governance tests

### Features
- [Feature — Cross-platform portability and centralized lock isolation](features/cross-platform-and-lock-isolation.md) — centralized .locks/ directory isolation, POSIX path and CRLF normalization, cross-platform Git hooks, and local Windows/Linux simulation tests
- [Feature — FastMCP integration](features/mcp-server.md) — model Context Protocol server exposing 9 focused hot-path tools over stdio JSON-RPC
- [Feature — Passive lifecycle hooks and CI PR gate](features/lifecycle-hooks-and-ci-gate.md) — read-only CI governance PR gate, composite GitHub Action, and cross-platform passive lifecycle hook runtime
- [Feature — Polyglot AST guards and context budget telemetry](features/polyglot-ast-guards-and-stats.md) — optional Tree-sitter polyglot AST Guard C for 10 language parsers and read-only brain79 stats context budget telemetry
- [Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics](features/project-upgrade-and-multi-harness-doctor.md) — non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP and lifecycle hook setup, and brain79 doctor diagnostics
- [Feature — Session knowledge triage and research persistence](features/session-triage-and-research-persistence.md) — session knowledge triage (Amnesia Test), zero-code research persistence guard, profile-aware curation guide, path prefix normalization, and handoff schema ergonomics
- [Feature — Short-term handoff continuity, freshness, and lifecycle operations](features/handoff-continuity.md) — tactical session transitions, freshness evaluation, authority decay, anti-hallucination work tracking, and operational purge
- [Feature — Standalone CLI interface](features/cli.md) — 26 deterministic CLI subcommands for managing wiki knowledge, context telemetry, CI governance, lifecycle hooks, linters, and handoffs
- [Feature — Team-safe Git collaboration and low-friction onboarding](features/team-collaboration-and-onboarding.md) — team-safe Git collaboration, git-ignored derived caches with deterministic rebuilds, 3-way INDEX.md merge driver, bootstrap --auto-map, centralized git\_ops, and dual-tier enforcement
- [Feature — Transitive drift detection, holistic ripple gates, anti-sprawl guards, and unbounded governing context](features/transitive-drift-and-ripple-guards.md) — merkle leaf-manifest drift detection, multi-hop DAG propagation, hard session ripple gate, anti-sprawl guard, AST signature verification, and unbounded Signal 1 context
- [Feature — Versioning and release governance](features/version-governance.md) — single-source semantic versioning via Hatchling, MCP handshake version reporting, and automated changelog/badge parity checks
- [Feature — Wiki organizational enforcement](features/organizational-enforcement.md) — prevent organic wiki degradation through frontmatter schema validation, decision leakage detection, unified lint collection, and navigation indexing

### Product
- [Brain-79 — Product vision](product/overview.md) — deterministic AI memory and mechanical documentation protocol designed to prevent organic wiki degradation in software repositories.

### Topics
- [Phase 16 — Longitudinal anti-rot benchmark harness and release gate](topics/phase-16-anti-rot-benchmark-results.md) — phase 16 longitudinal anti-rot benchmark harness, LedgerPulse testbed, calibrated baseline AC-6 results, and SPEC-202611 remediation tracker
- [Resolved v0.13.0 defects — Navigation registry completeness, lint index desynchronization, and MCP version skew](topics/v0-13-0-navigation-registry-and-lint-defects.md) — resolved v0.13.0 defects in navigation registry completeness, lint index desynchronization, and stale MCP version skew detection (fixed in v0.13.1)
