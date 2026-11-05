---
type: architecture
summary: industrial-scale roadmap covering completed core protocol phases (0-6.6) and next-stage adoption and context guardrails (7-8)
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
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-015-sentence-case-first-policy.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
  - features/version-governance.md
  - features/cross-platform-and-lock-isolation.md
  - features/session-triage-and-research-persistence.md
  - features/handoff-freshness.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - architecture/defect-backlog.md
last_updated: 2026-11-05
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering roadmap of `brain-79`. Phases 0 through 6.6 established the core deterministic memory engine, the Two-Call Session Protocol, universal ontologies, release governance, cross-platform `.locks/` isolation, session knowledge triage, and handoff freshness with authority decay. Phases 7 and 8 focus on **universal multi-harness adoption and context-budget guardrails**.

---

## Completed foundation (Phases 0–6.6 — condensed)

- **[x] Phase 0 — Core invariant alignment**: unified write-time validation with organizational linting, enforced pure routing table rules on `INDEX.md` (ADR-008), fixed `bootstrap` templates, and standardized `_raw/sessions/` frontmatter.
- **[x] Phase 1 — Declarative schema & dual ontology (ADR-009)**: decoupled validation mechanism from ontology policy via `.brain-79/SCHEMA.md` with `<0.1ms` caching, built-in `software` and `general` profiles, and custom directory extensions.
- **[x] Phase 2 — Deterministic pre-work context & 1-call orientation (ADR-010)**: introduced `brain79_orient` and the 3-signal context ranker (`applies_to` path globs + field-weighted BM25 + 1-hop governing ADR graph expansion).
- **[x] Phase 3 — Zero-turn session execution (ADR-011)**: introduced `brain79_session_commit` (all-or-nothing pre-flight transaction for raw logs, writes, edits, and handoffs) and section-projected batch reads (`brain79_read_batch`).
- **[x] Phase 4 — Structural quality & drift detection (ADR-012)**: added per-type `## H2` structural skeleton enforcement, auto-injected backlink footers, and git-backed code-to-wiki drift detection (`documentation_drift_suspected`).
- **[x] Phase 5 — Versioning & release governance (ADR-013)**: single-source dynamic versioning via Hatchling (`__version__ = "2.0.0"`), FastMCP server version reporting, and automated release parity tests (SemVer, badges, changelog, CLI/MCP).
- **[x] Phase 5.5 — Defect backlog & agent protocol polish**: resolved `SCHEMA_GENERAL.md` broken root link (BUG-001) with code-fence safe footer normalizer, refined composite H2 atomicity heuristics (BUG-002), exposed active schema summary in `orient()` (INEF-002), made write receipts self-documenting (`INDEX.md auto-synced`) (INEF-001), and formalized the on-demand handoff policy across engine and manifests (INEF-003).
- **[x] Phase 6 — Centralized `.locks/` isolation, cross-platform OS portability & sentence case governance (ADR-014, ADR-015)**: isolated all mutex locks into `.brain-79/.locks/`, added automatic legacy lock purge, enforced segment-by-segment Linux case-sensitivity parity on macOS APFS, ensured POSIX path normalization across registries and engines, implemented atomic replace with retry on NTFS PermissionError, guaranteed pure LF line endings on all I/O, and standardized sentence case across all documentation and templates.
- **[x] Phase 6.5 — Session knowledge triage, research persistence guard, and handoff ergonomics**: introduced the Amnesia Test (3-way triage protocol), unpersisted research engine guard in handoff and session_commit, schema-level parameter alias tolerance (decisions, next_steps, open_questions, pending_tasks), profile-aware curation guide, redundant .brain-79/ path prefix stripping, and real-agent pre-merge E2E smoke suite (scripts/run_e2e_smoke.py).
- **[x] Phase 6.6 — Handoff freshness, provenance & authority decay (ADR-016)**: established that handoffs are perishable transition notes whose authority decays with workspace drift. Captured deterministic provenance (created_at, git_branch, git_head, wiki_digest, code_digest) in handoff frontmatter, added state classification (fresh, stale, foreign_branch, unverified) in handoff_freshness.py, rendered dynamic authority-decay banners and historical boot instructions in orient(), added branch-aware latest resolution, escalated aging pending tasks, and standardized English handoff templates with sentence-case colons outside bold.

---

## Upcoming execution roadmap (ordered by dependency and impact)

```
+-----------------------------------------------------------------------------------+
| Phase 7 (TOP PRIORITY): Multi-harness zero-config & doctor diagnostics (v0.8.0) | [ ] Next   |
+-----------------------------------------------------------------------------------+
| Phase 8: Zero-clone distribution & context budget guardrails (v0.9.0)          | [ ] Planned|
+-----------------------------------------------------------------------------------+
```

### Phase 7 (top priority): Project protocol upgrade, legacy wiki reconditioning and doctor diagnostics (`brain79 doctor`)
- **Specification**: [Feature — Project upgrade, legacy wiki conditioning, multi-harness setup & doctor diagnostics](../features/project-upgrade-and-multi-harness-doctor.md)
- **Scope**: solve "Split-Brain" version skew across existing projects via delimited managed blocks in `AGENTS.md` (`<!-- brain79:start -->`), non-destructive `SCHEMA.md` upgrades (preserving `profile` and `custom_types`), two-tier legacy wiki reconditioning (`migrate_wiki` v2), GUI-safe absolute binary paths in MCP configs, and the `brain79 doctor [--fix]` diagnostic tool.

### Phase 8: Zero-clone distribution and context budget guardrails
- **Problem**: installing or updating `brain-79` currently assumes a cloned repository (`scripts/install.py` and `git pull` inside `brain79 update`). Additionally, oversized articles can inflate `orient` payloads.
- **Deliverables**:
  1. **Standalone package installation & update**: support `uv tool install` from Git/PyPI and `uvx brain79`, decoupling `brain79 update` from local git repository assumptions.
  2. **Context budget & article size guardrails**: enforce a configurable payload ceiling (`max_chars` / `max_tokens`) in `brain79_orient` and surface an `article_too_large` warning in `brain79 lint` when articles exceed optimal context size.

---

[← Volver al Índice](../INDEX.md)
