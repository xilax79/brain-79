---
type: feature
summary: non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP setup, and brain79 doctor diagnostics
status: planned
version: 0.9.0
applies_to:
  - src/brain79/core/init_project.py
  - src/brain79/core/migration.py
  - src/brain79/cli/dispatch.py
  - src/brain79/server.py
  - src/brain79/core/orient.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/symmetry.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
last_updated: 2026-11-13
applies_to_digest: "sha256:ed67e7a5ea78462b"
applies_to_count: 5
---

# Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics

## Overview

This document defines the project protocol upgrade and multi-harness doctor subsystem, resolving the **"Split-Brain" version skew problem** when the global `brain79` binary is updated while existing project repositories still host older `AGENTS.md`, `SCHEMA.md`, `.mcp.json`, git hooks, and legacy wiki articles.

It establishes a non-destructive project protocol upgrader (`brain79 update-project` / `brain79 init --upgrade`), a resilient 2-tier multi-harness MCP registration model, deterministic wiki reconditioning (`migrate_wiki` v2), and the `brain79 doctor` diagnostic engine with 1:1 CLI and MCP symmetry.

---

## Problem statement

### 1. The "split-brain" project skew problem
When `brain79 init` runs on a project under an older version, static protocol files (`AGENTS.md`, `.brain-79/SCHEMA.md`, `.git/hooks/pre-commit`, `.mcp.json`) are stamped into the repository. When the global `brain79` binary is later upgraded:
- Calling `brain79 init` on an existing project aborts with `"Wiki already exists... Delete .brain-79/ manually"`, leaving `AGENTS.md` and `SCHEMA.md` frozen on obsolete instructions.
- Overwriting `AGENTS.md` or `SCHEMA.md` blindly destroys user-authored project notes, custom persona directives, or custom folder/field declarations (`custom_types:`) in `SCHEMA.md`.

### 2. Incomplete reconditioning in `migration.py`
Existing `src/brain79/core/migration.py` has 3 mechanical gaps when reconditioning a wiki:
1. **Early exit on existing `type` and `summary`**: If an article already possesses `type` and `summary`, `migrate_wiki` skips it immediately—leaving missing backlink footers, unnormalized bullet colons, or missing type-specific required fields uncorrected.
2. **Semantic structure exemption vs. strict section linting**: Articles imported or written before strict section enforcement that lack specific H2 headings (e.g. `## Consequences` in an ADR) need automatic assignment to `status: legacy` / `stability: legacy` so `lint --strict` exempts them until an agent or engineer edits them, rather than inventing fake prose sections.
3. **Authority decay and handoff invalidation (ADR-016)**: Mass-migrating articles alters `compute_wiki_digest(wiki_root)`, turning active handoffs `stale`. The upgrader must provide an explicit `--commit-transition` path so authority decay does not leave agents with a stale handoff after a maintenance upgrade.

### 3. Multi-harness scope and portability hazards in `init_project.py`
- **Portability bug in current `init_project.py`**: Currently, `init_project.py` resolves `binary_path = shutil.which("brain79") or "brain79"` and writes machine-specific absolute paths (e.g. `/Users/xilax/.local/bin/brain79`) into `.mcp.json` and `.agents/mcp_config.json`. When another developer on Linux or Windows clones the repository, their MCP client fails with `ENOENT`.
- **Harness proliferation and maintenance boundaries**: Project-level tools must automate portable project-level files inside the repository (Tier 1) and keep user-level desktop GUI configurations outside the repository informational by default with explicit opt-in (`--include-desktop`, Tier 2).

---

## Architectural design (5 pillars)

