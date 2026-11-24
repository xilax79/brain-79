---
spec_id: SPEC-014
title: Passive lifecycle hooks and CI PR gate
target_version: v0.15.0
status: implemented
owner: xilax
last_updated: 2026-11-24
related_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - features/team-collaboration-and-onboarding.md
  - features/transitive-drift-and-ripple-guards.md
  - features/cli.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
target_wiki:
  - decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md
  - features/lifecycle-hooks-and-ci-gate.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - features/team-collaboration-and-onboarding.md
  - features/cli.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - architecture/current-state.md
  - architecture/roadmap-industrial-scale.md
  - product/overview.md
  - changelog/v0-15-0.md
---

# SPEC-014 — Passive lifecycle hooks and CI PR gate

## Problem statement and goal

`brain-79` currently relies on voluntary agent compliance with `AGENTS.md` / `CLAUDE.md` instructions to invoke `brain79_orient` at session start and `brain79_session_commit` before session exit, while local `.git/hooks/pre-commit` checks can be bypassed (`--no-verify`) or skipped when third-party hook managers (Husky, Lefthook, `pre-commit`) are present. Furthermore, human engineers reviewing Pull Requests in GitHub lack automated visibility into which governing wiki articles have drifted or which Architectural Decision Records (ADRs) govern the files modified in a PR diff. This phase closes the voluntary-compliance gap via opt-in native agent lifecycle hooks (`SessionStart` and `Stop` for Claude Code, Antigravity, and Cursor) backed by a cross-platform CLI execution engine (`brain79 ci-check`), delivers a reusable GitHub Action PR gate (`action.yml`), and formalizes the dual-tier team workflow (`balanced` local enforcement paired with `strict` CI PR gating).

## Non-goals (out of scope)

- **No new MCP tools**: per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md), `MCP_TOOLS` remains fixed at 9 focused hot-path tools. `brain79 ci-check` is strictly a CLI-only subcommand (`WHITELIST` expands from 24 to 25 subcommands).
- **No external runtime or network dependencies in `src/brain79/`**: `brain79 ci-check` MUST NOT import `requests`, `httpx`, or `PyGithub`, and MUST NOT make network calls from Python. GitHub PR commenting is handled exclusively in the composite GitHub Action (`action.yml`) via the runner's pre-installed `gh` CLI / GitHub REST API.
- **No shell-script hook payloads**: lifecycle hooks MUST NOT write `.sh` or `.ps1` wrapper scripts into user repositories; all hooks invoke `brain79 ci-check --lifecycle-hook ...` directly so they work identically across macOS, Linux, and Windows.
- **No mandatory hook injection on default `brain79 init`**: lifecycle hooks are strictly opt-in (`--install-lifecycle-hooks` or explicit `--harnesses` selection) so default project initialization remains non-intrusive and backward-compatible.
- **No Phase 15 capabilities**: do not implement Tree-sitter polyglot AST guards, `brain79 stats`, longitudinal LLM benchmarks, or PyPI publishing under this specification.

## Dependencies

- **Internal seams**:
  - `src/brain79/core/git_ops.py` (centralized Git subprocess layer).
  - `src/brain79/core/drift.py` (`WorkspaceIndex`, `detect_all_drift`, zero-masking `rebuild_drift_manifest`).
  - `src/brain79/core/context.py` (`rank_context_articles` 3-signal context ranking and 1-hop ADR expansion).
  - `src/brain79/core/lint.py` and `src/brain79/core/lint_organizational.py` (`lint_wiki`, `lint_organizational`).
  - `src/brain79/core/harnesses/` (`HarnessAdapter` protocol and registry).
  - `src/brain79/cli/dispatch.py` and `src/brain79/__main__.py` (CLI whitelist and dispatcher).
- **External / optional**: none (zero new Python dependencies; Python 3.11+ stdlib plus existing `pyyaml`, `filelock`, `fastmcp`).

## Constraints and invariants

All requirements must preserve the repository's canonical invariants:

- **Versioning**: pre-GA minor bump (`0.15.0`) per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md) and single-source parity per [ADR-013](../.brain-79/decisions/adr-013-versioning-and-release-governance.md).
- **Concurrency and cross-platform I/O**: lock hierarchy and atomic LF writes per [ADR-014](../.brain-79/decisions/adr-014-centralized-locks-and-cross-platform-io.md). `brain79 ci-check` is strictly read-only on `.brain-79/` (`persist=False` when rebuilding in-memory caches) except when writing to an explicit external `--summary-file` or `$GITHUB_STEP_SUMMARY`.
- **CLI and MCP symmetry**: MCP-subset / CLI-superset invariant (`MCP_TOOLS` ⊂ `WHITELIST`, 9 MCP tools ⊂ 25 CLI subcommands) per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md) and [symmetry.md](../.brain-79/architecture/symmetry.md).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Documentation style**: clean B2 English, sentence case first, and living manual rules (`<= 20 KB`, `<= 400` lines, zero temporal markers in living manual titles/overviews) per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **Doctor check count invariant**: on a clean repository without broken optional harnesses, `run_doctor()` MUST continue returning the 9 canonical check categories so existing CI and unit test contracts (`tests/test_project_upgrade_and_doctor.py`, `tests/test_ci_workflow.py`) remain unbroken.
- **Lifecycle hook fail-open & loop-immunity invariant**: `--lifecycle-hook` execution MUST never exit non-zero, read unbounded `stdin`, crash on Windows `cp1252` `stdout`, or trap an agent in an infinite continuation loop; if `.brain-79/` is missing, `stdin` exceeds `1 MB` or is malformed/non-object JSON, an internal error occurs, or the hook payload indicates an active continuation or non-normal termination (`continuationActive`, `stop_hook_active`, `loop_count >= 1`, Antigravity `terminationReason != "NO_TOOL_CALL"`, Cursor `status != "completed"`), it MUST emit `{}` on `stdout` (ASCII-escaped JSON, flushed) and exit `0`.

## Open questions

All open questions have been resolved by the `owner` (`xilax`):

- [x] **Q-1 (Hook execution mechanism)**: **Native CLI handler selected (`brain79 ci-check --lifecycle-hook <session-start|stop> --client <auto|claude|agy|cursor>`)** — lifecycle hook JSON configurations invoke `brain79 ci-check --lifecycle-hook ...` directly rather than external `.sh`/`.ps1` scripts, ensuring 100% cross-platform execution on Windows (`cmd /c`) and Unix (`sh -c`).
- [x] **Q-2 (Opt-in lifecycle hook installation policy)**: **Opt-in selected (`--install-lifecycle-hooks` on `init` / `update-project`, or `--harnesses hooks` / `claude_hooks,agy_hooks,cursor_hooks`)** — default `brain79 init` does not write hook files unless requested; once installed on disk, `update-project` and `doctor` automatically detect, synchronize, and diagnose them.
- [x] **Q-3 (Default enforcement tier evaluation)**: **Dual-tier decoupled default selected** — `.brain-79/SCHEMA.md` and `brain79 init` retain `enforcement: strict` as the global schema default (preserving single-developer safety and Phase 12 backward compatibility), while `brain79 ci-check` defaults its effective enforcement tier to `strict` (`--enforcement strict`, configurable via `--enforcement <strict|balanced|advisory|schema>`). Teams desiring low-friction local iteration initialize or configure `enforcement: balanced` in `SCHEMA.md` while running `brain79 ci-check` (which enforces `strict` by default) in their CI PR gate.

