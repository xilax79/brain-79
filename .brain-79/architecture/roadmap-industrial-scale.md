---
type: architecture
summary: Industrial-scale roadmap covering completed core protocol phases (0-4) and next-stage adoption, portability, and release governance (5-8)
stability: stable
applies_to:
  - src/brain79/__init__.py
  - src/brain79/__main__.py
  - pyproject.toml
related:
  - decisions/adr-009-declarative-schema-and-dual-ontologies.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-013-versioning-and-release-governance.md
  - features/version-governance.md
  - features/cross-platform-and-lock-isolation.md
  - architecture/defect-backlog.md
last_updated: 2026-11-03
---

# Architecture — Industrial-Scale Roadmap & Adoption Evolution

## Overview

This document tracks the engineering roadmap of `brain-79`. Phases 0 through 4 established the core deterministic memory engine, the Two-Call Session Protocol, and universal ontologies. Phases 5 through 8 focus on **release governance, cross-platform portability, universal harness adoption, and context-budget guardrails**.

---

## Completed Foundation (Phases 0–4 — Condensed)

- **[x] Phase 0 — Core Invariant Alignment:** Unified write-time validation with organizational linting, enforced pure routing table rules on `INDEX.md` (ADR-008), fixed `bootstrap` templates, and standardized `_raw/sessions/` frontmatter.
- **[x] Phase 1 — Declarative Schema & Dual Ontology (ADR-009):** Decoupled validation mechanism from ontology policy via `.brain-79/SCHEMA.md` with `<0.1ms` caching, built-in `software` and `general` profiles, and custom directory extensions.
- **[x] Phase 2 — Deterministic Pre-Work Context & 1-Call Orientation (ADR-010):** Introduced `brain79_orient` and the 3-signal context ranker (`applies_to` path globs + field-weighted BM25 + 1-hop governing ADR graph expansion).
- **[x] Phase 3 — Zero-Turn Session Execution (ADR-011):** Introduced `brain79_session_commit` (all-or-nothing pre-flight transaction for raw logs, writes, edits, and handoffs) and section-projected batch reads (`brain79_read_batch`).
- **[x] Phase 4 — Structural Quality & Drift Detection (ADR-012):** Added per-type `## H2` structural skeleton enforcement, auto-injected backlink footers, and git-backed code-to-wiki drift detection (`documentation_drift_suspected`).
- **[x] Phase 5 — Versioning & Release Governance (ADR-013):** Single-source dynamic versioning via Hatchling (`__version__ = "2.0.0"`), FastMCP server version reporting, and automated release parity tests (SemVer, badges, changelog, CLI/MCP).

---

## Upcoming Execution Roadmap (Ordered by Dependency & Impact)

```
+-----------------------------------------------------------------------------------+
| Phase 5.5: Defect Backlog & Agent Protocol Polish (Pre-Phase 6)     | [ ] Planned |
+-----------------------------------------------------------------------------------+
| Phase 6: Centralized .locks/ Isolation & Cross-Platform OS I/O      | [ ] Planned |
+-----------------------------------------------------------------------------------+
| Phase 7: Multi-Harness Zero-Config & Doctor Diagnostics             | [ ] Planned |
+-----------------------------------------------------------------------------------+
| Phase 8: Zero-Clone Distribution & Context Budget Guardrails        | [ ] Planned |
+-----------------------------------------------------------------------------------+
```

### Phase 5.5: Defect Backlog & Agent Protocol Polish
- **Specification:** [Architecture — Defect Backlog & Agent Efficiency Deep Dive](defect-backlog.md)
- **Scope:** Fix `SCHEMA_GENERAL.md` broken root link (`BUG-001`), refine H2 atomicity heuristics & code-fence masking (`BUG-002`), include active schema summary in `orient()`, make `write`/`edit` receipts self-documenting (`INDEX.md auto-synced`), and enforce the **On-Demand Handoff Policy** (handoffs written only on explicit user request or autonomous sub-agent termination, never per turn).

### Phase 6: Centralized `.locks/` Isolation & Cross-Platform OS Portability
- **Specification:** [Feature — Cross-Platform Portability & Centralized Lock Isolation](../features/cross-platform-and-lock-isolation.md)
- **Scope:** Isolate all `filelock` mutex files into `.brain-79/.locks/` (eliminating `.md.lock` clutter in content directories), enforce `.as_posix()` path normalization and strict `LF` (`\n`) I/O across Windows/Linux/macOS, add NTFS retry resilience on atomic file replacement, harden `.git/hooks/pre-commit` PATH resolution, and verify via a local cross-platform simulation test suite (no external CI required).

### Phase 7: Multi-Harness Zero-Config & Environment Diagnostics (`brain79 doctor`)
- **Problem:** Different AI harnesses (Pi, Claude Code, Claude Desktop, Cursor, Windsurf, OpenCode, VS Code) expect MCP configurations in different paths, and desktop GUI apps do not inherit terminal `$PATH`, causing `spawn brain79 ENOENT` failures.
- **Deliverables:**
  1. **Harness-Aware Setup (`brain79 init` / `setup`):** Auto-detect or target specific harnesses, resolving absolute executable paths where GUI clients require them.
  2. **Diagnostic Command (`brain79 doctor`):** 1-second health check verifying binary PATH visibility, `.mcp.json` validity, `.brain-79/` permissions, lock acquisition, and git hook status.

### Phase 8: Zero-Clone Distribution & Context Budget Guardrails
- **Problem:** Installing or updating `brain-79` currently assumes a cloned repository (`scripts/install.py` and `git pull` inside `brain79 update`). Additionally, oversized articles can inflate `orient` payloads.
- **Deliverables:**
  1. **Standalone Package Installation & Update:** Support `uv tool install` from Git/PyPI and `uvx brain79`, decoupling `brain79 update` from local git repository assumptions.
  2. **Context Budget & Article Size Guardrails:** Enforce a configurable payload ceiling (`max_chars` / `max_tokens`) in `brain79_orient` and surface an `article_too_large` warning in `brain79 lint` when articles exceed optimal context size.

---

[← Volver al Índice](../INDEX.md)