### Pillar 1: Delimited managed blocks in `AGENTS.md` and schema preservation
1. **Managed block markers in `AGENTS.md`:**
   - Wrap the core protocol template (`src/brain79/templates/AGENTS.md`) inside versioned HTML comment delimiters:
     ```markdown
     <!-- brain79:start v{{VERSION}} -->
     # Brain-79 AI memory protocol
     ...
     <!-- brain79:end -->
     ```
     When rendering the template during `init`, `update-project`, or `doctor --fix`, replace `{{VERSION}}` dynamically with `brain79.__version__` (and keep root `./AGENTS.md` synchronized with active `__version__`).
   - **Parser and synchronization rules (`sync_agents_manifest`)**:
     - **Tolerant regex**: Match delimiters using whitespace-insensitive patterns: `r"<!--\s*brain79:start(?:\s+v?([0-9]+\.[0-9]+\.[0-9]+))?\s*-->"` and `r"<!--\s*brain79:end\s*-->"`.
     - **Corruption guard**: If an opening `brain79:start` marker exists without a matching `brain79:end` marker (or vice versa), **abort with an actionable error** (`corrupted_agents_manifest_delimiters`) rather than guessing or truncating user content.
     - **Idempotence and byte-level preservation**: Replacing the delimited block must preserve 100% of user content before `<!-- brain79:start ... -->` and after `<!-- brain79:end -->` (persona overrides, custom rules, project notes).
     - **Markerless fallback**: If no delimiters exist in an existing `AGENTS.md`, locate `# Brain-79 AI memory protocol` and replace up to `## Project notes` (or end of file), wrapping the managed section in standard delimiters while preserving `## Project notes` and everything outside the block. If `# Brain-79 AI memory protocol` is absent, append the delimited block at the end of `AGENTS.md`.

2. **Non-destructive `SCHEMA.md` upgrade (`sync_schema_file`):**
   - **Template bump**: update `src/brain79/templates/SCHEMA.md` and `SCHEMA_GENERAL.md` to declare `schema_version: 2` in their YAML frontmatter.
   - **Frontmatter preservation**: Parse existing `.brain-79/SCHEMA.md` frontmatter first. Retain `profile` (`software` or `general`), `custom_types:`, and any user-defined frontmatter keys, stamping `schema_version: 2` and `last_updated: <today>`.
   - **Body preservation**: update core normative tables and rules from the active profile template (`SCHEMA.md` or `SCHEMA_GENERAL.md`). If the existing `.brain-79/SCHEMA.md` contains a `## Project-specific schema extensions` section (or any content following that heading), preserve that trailing section intact at the end of the upgraded file.

---

### Pillar 2: Resilient 2-tier multi-harness MCP registration
Harness integration is partitioned into two tiers to guarantee cross-developer portability and CI testability:

#### Tier 1: Project-level auto-registration (automated by default on `init` and `update-project`)
Configures and updates exactly 3 standardized project-level files within the repository root via non-destructive JSON merging (`sync_project_mcp_configs`):
1. `.mcp.json` — Universal standard (**Pi**, **Claude Code CLI**, **OpenCode**, **Zed**): sets `"mcpServers.brain79"` with `{"command": "brain79", "args": ["--project-root", "."], "toolPrefix": "none"}`.
2. `.agents/mcp_config.json` — **Antigravity (`agy`)** standard: sets `"mcpServers.brain79"` with `{"command": "brain79", "args": ["--project-root", "."]}`.
3. `.cursor/mcp.json` — **Cursor IDE** project standard: sets `"mcpServers.brain79"` with `{"command": "brain79", "args": ["--project-root", "."]}`.

**Cross-platform portability and sanitization invariants:**
- Committed Tier 1 configs must **always** use the portable literal `"command": "brain79"` (never `shutil.which("brain79")` or absolute paths like `/Users/...` or `/home/...`).
- **Legacy absolute path sanitization**: when `update-project` or `doctor --fix` inspects any of the 3 Tier 1 files and finds `"command"` set to an absolute path ending in `/brain79` or `\brain79.exe`, it automatically normalizes `"command"` to `"brain79"`.
- **Non-destructive JSON merge**: all 3 Tier 1 files must be parsed as JSON objects, preserving 100% of other keys and third-party servers under `"mcpServers"`. If an existing file contains malformed JSON, back it up to `<filename>.bak` before writing a clean configuration.

