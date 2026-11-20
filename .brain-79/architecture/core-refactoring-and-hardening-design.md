---
type: architecture
summary: implementation specification and acceptance criteria for core architectural refactoring, concurrency hardening, security fixes, and modular decomposition prior to public release
stability: stable
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/navigation.py
  - src/brain79/core/locks.py
  - src/brain79/core/session_commit.py
  - src/brain79/core/git_ops.py
  - src/brain79/core/ast_guards/**
  - src/brain79/core/harnesses/**
  - src/brain79/core/drift.py
  - src/brain79/core/frontmatter.py
  - src/brain79/core/init_project.py
  - src/brain79/core/update.py
  - src/brain79/server.py
  - src/brain79/config.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - architecture/mcp-server.md
  - architecture/dispatcher.md
  - features/cross-platform-and-lock-isolation.md
  - features/transitive-drift-and-ripple-guards.md
  - decisions/adr-013-versioning-and-release-governance.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
last_updated: 2026-11-20
applies_to_digest: "sha256:d15dbbc63d48f98e"
applies_to_count: 23
---

# Architecture — Core refactoring and hardening

## Overview

This document defines the complete requirements, logical execution stages, and acceptance criteria for the `v0.11.0` architectural refactoring and hardening cycle. Its objective is to eliminate structural debt, concurrency hazards, silent fail-open error paths, and security gaps detected in the `13,811`-line `v0.10.0` codebase before implementing public-release, team-collaboration, and polyglot features.

## Ground rules and invariants

- **Versioning**: ships as `v0.11.0` per ADR-017. Does not bump to `1.0.0`.
- **Zero-dependency core**: introduces no new third-party runtime dependencies.
- **Backward compatibility**: existing CLI flags, MCP tool names/signatures, and public core helper functions remain intact (deprecated internals stay as thin re-exports during transition).
- **Test and type gates**: `uv run pytest`, `uv run mypy src tests`, `uv run brain79 lint --strict`, and `uv run brain79 doctor` must pass with zero regressions after every stage.

## Stage 1 — Correctness, concurrency, and transactional integrity

Target modules: `src/brain79/core/navigation.py`, `src/brain79/core/locks.py`, `src/brain79/core/session_commit.py`.

### R-1.1 — Case-normalized navigation sections
- Normalize `section` keys to lowercase in `register_article()` and `generate_quick_navigation()` before grouping and rendering `### {header_name}`.
- Self-heal existing mixed-case entries (such as `"Changelog"` vs. `"changelog"`) inside `.navigation_registry.json` during `regenerate_index_navigation()`.

### R-1.2 — Strict lock hierarchy and TOCTOU elimination
- Document and enforce a global lock acquisition order in `locks.py`: `_transaction.lock` -> `_registry.lock` -> `_drift_manifest.lock` -> `INDEX.md.lock`. No code path may acquire locks in reverse order.
- Eliminate the unlocked read window in `regenerate_index_navigation()`: compute the rendered Quick navigation section from the registry state captured under lock before releasing `_registry.lock`, preventing torn reads under concurrent writers.

### R-1.3 — Complete transactional rollback and scoped temp cleanup
- Track all `.tmp.*` paths created during a `commit_session()` call in an explicit transaction-local list; on `BaseException`, unlink only transaction-owned temp files instead of running `w_root.rglob("*.tmp*")`.
- Extend the Pass 3 pre-commit snapshot and rollback handler to cover `.navigation_registry.json`, `INDEX.md`, and any `_raw/sessions/` file created in Pass 3.
- Remove silent `except Exception: pass` around `regenerate_index_navigation(w_root)` in Pass 3: a failure must either trigger rollback or surface explicitly in the commit receipt (`health_status: "degraded"` with an actionable warning), never silent `"ok"`.

## Stage 2 — Centralized Git layer and error-handling hardening

Target modules: new `src/brain79/core/git_ops.py`, `drift.py`, `session_commit.py`, `orient.py`, `handoff_freshness.py`, `update.py`, `init_project.py`, `curate.py`, `context.py`, `wiki.py`, `doctor.py`, `frontmatter.py`.

### R-2.1 — Unified Git abstraction (`core/git_ops.py`)
- Consolidate all direct `subprocess.run(["git", ...])` invocations across the 10 calling modules into `core/git_ops.py`.
- Provide typed helpers (`git_status_porcelain`, `git_rev_parse_head`, `git_current_branch`, `git_last_commit_for_path`, `git_show_blob`, `git_diff_names`) returning structured `GitResult` objects and raising explicit `NotAGitRepoError` or `GitTimeoutError`.
- Always pass `-c core.quotepath=false` for path-returning commands and `--` before repository pathspecs.
- Support optional per-session caching of `HEAD` and file-blob lookups so AST verification avoids launching 3 sequential `git` subprocesses per verified file.

### R-2.2 — Eliminate silent fail-open in guardrails
- Audit broad `except Exception:` blocks across `drift.py`, `session_commit.py`, and `navigation.py`.
- In `has_public_python_api_changes` and Pass 2d (`dirty_git_paths`), distinguish expected non-git workspaces (`NotAGitRepoError`) from operational errors (`GitTimeoutError`, `OSError`, `UnicodeDecodeError`).
- Operational failures during verification must never silently return `(False, "")` or empty dirty sets; emit a structured warning or fail closed with an actionable `ValidationError` when verifying drifted articles.

### R-2.3 — Deep-copy safe frontmatter cache
- Replace shallow `list(v)` cloning in `_PARSE_CACHE` (`frontmatter.py`) with recursive deep-copying (`copy.deepcopy` or custom recursive cloner for dicts/lists) so callers mutating nested metadata cannot poison the long-lived MCP server cache.

## Stage 3 — Security hardening

Target modules: `src/brain79/core/drift.py` (or `core/ast_guards/`), `src/brain79/core/update.py`, `src/brain79/core/git_ops.py`.

### R-3.1 — Repository containment for code-reading paths
- Before reading any workspace file referenced by `applies_to` or AST verification (`target_disk = p_root / rel_posix_path`), resolve the path and verify `target_disk.resolve().is_relative_to(p_root)`.
- Reject symlinks or path expressions resolving outside `project_root` with a structured error/warning; never read external files.

### R-3.2 — Defensive CLI and Git argument validation
- Reject `branch_override` values starting with `-` in `update.py` (blocking option injection in addition to the existing character allowlist).
- Verify every path-accepting helper in `git_ops.py` terminates options with `--` and never uses `shell=True`.

## Stage 4 — Modular decomposition for roadmap extensibility

Target modules: `core/ast_guards/`, `core/harnesses/`, `server.py`, `config.py`, `drift.py`, `init_project.py`.

### R-4.1 — Pluggable AST inspector subsystem (`core/ast_guards/`)
- Extract Python AST signature extraction and comparison out of `drift.py` into `core/ast_guards/base.py` (`LanguageInspector` protocol + `SignatureDiff` dataclass) and `core/ast_guards/python_inspector.py`.
- Register inspectors by file extension in `core/ast_guards/__init__.py` so future Tree-sitter inspectors plug in without modifying `drift.py` or `session_commit.py`.
- Retain `extract_public_python_signatures` and `has_public_python_api_changes` as thin backward-compatible re-exports in `drift.py`.

### R-4.2 — Harness adapter registry (`core/harnesses/`)
- Extract harness configuration writers out of `init_project.py` into a `HarnessAdapter` protocol (`detect`, `sync`, `diagnose`) with concrete modules (`agents_md.py`, `mcp_json.py`, `cursor.py`, `antigravity.py`).
- Route `init_project.py` and `doctor.py` through the registry so new client adapters (`CLAUDE.md`, `.cursor/rules/`, Copilot, lifecycle hooks) register declaratively.

### R-4.3 — Configurable MCP server factory (`server.py`)
- Refactor static module-level tool registration in `server.py` into `create_mcp_server(profile: Literal["core", "full"] = "full") -> FastMCP`.
- Define explicit `CORE_TOOLS` and `ADMIN_TOOLS` sets; keep the default module-level `mcp = create_mcp_server(profile="full")` intact during this cycle so existing integrations and symmetry tests pass unchanged while enabling `--mcp-profile core` immediately.

### R-4.4 — Scoped project context (`config.py`)
- Introduce an immutable `ProjectContext(project_root: Path, wiki_root: Path)` backed by `contextvars.ContextVar` alongside `get_project_root()` / `set_project_root()`, enabling isolated multi-worktree execution without mutating process-global state.
- Eliminate circular-import workarounds (deferred intra-function imports) between `frontmatter.py`, `navigation.py`, and `lint.py` by extracting shared link/frontmatter parsing primitives cleanly.

## Stage 5 — Verification and release parity

- Sync the repository's own templates via `brain79 update-project` and regenerate `INDEX.md` so `brain79 orient` runs with zero advisory warnings and zero duplicate sections.
- Bump version to `0.11.0` across `src/brain79/__init__.py`, `README.md`, `CHANGELOG.md`, `.brain-79/changelog/v0-11-0.md`, and `AGENTS.md` per ADR-013.

## Acceptance criteria

| ID | Stage | Requirement | Verification |
|---|---|---|---|
| **AC-10.1** | Stage 1 | Mixed-case `section` values (`"Changelog"` and `"changelog"`) normalize to one `### Changelog` header in `INDEX.md`; live repo `INDEX.md` has zero duplicate headers. | `tests/test_navigation.py`, `brain79 orient` |
| **AC-10.2** | Stage 1 | `regenerate_index_navigation` holds locks in documented global order with zero unlocked read window between registry load and index rendering. | `tests/test_navigation.py`, `tests/test_chaos_and_fuzzing.py` |
| **AC-10.3** | Stage 1 | Simulated `BaseException` during Pass 3 rolls back articles, `.drift_manifest.json`, `.navigation_registry.json`, `INDEX.md`, and `_raw/sessions/`; an unrelated `.tmp` file from another worker is untouched. | `tests/test_session_commit.py`, `tests/test_chaos_and_fuzzing.py` |
| **AC-10.4** | Stage 1 | Failure in `regenerate_index_navigation` during Pass 3 is never silently swallowed as `"health_status": "ok"`. | `tests/test_session_commit.py` |
| **AC-10.5** | Stage 2 | Zero direct `subprocess.run(["git", ...])` calls remain outside `src/brain79/core/git_ops.py` (verified via static AST/grep test). | `tests/test_git_ops.py` |
| **AC-10.6** | Stage 2 | Simulated `GitTimeoutError` or unreadable target during AST Guard C or Pass 2d does not fail-open silently; emits structured warning or `ValidationError`. | `tests/test_drift.py`, `tests/test_session_commit.py` |
| **AC-10.7** | Stage 2 | Mutating nested lists or dicts returned by `parse_frontmatter()` does not alter subsequent cached returns for the same content. | `tests/test_frontmatter.py` |
| **AC-10.8** | Stage 3 | Symlink in workspace pointing outside `project_root` referenced by `applies_to` is rejected before reading by AST verification. | `tests/test_drift.py`, `tests/test_security.py` |
| **AC-10.9** | Stage 3 | `update_project(branch_override="--upload-pack=evil")` is rejected with exit code `1` before invoking `subprocess`. | `tests/test_update.py` |
| **AC-10.10** | Stage 4 | `core/ast_guards/` provides `LanguageInspector` protocol + Python inspector; verifying 10 `.py` files reuses cached `HEAD` lookup; `drift.py` re-exports preserve existing imports. | `tests/test_ast_guards.py`, `tests/test_drift.py` |
| **AC-10.11** | Stage 4 | `core/harnesses/` registry drives `init_project` and `doctor` across all Tier 1 harnesses with zero behavioral change for existing projects. | `tests/test_init_project.py`, `tests/test_project_upgrade_and_doctor.py` |
| **AC-10.12** | Stage 4 | `create_mcp_server(profile="core")` registers only `CORE_TOOLS`; `create_mcp_server(profile="full")` preserves 1:1 parity with all 22 MCP tools. | `tests/test_mcp_server.py`, `tests/test_symmetry.py` |
| **AC-10.13** | Stage 4 | `ProjectContext` `ContextVar` isolates concurrent roots in async/threaded tests without mutating global `_project_root`. | `tests/test_config.py` |
| **AC-10.14** | Stage 5 | Full CI suite (`pytest`, `mypy src tests`, `brain79 lint --strict`, `brain79 doctor`), `v0.11.0` version parity, and clean `orient()` on this repo all pass. | CI matrix, `tests/test_version_governance.py` |

---

[← Back to Index](../INDEX.md)
