---
type: architecture
summary: implementation specification and acceptance criteria for team-safe Git collaboration, INDEX.md merge driver, bootstrap --auto-map, and configurable enforcement tiers
stability: experimental
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/auto_map.py
  - src/brain79/core/navigation.py
  - src/brain79/core/drift.py
  - src/brain79/core/bootstrap.py
  - src/brain79/core/frontmatter.py
  - src/brain79/core/session_commit.py
  - src/brain79/core/wiki.py
  - src/brain79/core/init_project.py
  - src/brain79/core/doctor.py
  - src/brain79/core/git_ops.py
  - src/brain79/core/lint.py
  - src/brain79/cli/dispatch.py
  - src/brain79/server.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/core-refactoring-and-hardening-design.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - features/transitive-drift-and-ripple-guards.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
last_updated: 2026-11-20
applies_to_digest: "sha256:b5d4c85284428696"
applies_to_count: 13
---

# Architecture — Team-safe Git collaboration and low-friction onboarding

## Overview

This document specifies the complete requirements, execution stages, and acceptance criteria for **Phase 12** of the `brain-79` roadmap. It eliminates multi-developer Git merge collisions and lowers brownfield adoption friction through three capabilities built on the Phase 10 (`v0.11.0`) foundation:

1. **Merge-conflict-free derived state**: decouple machine-derived JSON caches (`.navigation_registry.json`, `.drift_manifest.json`, `.bootstrap_state.json`) from Git-tracked Markdown via `.brain-79/.gitignore` and deterministic on-demand rebuilds.
2. **Deterministic `INDEX.md` Git merge driver**: 3-way merge driver (`brain79 navigate --merge-driver %O %A %B`) wired via `.brain-79/.gitattributes` and local `.git/config`.
3. **Brownfield onboarding (`bootstrap --auto-map`) and enforcement tiers (`strict` / `balanced` / `advisory`)**: deterministic zero-overlap `applies_to` governance proposals and declarative strictness in `SCHEMA.md`.

## Ground rules and invariants

- **Sequencing and versioning**: Phase 12 has no hard dependency on Phase 11 (all seams shipped in `v0.11.0`). Per ADR-017, it ships as the next minor pre-GA version (`v0.13.0` after Phase 11, or `v0.12.0` if executed first); never bumps to `1.0.0`.
- **Zero-dependency core**: Python 3.11+ stdlib (`tomllib`, `json`, `re`, `pathlib`) plus existing dependencies (`pyyaml`, `filelock`, `fastmcp`).
- **Source of truth invariant**: `.brain-79/*.md` files remain the sole source of truth in Git. Deleting all derived JSON caches must never corrupt wiki state or mask real documentation drift.
- **Lock hierarchy compliance**: all cache rebuilds obey `LOCK_HIERARCHY` in `core/locks.py` (`_transaction.lock` -> `_registry.lock` -> `_drift_manifest.lock` -> `INDEX.md.lock`) and use `create_temp_path()` + `atomic_replace_with_retry()`.
- **CLI/MCP parity and compatibility**: preserve `tests/test_symmetry.py` parity; default `enforcement` is `strict` when omitted from `SCHEMA.md`; default `bootstrap` behavior is unchanged unless `auto_map=True`.

## Stage 1 — Merge-conflict-free derived state and deterministic rebuild

Target modules: `navigation.py`, `drift.py`, `init_project.py`, `doctor.py`, `session_commit.py`, `cli/dispatch.py`, `server.py`.

### R-1.1 — Git-ignored derived state manifest
- Add `sync_wiki_gitignore(wiki_root: Path, dry_run: bool = False) -> tuple[bool, str]` in `init_project.py` (invoked by `init_project()` and `update_project()`).
- Idempotently ensure `.brain-79/.gitignore` contains `.locks/`, `*.lock`, `*.tmp`, `*.tmp.*`, `.navigation_registry.json`, `.drift_manifest.json`, and `.bootstrap_state.json`, preserving custom user lines.
- Add a `derived_state_tracking` check in `doctor.py` using `git_ls_files`: if any derived JSON cache is still tracked in Git, emit a `warning` with `git rm --cached` remediation.

### R-1.2 — Deterministic navigation registry rebuild
- Implement `rebuild_navigation_registry(wiki_root: Path, *, persist: bool = True) -> dict[str, Any]` in `navigation.py`:
  - Scans `.md` files excluding `_raw/`, `.locks/`, `handoffs/`, `INDEX.md`, `SCHEMA.md` (`followlinks=False`).
  - Extracts `title`, `summary`, lowercase `section` (`"root"` for top-level files), and `graph_meta`; sorts entries by `path` ascending.
  - Atomically persists under `_registry.lock` when `persist=True`; returns in-memory registry gracefully on read-only filesystems (`PermissionError`/`OSError`).