#### Tier 2: Machine-level desktop harness integration (informational by default, opt-in via `--include-desktop`)
Covers user-level OS desktop configs outside the repository:
- **Claude Desktop**: macOS `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows `%APPDATA%\Claude\claude_desktop_config.json`, Linux `~/.config/Claude/claude_desktop_config.json`.
- **Windsurf**: `~/.codeium/windsurf/mcp_config.json`.
1. **Default mode (safe and read-only outside repo)**: `init` and `update-project` never mutate files outside `project_root` unless `--include-desktop` is passed. `brain79 doctor` checks if parent directories of these desktop configs exist and reports an informational snippet if unconfigured.
2. **Opt-in mode (`--include-desktop`)**: when passed to `update-project --include-desktop` or `doctor --fix --include-desktop` (or via custom config dir override in tests):
   - Creates a `.bak` backup of the target JSON file before mutating.
   - Merges a project-scoped entry `"brain79-<project_root.name>"` under `"mcpServers"` using the resolved absolute binary path (`shutil.which("brain79") or "brain79"`) and `"args": ["--project-root", "<abs_project_root>"]`, preserving all existing third-party servers.

---

### Pillar 3: Respectful Git hook integration (`sync_git_hooks`)
When inspecting `.git/hooks/pre-commit`:
1. If `.git` does not exist (e.g. `profile: general` without Git), skip silently.
2. If `.git/hooks/pre-commit` does not exist, write `PRE_COMMIT_HOOK_SCRIPT` with LF line endings and executable permissions (`mode | 0o111`).
3. If `.git/hooks/pre-commit` exists and contains `# brain-79 pre-commit hook`, update it in place to the latest `PRE_COMMIT_HOOK_SCRIPT`.
4. **Third-party hook manager preservation**: If `.git/hooks/pre-commit` exists and **lacks** `# brain-79 pre-commit hook` (or contains signatures for **Husky** `husky`, **pre-commit** `pre-commit.com`, **Lefthook** `lefthook`, or **Overcommit** `overcommit`), **never overwrite it**. Return a structured advisory notice explaining how to add `brain79 --project-root . lint --strict` to the existing hook pipeline.

---

### Pillar 4: Deterministic two-tier wiki reconditioning (`migrate_wiki` v2)
1. **Full-pass inspection (no blind early exit)**:
   For every markdown article in `.brain-79/` (excluding `INDEX.md`, `SCHEMA.md`, `_raw/`, `.locks/`), even if `type` and `summary` already exist:
   - **Step A — Required fields completion**: ensure `type` (inferred from location if missing), `last_updated`, and all type-specific defaults from `_TYPE_DEFAULTS` / `ActiveSchema` are present. Missing `summary` on indexable types is populated via `extract_title_and_summary` + `sanitize_summary`.
   - **Step B — Semantic structure & size exemption (Tier 2)**: If an article has an active status/stability (`accepted`, `shipped`, `stable`, `active`) but fails `check_missing_sections(body, target_type, schema)` or exceeds `MAX_ARTICLE_LINES` / `MAX_ARTICLE_BYTES`, automatically transition its `status` or `stability` to `legacy` so `lint --strict` exempts it without inventing artificial prose.
   - **Step C — Mechanical body & summary normalization (Tier 1)**: Apply `sanitize_summary(meta["summary"])`, `normalize_backlink_footer(body, rel_str)` (which appends `[← Volver al Índice](../INDEX.md)` on subfolder articles, avoids `../INDEX.md` on root files, and never duplicates existing backlinks), and `normalize_bullet_colons(body)`.
   - **Step D — Merkle digest seeding**: If `applies_to` is present, compute and stamp `applies_to_digest`, `applies_to_count`, and update `.drift_manifest.json`.
   - **Idempotence**: Only write to disk and append to `changes` if the resulting normalized content differs from the on-disk content.
