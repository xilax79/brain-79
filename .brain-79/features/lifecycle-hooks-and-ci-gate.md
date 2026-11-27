---
type: feature
summary: read-only CI governance PR gate, composite GitHub Action, legacy_frontmatter_digest lint advisory, and cross-platform passive lifecycle hook runtime
status: shipped
version: 0.18.0
applies_to:
  - src/brain79/core/ci_check.py
  - action.yml
related:
  - decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md
  - decisions/adr-023-external-drift-lockfile.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - features/team-collaboration-and-onboarding.md
  - features/cli.md
last_updated: 2026-11-27
---

# Feature — Passive lifecycle hooks and CI PR gate

## Overview

The passive lifecycle hooks and CI PR gate subsystem provides a read-only CI governance engine (`src/brain79/core/ci_check.py`), a composite GitHub Action (`action.yml`), and a cross-platform `SessionStart` / `Stop` lifecycle hook runtime (`brain79 ci-check --lifecycle-hook`).

## CI governance and PR gate (`run_ci_check`)

`run_ci_check()` executes inside `project_context()` with `persist=False` cache hydration using a single shared `WorkspaceIndex`:

1. **Diff range resolution**: uses `git_diff_range_names()` when `--base` is provided, falls back to `git_dirty_paths()` or `GITHUB_BASE_REF` (`origin/<base>` -> `<base>` -> `shallow_fallback`), and degrades gracefully in non-Git directories.
2. **Metadata exclusion**: `_EPHEMERAL_WIKI_FILES` (`ci_check.py`) and `_EXCLUDED_WIKI_FILES` (`handoff_freshness.py`) exclude `drift.lock` alongside `.navigation_registry.json` and `.drift_manifest.json` so lockfile updates never trigger false `impacted_articles` or handoff staleness.
3. **Impact and ADR surfacing**: partitions changed files into workspace targets and wiki articles, identifies impacted active governing articles (annotated with `updated_in_diff`), and expands 1-hop linked active ADRs in `decisions/`.
4. **Unified drift, conflict, and lint parity**: collects `detect_all_drift()` results (including exact per-file attribution from `.brain-79/drift.lock` on fresh clones and `"conflict": true` entries) and complete structural + organizational lint issues via `collect_wiki_lint_results()`.
5. **Fail-closed corrupt lockfile vs. fail-open lifecycle hooks**: corrupt `.brain-79/drift.lock` raises `ValidationError(rule="corrupt_drift_lock")` (`Exit 1` in `ci-check`, never `Exit 2`), whereas `run_lifecycle_hook()` (`--lifecycle-hook`) preserves ADR-021 fail-open behavior (`{}` and `Exit 0`).
6. **Legacy frontmatter advisory (`lint_organizational.py`)**: when `.brain-79/drift.lock` coexists with `.md` articles retaining `applies_to_digest` or `applies_to_count`, `check_legacy_frontmatter_digest()` emits an `INFO`-severity `legacy_frontmatter_digest` advisory pointing to `brain79 migrate --apply` (never failing `lint --strict`, `lint --fail-on-warnings`, or `ci-check`).
7. **Dual-tier enforcement matrix**: defaults to `strict` in CI (`--enforcement <strict|balanced|advisory|schema>` plus `--fail-on-warnings`); `CRITICAL` lint errors always fail (`exit_code = 1`), while drift and `WARNING` issues fail under `strict` (or `--fail-on-warnings`) and warn (`exit_code = 0`) under `balanced` / `advisory`.
8. **Report persistence**: renders `<!-- brain79:ci-check -->` Markdown (`CiCheckReport.format_markdown()`) or JSON (`to_dict()`), and writes `--summary-file` or `$GITHUB_STEP_SUMMARY` even when the gate fails.

## Composite GitHub Action & CI workflow (`action.yml`, `.github/workflows/ci.yml`)

- **Composite action (`action.yml`)**: runs `brain79 ci-check --write-step-summary --format json` from `$GITHUB_ACTION_PATH` using `astral-sh/setup-uv@v10.4.0`, passes inputs via `env:` variables, exports `status`, `exit-code`, `drifted-count`, and `report-json-path` to `$GITHUB_OUTPUT`, and updates `<!-- brain79:ci-check -->` PR comments via `gh api --paginate`.
- **CI artifact upload & polyglot gating (`.github/workflows/ci.yml`)**: both `test` and `test-polyglot` failure upload steps configure `include-hidden-files: true` and `if-no-files-found: ignore` for `${{ runner.temp }}/.pytest_tmp`, and `test_fixture_sources_supported_by_ast_guard_c` gates optional `.mjs` polyglot assertions on `BRAIN79_REQUIRE_POLYGLOT=1` or installed JS grammar.

## Passive lifecycle hook runtime (`run_lifecycle_hook`)

`brain79 ci-check --lifecycle-hook <session-start|stop> --client <auto|claude|agy|cursor>` provides fail-open host integration:

- **Bounded cross-platform I/O**: reads at most `1 MB` from `stdin`, emits ASCII-escaped JSON (`ensure_ascii=True`) with `sys.stdout.flush()`, and always exits `0`.
- **Workspace and client resolution**: resolves `.brain-79/` from payload workspace keys (`cwd`, `workspacePaths`, `workspace_roots`) within `.git` boundaries and infers `agy`, `cursor`, or `claude` when `--client auto` is set.
- **Session start**: invokes `orient(task=task_hint, max_articles=4)` (truncating `task_hint` to `2,000` chars) and formats client-native context injection payloads.
- **Stop guard**: checks `continuationActive`, `stop_hook_active`, `loop_count >= 1`, `terminationReason != "NO_TOOL_CALL"`, `status != "completed"`, and `schema.enforcement == "advisory"` before surfacing drifted articles via `detect_all_drift()`.
- **Host-side `/tmp` anti-loop fallback guard**: when a host omits loop-flag fields on consecutive `stop` invocations, `run_lifecycle_hook("stop")` records the deterministic drift signature and timestamp under `Path(tempfile.gettempdir()) / "brain79-stop-guards"` (`_STOP_GUARD_SESSION_TTL_SECONDS = 1800.0` when a session key is present, `_STOP_GUARD_FALLBACK_TTL_SECONDS = 60.0` otherwise), returning `{}` on repeated identical drift without writing anything under `.brain-79/` or `.brain-79/.locks/`.

---

[← Back to Index](../INDEX.md)
