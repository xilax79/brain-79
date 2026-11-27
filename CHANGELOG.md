# Changelog

All notable changes to `brain-79` will be documented in this file.

> **Pre-GA versioning policy (ADR-017)**: `brain-79` follows SemVer 2.0.0 §4 pre-GA (`0.y.z`) versioning while maturing toward `1.0.0` General Availability. Minor bumps (`0.y.0`) may introduce controlled protocol or default changes documented with explicit migration notes below.

## [Unreleased]

## [0.18.0] - 2026-11-27

### Added
- **External drift lockfile and hash-free Markdown frontmatter (Phase 17, SPEC-017, ADR-023)**:
  - **Deterministic `.brain-79/drift.lock` (`core/drift.py`, `core/locks.py`)**: relocated machine-managed `applies_to_digest`, `applies_to_count`, and per-file leaf `targets` from `.md` frontmatter and `.drift_manifest.json` into a single Git-tracked, LF-formatted, `sort_keys=True` JSON lockfile (`version: "2.0"`), guarded by `_drift_lock.lock` in `LOCK_HIERARCHY` and preserved by `cleanup_legacy_inline_locks()`.
  - **3-way Git merge driver (`core/drift_merge.py`, `brain79 merge-drift-lock`)**: expanded `WHITELIST` from 26 to 27 CLI subcommands (retaining `MCP_TOOLS == 9`), resolving disjoint, identical, and 0-byte-`<base>` `add/add` merges cleanly (`Exit 0`), reverting same-key modify/modify and delete/modify conflicts to `base[k]` (pruning only when explicit `--wiki-root` confirms `.md` absence), and emitting fail-closed `"conflict": true` sentinels on conflicting `add/add` keys (`Exit 0`).
  - **Zero-diff `verified_articles` & Guard C baseline integrity (`core/session_commit.py`, `core/ast_guards/`)**: `verified_articles` updates only `.brain-79/drift.lock` without dirtying `.md` files (blocking `"conflict": true` entries with `verified_article_conflict_forbidden`); shared `resolve_article_baseline_commit()` uses two-pass bounded first-parent history (`%P` parent resolution, migration-commit skipping, and article-only Pass 2 fallback).
  - **Dual-read compatibility, `doctor`, and zero-masking migration (`core/migration.py`, `core/doctor.py`, `core/init_project.py`, `core/lint_organizational.py`)**: `check_article_drift()` resolves `drift.lock` -> legacy frontmatter + read-only `.drift_manifest.json` -> `last_updated` with zero disk writes on read-only paths; `init`/`update-project`/`doctor --fix` order `!drift.lock` after `*.lock` in `.brain-79/.gitignore`, register `brain79-drift-lock` in `.gitattributes`/`.git/config`, update `.git/hooks/pre-commit`, and migrate legacy digests idempotently without masking drift; `lint` emits `INFO` `legacy_frontmatter_digest` when unmigrated articles coexist with `drift.lock`.
  - **CI matrix reliability & Windows SLA-1 recovery (`.github/workflows/ci.yml`, `core/orient.py`)**: gated `.mjs` Guard C fixture checks on optional `polyglot` availability, enabled `include-hidden-files: true` + `if-no-files-found: ignore` for `.pytest_tmp` failure uploads, and eliminated `rebuild_drift_manifest()` calls during `orient()` when `drift.lock` covers active articles.

### Changed
- **27-command CLI superset**: expanded `WHITELIST` in `cli/dispatch.py` from 26 to 27 subcommands (`merge-drift-lock` is CLI-only; `MCP_TOOLS` remains fixed at 9 tools per ADR-020).

### Migration notes
- Run `brain79 update-project` (or `brain79 migrate --apply`) in existing repositories to extract legacy `applies_to_digest`/`applies_to_count` frontmatter keys into `.brain-79/drift.lock`, strip frontmatter digests, update `.brain-79/.gitignore` with `!drift.lock`, configure the `brain79-drift-lock` Git merge driver, and update `.git/hooks/pre-commit`.

## [0.17.0] - 2026-11-27

### Added
- **Longitudinal anti-rot benchmark harness and release gate (Phase 16, SPEC-016)**:
  - Added the `LedgerPulse` polyglot testbed (`benchmarks/anti_rot/fixture/`, 13 non-test Python and `.mjs` source files with hidden `S2`–`S12` contracts), realistic `AGENTS.md` + `docs/` control baseline (`control_agents.md`), dual-arm workspace initializer with fail-closed `agy` isolation probes (`workspace.py`), 12-session cold-start `runner.py`, deterministic rot/coverage/triage evaluator (`evaluator.py`), mechanically enforced blind semantic-recall probe (`recall.py`, `deny_src_reads.py`), binary release gate (`gate.py`), and `scripts/run_anti_rot_benchmark.py` (`--mode dry-run|live|evaluate`).
  - Live `AC-6` release gate verified `PASS` (7/7 criteria, exit `0`) on `gemini-4-hydrogen-low`: `0.0%` rot (`0/118` vs `1.12%` Arm B), `100.0%` canonical `src/**` coverage (`14/14` vs `50.0%` Arm B), `5.9x` fewer doc-read tokens (`2,479` vs `14,649`), `12/12` compliance, and `100.0%` (`24/24`) blind semantic recall.