2. **Handoff freshness transition (`--commit-transition`)**:
   - In `update-project` (and `doctor --fix`), if protocol or wiki files were modified and `--commit-transition` (`commit_transition=True`) is supplied, automatically write a fresh maintenance handoff (`session_type="maintenance"`, `summary=f"Upgraded project protocol and reconditioned wiki to brain79 v{__version__}"`, `boot_instruction="Project protocol and wiki reconditioned; proceed with active tasks."`) so the latest handoff remains `fresh` under ADR-016.

---

### Pillar 5: Project upgrader, `brain79 doctor`, and 1:1 CLI/MCP symmetry

#### 1. Symmetry contract (`tests/test_symmetry.py`)
Both new operational capabilities are exposed with 1:1 CLI and MCP parity (updating `EXPECTED_CLI_SUBCOMMANDS` from 22 to 24 and `EXPECTED_MCP_TOOLS` from 20 to 22):
- **Project Upgrader**:
  - CLI: `brain79 update-project [--dry-run] [--commit-transition] [--include-desktop]` (plus `brain79 init --upgrade` as an alias that invokes `update_project`). Calling `brain79 init` on an already-initialized wiki prints a clear message suggesting `brain79 update-project` (or runs it when `--upgrade` is passed).
  - MCP: `brain79_update_project(dry_run: bool = False, commit_transition: bool = False, include_desktop: bool = False)`
- **Diagnostic Doctor**:
  - CLI: `brain79 doctor [--fix] [--force] [--include-desktop] [--format text|json]`
  - MCP: `brain79_doctor(fix: bool = False, force: bool = False, include_desktop: bool = False, format: str = "text")`

#### 2. Passive protocol skew alert in `orient()`
When `orient()` runs, it performs a lightweight check (`check_protocol_version_skew(project_root, wiki_root)`): if `AGENTS.md` lacks `brain79:start` or declares a version older than `brain79.__version__`, or if `.brain-79/SCHEMA.md` has `schema_version < 2`, `orient()` includes a non-blocking one-line notice:
`> ℹ️ **Protocol update available**: Project templates predate brain79 v{__version__}. Run 'brain79 update-project' to sync AGENTS.md and SCHEMA.md.`

#### 3. Diagnostic engine (`src/brain79/core/doctor.py`)
Inspects 7 operational health categories in $<50\text{ ms}$:
1. `binary_and_environment`: CLI binary resolution in `$PATH` and Python runtime version.
2. `protocol_sync`: `AGENTS.md` delimiter integrity + version parity (`v{__version__}`) and `.brain-79/SCHEMA.md` `schema_version == 2`.
3. `wiki_structure`: Required profile directories, valid `INDEX.md` routing table, and 0 unmigrated articles.
4. `mcp_harnesses`: Presence, valid JSON, and portable `"command": "brain79"` (no hardcoded machine paths) across `.mcp.json`, `.agents/mcp_config.json`, and `.cursor/mcp.json` (plus informational status for Tier 2 desktop configs).
5. `locks_and_filesystem`: Write/acquire probe in `.brain-79/.locks/` and absence of legacy inline `.lock` files.
6. `git_hooks`: Profile-aware check of `.git/hooks/pre-commit` (executable `# brain-79 pre-commit hook`, or informational advisory if Husky/pre-commit is detected; skipped cleanly on gitless `general` profile).
7. `handoff_hygiene`: Freshness state of latest handoff and warning if unpurged handoff count exceeds threshold (`> 10`).

**Exit codes, JSON schema, and Git-aware `--fix` safety guard:**
- CLI exit codes: `0` (all checks `ok`), `1` (any check `error`, or `--fix` blocked by dirty working tree), `2` (any check `warning` with `0` errors).
- JSON output (`--format json` / `format="json"`): returns deterministic JSON `{"status": "ok"|"warning"|"error", "exit_code": 0|1|2, "checks": [{"category": ..., "status": ..., "message": ..., "actionable": ...}], "fixed": [...]}`.
- **Git-aware `--fix` safety guard**: when `fix=True` is called without `force=True`, if `is_git_workspace(project_root)` is `True`, run `git status --porcelain -- AGENTS.md .brain-79 .mcp.json .agents/mcp_config.json .cursor/mcp.json`. If any of those protocol paths have uncommitted changes, abort `--fix` with status `error` (`dirty_working_tree`) and instruct the user to commit/stash or pass `--force` (`force=True`). In gitless `general` workspaces, `--fix` proceeds without requiring Git. When `fix=True` executes, it runs `update_project()` + `migrate_wiki()` and re-evaluates all 7 checks.