## Requirements (EARS)

To allow a developer agent to implement and verify Phase 14 with zero friction, requirements are organized into five sequential stages. Complete and test each stage in order (`Stage 1` → `Stage 2` → `Stage 3` → `Stage 4` → `Stage 5`).

### Stage 1 — Git diff range resolution and core CI gate engine (`src/brain79/core/git_ops.py`, `src/brain79/core/ci_check.py`)

- **R-1.1**: THE `src/brain79/core/git_ops.py` module SHALL:
  1. Provide `git_diff_range_names(cwd: Path, base_ref: str, head_ref: str = "HEAD", *, timeout: float = 5.0) -> list[str]` which validates both `base_ref` and `head_ref` via `_validate_git_ref_arg()` plus strict range-arg checks (raising `ValueError` if empty/whitespace-only, starting with `-`, containing leading/trailing whitespace, control characters `\x00`/`\r`/`\n`, or embedded `..` range operators), executes `git -c core.quotepath=false diff --name-only -z <base_ref>...<head_ref> --` via `run_git_bytes`, falls back to two-dot `<base_ref>..<head_ref>` ONLY when the three-dot invocation fails for merge-base/shallow-history reasons (propagating `NotAGitRepoError` and `GitTimeoutError` immediately without fallback), and returns a deduplicated list of normalized POSIX relative paths (`normalize_posix_input(p).lstrip("/")`), raising `GitError` if both three-dot and two-dot diff invocations fail.
  2. Harden `git_ls_files()` to raise `GitError` when `git ls-files` exits non-zero (matching `git_dirty_paths()` and `git_rev_parse_head()`), ensuring `WorkspaceIndex.build()` cleanly falls back to filesystem scanning in containerized or dubious-ownership CI runners instead of returning `[]` and triggering false-positive `deleted` drift.
- **R-1.2**: THE `src/brain79/core/ci_check.py` module SHALL define typed dataclass `CiCheckReport` (with `to_dict()` exposing canonical keys `status`, `exit_code`, `enforcement`, `diff_range`, `changed_files`, `drifted_articles`, `impacted_articles`, `relevant_adrs`, `lint_status`, `lint_errors_count`, `lint_warnings_count`, `issues`, and `markdown_summary`) and `run_ci_check(project_root: Path | None = None, wiki_root: Path | None = None, *, base_ref: str | None = None, head_ref: str = "HEAD", enforcement: Literal["strict", "balanced", "advisory", "schema"] = "strict", fail_on_warnings: bool = False, summary_file: Path | None = None, write_step_summary: bool = False) -> CiCheckReport` executing strictly read-only evaluation (`persist=False` on cache hydration) inside `with project_context(p_root, w_root):` using a single shared `WorkspaceIndex`.
- **R-1.3**: WHEN `run_ci_check()` resolves changed workspace paths and `diff_range`, THE engine SHALL:
  1. Use `git_diff_range_names(p_root, base_ref, head_ref)` when `base_ref` is explicitly provided (`diff_range = f"{base_ref}...{head_ref}"`), propagating `ValueError`, `NotAGitRepoError`, `GitTimeoutError`, and `GitError` to the caller.
  2. When `base_ref` is `None`, validate `head_ref` if non-default, inspect `git_dirty_paths(p_root, exclude_prefix=None)` (`diff_range = "working_tree"` when non-empty); if the working tree is clean and `GITHUB_BASE_REF` is non-empty in `os.environ`, defensively validate `env_base` and attempt `git_diff_range_names(p_root, f"origin/{env_base}", head_ref)` (falling back to `env_base`, and then gracefully to `changed_files = []` with `diff_range = "shallow_fallback"` if invalid or not fetched locally).
  3. Degrade gracefully to `changed_files = []` (`diff_range = "non_git"` or `"working_tree"`) when executed in a non-Git workspace (`NotAGitRepoError`) or when `git_dirty_paths()` fails outside an explicit `--base` invocation.
- **R-1.4**: WHEN `run_ci_check()` evaluates governance impact for `changed_files`, THE engine SHALL:
  1. Resolve the wiki relative prefix (`wiki_rel = rel_posix(w_root, p_root)`, fallback `".brain-79"`) and partition `changed_files` into modified workspace files (outside `f"{wiki_rel}/"`) and modified wiki articles (`.md` files inside `f"{wiki_rel}/"`, excluding `_raw/`, `.locks/`, `handoffs/`, `INDEX.md`, `SCHEMA.md`, and dotfiles such as `.gitignore`, `.gitattributes`, `.drift_manifest.json`, `.navigation_registry.json`, `.bootstrap_state.json`).
  2. Identify `impacted_articles`: active wiki articles (excluding `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES`) whose `applies_to` patterns match at least one non-ephemeral changed file via `match_applies_to_pattern()` (excluding self-matches so deleted files in PR diffs still surface their governing articles), sorted deterministically by `path` and annotated with `{"path": rel_path, "matched_files": [...], "updated_in_diff": bool}`.
  3. Identify `relevant_adrs`: active (`status` in `{"accepted", "stable", ""}` and not in `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES`) decision articles in `decisions/` strictly contained inside `w_root` (`candidate_path.is_relative_to(w_root)`) that either directly match changed files via `applies_to` or are linked (`related` / `outgoing_links`) from `impacted_articles` (1-hop Signal 3 expansion), deduplicated, sorted deterministically by `path`, and annotated with `{"path": adr_rel_path, "title": title, "summary": summary}`.
  4. Identify `drifted_articles` across the wiki via `detect_all_drift(wiki_root=w_root, project_root=p_root, workspace_index=ws)`, recording per-article drift items (`{"article_path": rel_path, "drift_kind": kind, "workspace_file": target, "message": msg}`).
  5. Collect complete wiki lint results (`lint_status` in `{"OK", "WARNING", "CRITICAL"}`, `lint_errors_count`, `lint_warnings_count`, and serialized `issues`) covering **both** `lint_wiki` link/structural checks (broken local links, namespace violations, structural errors, orphans, schema warnings) and `lint_organizational` checks so `lint_errors_count`, `lint_warnings_count`, and `issues` are 100% consistent with `lint_status` (a broken local link increments `lint_errors_count` and appears in `issues`).
