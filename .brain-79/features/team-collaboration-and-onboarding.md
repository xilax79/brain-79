---
type: feature
summary: team-safe Git collaboration, git-ignored derived caches with deterministic rebuilds, 3-way INDEX.md merge driver, bootstrap --auto-map, centralized git_ops, and configurable enforcement tiers
status: shipped
version: 0.13.0
applies_to:
  - src/brain79/core/auto_map.py
  - src/brain79/core/git_ops.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - features/transitive-drift-and-ripple-guards.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
last_updated: 2026-11-21
applies_to_digest: "sha256:f5e785862375fdd7"
applies_to_count: 2
---

# Feature — Team-safe Git collaboration and low-friction onboarding

## Overview

This subsystem eliminates multi-developer Git merge collisions on derived wiki files, automates brownfield repository onboarding, centralizes subprocess Git operations, and allows teams to graduate gradually into strict governance enforcement.

## Core capabilities

### 1. Centralized Git layer (`src/brain79/core/git_ops.py`)
All Git invocations route through `core/git_ops.py` with `shell=False`, explicit timeouts, UTF-8 / `-c core.quotepath=false` handling, and structured exceptions (`NotAGitRepoError`, `GitTimeoutError`, `GitError`):
- Repository status and history helpers (`git_dirty_paths`, `git_ls_files`, `git_recent_file_churn`, `GitSessionCache`).
- Local-only Git config helpers (`git_config_get_local`, `git_config_set_local`) used by the `INDEX.md` merge driver setup.

### 2. Merge-conflict-free derived state and deterministic rebuilds
- **Git-ignored caches**: `init` and `update-project` idempotently maintain `.brain-79/.gitignore` to ignore `.locks/`, `*.lock`, `*.tmp`, `*.tmp.*`, `.navigation_registry.json`, `.drift_manifest.json`, and `.bootstrap_state.json` while preserving user lines.
- **Navigation registry rebuild**: `rebuild_navigation_registry()` (`brain79 navigate --rebuild`) deterministically reconstructs `.navigation_registry.json` from on-disk Markdown files (read-only safe, `followlinks=False`). `load_registry()` also reconciles incomplete or stale `.navigation_registry.json` caches against `_scan_indexable_md_files()` automatically so truncated caches cannot propagate into `INDEX.md`.
- **Zero-masking drift manifest rebuild**: `rebuild_drift_manifest()` hydrates `targets` only when `curr_digest == stored_digest`; when a governed article is drifted (`curr_digest != stored_digest`), `targets` are omitted and `check_article_drift()` provides `fallback_targets` so Guard A and Guard C continue operating without `.drift_manifest.json`.

### 3. Three-way `INDEX.md` Git merge driver
- `brain79 navigate --merge-driver %O %A %B` invokes `merge_index_files()` in `navigation.py`:
  - Preserves `type: navigation` and selects `max(last_updated)` across branches.
  - Performs a 3-way merge of the preamble above `## Quick navigation` (writing standard Git conflict markers and exiting `1` if both sides diverged).
  - Deterministically merges `## Quick navigation` entries (respecting single-side deletions, preserving additions, re-extracting from disk on concurrent edits) and writes canonically sorted LF output with exit code `0`.
- Wired automatically via `.brain-79/.gitattributes` (`INDEX.md merge=brain79-index`) and local `.git/config` during `init` (opt-out: `--no-merge-driver`), `update-project`, and `doctor --fix`.

### 4. Automated brownfield onboarding (`src/brain79/core/auto_map.py`)
- `brain79 bootstrap --auto-map [--max-modules N]` (and `brain79_bootstrap(auto_map=True, max_modules=N)`) analyzes repositories using stdlib-only signals:
  1. Package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`).
  2. Bounded directory topology (`depth <= 3`, `followlinks=False`, capped at `max_walk_files=5000`).
  3. Recent Git churn (`git_recent_file_churn()`, gracefully degrading to `0` on non-Git repos).
- **Zero-overlap guarantee by construction**: narrows parent patterns to single-level globs whenever child directories are proposed, guaranteeing zero pairwise `applies_to` file intersection across emitted `ModuleProposal` entries.

### 5. Configurable enforcement tiers (`strict` / `balanced` / `advisory`)
Declared via `enforcement:` in `.brain-79/SCHEMA.md` (default `strict`; configurable via `brain79 init --enforcement <tier>` and preserved by `update-project`):

| Guard / check | `strict` (default) | `balanced` | `advisory` |
|---|---|---|---|
| Core structural integrity (YAML, required fields/enums, path containment, pure `INDEX.md`) | **BLOCK** | **BLOCK** | **BLOCK** |
| Hard Session Ripple Gate (`unresolved_session_ripple`) | **BLOCK** | **WARN** | **WARN** |
| `verified_articles` Guards A & B (structural / umbrella) | **BLOCK** | **BLOCK** | **WARN** |
| `verified_articles` Guard C (Python AST public API diff) | **BLOCK** | **WARN** | **WARN** |
| Anti-Sprawl Overlap (`anti_sprawl_overlap_violation`) | **BLOCK** | **BLOCK** | **WARN** |
| Missing `applies_to` target (`applies_to_target_missing`) | **BLOCK** | **WARN** | **WARN** |
| Operational Git errors (`git_status_verification_failed`, AST Git errors) | **BLOCK** | **BLOCK** | **WARN** |

- `brain79 lint --strict` exits `1` on `CRITICAL` or `WARNING` under `strict`, exits `1` on `CRITICAL` only under `balanced`/`advisory`, and supports `--fail-on-warnings` to enforce warning failures under any tier.

---

[← Back to Index](../INDEX.md)
