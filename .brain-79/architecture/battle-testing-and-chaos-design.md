---
type: architecture
summary: implementation contract for v0.10.0 battle-testing, covering the multi-OS CI matrix, chaos and fuzz tests, the five-archetype gauntlet, live-agent recovery smoke, failure catalog, and acceptance gates
stability: stable
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/locks.py
  - src/brain79/core/drift.py
  - src/brain79/core/wiki.py
  - src/brain79/core/validation.py
  - src/brain79/core/frontmatter.py
  - src/brain79/core/migration.py
  - src/brain79/core/session_commit.py
  - scripts/run_e2e_smoke.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - features/transitive-drift-and-ripple-guards.md
  - decisions/adr-013-versioning-and-release-governance.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
last_updated: 2026-11-17
applies_to_digest: "sha256:ecc9db593489ae7f"
applies_to_count: 8
---

# Architecture — Battle-testing, chaos fuzzing, and multi-repo gauntlet

## Overview

This document is the implementation contract for `v0.10.0`. An agent must be able to build every deliverable from it without guessing. The roadmap keeps the summary and the acceptance table; this file keeps the details.

Ground rules:
- **Versioning**: Phase 9 ships as `0.10.0` (each phase increments `y` in `x.y.z`). It never bumps to `1.0.0`; only the project owner decides that.
- **Scope**: tests, CI, scripts, and version-parity files. No new runtime features. A defect found by a test is fixed in `src/brain79/` in the same phase, with a regression test. No `xfail` or `skip` may hide a real defect.
- **Starting state**: `.github/workflows/` does not exist, and `scripts/` has only `run_e2e_smoke.py` (4 scenarios). Dev dependencies are `pytest`, `pytest-asyncio`, and `mypy`. No new third-party dependency is added (no `hypothesis`).
- **Real API names**: `validate_article_content` (`validation.py`), `parse_frontmatter` (`frontmatter.py`), `migrate_wiki`, `write_article`, `edit_article`, `commit_session`, `regenerate_index_navigation`, `WorkspaceIndex.build`. Exceptions: `ValidationError` and `FrontmatterError` (both `ValueError`).
- **Markers**: register `chaos`, `gauntlet`, and `perf` in `[tool.pytest.ini_options]` with `--strict-markers`. Plain `pytest` runs all of them; `-m "not perf"` is allowed only for local speed.
- **Determinism**: every random input uses `random.Random(seed)`. The seed is printed on failure and can be set with `BRAIN79_FUZZ_SEED`. Default seed list is fixed (`0..19`).
- **Isolation**: every test uses `tmp_path`. `conftest.py` already purges `BRAIN79_*` env vars; the new `BRAIN79_FUZZ_SEED` and `BRAIN79_PERF_FACTOR` are read inside the tests that need them.

## CI matrix (Deliverable 9.1)

File: `.github/workflows/ci.yml`. Trigger: `push` and `pull_request` on `main`. Top-level `permissions: contents: read`.

| Item | Contract |
|---|---|
| Matrix | `os: [ubuntu-latest, macos-latest, windows-latest]` × `python: ["3.11", "3.12", "3.13"]` = 9 jobs, `fail-fast: false`, `timeout-minutes: 20` |
| Setup | `actions/checkout`, `astral-sh/setup-uv`, then `uv sync --group dev` on the matrix Python. Actions are pinned to a major version tag |
| Line endings | add `.gitattributes` with `* text=auto eol=lf` so Windows checkouts keep LF and Merkle digests match |
| Steps | `uv run pytest -q`, `uv run mypy src tests`, `uv run brain79 lint --strict`, `uv run brain79 doctor --format json` |
| Doctor policy | `doctor` exit code `0` passes, `1` fails the job. Exit code `2` (warnings only) passes **only** when every warning rule is in an allowlist stored in `tests/test_ci_workflow.py`; any other warning fails |
| Windows shell | hook tests run with Git Bash (preinstalled on `windows-latest`); tests needing POSIX `sh` carry `skipif(shutil.which("sh") is None)` and may not skip on `ubuntu` or `macos` |
| Cleanup | on failure, upload `pytest` temp roots (`--basetemp=.pytest_tmp`) as an artifact |

Platform tests that need a real OS (not mocks), added to `tests/test_cross_platform_and_locks.py` or the chaos file:
- `win32` only: `atomic_replace_with_retry` succeeds while another handle is open briefly; `%APPDATA%` branch in `init_project.py` is exercised with the real variable; CRLF working-tree input yields the same drift digest as LF.
- `darwin` and `win32` (case-insensitive FS): writing `Topics/A.md` after `topics/a.md` is rejected or normalized by exact-case resolution, never silently duplicated.
- All platforms: a path with spaces and non-ASCII characters in the project root works end to end.

## Chaos and fuzzing (Deliverable 9.2)

File: `tests/test_chaos_and_fuzzing.py`. Total runtime on one runner: `<= 120 s`.