- **R-1.5**: WHEN `run_ci_check()` computes `status` (`"ok"` | `"warning"` | `"failed"`) and `exit_code` (`0` | `1`), THE engine SHALL resolve the effective enforcement tier (`active_schema.enforcement` when `enforcement == "schema"`, otherwise the explicit `enforcement` argument, defaulting to `"strict"`) and apply the following deterministic matrix:
  1. If `.brain-79/` or `.brain-79/INDEX.md` does not exist: `status = "failed"`, `exit_code = 1`.
  2. If `lint_status == "CRITICAL"`: `status = "failed"`, `exit_code = 1` under all tiers (`strict`, `balanced`, `advisory`).
  3. If `len(drifted_articles) > 0`:
     - Under effective tier `strict` (or when `fail_on_warnings=True`): `status = "failed"`, `exit_code = 1`.
     - Under effective tier `balanced` or `advisory` (with `fail_on_warnings=False`): `status = "warning"`, `exit_code = 0`.
  4. If `lint_status == "WARNING"`:
     - Under effective tier `strict` (or when `fail_on_warnings=True`): `status = "failed"`, `exit_code = 1`.
     - Under effective tier `balanced` or `advisory` (with `fail_on_warnings=False`): `status = "warning"`, `exit_code = 0`.
  5. Otherwise: `status = "ok"`, `exit_code = 0`.
- **R-1.6**: THE `CiCheckReport.format_markdown()` method SHALL render a concise GitHub-flavored Markdown summary prefixed with the idempotent HTML marker `<!-- brain79:ci-check -->` and `# Brain-79 CI governance report` (sanitizing embedded newlines in titles/summaries to preserve Markdown list integrity), containing:
  1. A status badge line (`[Status: PASSED | WARNING | FAILED] [Enforcement: <tier>] [Diff: <diff_range>]`).
  2. **Drifted governing articles**: bullet list of drifted articles and their modified/deleted/added/missing/transitive target files (capped at 30 items with overflow count), or `- None (0 drifted articles).` when clean.
  3. **Impacted governing articles for diff**: bullet list showing each impacted article, matched changed files, and whether it was updated in the diff (`updated in diff` vs. `not updated in diff`, capped at 30 items with overflow count), or `- None.` when no governed files changed.
  4. **Relevant governing ADRs**: bullet list of linked active ADRs (`path` — `title`: `summary`, capped at 30 items with overflow count) for human PR reviewers, or `- None.` when no ADRs apply.
  5. **Wiki lint summary**: status (`OK`, `WARNING`, `CRITICAL`) and top actionable error/warning bullets (capped at 15 items with overflow count).
- **R-1.7**: WHERE `summary_file` is provided or `write_step_summary=True` (with `GITHUB_STEP_SUMMARY` set to a non-empty file path in `os.environ`), THE `run_ci_check()` function SHALL persist the rendered Markdown summary (UTF-8 with LF `\n` line endings) even when `status == "failed"`:
  1. For `summary_file`: atomically overwrite the target file (raising `FileNotFoundError` -> exit code `2` if its parent directory does not exist, or `IsADirectoryError`/`OSError` -> exit code `3` if the target is a directory).
  2. For `write_step_summary=True`: append to `$GITHUB_STEP_SUMMARY` separated by a trailing newline when `GITHUB_STEP_SUMMARY` is non-empty, or no-op silently when unset/empty.

### Stage 2 — Native lifecycle hook runtime handler (`src/brain79/core/ci_check.py`)

- **R-2.1**: THE `src/brain79/core/ci_check.py` module SHALL provide `run_lifecycle_hook(event: Literal["session-start", "stop"], *, client: Literal["auto", "claude", "agy", "cursor"] = "auto", stdin_payload: str | None = None, project_root: Path | None = None) -> dict[str, Any]` which reads JSON input from `stdin_payload` or cross-platform bounded `sys.stdin` (when `not sys.stdin.isatty()`, reading at most `MAX_INPUT_BYTES + 1` bytes where `MAX_INPUT_BYTES = 1_048_576`, never using Unix-only `select.select()` on pipes), rejects oversized or non-object (`not isinstance(payload, dict)`) payloads by failing open to `{}`, and always returns a JSON-serializable dictionary with exit code `0`. The CLI dispatcher SHALL emit the JSON response on `stdout` using `json.dumps(result, ensure_ascii=True)` (preventing `UnicodeEncodeError` on Windows `cp1252` consoles) followed by an explicit `sys.stdout.flush()`.
- **R-2.2**: WHEN `run_lifecycle_hook()` resolves the workspace and client protocol, THE handler SHALL:
  1. Resolve `project_root` from explicit `project_root` override, or from validated non-empty string path candidates extracted from payload workspace fields (`"cwd"`, first string element of `"workspacePaths"`, first string element of `"workspace_roots"`) by walking ancestors to locate `.brain-79/` while respecting `.git` repository boundaries (stopping ancestor traversal after inspecting a directory containing `.git`, matching `config.get_project_root()`), or fall back to `config.get_project_root()`.
  2. When `client == "auto"`, infer `"agy"` if any of `"hookEventName"`, `"workspacePaths"`, `"continuationActive"`, `"terminationReason"`, or `"conversationId"` is present in the payload; infer `"cursor"` if `"workspace_roots"`, `"loop_count"`, or `payload.get("hook_event_name") == "sessionStart"` is present; otherwise default to `"claude"`.
  3. If `.brain-79/INDEX.md` does not exist at the resolved root, or if any unexpected exception occurs, fail open by returning `{}`.
- **R-2.3**: WHEN `run_lifecycle_hook()` executes with `event == "session-start"`, THE handler SHALL extract optional `task_hint` from string payload fields `"lastUserInput"` or `"prompt"` (stripped and truncated to `2,000` characters to bound regex/TF-IDF cost), invoke `orient(task=task_hint, wiki_root=w_root, max_articles=4)` inside `with project_context(p_root, w_root):`, and return:
  - For `client == "agy"`: `{"injectSteps": [{"systemMessage": {"systemMessage": orient_report}}]}`.
  - For `client == "claude"`: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": orient_report}}`.
  - For `client == "cursor"`: `{"additional_context": orient_report}`.