- **Agent ergonomics, strict bootstrap governance, and batch-read parity (SPEC-202611)**:
  - Profile-aware `auto_map: bool | None = None` across `run_bootstrap()`, `brain79_bootstrap()`, and CLI `brain79 bootstrap` (`--auto-map` / `--no-auto-map`), defaulting to `True` on `software` wikis with disjoint `overview.md`/`stack.md`/module partitioning examples.
  - Ergonomic `brain79_read_batch(paths=[...])` and string-element `requests` normalization across MCP (`server.py`, flat non-`anyOf` wire schema) and CLI (`brain79 read-batch --paths ...`, `--file`, `--stdin`), preserving `MCP_TOOLS == 9` and `WHITELIST == 26`.
  - Strict-mode `unanchored_governance_article` pre-flight parity across `commit_session()`, `write_article()`/`brain79_edit`, `write_many_articles()`, and `check_file_health()`.
  - Clean `orient()`/`context.py` ranking excluding `INDEX.md`/`SCHEMA.md` before `top_n`, prioritizing active articles over `INACTIVE_STATUSES`, and emitting bounded (`<= 20`) `brain79_read_batch(paths=[...])` reminders.

### Migration notes
- Run `brain79 update-project` in existing repositories to synchronize `AGENTS.md`, `SCHEMA.md`, and `SKILL.md` to `v0.17.0`.

## [0.16.0] - 2026-11-24

### Added
- **Polyglot AST Guard C and context budget telemetry (Phase 15, SPEC-015, ADR-022)**:
  - **Language-agnostic AST guard orchestrator (`core/ast_guards/orchestrator.py`)**: extracted generalized `has_public_api_changes()` with 2 MB asymmetric size guard (`MAX_AST_SOURCE_BYTES`), symlink escape checks, `GitSessionCache` integration, and thread-safe lazy inspector discovery (`find_spec`-based metadata discovery + `threading.Lock`-guarded `Language()` initialization).
  - **Optional `brain79[polyglot]` Tree-sitter engine (`core/ast_guards/treesitter_inspector.py`, `polyglot.py`)**: added opt-in `TreeSitterInspector` and collision-free qualified signature extractors for 10 language parsers (`typescript`, `tsx`, `javascript`, `go`, `rust`, `java`, `c_sharp`, `php`, `ruby`, `bash`) alongside built-in `PythonInspector` (11 parsers total), keeping the core package zero-dependency.
  - **Read-only context budget telemetry (`core/stats.py`, `brain79 stats`)**: added `compute_stats()`, `estimate_tokens()`, and `brain79 stats` (`--format text|json`, `--task`, `--paths`, `--max-articles`, `--project-root`) reporting wiki health, token budgets (`orient()`, full wiki, active vs. superseded), and governance coverage with zero filesystem mutations.
  - **Doctor and CI polyglot diagnostics (`core/doctor.py`, `.github/workflows/ci.yml`)**: added AST guard capability summary in `doctor` (`binary_and_environment`), `ast_guards` warning check on broken grammars, and cross-platform `jobs.test-polyglot` CI matrix (`BRAIN79_REQUIRE_POLYGLOT=1`).

### Changed
- **26-command CLI superset**: expanded `WHITELIST` in `cli/dispatch.py` from 25 to 26 subcommands (`stats` is CLI-only; `MCP_TOOLS` remains fixed at 9 tools per ADR-020).
- **Language-agnostic public positioning**: updated `README.md`, `USER_GUIDE.md`, and `ARCHITECTURE.md` to highlight universal repository support (Merkle drift, `orient()`, hooks, CI gates) alongside `brain79[polyglot]` and custom `LanguageInspector` extensibility.

### Migration notes
- Core `brain79` remains zero-dependency for Tree-sitter; install `uv tool install "brain79[polyglot]"` (or `pip install "brain79[polyglot]"`) to enable deep AST Guard C verification across TypeScript, TSX, JavaScript/JSX, Go, Rust, Java, C#, PHP, Ruby, and Bash.
- Run `brain79 update-project` in existing repositories to synchronize `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md`, and `.agents/plugins/brain79/skills/brain79-wiki/SKILL.md` to `v0.16.0`.

## [0.15.0] - 2026-11-24

### Added
- **Passive lifecycle hooks and CI PR gate (Phase 14, SPEC-014, ADR-021)**:
  - **Read-only CI governance and PR gate (`core/ci_check.py`, `brain79 ci-check`)**: added `run_ci_check()` and `CiCheckReport` with Git diff range resolution (`git_diff_range_names()`), impacted governing article detection, 1-hop active ADR surfacing, full structural + organizational lint parity, dual-tier enforcement evaluation (`strict` default in CI, `balanced`/`advisory`/`schema`, `--fail-on-warnings`), Markdown/JSON output, and `--summary-file` / `$GITHUB_STEP_SUMMARY` persistence (`<!-- brain79:ci-check -->`).
  - **Native passive lifecycle hook runtime (`--lifecycle-hook <session-start|stop>`)**: added cross-platform, fail-open (`{}` on error/oversized stdin/missing wiki), ASCII-safe JSON handler for Claude Code (`claude`), Antigravity (`agy`), and Cursor (`cursor`) with loop-immunity and non-normal termination guards (`continuationActive`, `stop_hook_active`, `loop_count`, `terminationReason`, `status`).
  - **Opt-in lifecycle hook harness adapters (`core/harnesses/lifecycle_hooks.py`)**: added `ClaudeHooksAdapter` (`.claude/settings.json`), `AntigravityHooksAdapter` (`.agents/plugins/brain79/hooks.json`), and `CursorHooksAdapter` (`.cursor/hooks.json`), wired to `--install-lifecycle-hooks` on `brain79 init` and `brain79 update-project` (plus `--harnesses hooks`), with non-destructive JSON merging, corrupt-file `.bak` backup, and `brain79 doctor [--fix]` diagnostics.
  - **Composite GitHub Action (`action.yml`)**: added reusable composite action with pinned `astral-sh/setup-uv@v10.4.0`, injection-safe `env:` variable passing, `$GITHUB_OUTPUT` exports, and idempotent `<!-- brain79:ci-check -->` PR commenting via `gh api`; integrated `brain79 ci-check --write-step-summary` into `.github/workflows/ci.yml`.
  - **Git diff range and `git_ls_files()` hardening (`core/git_ops.py`)**: added `git_diff_range_names()` with option/range-injection validation and three-dot to two-dot shallow fallback, and updated `git_ls_files()` to raise `GitError` on non-zero exit so `WorkspaceIndex.build()` cleanly falls back to filesystem scanning.

