---
type: feature
summary: read-only CI governance PR gate, composite GitHub Action, and cross-platform passive lifecycle hook runtime
status: shipped
version: 0.15.0
applies_to:
  - src/brain79/core/ci_check.py
  - action.yml
related:
  - decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - features/team-collaboration-and-onboarding.md
  - features/cli.md
last_updated: 2026-11-24
applies_to_digest: "sha256:5c36ba2d09b931c7"
applies_to_count: 2
---

# Feature — Passive lifecycle hooks and CI PR gate

## Overview

The passive lifecycle hooks and CI PR gate subsystem provides a read-only CI governance engine (`src/brain79/core/ci_check.py`), a composite GitHub Action (`action.yml`), and a cross-platform `SessionStart` / `Stop` lifecycle hook runtime (`brain79 ci-check --lifecycle-hook`).

## CI governance and PR gate (`run_ci_check`)

`run_ci_check()` executes inside `project_context()` with `persist=False` cache hydration using a single shared `WorkspaceIndex`:

1. **Diff range resolution**: uses `git_diff_range_names()` when `--base` is provided, falls back to `git_dirty_paths()` or `GITHUB_BASE_REF` (`origin/<base>` -> `<base>` -> `shallow_fallback`), and degrades gracefully in non-Git directories.
2. **Impact and ADR surfacing**: partitions changed files into workspace targets and wiki articles, identifies impacted active governing articles (annotated with `updated_in_diff`), and expands 1-hop linked active ADRs in `decisions/`.
3. **Unified drift and lint parity**: collects `detect_all_drift()` results and complete structural + organizational lint issues via `collect_wiki_lint_results()`.
4. **Dual-tier enforcement matrix**: defaults to `strict` in CI (`--enforcement <strict|balanced|advisory|schema>` plus `--fail-on-warnings`); `CRITICAL` lint errors always fail (`exit_code = 1`), while drift and `WARNING` issues fail under `strict` (or `--fail-on-warnings`) and warn (`exit_code = 0`) under `balanced` / `advisory`.
5. **Report persistence**: renders `<!-- brain79:ci-check -->` Markdown (`CiCheckReport.format_markdown()`) or JSON (`to_dict()`), and writes `--summary-file` or `$GITHUB_STEP_SUMMARY` even when the gate fails.

## Composite GitHub Action (`action.yml`)

The root `action.yml` composite action runs `brain79 ci-check --write-step-summary --format json` from `$GITHUB_ACTION_PATH` using `astral-sh/setup-uv@v10.4.0`, passes all inputs exclusively through `env:` variables to prevent script injection, exports `status`, `exit-code`, `drifted-count`, and `report-json-path` to `$GITHUB_OUTPUT`, and optionally creates or updates a single idempotent `<!-- brain79:ci-check -->` PR comment via `gh api --paginate`.

## Passive lifecycle hook runtime (`run_lifecycle_hook`)

`brain79 ci-check --lifecycle-hook <session-start|stop> --client <auto|claude|agy|cursor>` provides fail-open host integration:

- **Bounded cross-platform I/O**: reads at most `1 MB` from `stdin`, emits ASCII-escaped JSON (`ensure_ascii=True`) with `sys.stdout.flush()`, and always exits `0`.
- **Workspace and client resolution**: resolves `.brain-79/` from payload workspace keys (`cwd`, `workspacePaths`, `workspace_roots`) within `.git` boundaries and infers `agy`, `cursor`, or `claude` when `--client auto` is set.
- **Session start**: invokes `orient(task=task_hint, max_articles=4)` (truncating `task_hint` to `2,000` chars) and formats client-native context injection payloads.
- **Stop guard**: checks `continuationActive`, `stop_hook_active`, `loop_count >= 1`, `terminationReason != "NO_TOOL_CALL"`, `status != "completed"`, and `schema.enforcement == "advisory"` before surfacing drifted articles via `detect_all_drift()`.

---

[← Back to Index](../INDEX.md)