- **R-2.4**: WHEN `run_lifecycle_hook()` executes with `event == "stop"`, THE handler SHALL:
  1. Check loop-immunity and non-normal termination guards in the input payload: return `{}` immediately if:
     - `payload.get("continuationActive") is True` (Antigravity continuation guard),
     - `payload.get("stop_hook_active") is True` (Claude Code continuation guard),
     - Cursor `loop_count` is present and evaluates to `>= 1` (safely coercing integer/numeric values; failing open on non-numeric values),
     - Antigravity `terminationReason` is present, non-empty, and not equal to `"NO_TOOL_CALL"` (e.g., `"USER_CANCELED"`, `"ERROR"`, `"MAX_INVOCATIONS"`, `"MAX_FORCED_INVOCATIONS"`, `"MAX_TOKEN_BUDGET_EXCEEDED"`), or
     - Cursor `status` is present, non-empty, and not equal to `"completed"` (e.g., `"aborted"`, `"error"`).
  2. Load active schema via `load_active_schema(w_root)` inside `with project_context(p_root, w_root):` and return `{}` immediately if `schema.enforcement == "advisory"`.
  3. Run `detect_all_drift(wiki_root=w_root, project_root=p_root)`; if zero drift is detected, return `{}`.
  4. When one or more articles are drifted, construct a concise remediation message (`reason`) listing the drifted article paths and instructing the agent to resolve drift via `brain79_session_commit` (or `verified_articles`), and return:
     - For `client == "agy"`: `{"decision": "continue", "reason": reason}`.
     - For `client == "claude"`: `{"decision": "block", "reason": reason}`.
     - For `client == "cursor"`: `{"followup_message": reason}`.

### Stage 3 — Opt-in lifecycle hook harness adapters (`src/brain79/core/harnesses/`, `init_project.py`, `doctor.py`)

- **R-3.1**: THE `src/brain79/core/harnesses/lifecycle_hooks.py` module SHALL implement three opt-in `HarnessAdapter` classes exported in `src/brain79/core/harnesses/__init__.py` matching each host's native JSON schema:
  1. `ClaudeHooksAdapter` (`name = "claude_hooks"`, file: `.claude/settings.json`): merges grouped matcher entries under `"hooks"` → `"SessionStart"` and `"Stop"`, each containing `{"matcher": "", "hooks": [{"type": "command", "command": "brain79 ci-check --lifecycle-hook <session-start|stop> --client claude", "timeout": 15}]}`. `detect()` returns `True` ONLY when `.claude/settings.json` is a file containing a `brain79` hook entry under `"hooks"` (or unparseable JSON text referencing `brain79`), returning `False` for unrelated Claude Code settings files without `brain79` hooks.
  2. `AntigravityHooksAdapter` (`name = "agy_hooks"`, file: `.agents/plugins/brain79/hooks.json`): merges top-level named hook `"brain79-lifecycle"` with `"enabled": true` (preserving user `"enabled": false` if already set on disk) and **flat** handler arrays for `"SessionStart"` and `"Stop"`, each containing `{"type": "command", "command": "brain79 ci-check --lifecycle-hook <session-start|stop> --client agy", "timeout": 15}`. `detect()` returns `True` whenever `.agents/plugins/brain79/hooks.json` is a file (owned by the `brain79` plugin directory); `diagnose()` permits `"enabled": false` without error or warning.
  3. `CursorHooksAdapter` (`name = "cursor_hooks"`, file: `.cursor/hooks.json`): merges `"version": 1` and **flat** handler arrays under `"hooks"` → `"sessionStart"` and `"stop"`, each containing `{"command": "brain79 ci-check --lifecycle-hook <session-start|stop> --client cursor", "timeout": 15}`. `detect()` returns `True` ONLY when `.cursor/hooks.json` is a file containing a `brain79` hook entry under `"hooks"` (or unparseable JSON text referencing `brain79`), returning `False` for unrelated third-party Cursor hooks files.
- **R-3.2**: WHEN any lifecycle hook adapter executes `sync(project_root, dry_run=False)`, THE adapter SHALL:
  1. Guard against directory collisions (skip safely without crashing if the target path is a directory).
  2. Merge or update its `brain79` hook entries idempotently and non-destructively into existing JSON files (preserving all unrelated settings, third-party hooks, matcher groups, and custom keys, and deduplicating existing `brain79` entries rather than appending duplicates).
  3. When existing JSON is malformed or non-object and `dry_run=False`, back up the corrupt file using `Path.replace()` (or `atomic_replace_with_retry`) to `<filename>.bak` (preventing `FileExistsError` on repeated corruption on Windows) before writing clean LF-terminated UTF-8 JSON.
  4. Perform zero filesystem mutations (no `.bak` writes, no `mkdir`) when `dry_run=True`.
- **R-3.3**: THE harness registry (`src/brain79/core/harnesses/__init__.py`) SHALL keep `get_harness_adapters()` returning the 7 default Tier 1 adapters, store the 3 opt-in lifecycle hook adapters in `_LIFECYCLE_HOOK_ADAPTERS` exposed via `get_lifecycle_hook_adapters() -> tuple[HarnessAdapter, ...]`, register `"hooks": ("claude_hooks", "agy_hooks", "cursor_hooks")`, `"claude_hooks": ("claude_hooks",)`, `"agy_hooks": ("agy_hooks",)`, and `"cursor_hooks": ("cursor_hooks",)` in `_HARNESS_ALIASES`, and update `resolve_harness_selection()` to look up targets across both `_HARNESS_ADAPTERS` and `_LIFECYCLE_HOOK_ADAPTERS` (keeping `None` and `"all"` resolving to the 7 default Tier 1 adapters while expanding `"all"` in comma-separated lists such as `"all,hooks"` without dropping subsequent tokens).
- **R-3.4**: THE `init_project()` and `update_project()` functions in `src/brain79/core/init_project.py` (and `brain79 init` / `brain79 update-project` in `src/brain79/cli/dispatch.py`) SHALL accept `install_lifecycle_hooks: bool = False` (CLI flag `--install-lifecycle-hooks` / `--lifecycle-hooks`):
  1. When `install_lifecycle_hooks=True`, `init_project()` (including the `upgrade=True` branch) and `update_project()` synchronize all three lifecycle hook adapters (`ClaudeHooksAdapter`, `AntigravityHooksAdapter`, `CursorHooksAdapter`), deduplicating by `adapter.name` if also selected via `--harnesses`, and `update_project()` reports touched paths under `"lifecycle_hooks": list[str]`.
  2. When `install_lifecycle_hooks=False`, `update_project()` synchronizes ONLY lifecycle hook adapters that are **already installed on disk** (`adapter.detect(project_root) is True`), never injecting hooks into unrelated `.claude/settings.json` or `.cursor/hooks.json` files.
- **R-3.5**: WHEN `diagnose_all_harnesses(project_root)` and `run_doctor()` inspect a repository, THE diagnostic engine SHALL check any lifecycle hook adapter where `adapter.detect(project_root) is True` (verifying valid JSON syntax and exact portable `"brain79 ci-check --lifecycle-hook <session-start|stop> --client <claude|agy|cursor>"` commands):
  1. If an installed lifecycle hook file contains corrupt JSON, `run_doctor()` SHALL emit a `harness:<name>` check with `status = "error"` (`exit_code = 1`); if misconfigured or using a non-portable command path, `run_doctor()` SHALL emit `status = "warning"` (`exit_code = 2`).
  2. During `brain79 doctor --fix`, `run_doctor()` SHALL include `.claude/settings.json` and `.cursor/hooks.json` (in addition to `.agents/plugins/brain79` which already covers `hooks.json`) in the dirty working-tree guard, repair installed lifecycle hook files via `update_project()`, and append repaired hook paths to `report.fixed`.
  3. When lifecycle hooks are not installed (`detect() is False`) or are healthy (`diagnose() == []`), `run_doctor()` SHALL add zero extra check items, preserving the 9 canonical check categories.