- Auto-rebuild inside `load_registry(wiki_root)` when `.navigation_registry.json` is missing/corrupt and indexable `.md` files exist.
- Add `rebuild: bool = False` to `regenerate_index_navigation()`, `brain79 navigate --rebuild`, and MCP `brain79_navigate(rebuild=...)`.

### R-1.3 — Drift-safe manifest rebuild without masking drift
- Implement `rebuild_drift_manifest(wiki_root: Path, project_root: Path | None = None, *, persist: bool = True, workspace_index: WorkspaceIndex | None = None) -> dict[str, Any]` in `drift.py`:
  - Scans active `.md` articles declaring `applies_to` and `applies_to_digest`, computing `(curr_digest, curr_count, curr_targets)`.
  - **Zero-masking invariant**: hydrate `manifest["articles"][rel_path]` **only when `curr_digest == stored_digest`**. When `curr_digest != stored_digest`, omit `targets` so real drift stays visible.
  - Persists atomically under `_drift_manifest.lock` when `persist=True` (read-only safe).
- Support `auto_rebuild: bool = False` in `load_drift_manifest()` and trigger on-demand hydration when `.drift_manifest.json` is missing during `detect_all_drift()` / `check_article_drift()`.

### R-1.4 — Guard parity when `.drift_manifest.json` is absent
- Enhance `check_article_drift()` fallback (when `stored_digest` exists, `manifest_entry` is absent, and `curr_digest != stored_digest`):
  - Compare `curr_count` against frontmatter `applies_to_count` (`stored_count`): emit `"missing"` (`curr_count == 0`), `"added"` (`curr_count > stored_count`), `"deleted"` (`curr_count < stored_count`), or `"modified"`.
  - Attach `fallback_targets: list[str]` (sorted `curr_targets.keys()`) so `session_commit.py` Pass 2c Guard C inspects all matching `.py` targets via `has_public_python_api_changes()`.

## Stage 2 — Deterministic INDEX.md Git merge driver

Target modules: `navigation.py`, `git_ops.py`, `init_project.py`, `doctor.py`, `cli/dispatch.py`.

### R-2.1 — Three-way deterministic `INDEX.md` merger
- Implement `merge_index_files(base_path: Path, ours_path: Path, theirs_path: Path, *, wiki_root: Path | None = None) -> int` in `navigation.py`:
  - Parses frontmatter, static preamble (above `## Quick navigation`), and `## Quick navigation` entries (`path -> (section_lower, bullet_line)`) from `%O`, `%A`, `%B`.
  - **Frontmatter**: preserve `type: navigation`; set `last_updated` to `max(ours, theirs)` for valid `YYYY-MM-DD` dates; merge other keys (changed side wins, `ours` breaks ties).
  - **Preamble**: 3-way merge (`ours == base` -> `theirs`; `theirs == base` or `ours == theirs` -> `ours`); if both sides diverged, write standard conflict markers (`<<<<<<< ours` / `=======` / `>>>>>>> theirs`) to `ours_path` and return `1`.
  - **Quick navigation**: for each `path` in `base | ours | theirs`: respect single-side deletion, include additions, prefer modified side; if modified in both sides, re-extract from `(wiki_root / path)` when present on disk, otherwise deterministically take `ours`.
  - Render sections canonically (matching `_render_quick_navigation()`), write atomically to `ours_path` with LF (`\n`), and return `0`.

### R-2.2 — CLI driver entry point
- Add `--merge-driver BASE OURS THEIRS` (`nargs=3`) to `brain79 navigate` in `cli/dispatch.py`.
- Exit codes: `0` clean merge, `1` preamble conflict, `2` missing input files. Must operate on temporary Git files without requiring `.navigation_registry.json` or `.locks/`.

### R-2.3 — Automated Git configuration and diagnostics
- Add `git_config_set_local(cwd, key, value)` and `git_config_get_local(cwd, key)` in `core/git_ops.py` (always `--local`, never `shell=True`).
- Add `sync_git_merge_driver(project_root: Path, *, install: bool = True, dry_run: bool = False) -> tuple[bool, str]` in `init_project.py`:
  - Idempotently ensures `.brain-79/.gitattributes` contains `INDEX.md merge=brain79-index` (preserving custom lines).
  - Inside a Git repo with `install=True`, sets `merge.brain79-index.name` and `merge.brain79-index.driver = brain79 navigate --merge-driver %O %A %B`.
- Wire into `init_project()` (with `--no-merge-driver` opt-out), `update_project()`, and `doctor.py` (`git_merge_driver` check + `doctor --fix` repair).

## Stage 3 — Automated brownfield onboarding (`bootstrap --auto-map`)

Target modules: new `src/brain79/core/auto_map.py`, `bootstrap.py`, `git_ops.py`, `cli/dispatch.py`, `server.py`.

