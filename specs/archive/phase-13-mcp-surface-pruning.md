---
spec_id: SPEC-013
title: MCP surface pruning and focused CLI-superset architecture
target_version: v0.14.0
status: implemented
owner: xilax
last_updated: 2026-11-23
related_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/symmetry.md
  - architecture/mcp-server.md
  - architecture/dispatcher.md
  - architecture/current-state.md
  - features/mcp-server.md
  - features/cli.md
  - decisions/adr-001-hybrid-cli.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
target_wiki:
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
  - architecture/symmetry.md
  - architecture/mcp-server.md
  - architecture/dispatcher.md
  - architecture/current-state.md
  - architecture/roadmap-industrial-scale.md
  - features/mcp-server.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - changelog/v0-14-0.md
---

# SPEC-013 — MCP surface pruning and focused CLI-superset architecture

## Problem statement and goal

`src/brain79/server.py` currently spans 956 lines exposing 22 MCP tools split across two profiles (`core` with 8 tools and `full` with 22 tools) via `--mcp-profile` and `BRAIN79_MCP_PROFILE`. Thirteen of the 14 `ADMIN_TOOLS` are either subsumed by the two-call session protocol (`brain79_orient` and `brain79_session_commit` per ADR-010/011) or are sporadic terminal maintenance commands (`migrate`, `doctor`, `update-project`, `navigate`, `handoff-purge`). This pre-PyPI pruning phase removes redundant MCP wrappers and dual-profile branching, cuts `server.py` roughly in half, and codifies the permanent boundary: **MCP exposes the focused agent hot path; the CLI exposes the complete operational and administrative superset**.

## Non-goals (out of scope)

- **No CLI subcommand removals**: all 24 CLI subcommands in `WHITELIST` (`src/brain79/cli/dispatch.py`) and all core modules under `src/brain79/core/` remain intact and fully functional.
- **No removal of `brain79_edit`**: targeted single-article edits remain in the MCP surface alongside `brain79_session_commit`.
- **No behavioral changes to core engines**: do not modify drift detection, AST guards, lock ordering, merge driver, auto-map, or organizational linting logic.
- **No Phase 14/15 work**: do not implement lifecycle hooks, `brain79 ci-check`, Tree-sitter AST guards, `brain79 stats`, or PyPI publishing under this specification.
- **No mutation of historical ADRs or changelogs**: preserve ADR-001 through ADR-019 and prior `changelog/` entries untouched (Chesterton's Fence, ADR-018).

## Dependencies

- **Internal seams**: `create_mcp_server()` in `src/brain79/server.py`, global CLI routing in `src/brain79/__main__.py`, harness templates in `src/brain79/templates/`.
- **External / optional**: none (zero new dependencies).

## Constraints and invariants

All requirements must preserve the repository's canonical invariants:

- **Versioning**: pre-GA minor bump (`0.14.0`) per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md) and single-source parity per [ADR-013](../.brain-79/decisions/adr-013-versioning-and-release-governance.md).
- **Dual-mode hybrid binary**: retain single `brain79` binary (no-subcommand stdio MCP server + whitelisted CLI dispatcher) per [ADR-001](../.brain-79/decisions/adr-001-hybrid-cli.md); refine the 1:1 symmetry policy in a new ADR (`ADR-020`).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Template size ceiling**: `src/brain79/templates/AGENTS.md` MUST remain `<= 6,500` bytes and preserve its compatibility anchors (updated to remove the obsolete `brain79_index` anchor).
- **Documentation style**: clean B2 English, sentence case, and living manual rules per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **Zero test coverage loss**: every existing test that previously called a pruned `brain79_*` MCP wrapper MUST be migrated to call the underlying `brain79.core.*` function, `brain79_session_commit`, or CLI `dispatch_cmd` rather than deleted.

## Open questions

All open questions have been resolved by the `owner` (`xilax`):