### Stage 4 — CLI dispatcher (`brain79 ci-check`) and reusable GitHub Action (`action.yml`, `.github/workflows/ci.yml`)

- **R-4.1**: THE CLI dispatcher (`src/brain79/cli/dispatch.py` and `ROOT_HELP` in `src/brain79/__main__.py`) SHALL add `"ci-check"` to `WHITELIST` (25 subcommands total, with `prog="brain79 ci-check"` and a multi-line `--help` description preserving existing `ROOT_HELP` lines tested by `tests/test_cli.py`), honoring global `--project-root` and exposing:
  - `--base <REF>`: optional base Git ref for PR diff comparison.
  - `--head <REF>`: head Git ref for PR diff comparison (default: `"HEAD"`).
  - `--enforcement <strict|balanced|advisory|schema>`: effective enforcement tier (default: `"strict"`).
  - `--fail-on-warnings`: fail with exit code `1` on warnings under any enforcement tier.
  - `--format <markdown|text|json>`: output format on `stdout` (`markdown` and `text` output the Markdown report; `json` outputs `CiCheckReport.to_dict()`).
  - `--summary-file <PATH>`: optional file path to write the Markdown summary.
  - `--write-step-summary`: append the Markdown summary to `$GITHUB_STEP_SUMMARY` when present in environment.
  - `--lifecycle-hook <session-start|stop>`: run the passive lifecycle hook handler instead of the CI report (emitting only a single ASCII-escaped JSON object on `stdout`, flushed, and exiting `0`).
  - `--client <auto|claude|agy|cursor>`: target client protocol for `--lifecycle-hook` (default: `"auto"`).
- **R-4.2**: WHEN `brain79 ci-check` is invoked in CI mode and Git diff resolution fails, THEN `dispatch_cmd("ci-check", ...)` SHALL map exceptions explicitly before `run_cli()`'s fallback mapper:
  - `GitTimeoutError` → write an actionable timeout error to `stderr` and return exit code `3`.
  - `ValueError` (e.g. option-like `--base=-invalid` or `--head=-invalid`), `NotAGitRepoError`, or `GitError` (e.g. unresolvable explicit `--base` ref) → write an actionable error message to `stderr` and return exit code `2`.
- **R-4.3**: THE repository root SHALL provide a composite GitHub Action manifest at `action.yml` (`name: "Brain-79 CI governance and PR gate"`, `runs.using: "composite"`) declaring `shell: bash` on every `run:` step, accepting inputs `python-version` (default `"3.12"`), `base-ref` (default `""`), `head-ref` (default `"HEAD"`), `enforcement` (default `"strict"`), `fail-on-warnings` (default `"false"`), `project-root` (default `"."`), `comment-on-pr` (default `"false"`), and `github-token` (default `${{ github.token }}`), and declaring outputs `status`, `exit-code`, `drifted-count`, and `report-json-path`.
- **R-4.4**: THE `action.yml` composite steps SHALL:
  1. Use pinned major action tags (`astral-sh/setup-uv@v10.4.0`).
  2. Pass every input (`base-ref`, `head-ref`, `enforcement`, `fail-on-warnings`, `project-root`, `comment-on-pr`, `github-token`) and event context (`github.event.pull_request.number`, `github.repository`) exclusively via step `env:` variables referenced as double-quoted shell variables (NEVER directly interpolating `${{ inputs.* }}` inside `run:` scripts, eliminating GitHub Actions script injection).
  3. Execute the pinned action package via `uv run --with "$GITHUB_ACTION_PATH" brain79 --project-root "$INPUT_PROJECT_ROOT" ci-check --write-step-summary --format json` (capturing its exit code via `set +e` / `EXIT_CODE=$?` so failing gates do not abort before outputs and PR commenting run), write the JSON report to `$RUNNER_TEMP/brain79-ci-check.json`, export `status`, `exit-code`, `drifted-count`, and `report-json-path` to `$GITHUB_OUTPUT`, and on `comment-on-pr == 'true'` during `pull_request` events create or update a single idempotent PR comment matched by `<!-- brain79:ci-check -->` via `gh api --paginate` (passing the JSON comment body via `--input -` to avoid `ARG_MAX`/quoting issues and degrading gracefully with a warning on HTTP 403 read-only fork tokens), before finally exiting with `$EXIT_CODE`.
- **R-4.5**: THE repository's own CI workflow (`.github/workflows/ci.yml`) SHALL include a `- name: Run brain79 ci-check` step running `uv run brain79 ci-check --write-step-summary` in `jobs.test.steps` placed **before** `Run brain79 doctor` (so untracked `doctor_report.json` never pollutes working-tree diff detection), while preserving `permissions: contents: read` and all 5 matrix cells enforced by `tests/test_ci_workflow.py`.

### Stage 5 — Symmetry, release `v0.15.0` parity, and living manual distillation

