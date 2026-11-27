---
type: feature
summary: external drift.lock Merkle tracking, multi-hop DAG propagation, zero-diff verified_articles, Guard C AST verification, and Hard Session Ripple Gate
status: shipped
version: 0.18.0
applies_to:
  - src/brain79/core/drift.py
  - src/brain79/core/context.py
  - src/brain79/core/session_commit.py
  - src/brain79/core/orient.py
  - src/brain79/core/ast_guards/__init__.py
  - src/brain79/core/ast_guards/base.py
  - src/brain79/core/ast_guards/orchestrator.py
  - src/brain79/core/ast_guards/python_inspector.py
related:
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
  - decisions/adr-018-living-manuals-and-temporal-decontamination.md
  - decisions/adr-023-external-drift-lockfile.md
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/session-triage-and-research-persistence.md
  - features/polyglot-ast-guards-and-stats.md
last_updated: 2026-11-27
---

# Feature — Transitive drift detection, holistic ripple gates, anti-sprawl guards, and unbounded governing context

## Overview

The Transitive Drift Detection and Ripple Guard subsystem prevents documentation decay, append-only drift, and wiki sprawl across evolving software codebases. It persists deterministic Merkle leaf-target state inside a Git-tracked `.brain-79/drift.lock` lockfile (`version: "2.0"`) while keeping Markdown frontmatter hash-free, and enforces four behavioral gates: the Hard Session Ripple Gate, the Anti-Sprawl Target Guard, unbounded Signal 1 context orientation, and AST public API signature verification.

## Subsystem architecture (7 pillars)

### 1. External `.brain-79/drift.lock` & dual-read attribution (`drift.py`)
- **Deterministic v2.0 schema**: stores `{"version": "2.0", "articles": {<rel_wiki_posix>: {"digest", "count", "targets", optional "conflict": true}}}` in UTF-8 LF JSON (`indent=2`, `sort_keys=True`), created only when `articles` is non-empty or the lockfile already exists.
- **Fail-closed validation**: `load_drift_lock()` rejects duplicate keys, `NaN`/`Infinity`, unknown keys, `"conflict": false`, or malformed paths/digests with `ValidationError(rule="corrupt_drift_lock")` across all read and write paths (`navigation.py` callers never swallow it).
- **Strict dual-read precedence**: `check_article_drift()` resolves baselines in order: (1) `.brain-79/drift.lock` (emitting `drift_kind: "conflict"` immediately when `"conflict": true`, exact leaf `modified`/`added`/`deleted`/`missing` attribution when `targets` is non-empty, or count/digest fallback when `targets` is `{}`), (2) legacy frontmatter `applies_to_digest` with read-only `.drift_manifest.json` (`persist=False`), (3) legacy `last_updated` timestamp fallback.
- **Constant memory & `WorkspaceIndex`**: streams files in 64 KB chunks with LF normalization (`\r\n` -> `\n`) and UTF-8 BOM stripping; excludes `drift.lock` from `WorkspaceIndex.all_paths` (`ephemeral_files`).

### 2. Multi-hop DAG transitive propagation & unanchored governance
- **Recursive DAG closure**: propagates `drift_kind: "transitive"` upward from direct leaf or `"conflict": true` articles to umbrella articles via cycle-immune memoized DFS, forwarding `lock_data` and `manifest_data`.
- **Unanchored governance detection**: `check_unanchored_governance()` flags active software articles lacking `applies_to`.

### 3. Hash-free Markdown writes & pruning (`wiki.py`, `validation.py`, `frontmatter.py`)
- **Frontmatter stripping**: `write_article()`, `edit_article()`, `write_many_articles()`, and `commit_session()` strip legacy `applies_to_digest` and `applies_to_count` from `.md` frontmatter (including when `force_validation_skip=True` on valid YAML) and update `.brain-79/drift.lock` under `_drift_lock.lock`.
- **Automatic pruning**: deleting, archiving, transitioning to `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES`, or removing `applies_to` prunes the article's entry from `.brain-79/drift.lock`.

### 4. Anti-sprawl guard (`duplicate_governance_target`)
- `check_anti_sprawl_overlap()` blocks redundant articles in `features/`, `architecture/`, `product/`, or `topics/` when claimed file targets or title stems collide with existing active articles unless `supersedes` or `allow_overlapping_governance: true` is set.

### 5. Unbounded Signal 1 context & working-tree auto-binding (`orient.py`, `context.py`)
- **Unbounded Signal 1**: `rank_context_articles()` preserves 100% of direct `applies_to` matches without `top_n=4` truncation.
- **Working-tree auto-binding**: when `paths` is omitted in `orient()`, dirty or modified git files are discovered and ranked automatically.
- **Mandatory reading manifest**: surfaces excess governing articles when inlined content exceeds the 64 KB token budget.

### 6. Session impact checklist (`curate.py`)
- `prepare_curation_guide()` cross-references modified workspace files against governing articles, outputting a pre-commit checklist.

### 7. Four-phase transaction pipeline & Hard Session Ripple Gate (`session_commit.py`)
- Writes, edits, lockfile updates, and handoffs execute inside outer mutex `.brain-79/.locks/_transaction.lock`:
  - **Pass 1**: in-memory syntax and schema pre-flight validation with legacy frontmatter digest stripping.
  - **Pass 2**: upfront `load_drift_lock()` check, Anti-sprawl check (2a), digest staging into `lock_staging` (2b), verified article review (2c), and **Hard Session Ripple Gate (2d)** evaluating `art_path in lock_staging["articles"]` or legacy `applies_to_digest` plus `"conflict": true` articles so hash-free frontmatter never disables `unresolved_session_ripple`.
  - **Zero-diff `verified_articles` & conflict blocking**: Pass 2c rejects `"conflict": true` entries with `verified_article_conflict_forbidden` (`strict`/`balanced`), updates only `lock_staging["articles"][v_path]` without modifying `.md` files (`writes`/`edits` take precedence if both name an article), and preserves `.md` `git diff` empty.
  - **Guard C (`core/ast_guards/`)**: `orchestrator.py` and `python_inspector.py` delegate baseline commit lookup to shared `resolve_article_baseline_commit()` with two-pass bounded first-parent history (`%P` parent resolution, migration-commit skipping, and article-only Pass 2 fallback).
  - **Pass 3 & Pass 4**: atomic multi-file disk persistence and `.brain-79/drift.lock` write with full byte-for-byte rollback (including unlinking newly created `drift.lock`), followed by post-persistence handoff emission.

## Key invariants and error codes

| Rule / error code | Component | Behavior |
|---|---|---|
| `corrupt_drift_lock` | `drift.py` | Fails closed (`Exit 1`) on malformed `.brain-79/drift.lock` across all read/write paths |
| `verified_article_conflict_forbidden` | `session_commit.py` | Blocks `verified_articles` on `"conflict": true` entries under `strict`/`balanced` |
| `unresolved_session_ripple` | `session_commit.py` | Blocks commit if modified files leave any governing or umbrella article drifted |
| `verified_article_public_signature_changed` | `session_commit.py` | Blocks rubber-stamping via `verified_articles` when public AST signatures changed |
| `duplicate_governance_target` | `validation.py` | Blocks creating duplicate articles claiming already-governed target files |
| `unanchored_governance_article` | `lint_organizational.py` | Flags active software articles lacking `applies_to` declarations |
| `applies_to_target_missing` | `lint_organizational.py` | Flags `applies_to` patterns that match zero real workspace files |
| `shared_target_in_leaf_article` | `lint_organizational.py` | Advises when sibling leaf articles share the same source file without coordination |

---

[← Back to Index](../INDEX.md)
