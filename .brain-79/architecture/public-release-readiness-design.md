---
type: architecture
summary: implementation specification and acceptance criteria for English-first backlinks, native multi-harness adapters, core MCP surface compaction, and honest README positioning
stability: experimental
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/frontmatter.py
  - src/brain79/core/drift.py
  - src/brain79/core/orient.py
  - src/brain79/core/validation.py
  - src/brain79/core/migration.py
  - src/brain79/core/lint_organizational.py
  - src/brain79/core/harnesses/**
  - src/brain79/core/init_project.py
  - src/brain79/core/doctor.py
  - src/brain79/server.py
  - src/brain79/__main__.py
  - src/brain79/templates/**
  - README.md
  - CHANGELOG.md
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/core-refactoring-and-hardening-design.md
  - architecture/current-state.md
  - architecture/mcp-server.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - decisions/adr-013-versioning-and-release-governance.md
  - decisions/adr-015-sentence-case-first-policy.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
last_updated: 2026-11-20
applies_to_digest: "sha256:78847ba30334b3db"
applies_to_count: 29
---

# Architecture — Public release readiness and friction removal

## Overview

This document defines the complete requirements, logical execution stages, and acceptance criteria for **Phase 11 (`v0.12.0`, P0)** of the `brain-79` roadmap. Its objective is to remove every avoidable public-launch blocker and cut per-turn LLM token overhead prior to announcing `brain-79` as a public preview:

1. **English-first backlink standardization**: replace the hardcoded Spanish footer (`[← Volver al Índice](../INDEX.md)`) with English (`[← Back to Index](../INDEX.md)`), allow schema-level customization in `SCHEMA.md`, and auto-migrate existing wikis cleanly via `migrate_wiki`.
2. **Native multi-harness instruction adapters**: register non-destructive adapters in `core/harnesses/` for Claude Code (`CLAUDE.md`), Cursor (`.cursor/rules/brain79.mdc`), and GitHub Copilot (`.github/copilot-instructions.md`).
3. **MCP tool surface compaction (`core` default)**: compact `CORE_TOOLS` to 8 hot-path tools and switch the default FastMCP server profile from `full` (22 tools) to `core` (~64% schema reduction per turn), keeping `full` available via `--mcp-profile full` or `BRAIN79_MCP_PROFILE=full`.
4. **Honest positioning**: add an explicit **Limitations and trade-offs** section to `README.md` and clarify pre-GA version history in `CHANGELOG.md`.

## Ground rules and invariants

- **Versioning**: ships as `v0.12.0` per ADR-017. Never bumps to `1.0.0`.
- **Zero-dependency core**: introduces no third-party runtime dependencies.
- **Backward compatibility for existing wikis**: legacy Spanish backlinks (`[← Volver al Índice]`) remain accepted by `lint` and `validate_article_content()` so existing repositories do not break abruptly; `migrate_wiki()` canonicalizes them cleanly to the active schema label.
- **Non-destructive harness writes**: every instruction adapter (`CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md`) must use `<!-- brain79:start vX.Y.Z -->` / `<!-- brain79:end -->` delimiters and preserve all user-authored text outside the managed block.
- **CLI/MCP parity**: `create_mcp_server(profile="full")` retains all 22 tools with 100% parity against `WHITELIST`; `mcp` (default `core`) exposes exactly the 8 `CORE_TOOLS`.

## Stage 1 — English-first backlink standardization and migration

Target modules: `src/brain79/core/frontmatter.py`, `src/brain79/core/validation.py`, `src/brain79/core/migration.py`, `src/brain79/core/lint_organizational.py`, `src/brain79/templates/`.

### R-1.1 — Configurable English default backlink in `ActiveSchema`
- Define `DEFAULT_BACKLINK_LABEL = "← Back to Index"` in `frontmatter.py`.
- Add `backlink_label: str = DEFAULT_BACKLINK_LABEL` to `ActiveSchema` and parse optional `backlink_label:` from `.brain-79/SCHEMA.md` frontmatter in `load_active_schema()`.
- Validate `backlink_label`: strip whitespace; reject empty values or strings containing newlines, `[`, or `]` by falling back safely to `DEFAULT_BACKLINK_LABEL`.
- Update `generate_document_skeleton(target_type, schema=None)` to emit `[{active_label}](../INDEX.md)`.

### R-1.2 — Backward-compatible normalization and linter recognition
- Update `normalize_backlink_footer(body: str, rel_path: str, *, backlink_label: str | None = None, canonicalize_legacy: bool = False) -> str` in `frontmatter.py`:
  - Uses `backlink_label or DEFAULT_BACKLINK_LABEL` when injecting a missing footer (`[{label}]({rel_to_index})`).
  - Recognizes both the active configured label and legacy markers (`[← back to index]`, `[← return to index]`, `[← volver al índice]`, `[volver al índice]`) in the last 5 non-empty lines outside code fences.
  - When `canonicalize_legacy=True`, rewrites any recognized legacy marker in the tail to `[{label}]({rel_to_index})` without duplicating horizontal rules (`---`).
- Update `validate_article_content()` in `validation.py` to pass `backlink_label=active_schema.backlink_label` into `normalize_backlink_footer()`.
- Update `check_article_backlinks()` in `lint_organizational.py` to accept both `active_schema.backlink_label` and legacy markers, and update its `actionable` message to suggest `[{active_label}](../INDEX.md)`.

### R-1.3 — Automated migration and template updates
- Update `migrate_wiki()` in `migration.py` to invoke `normalize_backlink_footer(..., backlink_label=active_schema.backlink_label, canonicalize_legacy=True)` so existing Spanish footers migrate cleanly (respecting `dry_run=True` and reporting each updated file).
- Update `src/brain79/templates/SCHEMA.md`, `SCHEMA_GENERAL.md`, `AGENTS.md`, and `SKILL.md` to reference `[← Back to Index](../INDEX.md)` and document optional `backlink_label:` customization.

## Stage 2 — Native multi-harness instruction adapters

Target modules: `src/brain79/core/harnesses/` (`_delimited.py`, `claude_code.py`, `cursor_rules.py`, `copilot.py`, `__init__.py`), `src/brain79/core/init_project.py`, `src/brain79/core/doctor.py`, `src/brain79/cli/dispatch.py`, `src/brain79/templates/`.

### R-2.1 — Shared delimited block engine (`core/harnesses/_delimited.py`)
- Extract common delimited-block management (`sync_delimited_file`, `diagnose_delimited_file`) shared by `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, and `.github/copilot-instructions.md`:
  - Uses `<!-- brain79:start vX.Y.Z -->` and `<!-- brain79:end -->`.
  - Creates the file if missing, replaces only the managed block if markers exist, appends the block if the file exists without markers, and raises `ValueError("corrupted_harness_delimiters: ...")` on mismatched/duplicated markers.
  - Supports `dry_run: bool = False` and idempotent no-op detection.

### R-2.2 — Compact native harness adapters
- Add compact, token-efficient instruction template (~25–35 lines, directing agents to `brain79_orient`, `brain79_session_commit`, `brain79_lint`, and `AGENTS.md` without duplicating the full manual).
- Implement three `HarnessAdapter` classes in `src/brain79/core/harnesses/`:
  1. **`ClaudeCodeAdapter` (`claude_code.py`, `name = "claude_code"`)**: manages `CLAUDE.md` at `project_root`.
  2. **`CursorRulesAdapter` (`cursor_rules.py`, `name = "cursor_rules"`)**: manages `.cursor/rules/brain79.mdc` with Cursor MDC frontmatter (`description`, `alwaysApply: true`) plus delimited block.
  3. **`CopilotAdapter` (`copilot.py`, `name = "copilot"`)**: manages `.github/copilot-instructions.md` with delimited block.
- Register all three in `core/harnesses/__init__.py` alongside `AgentsMdAdapter`, `McpJsonAdapter`, `AntigravityAdapter`, and `CursorAdapter`.

### R-2.3 — Selective harness control and `init` / `update-project` / `doctor` wiring
- Support optional `harnesses: list[str] | None = None` in `init_project()` and CLI `--harnesses` on `brain79 init` (default `"all"`, or comma-separated subset such as `agents,claude,cursor,copilot,agy`).
- Route `init_project()`, `update_project()`, and `doctor.py` (`diagnose_all_harnesses()` + `doctor --fix`) through the full adapter registry so version skew or missing/corrupted delimiters in `CLAUDE.md`, `.cursor/rules/brain79.mdc`, or `.github/copilot-instructions.md` are diagnosed and repaired automatically.
- Ensure `doctor --fix` dirty-working-tree guard checks `CLAUDE.md`, `.cursor/rules/brain79.mdc`, and `.github/copilot-instructions.md` alongside existing protocol files.

## Stage 3 — MCP tool surface compaction (`core` default)

Target modules: `src/brain79/server.py`, `src/brain79/__main__.py`, `tests/test_symmetry.py`, `src/brain79/templates/AGENTS.md`, `src/brain79/templates/SKILL.md`.

### R-3.1 — Compact 8-tool `CORE_TOOLS` surface
- Redefine `CORE_TOOLS` in `server.py` to the 8 hot-path tools:
  1. `brain79_orient`
  2. `brain79_session_commit`
  3. `brain79_read`
  4. `brain79_read_batch`
  5. `brain79_edit`
  6. `brain79_context`
  7. `brain79_search`
  8. `brain79_lint`
- Move the remaining 14 tools into `ADMIN_TOOLS`: `brain79_index`, `brain79_schema`, `brain79_write`, `brain79_write_many`, `brain79_list`, `brain79_ingest`, `brain79_handoff_read`, `brain79_handoff_write`, `brain79_handoff_purge`, `brain79_bootstrap`, `brain79_navigate`, `brain79_migrate`, `brain79_update_project`, `brain79_doctor`.
- Assert invariants: `len(CORE_TOOLS) == 8`, `len(ADMIN_TOOLS) == 14`, `CORE_TOOLS.isdisjoint(ADMIN_TOOLS)`, and `len(CORE_TOOLS | ADMIN_TOOLS) == 22`.

### R-3.2 — Profile-aware server default and instructions
- Change `create_mcp_server(profile: Literal["core", "full"] = "core") -> FastMCP` default to `"core"` and set module-level `mcp = create_mcp_server(profile="core")`.
- Tailor FastMCP `instructions` per profile:
  - Under `core`: do **not** instruct agents to call tools absent from `core` (such as `brain79_schema` or `brain79_write`); direct them to `brain79_orient` (which includes the active schema summary), `brain79_session_commit` (for writes/edits/handoffs), and CLI `brain79 <command>` or `--mcp-profile full` for administrative operations.
  - Under `full`: retain full tool guidance.
- Update `__main__.py`:
  - Resolve profile with precedence: CLI `--mcp-profile <core|full>` > environment variable `BRAIN79_MCP_PROFILE` > default `"core"`.
  - Reject invalid `BRAIN79_MCP_PROFILE` values with a clear error message and exit code `2`.
  - Update `ROOT_HELP` to document `(default: core)` and `BRAIN79_MCP_PROFILE`.

### R-3.3 — Symmetry and token-budget verification
- Update `tests/test_symmetry.py` to assert both profiles explicitly:
  - `create_mcp_server(profile="full")` registers 22 tools with `full_tools ⊆ WHITELIST` and `WHITELIST - full_tools == {"init", "update"}`.
  - `mcp` (default `core`) registers exactly the 8 `CORE_TOOLS`, all present in `full_tools`.

## Stage 4 — Honest positioning and release documentation

Target files: `README.md`, `CHANGELOG.md`, `src/brain79/__init__.py`, `.brain-79/changelog/v0-12-0.md`, `.brain-79/architecture/roadmap-industrial-scale.md`, `.brain-79/architecture/current-state.md`.

### R-4.1 — `README.md` limitations, trade-offs, and updated guides
- Add an explicit `## Limitations and trade-offs` section in `README.md` documenting:
  - Python 3.11+ / `uv` runtime requirement.
  - AST Guard C currently covers Python only (polyglot Tree-sitter extra planned).
  - Protocol compliance relies on agent adherence to instruction files / MCP (passive lifecycle hooks and CI PR gate planned).
  - Multi-developer Git merge collisions on `INDEX.md` and derived JSON caches prior to Phase 12.
  - Deterministic TF-IDF / path retrieval vs. semantic embeddings.
- Document the `core` (8 tools, default) vs. `full` (22 tools, `--mcp-profile full` / `BRAIN79_MCP_PROFILE=full`) MCP profiles and all native instruction harnesses (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md`, `.agents/plugins/brain79/`).

### R-4.2 — `CHANGELOG.md` pre-GA calibration and `v0.12.0` release notes
- Clarify the ADR-017 pre-GA (`0.y.z`) versioning policy at the top of `CHANGELOG.md`.
- Add the `v0.12.0` release entry with explicit migration notes for `--mcp-profile` defaulting to `core` and English backlink migration via `brain79 update-project`.

## Stage 5 — Windows CI latency recovery, self-migration, and parity gates

Target modules: `src/brain79/core/drift.py`, `src/brain79/core/frontmatter.py`, `src/brain79/core/orient.py`, `src/brain79/core/handoff_freshness.py`, `tests/test_battle_gauntlet.py`.

### R-5.1 — `orient()` and `detect_all_drift()` hot-path optimization (Windows CI fix)
- Eliminate the `test_archetype_5_scale_benchmark` Windows CI failure (`orient latency 1780.5ms exceeded ceiling 1500.0ms`) by removing redundant syscalls and allocations introduced in the `v0.11.0` hardening pass:
  - Memoize resolved contained paths inside `WorkspaceIndex` (`drift.py`) and hoist `project_root.resolve()` out of per-file loops in `_resolve_contained_path()` / `compute_applies_to_manifest()`.
  - Replace generic `copy.deepcopy()` in `_PARSE_CACHE` (`frontmatter.py`) with a lightweight recursive cloner for primitive YAML structures (`dict`, `list`, `str`, `int`, `float`, `bool`, `None`, `date`, `datetime`), preserving full cache mutation immunity at lower overhead.
  - Share a single `GitSessionCache` across `orient()` sub-calls (`compute_handoff_freshness`, `detect_all_drift`) to avoid duplicate `git` subprocess spawns on Windows.
- Verify `test_archetype_5_scale_benchmark` passes under the existing `500.0 * perf_factor` ceiling without weakening the benchmark threshold.

### R-5.2 — Self-migration and release verification
- Bump version to `0.12.0` in `src/brain79/__init__.py`.
- Run `brain79 update-project` on the `brain-79` repository itself to migrate `.brain-79/` backlinks to `[← Back to Index](../INDEX.md)` and sync all native harness blocks to `v0.12.0`.
- Run `uv run pytest`, `uv run mypy src tests`, `uv run brain79 lint --strict`, and `uv run brain79 doctor` with zero failures.

## Acceptance criteria

- **AC-11.1**: new articles written via `write_article()` or `commit_session()` and skeletons from `generate_document_skeleton()` default to `[← Back to Index](../INDEX.md)` (or `INDEX.md` for root articles).
- **AC-11.2**: Declaring `backlink_label: "← Return to Hub"` in `SCHEMA.md` causes write normalization, skeleton generation, and `lint` to use and accept `[← Return to Hub](...)`; invalid values fall back safely to `"← Back to Index"`.
- **AC-11.3**: Existing articles using `[← Volver al Índice](../INDEX.md)` still pass `brain79 lint --strict` without errors; running `brain79 migrate` (with `dry_run=False`) rewrites them deterministically to `[← Back to Index](../INDEX.md)` and is idempotent on re-run.
- **AC-11.4**: `brain79 init` creates delimited protocol blocks in `CLAUDE.md`, `.cursor/rules/brain79.mdc` (with valid MDC frontmatter `alwaysApply: true`), and `.github/copilot-instructions.md` alongside `AGENTS.md` and MCP configs.
- **AC-11.5**: Running `init` or `update-project` against pre-existing `CLAUDE.md`, `.cursor/rules/brain79.mdc`, or `.github/copilot-instructions.md` preserves 100% of custom user content outside the `<!-- brain79:start ... -->` / `<!-- brain79:end -->` delimiters; corrupted delimiters raise `ValueError` and are reported as `error` by `doctor`.
- **AC-11.6**: `brain79 init --harnesses agents,claude` installs only the requested adapters; `brain79 doctor` diagnoses all active adapters and `doctor --fix` repairs stale or missing blocks.
- **AC-11.7**: `create_mcp_server()` (default) and `brain79` (no flags) start in `core` profile exposing exactly the 8 `CORE_TOOLS`; `--mcp-profile full` and `BRAIN79_MCP_PROFILE=full` expose all 22 tools; CLI flag overrides env var; invalid values exit `2`.
- **AC-11.8**: `core` server instructions never reference tools absent from `CORE_TOOLS`; `tests/test_symmetry.py` validates both `core` (8 tools) and `full` (22 tools) parity against `WHITELIST`.
- **AC-11.9**: `README.md` contains an explicit `## Limitations and trade-offs` section and documents `core`/`full` profiles and native harnesses; `CHANGELOG.md` documents the ADR-017 pre-GA policy and `v0.12.0` migration notes.
- **AC-11.10**: `tests/test_battle_gauntlet.py::test_archetype_5_scale_benchmark` passes within the `500.0 * perf_factor` `orient()` latency ceiling (including Windows CI runners) while preserving full `_PARSE_CACHE` deep-clone isolation and `_resolve_contained_path()` symlink containment.
- **AC-11.11**: the `brain-79` repository itself is synchronized to `v0.12.0` (English backlinks migrated, harnesses synced) and passes `uv run pytest`, `uv run mypy src tests`, `uv run brain79 lint --strict`, and `uv run brain79 doctor` with exit code `0`.

---

[← Back to Index](../INDEX.md)
