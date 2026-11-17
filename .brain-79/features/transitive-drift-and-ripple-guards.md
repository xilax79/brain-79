---
type: feature
summary: merkle leaf-manifest drift detection, multi-hop DAG propagation, hard session ripple gate, anti-sprawl guard, AST signature verification, and unbounded Signal 1 context
status: shipped
version: 0.8.1
applies_to:
  - src/brain79/core/drift.py
  - src/brain79/core/context.py
  - src/brain79/core/session_commit.py
  - src/brain79/core/orient.py
related:
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
  - decisions/adr-018-living-manuals-and-temporal-decontamination.md
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/session-triage-and-research-persistence.md
last_updated: 2026-11-13
applies_to_digest: "sha256:e8689c0afa5c50a0"
applies_to_count: 4
---

# Feature — Transitive drift detection, holistic ripple gates, anti-sprawl guards, and unbounded governing context

## Overview

The Transitive Drift Detection and Ripple Guard subsystem prevents documentation decay, append-only drift, and wiki sprawl across evolving software codebases. It combines a deterministic Merkle leaf manifest (`.drift_manifest.json`) and a multi-hop DAG transitive drift propagation engine with four behavioral enforcement gates: the Hard Session Ripple Gate, the Anti-Sprawl Target Guard, unbounded Signal 1 context orientation, and AST public API signature verification.

## Subsystem architecture (7 pillars)

### 1. Merkle leaf-manifest & constant-memory streaming (`drift.py`)
Tracks workspace target files governed by `applies_to` patterns in `.drift_manifest.json`:
- **Attribution**: categorizes drift kind per leaf file as `modified`, `added`, `deleted`, or `missing`.
- **Constant memory**: streams files in 64 KB chunks with byte-level LF normalization (`\r\n` $\rightarrow$ `\n`) and UTF-8 BOM stripping for cross-platform determinism.
- **WorkspaceIndex**: unified single-pass discovery combining git-tracked files with untracked source files and path normalization.

### 2. Multi-hop DAG transitive propagation & unanchored governance
- **Recursive DAG closure**: upward propagation from direct leaf articles to umbrella synthesis articles via cycle-immune memoized DFS.
- **Unanchored governance detection**: `check_unanchored_governance()` flags active software articles lacking `applies_to`.

### 3. Automatic write-time digest stamping
- Operational write primitives (`write_article`, `edit_article`, `write_many_articles`, `migrate_wiki`, `session_commit`) automatically compute and stamp `applies_to_digest` and `applies_to_count`.

### 4. Anti-Sprawl Guard (`duplicate_governance_target`)
- `check_anti_sprawl_overlap()` blocks redundant articles in `features/`, `architecture/`, `product/`, or `topics/` when claimed file targets or title stems collide with existing active articles unless `supersedes` or `allow_overlapping_governance: true` is set.

### 5. Unbounded Signal 1 context & working-tree auto-binding (`orient.py`, `context.py`)
- **Unbounded Signal 1**: `rank_context_articles()` preserves 100% of direct `applies_to` matches without `top_n=4` truncation.
- **Working-tree auto-binding**: when `paths` is omitted in `orient()`, dirty or modified git files are discovered and ranked automatically.
- **Mandatory Reading Manifest**: surfaces excess governing articles when inlined content exceeds the 64 KB token budget.

### 6. Session Impact Checklist (`curate.py`)
- `prepare_curation_guide()` cross-references modified workspace files against governing articles, outputting a pre-commit checklist.

### 7. Four-phase transaction pipeline & Hard Session Ripple Gate (`session_commit.py`)
- Writes, edits, manifest updates, and handoffs execute inside outer mutex `.brain-79/.locks/_transaction.lock`:
  - **Pass 1**: in-memory syntax and schema pre-flight validation.
  - **Pass 2**: Anti-sprawl check (2a), digest calculation (2b), verified article review (2c), and **Hard Session Ripple Gate (2d)**: aborts the transaction (`unresolved_session_ripple`) if any impacted article remains drifted.
  - **Guard C (AST verification)**: blocks `verified_articles` without prose updates if public AST signatures changed in governed `.py` files.
  - **Pass 3 & Pass 4**: Atomic multi-file disk persistence and handoff emission.

## Key invariants and error codes

| Rule / Error Code | Component | Behavior |
|---|---|---|
| `unresolved_session_ripple` | `session_commit.py` | Blocks commit if modified files leave any governing or umbrella article drifted |
| `verified_article_public_signature_changed` | `session_commit.py` | Blocks rubber-stamping via `verified_articles` when public AST signatures changed |
| `duplicate_governance_target` | `validation.py` | Blocks creating duplicate articles claiming already-governed target files |
| `unanchored_governance_article` | `lint_organizational.py` | Flags active software articles lacking `applies_to` declarations |
| `applies_to_target_missing` | `lint_organizational.py` | Flags `applies_to` patterns that match zero real workspace files |
| `shared_target_in_leaf_article` | `lint_organizational.py` | Advises when sibling leaf articles share the same source file without coordination |

---

[← Volver al Índice](../INDEX.md)
