---
type: feature
summary: team-safe Git collaboration, tracked .brain-79/drift.lock with 3-way merge driver, INDEX.md merge driver, bootstrap --auto-map, centralized git_ops, and dual-tier enforcement
status: shipped
version: 0.18.0
applies_to:
  - src/brain79/core/auto_map.py
  - src/brain79/core/git_ops.py
  - src/brain79/core/drift_merge.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - features/transitive-drift-and-ripple-guards.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - features/lifecycle-hooks-and-ci-gate.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md
  - decisions/adr-023-external-drift-lockfile.md
last_updated: 2026-11-27
---

# Feature — Team-safe Git collaboration and low-friction onboarding

## Overview

This subsystem eliminates multi-developer Git merge collisions on derived wiki files and `.brain-79/drift.lock`, automates brownfield repository onboarding, centralizes subprocess Git operations, and allows teams to combine low-friction local iteration (`balanced`) with strict CI Pull Request gating (`strict`).

## Core capabilities

### 1. Centralized Git layer (`src/brain79/core/git_ops.py`)
All Git invocations route through `core/git_ops.py` with `shell=False`, explicit timeouts, UTF-8 / `-c core.quotepath=false` handling, and structured exceptions (`NotAGitRepoError`, `GitTimeoutError`, `GitError`):
- Repository status, diff, and history helpers (`git_dirty_paths`, `git_ls_files`, `git_diff_range_names`, `git_first_parent_log`, `git_recent_file_churn`, `git_check_ignore`, `GitSessionCache`).
- `git_diff_range_names()` validates `base_ref` and `head_ref` against option/range injection, executes three-dot `diff --name-only -z`, and falls back to two-dot diff only on merge-base/shallow-history failures.
- `git_ls_files()` raises `GitError` on non-zero exit so `WorkspaceIndex.build()` cleanly falls back to filesystem scanning in containerized or dubious-ownership CI runners.
- Local-only Git config helpers (`git_config_get_local`, `git_config_set_local`) used by `brain79-index` and `brain79-drift-lock` merge driver setup.

### 2. Git-tracked `.brain-79/drift.lock` & 3-way merge driver (`drift_merge.py`)
- **`.gitignore` negation ordering**: `init`, `update-project`, and `migrate --apply` place `!drift.lock` strictly after `*.lock` in `DERIVED_STATE_GITIGNORE_ENTRIES`, and `sync_wiki_gitignore()` repairs inverted or missing `!drift.lock` rules while keeping `.locks/`, `.navigation_registry.json`, `.drift_manifest.json`, and `.bootstrap_state.json` ignored.
- **3-way `brain79 merge-drift-lock` driver**: configured via `.brain-79/.gitattributes` (`drift.lock merge=brain79-drift-lock`) and local `.git/config` (`brain79 merge-drift-lock %O %A %B`):
  - Merges disjoint edits, identical edits, delete/delete, and 0-byte-`<base>` disjoint `add/add` cleanly (`Exit 0`).
  - Reverts same-article modify/modify and delete/modify conflicts to `base[k]` (pruning `k` only if explicit existing `--wiki-root` confirms `<k>` is absent on disk).
  - Emits deterministic `"conflict": true` sentinel (`{"conflict": true, "count": 0, "digest": "sha256:0000000000000000", "targets": {}}`) on conflicting `add/add` keys (`Exit 0`).
  - Fails closed (`Exit 1`) on corrupt/empty `<ours>` or `<theirs>` without modifying `<ours>`, exits `2` on missing args/files or invalid `--wiki-root`, and exits `3` on write `OSError`.
- **Pre-commit hook**: `PRE_COMMIT_HOOK_SCRIPT` matches `^\.brain-79/(.*\.md|drift\.lock)$` so commits staging only `drift.lock` still run `brain79 lint --strict`.
- **Zero-masking idempotent migration (`migrate_wiki` Paso D)**: runs strictly after Paso B, preserves newer `drift.lock` entries, copies stale baselines without masking code/timestamp drift, strips malformed/legacy frontmatter digests, prunes deleted/inactive/demoted entries, and skips `INDEX.md` rewrites on no-op runs.

### 3. Three-way `INDEX.md` Git merge driver & navigation rebuilds
- `brain79 navigate --merge-driver %O %A %B` invokes `merge_index_files()` in `navigation.py`, preserving `type: navigation`, `max(last_updated)`, preamble 3-way merge, and canonically sorted `## Quick navigation` entries.
- `rebuild_navigation_registry()` (`brain79 navigate --rebuild`) reconstructs `.navigation_registry.json` from on-disk Markdown files, and `load_registry()` reconciles stale caches automatically.

### 4. Automated brownfield onboarding (`src/brain79/core/auto_map.py`, `bootstrap.py`)
- `brain79 bootstrap` (`auto_map: bool | None = None`) resolves `None` to `True` when `active_schema.profile == "software"` (`--no-auto-map` opt-out) and `False` under `profile == "general"`.
- Analyzes package manifests, bounded directory topology (`depth <= 3`, `followlinks=False`, `max_walk_files=5000`), and recent Git churn, proposing disjoint `applies_to` patterns for `architecture/overview.md` and `architecture/stack.md`.

### 5. Configurable enforcement tiers (`strict` / `balanced` / `advisory`) and dual-tier CI gate
Declared via `enforcement:` in `.brain-79/SCHEMA.md` (default `strict`), while `brain79 ci-check` defaults to `strict` independently (`--enforcement <strict|balanced|advisory|schema>`):

| Guard / check | `strict` (default) | `balanced` | `advisory` |
|---|---|---|---|
| Core structural integrity (YAML, required fields/enums, path containment, pure `INDEX.md`) | **BLOCK** | **BLOCK** | **BLOCK** |
| Hard Session Ripple Gate (`unresolved_session_ripple`) | **BLOCK** | **WARN** | **WARN** |
| `verified_articles` conflict sentinel (`verified_article_conflict_forbidden`) | **BLOCK** | **BLOCK** | **WARN** |
| Unanchored governance article (`unanchored_governance_article`) | **BLOCK** | **WARN** | **WARN** |
| `verified_articles` Guards A & B (structural / umbrella) | **BLOCK** | **BLOCK** | **WARN** |
| `verified_articles` Guard C (AST public API diff) | **BLOCK** | **WARN** | **WARN** |
| Anti-Sprawl Overlap (`anti_sprawl_overlap_violation`) | **BLOCK** | **BLOCK** | **WARN** |
| Missing `applies_to` target (`applies_to_target_missing`) | **BLOCK** | **WARN** | **WARN** |
| Operational Git errors (`git_status_verification_failed`, AST Git errors) | **BLOCK** | **BLOCK** | **WARN** |

### 6. Clean context discovery and schema parity (`context.py`, `orient.py`)
- `context.py` and `orient.py` exclude `INDEX.md` and `SCHEMA.md` before `top_n` truncation, prefer active articles over `INACTIVE_STATUSES`, and append a bounded reminder (`<= 20` paths) fetchable via `brain79_read_batch(paths=[...])`.

---

[← Back to Index](../INDEX.md)