### Multiprocess contention
- Use `multiprocessing.get_context("spawn")` (Windows and macOS default; Linux must match). Workers are top-level functions so they pickle.
- 8 workers wait on a shared `Barrier(8)`, then run 25 operations each, rotating `write_article`, `edit_article`, `regenerate_index_navigation`, and `commit_session`. Mix **distinct** targets (`topics/w{n}-{i}.md`) and **one shared** target (`topics/shared.md`).
- Parent joins with a 90 s deadline; a worker alive after the deadline is killed and the test fails.
- Each operation may only succeed or raise a structured `ValidationError` or lock-timeout error. Any other exception type fails the test.

Assertions after join:
1. `.navigation_registry.json` and `.drift_manifest.json` parse as JSON.
2. No file matching `*.tmp`, `*.tmp.*`, or `*.md.tmp` remains under `.brain-79/`.
3. Every lock in `.brain-79/.locks/` can be acquired with `timeout=0` (no leaked holder).
4. Every distinct article that reported success exists and parses; the shared article equals exactly one complete payload (no torn write, no mixed content).
5. `brain79 lint --strict` on the final wiki returns exit code `0`.

Crash case (`posix` only; `win32` skips with a reason): SIGKILL one worker while it holds a lock, then assert a fresh operation completes within the lock timeout (`10 s`) and leaves no orphan `.tmp` after the next write.

### Adversarial input fuzzing
Targets: `validate_article_content`, `parse_frontmatter`, and `migrate_wiki` (on a wiki seeded with the corpus). Allowed outcome: a normal return, `ValidationError`, or `FrontmatterError`. Forbidden: any other exception, a hang over 5 s per input, or a changed file on disk after a rejected write.

| Class | Corpus |
|---|---|
| YAML shape | unterminated `---`, top-level list or scalar, duplicate keys, non-string keys, tabs, anchors and aliases (billion-laughs style, depth and size capped), `!!python/object` tags (must not execute), 5,000-key frontmatter |
| Encoding | UTF-8 BOM, invalid UTF-8 bytes in a file on disk, NUL bytes, lone surrogates, `\r\n`, bare `\r`, and mixed endings in one file |
| Unicode | RTL scripts, zero-width joiners, combining marks, emoji and 255-byte slugs, NFC versus NFD duplicates of one filename |
| Size | 20,479, 20,480 (accepted), and 20,481 (rejected) bytes of UTF-8; same character counts with 3-byte characters; 400 versus 401 lines |
| Paths | `..` traversal, absolute paths, Windows reserved names (`CON`, `NUL`), trailing dots and spaces, symlink or junction escaping the wiki |
| Graphs | wiki-to-wiki cycles `A -> B -> C -> A` through `applies_to` entries that point at `.brain-79/*.md` and through `related`; a self-reference; a 200-node chain. `orient`, ripple propagation, and `lint` must terminate within 5 s and report the cycle or ignore the back edge deterministically |

Unreadable input on disk must produce a structured error, not `UnicodeDecodeError`. Where the engine currently raises one, fix it in `src/` (this is in scope).

### Environment faults
Read-only wiki directory, full disk (monkeypatched `OSError(ENOSPC)` in `write_text`), and `KeyboardInterrupt` during `commit_session` Pass 3. Required result: either the full commit is applied or none of it is; no partial article, no orphan `.tmp`, lock released.

## Gauntlet (Deliverables 9.3 and 9.4)

### Runner contract
- `scripts/run_battle_gauntlet.py [--archetype N] [--keep] [--json PATH]` builds each archetype in a temp dir, runs the lifecycle, prints one line per step, and writes a JSON report (`archetype`, `step`, `status`, `duration_ms`, `error`).
- Exit code `0` all passed, `1` any failed, `2` usage or environment error (for example `git` missing).
- `tests/test_battle_gauntlet.py` calls the same functions in-process and runs the script once as a subprocess to check exit code and report schema. One test per archetype.
- Git archetypes set `user.name`, `user.email`, `init.defaultBranch=main`, and `commit.gpgsign=false` locally in the temp repo. Tests must not touch global git config.
- On failure the temp dir is kept and its path is printed.

### Lifecycle (the 10 steps, every archetype)
1. `init` (or `init --upgrade` for archetype 2) · 2. `doctor` · 3. `bootstrap` · 4. `write` 3 articles · 5. `orient` with the task and paths · 6. `edit` one article · 7. `session-commit` with a handoff · 8. mutate source or wiki · 9. `lint --strict` and drift check expecting the archetype's state · 10. recover to clean (`doctor --fix`, ripple fix, or purge) and `lint --strict` exit `0`.