- [x] **Q-1**: **Option A selected (9 tools)** — retain `brain79_bootstrap` alongside the 8 core tools (`brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, `brain79_bootstrap`) so shell-less MCP clients can bootstrap empty wikis.
- [x] **Q-2**: **Option A selected (silent ignore)** — ignore legacy `BRAIN79_MCP_PROFILE` silently during MCP stdio startup (zero `stderr` output so strict MCP hosts never drop the handshake).

## Requirements (EARS)

### Capability 1 — Focused MCP tool surface (`src/brain79/server.py`)

- **R-1.1**: THE `brain79` FastMCP server (`create_mcp_server()` and module-level `mcp`) SHALL expose a single fixed set of 9 tools (`MCP_TOOLS`): `brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, and `brain79_bootstrap`.
- **R-1.2**: THE `src/brain79/server.py` module SHALL remove the 13 pruned MCP wrapper functions (`brain79_index`, `brain79_schema`, `brain79_write`, `brain79_write_many`, `brain79_list`, `brain79_ingest`, `brain79_handoff_read`, `brain79_handoff_write`, `brain79_handoff_purge`, `brain79_navigate`, `brain79_migrate`, `brain79_update_project`, `brain79_doctor`), the `ADMIN_TOOLS` constant, and the `profile` parameter from `create_mcp_server()`.
- **R-1.3**: THE FastMCP server `instructions` string SHALL reference ONLY tools present in `MCP_TOOLS`, SHALL direct agents to `brain79 <command>` CLI for administrative operations, and SHALL NOT mention `--mcp-profile`, `BRAIN79_MCP_PROFILE`, or any pruned tool name.
- **R-1.4**: WHEN `create_mcp_server()` registers tools, THE server SHALL preserve `output_schema=None`, `version=__version__`, and FastMCP/MCP `WARNING`-level stderr log suppression.

### Capability 2 — CLI entry point cleanup (`src/brain79/__main__.py`)

- **R-2.1**: THE CLI entry point (`src/brain79/__main__.py`) SHALL remove `--mcp-profile` option parsing, `_extract_mcp_profile()`, and the `--mcp-profile` line from `ROOT_HELP`.
- **R-2.2**: IF a caller invokes `brain79` with `--mcp-profile` or `--mcp-profile=<value>`, THEN `src/brain79/__main__.py` SHALL emit a clear actionable error to `stderr` stating that `--mcp-profile` was removed in `v0.14.0` and directing users to the single MCP surface / `brain79 <command>` CLI, and SHALL exit with code `2`.
- **R-2.3**: WHILE `BRAIN79_MCP_PROFILE` is set in the process environment, THE `brain79` MCP server startup SHALL ignore it silently with zero `stderr` output and start the focused 9-tool MCP server cleanly.
- **R-2.4**: THE CLI dispatcher (`src/brain79/cli/dispatch.py`) SHALL preserve all 24 subcommands in `WHITELIST` with unchanged flags, semantics, and POSIX exit codes.

### Capability 3 — Core runtime hints and packaged templates (`src/brain79/core/`, `src/brain79/templates/`)

- **R-3.1**: THE runtime guidance strings in `src/brain79/core/orient.py` (line 276), `src/brain79/core/handoff.py` (line 616), and `src/brain79/core/bootstrap.py` (line 526) SHALL NOT instruct agents to call pruned MCP tools (`brain79_write`, `brain79_handoff_read`); they SHALL reference `brain79_session_commit` / `brain79_edit` or the corresponding CLI subcommand (`brain79 handoff-read`). Preserve `generated_by: brain79_bootstrap` provenance strings in `bootstrap.py`.
- **R-3.2**: THE packaged templates (`src/brain79/templates/AGENTS.md`, `SKILL.md`, `SCHEMA.md`, `SCHEMA_GENERAL.md`) SHALL remove all references to `--mcp-profile`, `BRAIN79_MCP_PROFILE`, `core`/`full` profiles, and pruned MCP tools (`brain79_index`, `brain79_schema`, `brain79_write`, `brain79_write_many`, `brain79_list`, `brain79_ingest`, `brain79_handoff_*`, `brain79_navigate`, `brain79_migrate`, `brain79_update_project`, `brain79_doctor`), clearly distinguishing the focused MCP tools from the full 24-command CLI.
- **R-3.3**: THE `src/brain79/templates/AGENTS.md` template SHALL remain `<= 6,500` bytes and preserve all non-obsolete compatibility anchors (`<!-- brain79:start v{{VERSION}} -->`, `<!-- brain79:end -->`, `# Brain-79 AI memory protocol`, `pi-mcp-adapter`, `No-Op Idempotence`, `Zero-Modification Rule`, `## Project notes`, `.agents/plugins/brain79`, `git+https://github.com/xilax79/brain-79.git`).

### Capability 4 — Subset symmetry invariant and test migration (`tests/`)

- **R-4.1**: THE symmetry test suite (`tests/test_symmetry.py`) SHALL enforce the **MCP-subset / CLI-superset** invariant:
  1. `len(WHITELIST) == 24` CLI subcommands.
  2. Every tool registered on `create_mcp_server()` and `mcp` equals `MCP_TOOLS` and maps 1:1 to a subcommand in `WHITELIST` (`mcp_cli_names.issubset(WHITELIST)`).
  3. Parameter signatures and defaults for retained MCP tools (`brain79_session_commit` and `brain79_bootstrap`) match their `brain79.core.*` implementations.
- **R-4.2**: ALL 13 existing test files importing pruned symbols from `brain79.server` (`test_defect_backlog_remediations.py`, `test_navigation.py`, `test_mcp_server.py`, `test_session_triage_and_handoff_ergonomics.py`, `test_symmetry.py`, `test_handoff.py`, `test_phase12_auto_map.py`, `test_performance_improvements.py`, `test_migrate_frontmatter.py`, `test_bootstrap.py`, `test_cli.py`, `test_phase12_derived_state.py`, `test_phase1_integration_holes.py`) plus `test_init_project.py` (updating the `brain79_index` template anchor to `brain79_orient`) SHALL be migrated cleanly to test `brain79.core.*`, `brain79_session_commit`, or CLI `dispatch_cmd` with zero loss of behavioral coverage.

### Capability 5 — Release `0.14.0` parity and documentation synchronization

- **R-5.1**: THE release metadata (`src/brain79/__init__.py` `__version__ = "0.14.0"`, `README.md` version badge and MCP section, `USER_GUIDE.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `.brain-79/changelog/v0-14-0.md`, and managed blocks in `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md` via `brain79 update-project`) SHALL reflect `v0.14.0` and the pruned MCP surface consistently, passing `tests/test_version_governance.py`.
- **R-5.2**: THE architectural policy change SHALL be recorded in `.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md` and distilled across all impacted living manuals listed in `## Wiki impact map`.

## Interface and error contract

Aligned with [dispatcher.md](../.brain-79/architecture/dispatcher.md) (`0` success, `1` validation/operational failure, `2` invalid argument or `FileNotFoundError`, `3` `PermissionError`/`TimeoutError`/`OSError`, `130` interrupt).

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `brain79 --mcp-profile full` or `--mcp-profile=core` | Removed CLI flag passed | Print actionable migration error to `stderr` (`--mcp-profile` removed in `v0.14.0`; use `brain79 <command>` CLI); do not start server | Exit `2` |
| `BRAIN79_MCP_PROFILE=full brain79` | Legacy env var present during MCP stdio startup | Ignore silently (zero `stderr` noise during MCP handshake) and start focused MCP server cleanly | Exit `0` (stdio server runs) |
| `create_mcp_server()` | Called with unexpected keyword argument `profile=...` | Standard Python `TypeError` (removed parameter) | `TypeError` |
| `brain79 <admin-subcommand>` (e.g. `migrate`, `doctor`, `navigate`, `write`, `schema`) | Invoked via CLI | Execute identically to `v0.13.1` with zero regression | Existing POSIX exit code (`0`/`1`/`2`/`3`) |
| `brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, (`brain79_bootstrap`) | Invoked via MCP JSON-RPC | Execute identically to `v0.13.1`, including nested `args` proxy unpacking | String result / structured error |

## Migration and rollout

- **Default behavior**: existing MCP users already running the default `core` profile (8 tools since `v0.12.0`) experience zero breaking changes for session tools (and gain `brain79_bootstrap` out of the box if Q-1 selects Option A).
- **Breaking change for `--mcp-profile full` users**: documented prominently under `v0.14.0` in `CHANGELOG.md` and `.brain-79/changelog/v0-14-0.md`. Users whose MCP client config passes `--mcp-profile full` remove that argument and run administrative commands (`doctor`, `migrate`, `update-project`, `navigate`, `handoff-purge`) via CLI `brain79 <command>`.
- **Upgrade path**: existing repositories run `brain79 update-project` to refresh `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, and `SCHEMA.md` managed blocks to `v0.14.0`.
- **Rollback safety**: pure Markdown wiki format and `.brain-79/` files are untouched; downgrading `brain79` to `v0.13.1` leaves repositories 100% readable.

## Acceptance criteria (Given / When / Then)

### AC-1 — Fixed focused MCP tool surface and code reduction
- **Verifies**: `R-1.1`, `R-1.2`, `R-1.4`
- **Method**: `test`
- **Test ref**: `tests/test_mcp_server.py::test_create_mcp_server_focused_surface`
- **Given**: a fresh FastMCP server created via `create_mcp_server()` and module-level `mcp`.
- **When**: calling `await server.list_tools()` and inspecting `brain79.server` module attributes.
- **Then**: registered tool names equal `MCP_TOOLS` exactly (9 tools: `brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, `brain79_bootstrap`), none of the 13 pruned `brain79_*` symbols or `ADMIN_TOOLS` exist on `brain79.server`, `create_mcp_server()` takes zero `profile` argument, `server.version == __version__`, and `src/brain79/server.py` has zero dead wrapper code.

### AC-2 — Clean MCP server instructions with zero stale tool references
- **Verifies**: `R-1.3`
- **Method**: `test`
- **Test ref**: `tests/test_mcp_server.py::test_mcp_server_instructions_clean`
- **Given**: `server = create_mcp_server()`.
- **When**: inspecting `server.instructions`.
- **Then**: `server.instructions` contains `brain79_orient` and `brain79_session_commit`, references the CLI for administrative tasks, and contains zero occurrences of `--mcp-profile`, `BRAIN79_MCP_PROFILE`, or any pruned tool name (`brain79_index`, `brain79_schema`, `brain79_write`, `brain79_write_many`, `brain79_list`, `brain79_ingest`, `brain79_handoff_*`, `brain79_navigate`, `brain79_migrate`, `brain79_update_project`, `brain79_doctor`).

### AC-3 — Removed `--mcp-profile` flag exits 2; legacy env var is handshake-safe
- **Verifies**: `R-2.1`, `R-2.2`, `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_mcp_server.py::test_cli_removed_mcp_profile_and_env_var_ignored`
- **Given**: CLI invocation via `brain79.__main__.main(...)`.
- **When**: invoking `main(["--mcp-profile", "full"])`, `main(["--mcp-profile=core"])`, `main(["--help"])`, and `main(["--project-root", str(tmp_path)])` with `BRAIN79_MCP_PROFILE=full` set.
- **Then**: `--mcp-profile` invocations print an actionable removal message to `stderr` and exit with code `2`; `--help` contains zero `--mcp-profile` or `BRAIN79_MCP_PROFILE` text; and server startup with `BRAIN79_MCP_PROFILE=full` calls `mcp.run()` with zero `stderr` output.

### AC-4 — All 24 CLI subcommands preserved without regression
- **Verifies**: `R-2.4`
- **Method**: `test`
- **Test ref**: `tests/test_symmetry.py::test_mcp_cli_symmetry`
- **Given**: `WHITELIST` in `src/brain79/cli/dispatch.py` and the full CLI test suite.
- **When**: running `tests/test_cli.py` and `tests/test_symmetry.py`.
- **Then**: `len(WHITELIST) == 24`, every administrative CLI command (`migrate`, `doctor`, `update-project`, `navigate`, `bootstrap`, `write`, `write-many`, `index`, `schema`, `list`, `ingest`, `handoff-write`, `handoff-read`, `handoff-purge`) remains functional with unchanged exit codes.

### AC-5 — Core runtime hints and packaged templates contain zero pruned tool references
- **Verifies**: `R-3.1`, `R-3.2`, `R-3.3`
- **Method**: `test`
- **Test ref**: `tests/test_mcp_server.py::test_runtime_hints_and_templates_clean`
- **Given**: `src/brain79/core/{orient,handoff,bootstrap}.py` and `src/brain79/templates/{AGENTS.md,SKILL.md,SCHEMA.md,SCHEMA_GENERAL.md}`.
- **When**: running `tests/test_init_project.py` and scanning those files for pruned MCP tool names and `--mcp-profile`.
- **Then**: zero references to `--mcp-profile`, `BRAIN79_MCP_PROFILE`, or pruned MCP tool names remain in runtime hints or templates (except backward-compatible `generated_by: brain79_bootstrap` provenance if retained), and `templates/AGENTS.md` is `<= 6,500` bytes with all updated compatibility anchors intact.

### AC-6 — MCP-subset / CLI-superset symmetry and full test migration
- **Verifies**: `R-4.1`, `R-4.2`
- **Method**: `test`
- **Test ref**: `tests/test_symmetry.py::test_mcp_cli_symmetry`
- **Given**: all migrated test modules across `tests/`.
- **When**: running `uv run pytest` and `uv run mypy src tests`.
- **Then**: `tests/test_symmetry.py` validates `MCP_TOOLS` ⊂ `WHITELIST` plus retained parameter parity; zero test files import removed symbols from `brain79.server`; full `pytest` and `mypy src tests` pass with exit code `0`.

### AC-7 — Release `v0.14.0` parity, ADR-020, and zero wiki drift
- **Verifies**: `R-5.1`, `R-5.2`
- **Method**: `ci`
- **Test ref**: `tests/test_version_governance.py::test_changelog_entry_parity`
- **Given**: version bumped to `0.14.0`, `brain79 update-project` run on this repo, ADR-020 authored, and all impacted living manuals updated via `brain79_session_commit`.
- **When**: running `uv run pytest tests/test_version_governance.py tests/test_specs_governance.py`, `uv run brain79 lint --strict`, and `uv run brain79 doctor`.
- **Then**: all commands exit `0` with `[Status: OK]`, zero documentation drift, and full version parity across `__init__.py`, `README.md`, `CHANGELOG.md`, `.brain-79/changelog/v0-14-0.md`, and managed harnesses.

## Wiki impact map

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/server.py`, `src/brain79/__main__.py` | `decisions/adr-020-focused-mcp-surface-and-cli-superset.md` | `create` |
| `src/brain79/server.py`, `tests/test_symmetry.py` | `architecture/symmetry.md` | `update` |
| `src/brain79/server.py` | `architecture/mcp-server.md` | `update` |
| `src/brain79/server.py` | `features/mcp-server.md` | `update` |
| `src/brain79/__main__.py` | `architecture/dispatcher.md` | `update` |
| `src/brain79/templates/**`, `src/brain79/core/orient.py` | `features/project-upgrade-and-multi-harness-doctor.md` | `update` |
| `src/brain79/__init__.py`, `README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md` | `architecture/current-state.md` | `update` |
| `.brain-79/features/*.md` | `architecture/roadmap-industrial-scale.md` | `update` |
| `CHANGELOG.md`, `src/brain79/__init__.py` | `changelog/v0-14-0.md` | `create` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
uv run pytest
uv run mypy src tests
uv run brain79 lint --strict
uv run brain79 doctor
```

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| — | — | No amendments recorded yet. | — |

## Wiki distillation checklist (post-implementation)

Every item MUST be checked (`[x]`) before setting `status: implemented` and moving this file to `specs/archive/`:

- [x] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [x] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [x] Record `decisions/adr-020-focused-mcp-surface-and-cli-superset.md`.
- [x] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-14-0.md`.
- [x] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [x] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