### Changed
- **25-command CLI superset**: expanded `WHITELIST` in `cli/dispatch.py` from 24 to 25 subcommands (`ci-check` is CLI-only; `MCP_TOOLS` remains fixed at 9 tools per ADR-020).

### Migration notes
- Default `brain79 init` behavior is unchanged; opt into native lifecycle hooks with `brain79 init --install-lifecycle-hooks` or `brain79 update-project --install-lifecycle-hooks` (or `--harnesses hooks`).
- Teams preferring low-friction local iteration with strict mainline protection can set `enforcement: balanced` in `.brain-79/SCHEMA.md` and run `brain79 ci-check` (or `uses: xilax79/brain-79@v0.15.0`) in Pull Request workflows.
- Run `brain79 update-project` in existing repositories to synchronize `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md`, and `.agents/plugins/brain79/skills/brain79-wiki/SKILL.md` to `v0.15.0`.

## [0.14.0] - 2026-11-23

### Changed
- **Focused 9-tool MCP surface & CLI superset (Phase 13, SPEC-013, ADR-020)**:
  - Pruned 13 redundant/administrative MCP wrapper tools from `src/brain79/server.py` (`brain79_index`, `brain79_schema`, `brain79_write`, `brain79_write_many`, `brain79_list`, `brain79_ingest`, `brain79_handoff_read`, `brain79_handoff_write`, `brain79_handoff_purge`, `brain79_navigate`, `brain79_migrate`, `brain79_update_project`, `brain79_doctor`) and removed `ADMIN_TOOLS` and dual-profile branching (`create_mcp_server(profile=...)`).
  - Standardized a single fixed 9-tool `MCP_TOOLS` surface (`brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, `brain79_bootstrap`) while preserving all 24 CLI subcommands in `WHITELIST` untouched.
  - Updated runtime hints (`core/orient.py`, `core/handoff.py`, `core/bootstrap.py`), packaged templates (`AGENTS.md`, `SKILL.md`, `SCHEMA.md`, `SCHEMA_GENERAL.md`), and `tests/test_symmetry.py` (`MCP_TOOLS` ⊂ `WHITELIST`).

### Removed
- **`--mcp-profile` CLI flag and `BRAIN79_MCP_PROFILE` routing (`__main__.py`)**:
  - Passing `--mcp-profile` or `--mcp-profile=<value>` now emits an actionable migration error to `stderr` and exits with code `2`.
  - Legacy `BRAIN79_MCP_PROFILE` environment variables are silently ignored during MCP stdio startup with zero `stderr` output so strict MCP host handshakes never fail.

### Migration notes
- Users whose MCP client configuration previously passed `--mcp-profile full` should remove that flag; run administrative commands (`doctor`, `migrate`, `update-project`, `navigate`, `handoff-purge`, `schema`, `write`) via the `brain79 <command>` CLI.
- Run `brain79 update-project` in existing repositories to refresh `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md`, and `.agents/plugins/brain79/skills/brain79-wiki/SKILL.md` to `v0.14.0`.

## [0.13.1] - 2026-11-22

### Fixed
- **BUG-008 — `load_registry()` disk reconciliation (`core/navigation.py`)**: reconciled `.navigation_registry.json` completeness against `_scan_indexable_md_files(wiki_root)` whenever cached paths diverge from on-disk indexable `.md` files (missing articles or stale deleted entries), deterministically rebuilding from disk without deadlocking on `_registry.lock` when called from `register_article()` or `regenerate_index_navigation()`, and preserving read-only filesystem safety.
- **BUG-009 — `index_desync` organizational lint rule (`core/lint_organizational.py`)**: added `check_index_desync()` comparing `_scan_indexable_md_files(wiki_root)` against article links in `INDEX.md` `## Quick navigation` to surface missing or stale entries (blocking under `lint --strict`) with actionable remediation `Run 'brain79 navigate --regenerate --rebuild'`, while keeping empty wikis and fixtures without `INDEX.md` clean.
- **BUG-010 — Symmetric protocol version skew detection (`core/orient.py`)**: updated `check_protocol_version_skew()` to compare semantic versions symmetrically and emit an explicit warning when the running MCP server/CLI is older than the repository's `AGENTS.md` protocol marker (instructing the user to restart their MCP client/server or run `brain79 update`), while preserving forward-skew notices.

## [0.13.0] - 2026-11-20

### Added
- **Team-safe Git collaboration and low-friction onboarding (Phase 12)**:
  - **Merge-conflict-free derived state**: added `sync_wiki_gitignore()` in `init_project.py` to git-ignore `.navigation_registry.json`, `.drift_manifest.json`, and `.bootstrap_state.json` while preserving custom `.gitignore` lines; added `derived_state_tracking` check in `doctor.py`; added deterministic `rebuild_navigation_registry()` (`brain79 navigate --rebuild` / `brain79_navigate(rebuild=True)`) and zero-masking `rebuild_drift_manifest()` with full Guard A/C parity when `.drift_manifest.json` is absent.
  - **Deterministic `INDEX.md` Git merge driver**: implemented 3-way `merge_index_files()` and `brain79 navigate --merge-driver %O %A %B` wired via `.brain-79/.gitattributes` and local `.git/config` (`sync_git_merge_driver()`, `--no-merge-driver` opt-out on `init`, `git_merge_driver` check + `doctor --fix` repair).
  - **Brownfield onboarding (`bootstrap --auto-map`)**: added stdlib-only `core/auto_map.py` (`analyze_repository_boundaries()`) detecting `pyproject.toml`, `package.json`, `Cargo.toml`, and `go.mod` boundaries (including nested `src/` layouts), ranking by Git churn (`git_recent_file_churn()`), and guaranteeing strictly zero pairwise `applies_to` overlap; exposed `--auto-map`/`--max-modules` on CLI and `auto_map`/`max_modules` on `brain79_bootstrap`.
  - **Configurable enforcement tiers (`strict` / `balanced` / `advisory`)**: added declarative `enforcement:` in `SCHEMA.md` and `ActiveSchema` (default `strict`, safe fallback with warning on invalid values), `--enforcement` on `brain79 init`, tier-aware guard downgrades across `session_commit.py` and `wiki.py`, `[Enforcement: <tier>]` in `lint`, tier-aware `lint --strict` + `--fail-on-warnings`, and tier visibility in `orient()` and `doctor`.

### Migration notes
- Run `brain79 update-project` in existing repositories to update `.brain-79/.gitignore`, configure `.brain-79/.gitattributes` and the local `INDEX.md` Git merge driver, and sync templates to `v0.13.0`.
- If `.brain-79/.navigation_registry.json`, `.brain-79/.drift_manifest.json`, or `.brain-79/.bootstrap_state.json` were previously tracked in Git, untrack them with `git rm --cached .brain-79/.navigation_registry.json .brain-79/.drift_manifest.json .brain-79/.bootstrap_state.json` (verified by `brain79 doctor`).

## [0.12.0] - 2026-11-20

### Added
- **Public release readiness and friction removal (Phase 11)**:
  - **English-first backlink standardization**: replaced the hardcoded Spanish footer with `[← Back to Index](../INDEX.md)` (`DEFAULT_BACKLINK_LABEL`), added optional `backlink_label:` customization in `.brain-79/SCHEMA.md`, preserved backward-compatible recognition of legacy Spanish footers in `lint` and `validate_article_content()`, and enabled deterministic idempotent canonicalization in `migrate_wiki()`.
  - **Native multi-harness instruction adapters**: extracted shared delimited block engine (`core/harnesses/_delimited.py`), added compact instruction template (`HARNESS_COMPACT.md`), and registered `ClaudeCodeAdapter` (`CLAUDE.md`), `CursorRulesAdapter` (`.cursor/rules/brain79.mdc` with `alwaysApply: true`), and `CopilotAdapter` (`.github/copilot-instructions.md`). Added `--harnesses` selective installation on `brain79 init` and wired full diagnostics and dirty-tree guards into `brain79 doctor`.
  - **MCP tool surface compaction (`core` default)**: compacted `CORE_TOOLS` to 8 hot-path tools and switched the default FastMCP server profile from `full` (22 tools) to `core` (~64% schema reduction per turn), with `BRAIN79_MCP_PROFILE` env var support, CLI `--mcp-profile` precedence, and profile-tailored server instructions.
  - **Honest positioning**: added `## Limitations and trade-offs` and updated MCP profile / native harness guides in `README.md`.
  - **Windows CI `orient()` hot-path optimization**: memoized contained path resolution in `WorkspaceIndex`, replaced `copy.deepcopy()` in `_PARSE_CACHE` with a lightweight YAML primitive cloner, and shared `GitSessionCache` across `orient()` sub-calls.

### Migration notes
- **MCP profile default changed to `core` (8 tools)**: clients requiring all 22 MCP tools should start the server with `brain79 --mcp-profile full` or set `BRAIN79_MCP_PROFILE=full`, or use the symmetric CLI (`brain79 <command>`) for administrative tasks.
- **English backlinks and native harnesses**: run `brain79 update-project` in existing repositories to migrate legacy `[← Volver al Índice]` footers to `[← Back to Index]` and sync `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, and `.github/copilot-instructions.md` non-destructively.

## [0.11.0] - 2026-11-20

### Added
- **Core architectural refactoring, concurrency hardening, security fixes, and modular decomposition (Phase 10)**:
  - **Stage 1 — Correctness, concurrency, and transactional integrity**:
    - Lowercase section normalization and mixed-case self-healing in `core/navigation.py`, eliminating duplicate `INDEX.md` headers.
    - Documented and enforced global lock hierarchy (`_transaction.lock` -> `_registry.lock` -> `_drift_manifest.lock` -> `INDEX.md.lock`) via `OrderedFileLock` in `core/locks.py`, and eliminated the unlocked read window (TOCTOU) in `regenerate_index_navigation()`.
    - Complete Pass 3 rollback coverage in `core/session_commit.py` (`.navigation_registry.json`, `INDEX.md`, `_raw/sessions/`), transaction-scoped temp cleanup via `transaction_temp_scope()` / `create_temp_path()` (preserving unrelated worker `.tmp` files), and explicit `health_status: "degraded"` reporting when navigation regeneration fails.
  - **Stage 2 — Centralized Git layer and error-handling hardening**:
    - Consolidated all `git` subprocess invocations across the codebase into `src/brain79/core/git_ops.py` with typed helpers, `GitResult`, `NotAGitRepoError`, `GitTimeoutError`, `-c core.quotepath=false`, `--` pathspec termination, and optional `GitSessionCache`.
    - Eliminated silent fail-open paths in AST Guard C (`core/drift.py`) and Pass 2d (`core/session_commit.py`), failing closed with `ValidationError` on operational errors while cleanly handling non-git workspaces.
    - Deep-copy safe `_PARSE_CACHE` in `core/frontmatter.py` preventing nested dict/list mutation poisoning.
  - **Stage 3 — Security hardening**:
    - Enforced repository containment (`candidate.resolve().is_relative_to(project_root)`) before reading governed targets in AST verification and drift manifest hashing, rejecting escaping symlinks and `../` traversals.
    - Blocked Git option injection (`branch_override` / `remote` / `branch` starting with `-`) in `core/update.py` and `core/git_ops.py`.
  - **Stage 4 — Modular decomposition for roadmap extensibility**:
    - Extracted pluggable AST inspector subsystem (`core/ast_guards/`) with `LanguageInspector` protocol, `SignatureDiff`, `PythonInspector` (with `GitSessionCache` HEAD/blob reuse), and extension registry.
    - Extracted declarative Tier 1 harness adapter registry (`core/harnesses/`) driving `init_project.py` and `doctor.py`.
    - Refactored `server.py` into configurable `create_mcp_server(profile="core"|"full")` with `CORE_TOOLS` (14) and `ADMIN_TOOLS` (8), wired to `--mcp-profile <core|full>` in `__main__.py`.
    - Added immutable `ProjectContext` backed by `contextvars.ContextVar` in `config.py` for isolated multi-worktree async/threaded execution.

## [0.10.0] - 2026-11-17

### Added
- **Automated battle-testing, chaos fuzzing, and multi-repo gauntlet (Phase 9)**:
  - Cross-platform 5-cell L-shaped GitHub Actions CI matrix (Ubuntu × Python 3.11/3.12/3.13, macOS × Python 3.12, Windows × Python 3.12) in `.github/workflows/ci.yml` with pinned Node 24 action tags and `.gitattributes` line-ending standardization.
  - Comprehensive real-OS platform tests (`tests/test_cross_platform_and_locks.py`) asserting Windows reserved name rejection, case collision detection on case-insensitive filesystems, path whitespace/unicode handling, and CRLF drift hashing parity.
  - Multiprocess concurrency stress testing with 8 worker processes and `Barrier(8)` under contention, validating zero JSON state corruption, zero orphan temporary files, atomic lock release, and zero torn writes (`tests/test_chaos_and_fuzzing.py`).
  - POSIX SIGKILL process crash lock recovery.
  - Deterministic stdlib fuzzing across 6 corpus classes (YAML shapes, encodings, surrogates, boundary sizes, forbidden paths, and cyclic graphs).
  - Transactional Pass 3 session commits with filesystem snapshot and automatic all-or-nothing rollback on `BaseException` (`KeyboardInterrupt`, `ENOSPC`).
  - Five-archetype multi-repo battle gauntlet runner (`scripts/run_battle_gauntlet.py`) and test suite (`tests/test_battle_gauntlet.py`) executing a rigid 10-step lifecycle across dirty monorepos, chaotic legacy wikis, gitless research, branch warfare with AST Guard C, and scale benchmarks (200 articles, 1,000 files) with calibrated in-process latency ceilings.
  - Live-agent recovery smoke testing in `scripts/run_e2e_smoke.py` covering scenarios 5 (`unresolved_session_ripple`) and 6 (`duplicate_governance_target`) with model policy enforcement (`gemini-3.8-flash:low`) and exit code 77 skip behavior.

## [0.9.2] - 2026-11-17

### Added
- **Zero-clone installation, CLI/Python 3.11+ alignment, and 3-layer Diátaxis documentation**:
  - Zero-clone tool updating in `brain79 update` via `uv tool install --force git+https://github.com/xilax79/brain-79.git`, distinguishing standalone `site-packages` installs from local editable checkouts.
  - Safe dev checkout rebuilding via `uv tool install --editable --force .` and Windows running-executable lock handling.
  - Aligned minimum Python runtime requirement to 3.11+ across `doctor.py`, `templates/AGENTS.md`, and documentation.
  - Expanded `ROOT_HELP` in `__main__.py` with `update-project` and `doctor`, and aligned `update` subcommand help.
  - Three-layer Diátaxis documentation refactoring:
    - High-clarity, human-facing landing page in `README.md` with Karpathy LLM-wiki positioning, 4-row comparison table, ASCII workflow diagram, and day-to-day usage guide without internal jargon.
    - Deep user and protocol reference in `USER_GUIDE.md` detailing AGENTS.md + MCP harness integration, 5 concrete code-verified scenarios (cold-start orientation, stale doc protection with AST Guard C and Hard Session Ripple Gate, gitless research, on-demand handoffs with cryptographic provenance, and MCP tool vs CLI symmetry table).
    - Developer-grade `ARCHITECTURE.md` with complete 28-file source code map, verified step-by-step traces of `orient()` and `commit_session()`, and cross-platform concurrency invariants.
  - Retired HTML documentation files (`docs/whitepaper.html` and `docs/index.html`) in favor of standard, zero-dependency Markdown documentation.

## [0.9.1] - 2026-11-16

### Added
- **Antigravity (agy) native plugin, progressive AGENTS.md disclosure, and ancestor root walk**:
  - Native Antigravity workspace plugin initialization under `.agents/plugins/brain79/` with `plugin.json`, portable `mcp_config.json`, and on-demand `skills/brain79-wiki/SKILL.md`.
  - Retained legacy `.agents/mcp_config.json` for backward compatibility across existing tooling and environments.
  - Progressive disclosure split: compacted root `AGENTS.md` to <= 6,500 bytes while preserving all protocol anchors (`<!-- brain79:start -->`, `# Brain-79 AI memory protocol`, `pi-mcp-adapter`, `brain79_index`, `No-Op Idempotence`, `Zero-Modification Rule`, `## Project notes`).
  - Moved comprehensive MCP/CLI reference tables, workflows, JSON examples, and lint/migration procedures to on-demand `SKILL.md` (`brain79-wiki`).
  - Dynamic ancestor project root resolution when `--project-root .` or `--project-root=./` is specified, climbing to ancestor `.brain-79/` while respecting nested repository `.git` boundaries and `BRAIN79_PROJECT_ROOT`.
  - Isolated subdirectory initialization for `brain79 init` without `--project-root`.
  - Updated `brain79 doctor` diagnostic engine to validate `.agents/plugins/brain79/`, alert on missing plugin when legacy `.agents/mcp_config.json` is present, include plugin directory in dirty-tree git guard, and repair via `doctor --fix`.

## [0.9.0] - 2026-11-13

### Added
- **Project upgrade, legacy wiki reconditioning, and multi-harness doctor diagnostics**:
  - Non-destructive `AGENTS.md` manifest upgrader (`sync_agents_manifest`) wrapping instructions in versioned comment blocks (`<!-- brain79:start v0.9.0 -->`...`<!-- brain79:end -->`) while preserving user notes and persona directives.
  - Non-destructive `SCHEMA.md` upgrader (`sync_schema_file`) elevating to `schema_version: 2` while preserving custom directory profiles and extensions.
  - Universal portable Tier 1 MCP harnesses configured automatically across `.mcp.json`, `.agents/mcp_config.json`, and `.cursor/mcp.json` with machine-path sanitization.
  - Respectful Git hook integration preserving third-party managers (Husky, `pre-commit`, Lefthook).
  - Two-tier wiki reconditioning (`migrate_wiki` v2) with full-pass article inspection, backlink normalization, bullet colon repair, and semantic legacy status downgrade for incomplete articles.
  - Subsecond 7-point operational diagnostic engine (`brain79 doctor` / `brain79_doctor`) with POSIX exit codes `0/1/2`, text and JSON output, and Git-aware `--fix` safety guard.
  - Passive protocol skew alert in `orient()` prompting users when repository templates lag behind the installed binary.
  - Complete 1:1 CLI and FastMCP symmetry across 24 CLI subcommands and 22 MCP tools.

## [0.8.1] - 2026-11-13

### Added
- **Living manuals and temporal decontamination governance (ADR-018)**:
  - Added `check_temporal_contamination` to `lint_organizational.py` flagging temporal project management markers (`Phase X`, `Sprint Y`, `Milestone Z`, `WIP`) in titles, summaries, and headings of living manuals (`features/`, `architecture/`, `product/`).
  - Added `shipped_specification_title` rule ensuring shipped living manuals describe active capabilities rather than "specifications".
  - Established formal three-class document ontology (Immutable Audit Trail, Living System Truth, Ephemeral Operational Transition) with Chesterton's Fence invariant for ADRs.
  - Line-by-line semantic de-phasing across `src/brain79/` comments, docstrings, and root `AGENTS.md`.
  - Epocal changelog consolidation policy preventing navigation budget exhaustion.
  - Sized and synchronized state enums (`archived`) in `generate_frontmatter_template()`.

## [0.8.0] - 2026-11-12

### Added
- **Phase 6.7: Transitive drift, Merkle leaf manifest, and Hard Session Ripple Gate**:
  - Merkle leaf manifest (`.drift_manifest.json`) recording exact per-file modified, added, and deleted drift attribution with 64 KB chunk streaming and CRLF/BOM normalization.
  - Multi-hop DAG transitive drift propagation with cycle-immune memoized recursive upward propagation.
  - 4-phase transaction commit pipeline in `session_commit` and `write_many_articles` wrapped in outer `_transaction.lock`.
  - Pass 2d Hard Session Ripple Gate (`unresolved_session_ripple`) rejecting incomplete commits that leave impacted umbrella or governing articles drifted.
  - AST Guard C public signature verification using Python `ast` to detect public signature changes while allowing private helper refactors.
  - Anti-Sprawl Guard (`duplicate_governance_target`) blocking redundant article creation when governed code targets are already subsumed.
  - Unbounded Signal 1 context ranker in `rank_context_articles` returning all governing articles without `top_n` truncation.
  - Golden Blueprint reconditioning: anchored 100% of `src/brain79/**/*.py` across 16 canonical articles, consolidated handoff features into `features/handoff-continuity.md`, archived defect backlog, and verified zero drift across the entire workspace.


### Changed
- **Pre-GA Semantic Versioning Calibration**: Recalibrated package versioning from `2.0.2` to `0.7.2` to strictly reflect pre-release maturation status according to SemVer 2.0.0 §4 prior to public PyPI distribution.
- Preserves all architectural features from Phases 0 through 6.6 (Two-Call protocol, deterministic drift detection, FastMCP symmetry, and handoff authority decay).
- Aligns release roadmap: Phase 6.7 releases `0.8.0`, Phase 7 releases `0.9.0`, Phase 8 releases `0.10.0`, leading to `1.0.0` General Availability (GA).

### Added
- **Phase 6.6: Handoff freshness, provenance, and authority decay (ADR-016)**:
  - Deterministic provenance tracking in handoff frontmatter: `created_at`, `git_branch`, `git_head`, `wiki_digest`, and `code_digest`.
  - Content-based sha256 digests (`wiki_digest` over permanent wiki articles, `code_digest` over git working tree outside `.brain-79/`), immune to clone or checkout mtime modifications.
  - State classification engine in `src/brain79/core/handoff_freshness.py` (`fresh`, `stale`, `foreign_branch`, `unverified`).
  - Authority decay rendering in `orient()` and `read_handoff()`: warning banners for stale handoffs, relabeled historical boot instructions, and cross-branch task isolation.
  - Branch-aware `latest` resolution preferring current git branch before global fallback.
  - Advisory aging escalation banner when unpromoted pending tasks cross age or commit thresholds.
  - Standardized English handoff template with colons outside bold formatting.
- **Phase 6.5: Session knowledge triage, research persistence guard, and handoff ergonomics**:
  - The Amnesia Test 3-way triage protocol (Type A ephemeral $\rightarrow$ no-op, Type B zero-code research $\rightarrow$ mandatory wiki persistence, Type C code mutation $\rightarrow$ sync governing articles).
  - Unpersisted research engine guard in `write_handoff` and `commit_session` blocking premature session closure when knowledge was generated without permanent wiki writes.
  - Tolerant recursive proxy argument unpacking (`_unpack_nested_args`) and FastMCP schema alias compatibility.
  - Mechanical bullet colon normalizer (`normalize_bullet_colons`) enforcing sentence case formatting.
  - Real-agent pre-merge E2E smoke test suite (`scripts/run_e2e_smoke.py`).

## [2.0.2] - 2026-11-04

### Fixed
- **Root Backlink Normalization & General Profile Template (BUG-001)**:
  - Replaced invalid upward traversal `[← Volver al Índice](../INDEX.md)` with `[← Volver al Índice](INDEX.md)` in `src/brain79/templates/SCHEMA_GENERAL.md`.
  - Normalized root-level backlink traversals in `normalize_backlink_footer` strictly within unmasked tail lines outside code fences, preserving documentation examples inside code blocks.
- **Composite H2 Atomicity Heuristics & Code-Fence Masking (BUG-002)**:
  - Masked code fences in `check_article_atomicity` to avoid falsely counting markdown example headings.
  - Applied composite H2 thresholds: up to 15 for checklists/roadmaps, up to 12 for compact articles (<= 150 lines), and up to 10 for standard prose articles (> 150 lines).
- **Self-Documenting Tool Receipts & Agent Protocols (INEF-001, INEF-002, INEF-003)**:
  - Added `· INDEX.md auto-synced` to `brain79_write`, `brain79_edit`, and `brain79_write_many` receipts.
  - Added compact `## 📐 Active Schema Summary` header to `brain79_orient` cold-start output.
  - Formalized On-Demand Handoff Policy across server docstrings and AGENTS.md manifests.

### Removed
- **Obsolete Truco Arena Snapshot Fixture (`tests/test_truco_arena_integration.py` & `tests/fixtures/`)**:
  - Removed outdated 40+ file fixture snapshot dating from prototype v0.1 (August 2026) that required artificial test-time patching to pass modern linter rules.
  - Eliminated `refresh_truco_arena.sh` containing hardcoded absolute machine paths.
  - Full migration and strict linter coverage preserved in `tests/test_migrate_frontmatter.py` and `tests/test_lint_organizational.py`.

## [2.0.0] - 2026-11-03

### Added
- **Phase 5: Single-Source Semantic Versioning & Release Governance**:
  - Established `src/brain79/__init__.py` as the single source of truth for versioning, resolved dynamically by Hatchling (`dynamic = ["version"]`).
  - Added `version=__version__` to `FastMCP("brain79")` initialization for accurate JSON-RPC handshake metadata.
  - Enhanced CLI root help (`brain79 --help` / `brain79 help <subcmd>`) and added `-v` / `--version` flags with strict exit code 2 on unknown commands.
  - Implemented mechanical release parity test suite (`tests/test_version_governance.py`) enforcing SemVer compliance, Hatchling dynamic build configuration, README badge synchronization, and changelog parity across both `.brain-79/changelog/` and root `CHANGELOG.md`.
- **Phase 4: Structural Article Quality & Deterministic Drift Detection**:
  - Enforced document structural integrity with section skeletons per document type (`## Status`, `## Context`, `## Decision`, `## Consequences` for decisions; `## Overview` for features).
  - Automated backlink injection (`[← Volver al Índice](../INDEX.md)`) across all subfolder articles during write normalization.
  - Implemented Git-backed code-to-wiki drift detection (`documentation_drift_suspected`) alerting when workspace source files change after governing documentation `last_updated` dates.
- **Phase 3: Zero-Turn Session Execution (The Two-Call Session Protocol)**:
  - Introduced `brain79_session_commit` (FastMCP) and `brain79 session-commit` (CLI) providing 1-call atomic end-of-session finalization:
    - Pre-flight in-memory simulation and validation of writes, edits, and handoff anti-hallucination constraints with an all-or-nothing rollback guarantee (zero files hit disk on error).
    - Synchronous execution of raw session archiving (`_raw/sessions/`), article writes, partial edits, and immutable handoffs.
    - Single consolidated navigation registry update and index regeneration under lock.
    - Whole-transaction inline health diagnostics receipt (`check_file_health`).
  - Added section-projected reading via `sections` parameter in `brain79_read` / `brain79 read` and batch reading via `brain79_read_batch` / `brain79 read-batch`, eliminating turn tax and reducing context window token consumption.
  - Automatically append governing ADR reference hints (`💡 Linked ADRs: ...`) to article reads.
- **Phase 2: Deterministic Pre-Work Context & Graph-Augmented Cold Start**:
  - Introduced `brain79 orient` (CLI) and `brain79_orient(task?, paths?, max_articles?)` (MCP), consolidating routing table, latest handoff state, promotion alerts, and inlined governing documents into a single tool call.
  - Upgraded context ranking (`rank_context_articles`) to a 3-signal deterministic engine:
    1. *Signal 1*: Exact and glob matching of `applies_to` frontmatter against workspace files.
    2. *Signal 2*: Field-weighted TF-IDF (title $3\times$, summary $2\times$, body $1\times$) with down-ranking of superseded articles.
    3. *Signal 3*: 1-Hop ADR reference graph expansion pulling active governing decisions linked from matched articles.
  - Extended frontmatter schema and templates to recognize `applies_to`, `related`, and `supersedes` across all article types.
  - Updated navigation registry indexing to capture article graph edges (`applies_to`, `related`, and `outgoing_links`).
- **Phase 1: Declarative Schema & Dual Ontology**:
  - Decoupled validation engine (mechanism) from directory/type policies via `load_active_schema` with high-speed mtime caching.
  - Added built-in dual ontologies (`software` and `general`) supported via `brain79 init [--profile software|general]`.
  - Added support for arbitrary custom directories and frontmatter types declared in `.brain-79/SCHEMA.md` (`custom_types`).
  - Added dynamic profile sensitivity to `brain79 schema` / `brain79_schema()`.
  - Added dynamic `session_type` validation for handoffs, enabling general profile session types (`work`, `writing`, `analysis`, `research`).
  - Added schema-aware field preservation in `autofill_deterministic_fields` (preserving declared optional fields like `tags` on `topic` and auto-filling `date` on `log`).
  - Added explicit direct package dependency on `pyyaml` and `types-pyyaml`.
- **Frontmatter `summary` support**: articles can declare an explicit `summary` in YAML frontmatter, indexed directly into `INDEX.md` Quick navigation in $O(1)$ time without relying on body heuristics.
- **Article Backlink Convention**: documented and templated footer navigation links (`[← Volver al Índice](../INDEX.md)`) for seamless reading across editors.
- **Hardened Navigation Fallback**: improved `extract_title_and_summary` to ignore subheadings, bullet items, and trailing colons when no frontmatter summary is defined.
- **Phase 0: Foundation Cleanup & Parity**:
  - Unification of organizational linter with write validation (`validate_frontmatter`).
  - Strict enforcement of ADR-008 (*Pure Routing Table*) in `INDEX_ALLOWED_H2`.
  - Validation alignment for `brain79_bootstrap` manifests and `_raw/sessions/` frontmatter.

## [1.1.0] - 2026-10-29

### Added
- **`brain79 schema` / `brain79_schema()`**: inspect schema requirements and ready-to-paste frontmatter templates per type or for the entire wiki.
- **`brain79 edit` / `brain79_edit()`**: targeted in-place text replacement in wiki articles, saving LLM output tokens on minor edits without rewriting entire files.
- **`brain79 write-many` / `brain79_write_many()`**: batch write tool with atomic, all-or-nothing upfront validation pass and single consolidated navigation regeneration.
- **Inline Write Health Checks**: `brain79_write` and `brain79_edit` return instantaneous health checks (`· lint OK` or warnings), cutting redundant separate lint invocations.
- **Deterministic Field Auto-Fill**: `type` inferred from directory structure, `last_updated` and `date` defaulted to today UTC. Hallucinated keys (`title`, `tags`, `created`) automatically stripped (ADR-004 amendment).
- **Multi-Error Validation**: reports all schema violations simultaneously with copy-paste templates rather than failing fast on the first error.
- **Automatic Navigation Sync on Write**: article writes automatically register and regenerate `INDEX.md` Quick navigation atomically using file locks (ADR-006).

### Fixed
- **Handoff Navigation Pollution**: handoffs are strictly excluded from navigation registry and `INDEX.md`, preventing index bloat toward the 150-line limit.
- **FastMCP Duplicate Output**: configured `output_schema=None` across all MCP tools to prevent FastMCP wrapping results in duplicated `structuredContent`.
- **Handoff Tool Robustness**: relaxed `previous_handoff_ref="latest"` to handle empty state cleanly, expanded anti-hallucination indicators, and tightened `session_type` literal.
- **Lint Scalability**: replaced repetitive `Path.resolve()` link traversals with fast in-memory normalized path lookups.

## [1.0.0] - 2026-08-11

### Added
- **`brain79 handoff-purge`**: destructive command to wipe all handoff files
  and unregister them from the navigation registry. CLI/MCP symmetric, defaults
  to `--dry-run` for safety. Does not touch `_raw/` or auto-fix broken links
  in other articles (lint + agent handles those).
- **Wiki Organizational Enforcement System**:
  - Mechanical YAML frontmatter schema validation and type-location consistency checking (`frontmatter.py`, `validation.py`).
  - Strict V5 structural decision and technical debt leakage regex rules with CommonMark code fence masking.
  - Thread-safe, lock-file backed auto-generated navigation registry (`navigation.py`).
  - Extended organizational health linter (`lint_organizational.py`) with `--strict`, `--suggest-extract`, and `--format json` CLI flags.
  - Progressive V3 legacy wiki migration script (`migrate_frontmatter.py`) with `status: legacy` defaults and `--suggest-relocations`.
  - Bypassing validation via `force_validation_skip` flag / metadata (`force_skipped_article`).
  - Executable git pre-commit hook (`install_git_hooks`) automatically deployed during `brain79 init`.
  - State-aware dynamic curation guide generator (`curate.py`).
  - North-Star integration test suite based on Truco Arena real-world legacy wiki snapshot (`test_truco_arena_integration.py`).

### Fixed
- CLI `brain79 migrate` now defaults to `--dry-run` for 1:1 symmetry with MCP `brain79_migrate()`. Use `--apply` to apply mutations explicitly.