- **R-5.1**: THE symmetry and release documentation test suites (`tests/test_symmetry.py`, `tests/test_phase11_release_docs.py`, `tests/test_version_governance.py`) SHALL be updated to assert `len(WHITELIST) == 25` (`MCP_TOOLS` 9 tools ⊂ `WHITELIST` 25 CLI subcommands) and `"25-command"` CLI references in `README.md`.
- **R-5.2**: THE release metadata (`src/brain79/__init__.py` `__version__ = "0.15.0"`, `README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `.brain-79/changelog/v0-15-0.md`, `src/brain79/templates/AGENTS.md`, `src/brain79/templates/SKILL.md`, and repository harness blocks via `brain79 update-project`) SHALL be synchronized to `0.15.0` (updating `"24-command"` references to `"25-command"` in `templates/AGENTS.md` and `templates/SKILL.md`), keeping `src/brain79/templates/AGENTS.md` `<= 6,500` bytes.
- **R-5.3**: THE architectural decision (`decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md`) and new/updated living manuals (`features/lifecycle-hooks-and-ci-gate.md`, `features/project-upgrade-and-multi-harness-doctor.md`, `features/team-collaboration-and-onboarding.md`, `features/cli.md`, `architecture/dispatcher.md`, `architecture/symmetry.md`, `architecture/current-state.md`, `architecture/roadmap-industrial-scale.md`, `product/overview.md`) SHALL be committed via `brain79_session_commit` with zero documentation drift and zero overlapping `applies_to` violations.

## Interface and error contract

Aligned with [dispatcher.md](../.brain-79/architecture/dispatcher.md) (`0` success, `1` validation/operational failure, `2` invalid argument or `FileNotFoundError`, `3` `PermissionError`/`TimeoutError`/`OSError`, `130` interrupt).

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `brain79 ci-check` (default `strict`) | Clean wiki, zero drift, zero lint warnings/errors | Print Markdown report (or JSON when `--format json`) to `stdout`; optionally write step summary | Exit `0` |
| `brain79 ci-check` (effective tier `strict` or `--fail-on-warnings`) | Unresolved article drift or `WARNING`/`CRITICAL` lint issues | Print full report with drifted articles, relevant ADRs, and lint violations to `stdout`; still persist `--summary-file` / `$GITHUB_STEP_SUMMARY` | Exit `1` |
| `brain79 ci-check --enforcement balanced` (or `schema` when `SCHEMA.md` is `balanced`/`advisory`) | Drift or `WARNING` lint issues present, but `0` `CRITICAL` lint errors | Report status `WARNING` in output; do not fail CI gate unless `--fail-on-warnings` is passed | Exit `0` |
| `brain79 ci-check` | Missing `.brain-79/` or `.brain-79/INDEX.md` | Report status `FAILED` with actionable `brain79 init` message | Exit `1` |
| `brain79 ci-check --base=-invalid` or `--base nonexistent-ref` | Git ref starts with `-` / contains `..` or control chars (`ValueError`), cannot be resolved by Git (`GitError`), or not a Git repo (`NotAGitRepoError`) | Emit actionable error to `stderr`; make zero disk mutations | Exit `2` |
| `brain79 ci-check --base main` | Git subprocess times out (`GitTimeoutError`) | Emit actionable timeout error to `stderr`; make zero disk mutations | Exit `3` |
| `brain79 ci-check --summary-file <missing_dir>/out.md` | Parent directory of `--summary-file` does not exist (`FileNotFoundError`) | Emit actionable error to `stderr` | Exit `2` |
| `brain79 ci-check --lifecycle-hook session-start --client <claude\|agy\|cursor\|auto>` | Valid workspace with `.brain-79/` | Emit ASCII-escaped client-specific JSON payload containing `orient()` context on `stdout` and flush | Exit `0` |
| `brain79 ci-check --lifecycle-hook stop --client <claude\|agy\|cursor\|auto>` | Active drift detected, `enforcement != "advisory"`, and no active loop or non-normal termination guard (`continuationActive`/`stop_hook_active`/`loop_count`/`terminationReason`/`status`) | Emit ASCII-escaped client-specific continuation/block JSON with drifted article list on `stdout` and flush | Exit `0` |
| `brain79 ci-check --lifecycle-hook <session-start\|stop>` | Missing `.brain-79/`, `stdin > 1 MB`, malformed/non-object `stdin` JSON, active continuation/abort guard, or unexpected internal error | Fail open: emit `{}` on `stdout` and flush so the host IDE/CLI session never hangs or crashes | Exit `0` |
| `brain79 init --install-lifecycle-hooks` / `brain79 update-project --install-lifecycle-hooks` | Existing `.claude/settings.json`, `.agents/plugins/brain79/hooks.json`, or `.cursor/hooks.json` contains malformed JSON | Back up corrupt file via `.replace()` to `<file>.bak` (unless `dry_run=True`) and write valid merged LF JSON configuration | Exit `0` |

## Migration and rollout

- **Default behavior**:
  - Existing repositories upgrading to `v0.15.0` experience zero breaking changes: `SCHEMA.md` default enforcement remains `strict`, `MCP_TOOLS` remains the 9-tool focused surface, and `brain79 init` without `--install-lifecycle-hooks` creates the exact same files as `v0.14.0`.
  - Pre-existing `.claude/settings.json` or `.cursor/hooks.json` files that do not contain `brain79` hooks remain untouched by `brain79 update-project` and `brain79 doctor` unless the user explicitly opts in.
  - `brain79 ci-check` works out of the box on any existing `.brain-79/` repository, even when `.drift_manifest.json` and `.navigation_registry.json` are git-ignored (hydrating in memory via Phase 12's zero-masking rebuild).
- **Opt-in lifecycle hooks rollout**:
  - Users and teams opt into passive lifecycle hooks on new projects via `brain79 init --install-lifecycle-hooks` (or `--harnesses hooks` / `--harnesses all,hooks`) and on existing projects via `brain79 update-project --install-lifecycle-hooks`.
  - Once installed, subsequent `brain79 update-project` and `brain79 doctor [--fix]` runs automatically maintain and validate the installed hook files.
- **Recommended team CI rollout**:
  - Teams seeking low local friction with strict mainline protection set `enforcement: balanced` in `.brain-79/SCHEMA.md` and add `brain79 ci-check` (or `uses: xilax79/brain-79@v0.15.0`) to their GitHub Actions Pull Request workflow.
  - Note on shallow checkouts: `actions/checkout` defaults to `fetch-depth: 1`, which omits `origin/<base-ref>` locally (`ci-check` still checks full wiki drift and lint, degrading diff impact to `shallow_fallback`); workflows wanting full PR diff impact and 1-hop ADR surfacing should pass `fetch-depth: 0` (or fetch the base branch).
- **Rollback safety**:
  - Reverting to `v0.14.0` leaves `.brain-79/` 100% compatible; optional hook files (`.claude/settings.json`, `.agents/plugins/brain79/hooks.json`, `.cursor/hooks.json`) and `action.yml` do not alter `.brain-79/` schema or article format.

## Acceptance criteria (Given / When / Then)

### AC-1 — Git diff range resolution, option-injection defense, and `git_ls_files` resilience
- **Verifies**: `R-1.1`, `R-4.2`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_git_diff_range_names_and_option_injection_guard`
- **Given**: a temporary Git repository with a `main` branch and a feature branch modifying `src/app.py` and `.brain-79/features/app.md`.
- **When**: calling `git_diff_range_names(repo, "main", "HEAD")`, calling with option/range-injection refs `"-o"` and `"main..HEAD"`, simulating a `GitTimeoutError`, simulating a non-zero `git ls-files` failure, and invoking `dispatch_cmd("ci-check", ["--base=-o"])` and `dispatch_cmd("ci-check", ["--base", "nonexistent_branch_ref"])`.
- **Then**: `git_diff_range_names` returns `["src/app.py", ".brain-79/features/app.md"]` (falling back to two-dot `main..HEAD` when three-dot merge-base fails); `"-o"` and `"main..HEAD"` raise `ValueError`; `dispatch_cmd("ci-check", ["--base=-o"])` and `--base nonexistent_branch_ref` write actionable errors to `stderr` and return exit code `2`; `GitTimeoutError` returns exit code `3`; and `git_ls_files` raises `GitError` on non-zero returncode so `WorkspaceIndex.build()` falls back to filesystem scanning without false `deleted` drift.

### AC-2 — `run_ci_check` diff impact, 1-hop ADR surfacing, full lint parity, and drift detection on fresh CI checkout
- **Verifies**: `R-1.2`, `R-1.3`, `R-1.4`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_run_ci_check_diff_impact_adrs_and_fresh_checkout_drift`
- **Given**: a Git repository where `features/auth.md` (`applies_to: ["src/auth.py"]`, `related: ["decisions/adr-001-auth.md"]`) governs `src/auth.py`, `.drift_manifest.json` and `.navigation_registry.json` are deleted (simulating a fresh CI checkout), and a branch modifies `src/auth.py` without updating `features/auth.md`.
- **When**: calling `run_ci_check(project_root=repo, base_ref="main", head_ref="HEAD")` (and again after adding a broken local Markdown link inside `features/auth.md`).
- **Then**: `report.changed_files` includes `"src/auth.py"`, `report.impacted_articles` lists `features/auth.md` with `updated_in_diff=False`, `report.relevant_adrs` includes `decisions/adr-001-auth.md`, `report.drifted_articles` flags `features/auth.md`, neither `.drift_manifest.json` nor `.navigation_registry.json` is written to disk (`persist=False`), and introducing a broken local link yields `lint_status == "CRITICAL"` with `lint_errors_count >= 1` and a matching entry in `report.issues`.

### AC-3 — Dual-tier enforcement matrix in `ci-check` (`strict`, `balanced`, `advisory`, `schema`, `--fail-on-warnings`)
- **Verifies**: `R-1.5`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_ci_check_enforcement_tier_matrix`
- **Given**: a repository whose `.brain-79/SCHEMA.md` declares `enforcement: balanced` and which currently has an unresolved drifted article (`features/auth.md`) but `0` `CRITICAL` lint errors.
- **When**: running `brain79 ci-check` with default flags (`--enforcement strict`), with `--enforcement schema`, with `--enforcement schema --fail-on-warnings`, and after introducing a broken local link (`CRITICAL` lint error) under `--enforcement advisory`.
- **Then**: default `brain79 ci-check` enforces `strict` and exits `1` (`status == "failed"`); `--enforcement schema` honors `SCHEMA.md` (`balanced`) and exits `0` (`status == "warning"`); `--enforcement schema --fail-on-warnings` exits `1`; and a `CRITICAL` lint error exits `1` even under `advisory`.

### AC-4 — Markdown report marker, JSON serialization, and `$GITHUB_STEP_SUMMARY` output
- **Verifies**: `R-1.6`, `R-1.7`, `R-4.1`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_ci_check_formats_and_step_summary_output`, `tests/test_phase14_ci_check_and_hooks.py::test_cli_ci_check_git_errors_enforcement_and_formats`
- **Given**: a repository with governed articles and a mocked `GITHUB_STEP_SUMMARY` file path in `os.environ`.
- **When**: running `dispatch_cmd("ci-check", ["--write-step-summary", "--format", "json"])` and `dispatch_cmd("ci-check", ["--summary-file", str(tmp_path / "nonexistent_dir" / "summary.md")])`.
- **Then**: `stdout` parses as valid JSON containing `status`, `exit_code`, `enforcement`, `diff_range`, `changed_files`, `drifted_articles`, `impacted_articles`, `relevant_adrs`, `lint_status`, `lint_errors_count`, `lint_warnings_count`, `issues`, and `markdown_summary`; the `$GITHUB_STEP_SUMMARY` file contains `<!-- brain79:ci-check -->` and `# Brain-79 CI governance report` with LF endings; and the invalid `--summary-file` path exits with code `2`.

### AC-5 — Lifecycle hook `session-start` contract across Claude Code, Antigravity, and Cursor
- **Verifies**: `R-2.1`, `R-2.2`, `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_lifecycle_hook_session_start_all_clients`
- **Given**: an initialized repository with a governing article and subdirectory `.agents/plugins/brain79/`.
- **When**: invoking `run_lifecycle_hook("session-start", client=...)` (and CLI `brain79 ci-check --lifecycle-hook session-start`) for `"agy"` (from working directory `.agents/plugins/brain79/` with stdin `{"hookEventName": "SessionStart", "cwd": "<repo>", "lastUserInput": "update auth"}`), `"claude"`, and `"cursor"`, plus oversized (`> 1 MB`) and non-object (`"[]"`) stdin payloads.
- **Then**:
  - `"agy"` returns `{"injectSteps": [{"systemMessage": {"systemMessage": ...}}]}` containing the `Brain-79 — Session Cold Start Orientation` report.
  - `"claude"` returns `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}`.
  - `"cursor"` returns `{"additional_context": ...}`.
  - CLI stdout is valid ASCII-safe JSON (compatible with Windows `cp1252`), oversized/non-object payloads fail open to `{}`, and all invocations exit with code `0`.

### AC-6 — Lifecycle hook `stop` drift interception, loop-prevention guards, and fail-open safety
- **Verifies**: `R-2.2`, `R-2.4`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_lifecycle_hook_stop_drift_and_loop_guards`
- **Given**: a repository with a modified governed source file (`src/auth.py`) leaving `features/auth.md` drifted.
- **When**:
  1. Invoking `run_lifecycle_hook("stop")` with clean initial payloads for `"agy"`, `"claude"`, and `"cursor"` (including `{"status": "completed", "loop_count": 0}` for Cursor).
  2. Invoking `run_lifecycle_hook("stop")` with active continuation or non-normal termination flags (`{"continuationActive": True}` and `{"terminationReason": "USER_CANCELED"}` for `"agy"`, `{"stop_hook_active": True}` for `"claude"`, `{"loop_count": 1}` and `{"status": "aborted", "loop_count": 0}` for `"cursor"`).
  3. Invoking `run_lifecycle_hook("stop")` when `SCHEMA.md` has `enforcement: advisory`, when `.brain-79/` is absent (including inside a child `.git` repo whose parent has `.brain-79/`), or when `stdin` contains malformed JSON `"{bad"`.
- **Then**:
  1. Initial stop calls return `{"decision": "continue", "reason": ...}` (`agy`), `{"decision": "block", "reason": ...}` (`claude`), and `{"followup_message": ...}` (`cursor`) naming `features/auth.md`.
  2. All continuation-active, non-normal termination/aborted, `advisory`, missing-wiki (respecting `.git` boundaries), and malformed-stdin calls return `{}` and exit with code `0`.

### AC-7 — Opt-in lifecycle hook adapters, non-destructive JSON merging, and `doctor` diagnostics
- **Verifies**: `R-3.1`, `R-3.2`, `R-3.3`, `R-3.4`, `R-3.5`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_lifecycle_hook_adapters_sync_and_doctor`
- **Given**: a project directory with pre-existing unrelated custom keys in `.claude/settings.json` (`{"permissions": {"allow": ["Bash"]}}`) and `.cursor/hooks.json` (`{"version": 1, "hooks": {"stop": [{"command": "echo custom"}]}}`).
- **When**:
  1. Running default `init_project(tmp_path)` and `update_project(tmp_path)` without `install_lifecycle_hooks`, then running `run_doctor(tmp_path)`.
  2. Running `update_project(tmp_path, install_lifecycle_hooks=True)` (and testing `init_project(..., harnesses=["all", "hooks"])` and `dry_run=True` on corrupt JSON).
  3. Corrupting `.claude/settings.json` command string (warning) and corrupting `.agents/plugins/brain79/hooks.json` JSON syntax (error), running `run_doctor(tmp_path)`, and then running `run_doctor(tmp_path, fix=True, force=True)`.
- **Then**:
  1. Default `init_project` and `update_project` do NOT inject hooks into pre-existing unrelated `.claude/settings.json` or `.cursor/hooks.json`, do NOT create `.agents/plugins/brain79/hooks.json`, and `run_doctor` returns the exact 9 canonical checks with status `ok`.
  2. `install_lifecycle_hooks=True` merges all 3 hook files using each host's exact schema (grouped matcher for Claude, flat handlers under `"brain79-lifecycle"` for Antigravity, flat handlers under `"hooks"` for Cursor) while preserving `"permissions"` and `"echo custom"`, `dry_run=True` makes zero disk mutations, and `run_doctor` still returns 9 checks when healthy (including when Antigravity `"enabled": false`).
  3. Non-portable command emits `harness:claude_hooks` warning (`exit_code == 2`), corrupt JSON emits `harness:agy_hooks` error (`exit_code == 1`), and `run_doctor(..., fix=True, force=True)` repairs both back to `exit_code == 0` while recording repairs in `report.fixed`.

### AC-8 — Composite GitHub Action (`action.yml`) and repository CI workflow integration
- **Verifies**: `R-4.3`, `R-4.4`, `R-4.5`
- **Method**: `test`
- **Test ref**: `tests/test_phase14_ci_check_and_hooks.py::test_github_action_manifest_and_ci_workflow`
- **Given**: `action.yml` at the repository root and `.github/workflows/ci.yml`.
- **When**: parsing both YAML manifests and running `tests/test_ci_workflow.py`.
- **Then**: `action.yml` is a valid `using: "composite"` action with `shell: bash` on every `run:` step, declares `base-ref`, `head-ref`, `enforcement`, `fail-on-warnings`, `project-root`, `comment-on-pr`, and `github-token` inputs, uses pinned action tags (`@v10.4.0`), passes all inputs exclusively via step `env:` variables (zero `${{ inputs.* }}` inside `run:` bodies), invokes `brain79` from `"$GITHUB_ACTION_PATH"`, captures exit code before exporting `$GITHUB_OUTPUT` and upserting the idempotent `<!-- brain79:ci-check -->` PR comment, and `.github/workflows/ci.yml` places `uv run brain79 ci-check --write-step-summary` before `Run brain79 doctor` while passing all `tests/test_ci_workflow.py` assertions.

### AC-9 — 25-command CLI superset symmetry, release `v0.15.0` parity, and zero wiki drift
- **Verifies**: `R-5.1`, `R-5.2`, `R-5.3`
- **Method**: `ci`
- **Test ref**: `tests/test_symmetry.py::test_mcp_cli_symmetry`, `tests/test_version_governance.py::test_changelog_entry_parity`
- **Given**: version bumped to `0.15.0`, `WHITELIST` containing 25 CLI subcommands, `ADR-021` and `features/lifecycle-hooks-and-ci-gate.md` created, and all impacted living manuals updated via `brain79_session_commit`.
- **When**: running `uv run pytest`, `uv run mypy src tests`, `uv run brain79 lint --strict`, `uv run brain79 ci-check`, and `uv run brain79 doctor`.
- **Then**: all verification commands exit `0` with `[Status: OK]` / `[Status: PASSED]`, `templates/AGENTS.md` is `<= 6,500` bytes (with `"25-command"` parity), and zero documentation drift exists across `.brain-79/`.

## Wiki impact map

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/core/ci_check.py`, `action.yml` | `decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md` | `create` |
| `src/brain79/core/ci_check.py`, `action.yml` | `features/lifecycle-hooks-and-ci-gate.md` | `create` |
| `src/brain79/core/harnesses/**`, `src/brain79/core/init_project.py`, `src/brain79/core/doctor.py` | `features/project-upgrade-and-multi-harness-doctor.md` | `update` |
| `src/brain79/core/git_ops.py` | `features/team-collaboration-and-onboarding.md` | `update` |
| `src/brain79/cli/dispatch.py`, `src/brain79/__main__.py` | `features/cli.md` | `update` |
| `src/brain79/cli/dispatch.py`, `src/brain79/__main__.py` | `architecture/dispatcher.md` | `update` |
| `src/brain79/cli/dispatch.py`, `tests/test_symmetry.py` | `architecture/symmetry.md` | `update` |
| `src/brain79/__init__.py`, `README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md` | `architecture/current-state.md` | `update` |
| `.brain-79/features/*.md` | `architecture/roadmap-industrial-scale.md` | `update` |
| `.brain-79/features/*.md`, `src/brain79/__init__.py` | `product/overview.md` | `update` |
| `CHANGELOG.md`, `src/brain79/__init__.py` | `changelog/v0-15-0.md` | `create` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
uv run pytest
uv run mypy src tests
uv run brain79 lint --strict
uv run brain79 ci-check
uv run brain79 doctor
```

Note: `uv run pytest` includes `tests/test_specs_governance.py`, which mechanically verifies spec frontmatter, naming, `R-X.Y` ↔ `AC` traceability, `related_wiki`/`target_wiki`, and `implemented` closure criteria.

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| 2026-11-24 | spec-auditor | Pre-implementation adversarial audit hardening: blocked GitHub Actions script injection and pinned `$GITHUB_ACTION_PATH` execution + deferred exit code in `action.yml`; fixed `ValueError`/`GitTimeoutError` exit-code mapping (`2` vs `3`); tightened Git ref validation, `-z` diff parsing, and `git_ls_files()` error propagation; unified structural+organizational lint counting; added 1 MB `stdin` cap, Windows `ensure_ascii=True` JSON output, `.git` walk boundary, and Cursor `status != "completed"` guard; specified exact host hook JSON schemas (Claude grouped, Antigravity/Cursor flat) and non-intrusive `detect()`; ordered `ci-check` before `doctor_report.json` in `ci.yml`. | `R-1.1`–`R-1.7`, `R-2.1`–`R-2.4`, `R-3.1`–`R-3.5`, `R-4.1`–`R-4.5`, `R-5.2`, `AC-1`–`AC-9` |

## Wiki distillation checklist (post-implementation)

Every item MUST be checked (`[x]`) before setting `status: implemented` and moving this file to `specs/archive/`:

- [x] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [x] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [x] Record `decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md`.
- [x] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-15-0.md`.
- [x] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [x] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
