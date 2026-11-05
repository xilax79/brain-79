---
type: architecture
summary: industrial-scale roadmap covering completed core protocol phases (0-4) and next-stage adoption, portability, and release governance (5-8)
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
  - features/project-upgrade-and-multi-harness-doctor.md
  - architecture/defect-backlog.md
last_updated: 2026-11-04
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering roadmap of `brain-79`. Phases 0 through 4 established the core deterministic memory engine, the Two-Call Session Protocol, and universal ontologies. Phases 5 through 8 focus on **release governance, cross-platform portability, universal harness adoption, and context-budget guardrails**.

---

## Completed foundation (Phases 0–4 — condensed)

- **[x] Phase 0 — Core Invariant Alignment:** Unified write-time validation with organizational linting, enforced pure routing table rules on `INDEX.md` (ADR-008), fixed `bootstrap` templates, and standardized `_raw/sessions/` frontmatter.
- **[x] Phase 1 — Declarative Schema & Dual Ontology (ADR-009):** Decoupled validation mechanism from ontology policy via `.brain-79/SCHEMA.md` with `<0.1ms` caching, built-in `software` and `general` profiles, and custom directory extensions.
- **[x] Phase 2 — Deterministic Pre-Work Context & 1-Call Orientation (ADR-010):** Introduced `brain79_orient` and the 3-signal context ranker (`applies_to` path globs + field-weighted BM25 + 1-hop governing ADR graph expansion).
- **[x] Phase 3 — Zero-Turn Session Execution (ADR-011):** Introduced `brain79_session_commit` (all-or-nothing pre-flight transaction for raw logs, writes, edits, and handoffs) and section-projected batch reads (`brain79_read_batch`).
- **[x] Phase 4 — Structural Quality & Drift Detection (ADR-012):** Added per-type `## H2` structural skeleton enforcement, auto-injected backlink footers, and git-backed code-to-wiki drift detection (`documentation_drift_suspected`).
- **[x] Phase 5 — Versioning & Release Governance (ADR-013):** Single-source dynamic versioning via Hatchling (`__version__ = "2.0.0"`), FastMCP server version reporting, and automated release parity tests (SemVer, badges, changelog, CLI/MCP).
- **[x] Phase 5.5 — Defect Backlog & Agent Protocol Polish:** Resolved `SCHEMA_GENERAL.md` broken root link (BUG-001) with code-fence safe footer normalizer, refined composite H2 atomicity heuristics (BUG-002), exposed Active Schema Summary in `orient()` (INEF-002), made write receipts self-documenting (`INDEX.md auto-synced`) (INEF-001), and formalized the On-Demand Handoff Policy across engine and manifests (INEF-003).
- **[x] Phase 6 — Centralized `.locks/` Isolation & Cross-Platform OS Portability (ADR-014):** Isolated all mutex locks into `.brain-79/.locks/` (eliminating adjacent `.md.lock` clutter), added automatic legacy lock purge, enforced segment-by-segment Linux case-sensitivity parity on macOS APFS, ensured POSIX path normalization across registries and engines, implemented atomic replace with retry on NTFS PermissionError, and guaranteed pure LF line endings on all I/O.

---

## Upcoming execution roadmap (ordered by dependency and impact)

```
+-----------------------------------------------------------------------------------+
| Phase 7: Multi-Harness Zero-Config & Doctor Diagnostics             | [ ] Planned |
+-----------------------------------------------------------------------------------+
| Phase 8: Zero-Clone Distribution & Context Budget Guardrails        | [ ] Planned |
+-----------------------------------------------------------------------------------+
```

### Phase 7: Project protocol upgrade, legacy wiki reconditioning and doctor diagnostics (`brain79 doctor`)
- **Specification:** [Feature — Project Upgrade, Legacy Wiki Conditioning, Multi-Harness Setup & Doctor Diagnostics](../features/project-upgrade-and-multi-harness-doctor.md)
- **Scope:** Solve "Split-Brain" version skew across existing projects via delimited managed blocks in `AGENTS.md` (`<!-- brain79:start -->`), non-destructive `SCHEMA.md` upgrades (preserving `profile` and `custom_types`), two-tier legacy wiki reconditioning (`migrate_wiki` v2), GUI-safe absolute binary paths in MCP configs, and the `brain79 doctor [--fix]` diagnostic tool.

### Phase 8: Zero-clone distribution and context budget guardrails
- **Problem:** Installing or updating `brain-79` currently assumes a cloned repository (`scripts/install.py` and `git pull` inside `brain79 update`). Additionally, oversized articles can inflate `orient` payloads.
- **Deliverables:**
  1. **Standalone Package Installation & Update:** Support `uv tool install` from Git/PyPI and `uvx brain79`, decoupling `brain79 update` from local git repository assumptions.
  2. **Context Budget & Article Size Guardrails:** Enforce a configurable payload ceiling (`max_chars` / `max_tokens`) in `brain79_orient` and surface an `article_too_large` warning in `brain79 lint` when articles exceed optimal context size.

---

[← Volver al Índice](../INDEX.md)
