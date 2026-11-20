---
type: architecture
summary: master defect backlog and forensic analysis for live evaluation findings on Grand Palace Casino (test-wiki)
stability: archived
applies_to:
  - src/brain79/core/init_project.py
  - src/brain79/core/validation.py
  - src/brain79/core/lint_organizational.py
  - src/brain79/core/handoff_freshness.py
  - src/brain79/core/frontmatter.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - features/transitive-drift-and-ripple-guards.md
last_updated: 2026-11-12
applies_to_digest: "sha256:f618db2936fc9d9f"
applies_to_count: 5
---

# Architecture — Defect backlog and live evaluation remediations

## Overview

This document consolidates the forensic root-cause analysis and actionable engineering specification for defects, edge cases, and agent protocol gaps discovered during live evaluation on the **Grand Palace Casino** testbed (`/tmp/test-wiki` and `/private/tmp/test-wiki`).

The testbed project implements a comprehensive web casino platform featuring five decoupled game engines (American Roulette, Classic Blackjack, Royal VIP Slots, VIP Punto Banco Baccarat, and Aerospace Crash), a shared reactive state store, procedural Web Audio API synthesis, HTML5 Canvas 2D rendering, and 100% passing test suites across all mathematical models.

The Phase 6.7 core engine performed as designed during live execution: Merkle drift detection successfully identified unaddressed ripple effects on shared infrastructure files, research topics were persisted across zero-code sessions (Type B Amnesia Test), and multi-turn transactions remained atomic. The findings below address ergonomics, profile-aware Git lifecycle integration, and authoring heuristics for follow-up implementation.

---

## Evaluation testbed reference

- **Path**: `/tmp/test-wiki` (symlinked as `/private/tmp/test-wiki`)
- **Domain**: Grand Palace Casino web platform (lobby, roulette, blackjack, slots, baccarat, crash)
- **Codebase assets**:
  - Engines: `js/engine.js`, `js/blackjack-engine.js`, `js/slots-engine.js`, `js/baccarat-engine.js`, `js/crash-engine.js`
  - Tests: `js/test-engine.js`, `js/test-blackjack.js`, `js/test-slots.js`, `js/test-baccarat.js`, `js/test-crash.js`, `js/test-state.js`
  - Infrastructure: `js/app.js`, `js/sound.js`, `js/state.js`, `css/style.css`, `index.html`
- **Active wiki state**: `.brain-79/` with 17 registered articles across product, architecture, features, topics, and changelog.

---

## 1. Ergonomics and lifecycle remediations (implemented in feat/uat-remediations)

### BUG-003 (Resolved): Profile-aware Git repository enforcement and fallback code digest
- **Status**: resolved in `feat/uat-remediations`.
- **Severity**: high.
- **Locations**: `src/brain79/core/init_project.py`, `src/brain79/core/handoff_freshness.py`, `src/brain79/core/lint_organizational.py`.
- **Symptom**: running `brain79 init` in `/tmp/test-wiki` succeeded without an active Git repository. This resulted in:
  1. `handoff_freshness.py` assigning `git_branch: "none"`, `git_head: "none"`, and `code_digest: "none"`.
  2. Loss of cryptographic code mutation verification in handoff freshness.
  3. Pre-commit hooks (`.git/hooks/pre-commit`) silently skipping installation.
- **Forensic root cause & adversarial boundaries**:
  While software projects require Git for authority hierarchy (`code and git > wiki > handoff`), workspaces initialized with `--profile general` (research notes, sports statistics, market forecasts, legal analysis) **must remain 100% free of Git requirements**. Making Git mandatory across all profiles would break valid zero-git document repositories.
- **Remediation**:
  1. **Profile-restricted auto-init (`init_project.py`)**: when `profile == "software"`, if no `.git` directory exists and the workspace is not inside a Git worktree, execute `git init` automatically (unless explicitly disabled via `--no-git`). For `--profile general`, do not mandate Git.
  2. **Profile-aware linter check (`lint_organizational.py`)**: issue rule `missing_git_repository` (severity: info) strictly when `profile == "software"`. Workspaces with `--profile general` are exempt.
  3. **Fallback code digest (`handoff_freshness.py`)**: when a software workspace lacks `.git`, `compute_code_digest()` falls back to walking the filesystem via `WorkspaceIndex` and hashing source files with 64 KB leaf byte-streaming instead of returning `"none"`.

---