### R-3.1 — Git churn helper in `core/git_ops.py`
- Add `git_recent_file_churn(cwd: Path, *, max_commits: int = 200, timeout: float = 5.0) -> dict[str, int]` via `git -c core.quotepath=false log -n <N> --name-only --pretty=format:`.
- Raises `NotAGitRepoError` outside Git repos; returns `{}` on repositories with zero commits.

### R-3.2 — Deterministic repository mapper (`core/auto_map.py`)
- Define `ModuleProposal` (`slug`, `article_path`, `article_type`, `applies_to`, `file_count`, `recent_commits`, `primary_language`, `confidence`, `signals`) and `AutoMapReport` (`proposals`, `truncated_count`, `git_available`, `total_code_files`, `warnings`).
- Implement `analyze_repository_boundaries(project_root: Path, *, max_modules: int = 12, max_walk_files: int = 5000) -> AutoMapReport` using three signals:
  1. **Package/workspace manifests** (stdlib only): `pyproject.toml` (`tomllib`), `package.json` (`json`), `Cargo.toml` (`tomllib`), `go.mod`.
  2. **Directory topology and code density**: bounded walk (depth `<= 3`, `followlinks=False`, contained inside `project_root`, capped at `max_walk_files`) excluding `_EXCLUDED_DIRS`, `tests/`, `test/`, `__tests__/`, `docs/`, `.github/`, grouping directories with `>= 1` source file.
  3. **Git churn ranking**: aggregates `git_recent_file_churn()` per candidate (degrading to `0` on non-Git repos); sorts by `(has_manifest DESC, recent_commits DESC, file_count DESC, slug ASC)` and caps at `max_modules`.

### R-3.3 — Zero-overlap anti-sprawl guarantee by construction
- Validate all emitted `ModuleProposal` `applies_to` patterns pairwise against workspace files via `match_applies_to_pattern()`.
- Narrow parent patterns to single-level globs (e.g., `src/pkg/*.py`) whenever a child subdirectory is also proposed, guaranteeing **zero shared workspace files** across emitted proposals.

### R-3.4 — Bootstrap integration and CLI/MCP parity
- Extend `run_bootstrap(scope=None, force=False, auto_map=False, max_modules=12)` in `bootstrap.py`.
- When `auto_map=True`, append `## Auto-mapped governance boundaries` with summary table, ready-to-paste YAML frontmatter blocks, and commit instructions.
- Expose `--auto-map` and `--max-modules` on `brain79 bootstrap` and `auto_map`, `max_modules` on `brain79_bootstrap`.

## Stage 4 — Configurable enforcement tiers (`strict` / `balanced` / `advisory`)

Target modules: `frontmatter.py`, `session_commit.py`, `wiki.py`, `lint.py`, `orient.py`, `init_project.py`, `doctor.py`, `cli/dispatch.py`, `templates/SCHEMA.md`, `templates/SCHEMA_GENERAL.md`.

### R-4.1 — Declarative `enforcement` setting in `SCHEMA.md` and `ActiveSchema`
- Parse optional `enforcement: strict | balanced | advisory` from `SCHEMA.md` frontmatter (default `"strict"`).
- Add `enforcement: Literal["strict", "balanced", "advisory"] = "strict"` and `schema_warnings: list[str]` to `ActiveSchema`. Invalid values fall back safely to `"strict"` and record a structured warning surfaced by `lint` and `doctor`.
- Add `--enforcement <strict|balanced|advisory>` to `brain79 init`; ensure `sync_schema_file()` preserves user-selected `enforcement` on `update-project`.

### R-4.2 — Tier behavior matrix

| Guard / check | `strict` (default) | `balanced` | `advisory` |
|---|---|---|---|
| Core structural integrity (YAML, required fields/enums, path containment, no inline decisions, `INDEX.md` pure routing) | **BLOCK** | **BLOCK** | **BLOCK** |
| Hard Session Ripple Gate (`unresolved_session_ripple`) | **BLOCK** | **WARN** | **WARN** |
| `verified_articles` Guards A & B (structural / umbrella) | **BLOCK** | **BLOCK** | **WARN** |
| `verified_articles` Guard C (Python AST public API diff) | **BLOCK** | **WARN** | **WARN** |
| Anti-Sprawl Overlap (`anti_sprawl_overlap_violation`) | **BLOCK** | **BLOCK** | **WARN** |
| Missing `applies_to` target (`applies_to_target_missing`) | **BLOCK** | **WARN** | **WARN** |
| Operational Git errors (`git_status_verification_failed`, AST Git errors) | **BLOCK** | **BLOCK** | **WARN** |