### Archetypes
| # | Workspace | Must prove |
|---|---|---|
| 1 | Python and TypeScript files, `.png` and `.sqlite` binaries, ignored `node_modules/`, `.venv/`, `dist/` | `WorkspaceIndex` excludes ignored dirs and binaries, cross-language `applies_to` globs resolve, index latency within budget |
| 2 | 25 hand-written `.md` with missing frontmatter, broken links, missing H2; a `.husky/` pre-commit plus `core.hooksPath`; `.mcp.json` with `/Users/old/brain79` | After `init --upgrade` and `doctor --fix`: byte-identical content hash for every original body (zero data loss), legacy files carry `status: legacy`, Husky hook and `core.hooksPath` unchanged, stale path replaced, `lint --strict` exit `0` with legacy exemptions only for the rules in ADR-003 |
| 3 | `--profile general`, no `.git`, no code, 10 sessions | Amnesia Test guard blocks Type B writes without findings, custom `SCHEMA.md` folder types validate, handoff freshness works without git (no crash, no false `foreign_branch`) |
| 4 | Git repo with `main`, `feat/payments`, `hotfix/auth`; rebase; public function signature change | Handoff reports `foreign_branch` on another branch and `stale` after drift; Guard C blocks a signature change; `verified_articles` cannot bypass it; the ripple gate clears after the article is updated |
| 5 | 200 articles and 1,000 source files | `orient`, `lint --strict`, and `doctor` stay inside the budgets below |

### Latency budgets
Budgets are measured in-process (no interpreter startup), median of 5 runs after one warm-up, with the `git ls-files` timeout (`2.0 s`) unchanged. Calibration step: run `scripts/benchmark_baseline.py` on the three OS runners first, then freeze the numbers in `tests/test_battle_gauntlet.py`. Initial ceilings: `WorkspaceIndex.build` on archetype 1 `<= 250 ms`; on archetype 5 `orient <= 500 ms`, `lint --strict <= 1,500 ms`, `doctor <= 1,500 ms`. `BRAIN79_PERF_FACTOR` (default `1`, CI sets `3`) scales them. A budget may only be raised in a PR that states the measured reason.

### Live-agent recovery smoke (9.4)
- **Model policy**: any test that needs a paid LLM uses `gemini-3.8-flash` with effort `low` to minimize cost. Effort `medium` is allowed only for a scenario that demonstrably fails at `low`, and the exception is recorded in the changelog. No other model or higher effort is used.
- Extend `scripts/run_e2e_smoke.py` with scenarios 5 (`unresolved_session_ripple`) and 6 (`duplicate_governance_target`). The prompt must **not** mention the rule or the fix.
- It needs a real agent CLI, network, and cost, so it is **not** part of CI or `pytest`. It runs manually before release. Exit `77` (skipped) when no agent CLI is found.
- Pass rule per scenario: up to 3 attempts, pass if at least 2 succeed. A success means the second `session_commit` call is accepted, the first call was rejected with the expected rule, and `check_mcp_zero_retry` shows no third attempt. Record agent, model, effort, date, and results in `changelog/v0-10-0.md`.

## Failure catalog and acceptance gates

| ID | Failure mode | Detected by |
|---|---|---|
| F1 | Torn or corrupt JSON state under contention | chaos assertions 1, 4 |
| F2 | Leaked lock or temp file | chaos assertions 2, 3 and crash case |
| F3 | Lost update on the shared article | chaos assertion 4 |
| F4 | Windows locked-file replace, CRLF digest mismatch, `%APPDATA%` path | `win32` platform tests |
| F5 | Case-insensitive filename collision | `darwin` and `win32` platform test |
| F6 | Unhandled exception on hostile input, hang, YAML code execution | fuzz corpus |
| F7 | Wiki graph cycle causing recursion or infinite loop | graph corpus |
| F8 | Partial commit on interrupt, disk full, or read-only dir | environment faults |
| F9 | Data loss when upgrading a legacy wiki | archetype 2 |
| F10 | Hook manager overwritten | archetype 2 |
| F11 | Gitless crash or false branch detection | archetype 3 |
| F12 | Guard C or ripple gate bypass | archetype 4 |
| F13 | Latency regression at scale | archetype 5 and 1 budgets |
| F14 | CI drift (missing OS or Python cell, unpinned action, doctor warning masked) | `tests/test_ci_workflow.py` |
| F15 | Agent cannot self-correct from an `actionable` hint | live smoke |
| F16 | Release parity broken | version-governance tests |

Gate for `v0.10.0` (all required): the 9-cell CI matrix is green on the release commit; `tests/test_ci_workflow.py` parses `ci.yml` with `pyyaml` and asserts the matrix, `fail-fast: false`, the four steps, pinned actions, and the doctor allowlist; chaos and gauntlet tests pass on all cells; the same chaos test passes 20 consecutive local runs (flake check); the live smoke is recorded; `__version__` is `0.10.0` with `README.md` badge, `CHANGELOG.md`, `changelog/v0-10-0.md`, and `AGENTS.md` anchor synced; the roadmap and `current-state.md` mark Phase 9 shipped; `brain79 lint --strict` and `brain79 doctor` are clean with zero drift.

---

[← Volver al Índice](../INDEX.md)