### BUG-004 (Resolved): Shared umbrella file governance and sibling leaf article conflicts
- **Status**: resolved in `feat/uat-remediations`.
- **Severity**: medium.
- **Locations**: `src/brain79/core/validation.py`, `src/brain79/core/lint_organizational.py`.
- **Symptom**: in `/tmp/test-wiki`, `architecture/roulette-engine.md` declared `applies_to` over `css/style.css`, `js/app.js`, and `js/sound.js`. When the Crash Game was added, those shared files were modified, triggering drift.
- **Forensic root cause & adversarial evaluation**:
  The drift engine worked exactly as designed: `css/style.css` was modified, so the article claiming to govern it was flagged. The architectural mistake was human/agent authoring error: a specialized leaf game article claimed ownership over transversal platform files.
- **Remediation**:
  1. **Sibling overlap heuristic (`lint_organizational.py`)**: added advisory check `shared_target_in_leaf_article` (severity: info) alerting when multiple sibling leaf articles claim the same workspace file without declaring `supersedes` or `allow_overlapping_governance`.
  2. **Suppression mechanism**: setting `allow_overlapping_governance: true` or referencing sibling articles via `related` or `supersedes` suppresses the advisory alert.

---

### BUG-005 (Resolved): Architectural decision deficit heuristic (advisory, non-blocking)
- **Status**: resolved in `feat/uat-remediations`.
- **Severity**: medium (advisory).
- **Locations**: `src/brain79/core/lint_organizational.py`, `src/brain79/core/orient.py`, `src/brain79/core/curate.py`.
- **Symptom**: despite implementing five distinct games, shared localStorage state, Web Audio API synthesis, and mathematical payout models, `.brain-79/decisions/` in `/tmp/test-wiki` remained 100% empty (0 ADRs).
- **Remediation**:
  1. **Non-blocking info check (`lint_organizational.py`)**: emits rule `architectural_decision_deficit` strictly with `severity: info` when a software wiki has $\ge 3$ features or architecture articles but 0 active ADRs.
  2. **Advisory agent prompt (`orient.py`, `curate.py`)**: renders an advisory tip in `brain79_orient()` and curation summaries reminding agents to record architectural decisions when multiple new subsystems are created.

---

### BUG-006 (Resolved): Source code coverage gap detection (uncovered source files)
- **Status**: resolved in `feat/uat-remediations`.
- **Severity**: medium.
- **Locations**: `src/brain79/core/lint_organizational.py`.
- **Symptom**: in `/tmp/test-wiki`, core game engines (`js/blackjack-engine.js`, `js/slots-engine.js`) were unanchored—not claimed by the `applies_to` frontmatter of any feature or architecture article.
- **Forensic root cause & rejection of antipattern**:
  The initial proposal to enforce 1:1 filename matching between `product/<slug>.md` and `features/<slug>.md` is an antipattern and was rejected. The real metric is source code coverage.
- **Remediation**:
  1. **Uncovered source files check (`uncovered_source_files`)**: scans the workspace for recognized source files (`.py`, `.js`, `.ts`, etc., excluding `tests/`, `scripts/`, `node_modules/`, `.venv/`) and flags unanchored source code files (severity: info) not covered by any active `applies_to` rule.

---

### BUG-007 (Resolved): Frontmatter summary casing normalization and changelog slug standard
- **Status**: resolved in `feat/uat-remediations`.
- **Severity**: minor / polish.
- **Locations**: `src/brain79/core/frontmatter.py`.
- **Symptom**:
  1. Agents authoring frontmatter frequently supply capitalized summaries violating sentence case governance.
  2. Changelogs in `/tmp/test-wiki` were created as `1.1.0.md` instead of the kebab-case standard `v1-1-0.md`.
- **Remediation**:
  1. **Implemented in `src/brain79/core/frontmatter.py`**: `sanitize_summary()` normalizes initial words to lowercase while strictly preserving acronyms (`CLI`, `MCP`, `ADR`, `RTP`) and proper nouns.
  2. **Location consistency validation**: `validate_location_consistency()` rejects changelog slugs with dots or starting with a digit (`rule: invalid_changelog_slug`), requiring standard kebab-case semver slugs (`vX-Y-Z.md`).

---

## 2. Historical remediations (archived Phase 5.5 / 6)

The following historical issues were fully resolved and verified in prior milestones:
- **BUG-001 (Resolved)**: root backlink normalization and broken link in `SCHEMA_GENERAL.md`.
- **BUG-002 (Resolved)**: composite H2 atomicity thresholds and code fence masking in `lint_organizational.py`.
- **INEF-001 (Resolved)**: self-documenting tool receipts eliminating redundant `write` $\rightarrow$ `navigate` $\rightarrow$ `index` loops.
- **INEF-002 (Resolved)**: active schema summary included in cold start `orient`.
- **INEF-003 (Resolved)**: on-demand handoff policy codification preventing conversational handoff spam.

---

[← Back to Index](../INDEX.md)