### R-4.3 — Linter, `orient`, and `doctor` visibility
- Add `[Enforcement: <tier>]` to `lint_wiki()` report header.
- Update `brain79 lint --strict` exit code: exit `1` on `CRITICAL` or `WARNING` under `strict`; exit `1` on `CRITICAL` only under `balanced`/`advisory`; add `--fail-on-warnings` to force exit `1` on warnings under any tier.
- Display active `enforcement` tier in `orient()` Active Schema Summary and `doctor` (`protocol_sync`).

### R-4.4 — Non-blocking warning propagation
- In `session_commit.py`: collect downgraded guard warnings in `all_warnings`, set `health_status = "warnings"` (unless `"degraded"`), and include `"enforcement": active_schema.enforcement` in the receipt.
- In `wiki.py` (`write_article()`, `write_many_articles()`): append downgraded `anti_sprawl_overlap_violation` / `applies_to_target_missing` warnings to the return message.

## Stage 5 — Verification, CLI/MCP parity, and release synchronization

- Extend `tests/test_symmetry.py` to assert parity for `bootstrap` (`auto_map`, `max_modules`) and `navigate` (`rebuild`).
- Update `README.md`, `CHANGELOG.md`, `SCHEMA.md` templates, and `roadmap-industrial-scale.md`.
- Run `uv run pytest`, `uv run mypy src tests`, `uv run brain79 lint --strict`, and `uv run brain79 doctor` with zero failures.

## Acceptance criteria

- **AC-12.1**: `init` and `update-project` ensure `.brain-79/.gitignore` ignores `.navigation_registry.json`, `.drift_manifest.json`, and `.bootstrap_state.json` while preserving custom lines; `doctor` warns with `git rm --cached` guidance if any derived JSON is tracked in Git.
- **AC-12.2**: Deleting `.navigation_registry.json` and calling `load_registry()`, `orient()`, `context()`, or `navigate --regenerate --rebuild` deterministically reconstructs registry and `INDEX.md` from Markdown on disk.
- **AC-12.3**: Deleting `.drift_manifest.json` and calling `rebuild_drift_manifest()` or `detect_all_drift()` hydrates exact `targets` only when `curr_digest == stored_digest`, never masking drift when `curr_digest != stored_digest`.
- **AC-12.4**: Without `.drift_manifest.json`, adding/deleting a governed file or breaking a Python public signature still fails `session_commit(verified_articles=...)` with Guard A or Guard C under `strict`.
- **AC-12.5**: Real `git merge` integration test: two divergent branches add/delete distinct articles and update `INDEX.md`; `brain79-index` merge driver exits `0`, preserves both branches' entries in canonical sorted order, respects deletions, and keeps `max(last_updated)`.
- **AC-12.6**: Divergent concurrent edits to the `INDEX.md` preamble above `## Quick navigation` emit standard Git conflict markers and exit `1` without silent data loss.
- **AC-12.7**: `init` (unless `--no-merge-driver`) and `update-project` idempotently configure `.brain-79/.gitattributes` and local `.git/config`; `doctor` checks it and `doctor --fix` installs it.
- **AC-12.8**: `bootstrap --auto-map` detects boundaries from `pyproject.toml`, `package.json`, `Cargo.toml`, and `go.mod` using stdlib only, ranks via Git churn, and degrades gracefully on non-Git repos.
- **AC-12.9**: Pairwise file intersection of `applies_to` across all emitted `ModuleProposal` entries is strictly `0` (creating all proposed articles never triggers `anti_sprawl_overlap_violation`).
- **AC-12.10**: `brain79 bootstrap --auto-map --max-modules N` and MCP `brain79_bootstrap(auto_map=True, max_modules=N)` return identical proposals and pass `tests/test_symmetry.py`.
- **AC-12.11**: Omitted `enforcement:` defaults to `strict`; invalid values fall back to `strict` with a warning in `lint` and `doctor`; `update-project` preserves configured `enforcement`.
- **AC-12.12**: under `advisory`, ripple gate, Guards A/B/C, anti-sprawl, and missing `applies_to` downgrade to warnings (`health_status="warnings"`), while invalid YAML/structural invariants still raise `ValidationError`.
- **AC-12.13**: under `balanced`, anti-sprawl and Guards A/B still block, while ripple gate, Guard C (AST), and missing `applies_to` downgrade to warnings.
- **AC-12.14**: `brain79 lint --strict` exits `1` on `WARNING` under `strict`, exits `0` on `WARNING` (`1` on `CRITICAL`) under `balanced`/`advisory`, and exits `1` on `WARNING` with `--fail-on-warnings`.
- **AC-12.15**: `orient()` and `doctor` display the active `enforcement` tier, and `lint` includes `[Enforcement: <tier>]`.
- **AC-12.16**: Full test suite (`uv run pytest`), `uv run mypy src tests`, `uv run brain79 lint --strict`, and `uv run brain79 doctor` pass with exit code `0`.

---

[← Back to Index](../INDEX.md)