---

## Acceptance criteria and verification gates

| ID | Criterion | Verification Test |
|---|---|---|
| **AC-1** | **Non-destructive `AGENTS.md` sync & corruption guard**: `sync_agents_manifest()` updates the `<!-- brain79:start v{__version__} -->`...`<!-- brain79:end -->` block while preserving 100% of custom text before and after; converts markerless legacy `AGENTS.md` preserving `## Project notes`; aborts with `corrupted_agents_manifest_delimiters` if an opening marker lacks a closing marker. | `test_sync_agents_manifest_preserves_user_content_and_guards_corruption` |
| **AC-2** | **Non-destructive `SCHEMA.md` upgrade**: `sync_schema_file()` upgrades `schema_version` to `2` while preserving `profile` (`software` or `general`), `custom_types:` in YAML frontmatter, and `## Project-specific schema extensions` in the body. | `test_sync_schema_file_preserves_custom_types_and_extensions` |
| **AC-3** | **Portable Tier 1 MCP configs & Tier 2 opt-in backup**: `init` and `update-project` create/merge `.mcp.json`, `.agents/mcp_config.json`, and `.cursor/mcp.json` using portable `"command": "brain79"`, preserving third-party `mcpServers`, and sanitizing any legacy `/Users/.../brain79` absolute paths. Tier 2 (`--include-desktop`) creates a `.bak` backup and registers `"brain79-<project>"` only when explicitly requested. | `test_tier1_portable_mcp_configs_and_tier2_opt_in_backup` |
| **AC-4** | **Respectful Git hook integration**: `sync_git_hooks()` installs/updates `# brain-79 pre-commit hook`, but never overwrites existing Husky, `pre-commit`, Lefthook, or custom hooks lacking the brain-79 marker, returning an actionable integration notice instead. | `test_git_hook_preserves_third_party_managers` |
| **AC-5** | **Full-pass `migrate_wiki` v2 & `--commit-transition`**: `migrate_wiki()` repairs missing backlinks, bullet colons, and missing required fields even on articles that already have `type` and `summary`; assigns `status: legacy` / `stability: legacy` to active articles missing required H2 sections; and `update-project --commit-transition` emits a `fresh` maintenance handoff. | `test_migrate_wiki_v2_full_pass_and_commit_transition` |
| **AC-6** | **Passive skew alert in `orient()`**: `orient()` emits the `Protocol update available` one-line banner when `AGENTS.md` version or `SCHEMA.md` `schema_version` lags behind the running binary, and emits no banner once `update-project` has run. | `test_orient_protocol_skew_banner` |
| **AC-7** | **`brain79 doctor` diagnostics, exit codes (`0/1/2`), and `--fix` safety guard**: `doctor` evaluates all 7 categories in `< 50ms`, supports `--format json`, returns exit codes `0` (clean), `2` (skew/warning), `1` (error), blocks `--fix` on uncommitted protocol files unless `--force` is set, and heals skewed projects to exit code `0` when `--fix` runs. | `test_doctor_diagnostics_exit_codes_and_fix_safety_guard` |
| **AC-8** | **1:1 CLI/MCP symmetry & version governance**: `update-project` / `brain79_update_project` and `doctor` / `brain79_doctor` pass all parameter and count assertions in `tests/test_symmetry.py` (24 CLI subcommands, 22 MCP tools), and `brain79` version is bumped to `0.9.0` with full release parity. | `tests/test_symmetry.py` & `tests/test_version_governance.py` |

---

[← Volver al Índice](../INDEX.md)
