---
type: architecture
summary: technical specification for zero-config Antigravity (agy) plugin initialization, progressive AGENTS.md disclosure, and ancestor root resolution
stability: experimental
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/init_project.py
  - src/brain79/core/doctor.py
  - src/brain79/config.py
  - src/brain79/__main__.py
  - src/brain79/cli/dispatch.py
  - src/brain79/templates/AGENTS.md
related:
  - architecture/roadmap-industrial-scale.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - decisions/adr-013-versioning-and-release-governance.md
last_updated: 2026-11-16
applies_to_digest: "sha256:557d554469f81d87"
applies_to_count: 6
---

# Architecture — Antigravity (agy) plugin initialization and progressive disclosure

## Overview

`brain79 init` configures `.mcp.json`, `.cursor/mcp.json`, and `.agents/mcp_config.json`. However, Antigravity CLI (`agy`) ignores `.agents/mcp_config.json` and only loads MCP servers from `~/.gemini/config/mcp_config.json` or from plugins under `.agents/plugins/<name>/`. In addition, the `AGENTS.md` template (`13,439` bytes) consumes roughly `15–18%` of `agy`'s `20,000`-token rules budget on every turn and tells `agy` users to configure `.mcp.json`. Finally, `parse_global_flags()` resolves `--project-root .` to `Path.cwd().resolve()`, causing `agy` sessions launched inside subdirectories to miss `<repo-root>/.brain-79/`.

This specification defines the complete engineering design to make `brain79 init`, `brain79 update-project`, and `brain79 doctor` work out of the box for `agy` while maintaining full backward compatibility.

---

## Native Antigravity plugin scaffolding

Modify `sync_project_mcp_configs()` in `src/brain79/core/init_project.py` to generate a workspace plugin under `<project_root>/.agents/plugins/brain79/`:

```text
.agents/
├── mcp_config.json                  # Retained for backward compatibility
└── plugins/
    └── brain79/
        ├── plugin.json              # Antigravity plugin marker
        ├── mcp_config.json          # Portable stdio MCP registration
        └── skills/
            └── brain79-wiki/
                └── SKILL.md         # On-demand CLI/MCP operational manual
```

### File contracts

1. **`.agents/plugins/brain79/plugin.json`**:
   - If missing, write `{"name": "brain79"}\n` (2-space indent, UTF-8, `\n` line endings).
   - If present and valid JSON object: preserve all user-defined fields (such as `"disabled"`, `"author"`, or `"homepage"`) and set `"name": "brain79"` only when `"name"` is missing or empty.
   - If corrupt JSON or non-dict JSON: back up to `plugin.json.bak` and recreate `{"name": "brain79"}\n`.
2. **`.agents/plugins/brain79/mcp_config.json`**:
   - Use the exact same merge, sanitization, and `.bak` backup logic as `.mcp.json` (preserving any third-party entries in `mcpServers`).
   - Upsert `mcpServers["brain79"] = {"command": "brain79", "args": ["--project-root", "."]}` (do not add `toolPrefix`; `agy` only expects `command` and `args`).
3. **`.agents/plugins/brain79/skills/brain79-wiki/SKILL.md`**:
   - Load from a new package template `src/brain79/templates/SKILL.md` via `importlib.resources.files("brain79.templates")`.
   - Replace `{{VERSION}}` if present and write only when missing or content differs.
4. **Dry-run and packaging parity**:
   - When `dry_run=True`, `sync_project_mcp_configs()` must not create `.agents/plugins/` directories or write files, and must still append changed relative paths (`".agents/plugins/brain79/plugin.json"`, `".agents/plugins/brain79/mcp_config.json"`, `".agents/plugins/brain79/skills/brain79-wiki/SKILL.md"`) to the returned `changed` list.
   - Verify `pyproject.toml` keeps `"src/brain79/templates" = "brain79/templates"` under `[tool.hatch.build.targets.wheel.shared-data]` so `SKILL.md` ships in wheels.
   - Update `init_project()` stdout output to report `.agents/plugins/brain79/`.

### Backward compatibility rules

- **Retain `.agents/mcp_config.json`**: keep generating and sanitizing `.agents/mcp_config.json` inside `sync_project_mcp_configs()`. `agy` ignores it safely, while legacy scripts, third-party tools, and existing tests continue to pass without breaking.
- **Keep `--include-desktop` scoped**: do not write `brain79-<project_name>` entries into `~/.gemini/config/mcp_config.json`. Global `agy` registration would launch every project's server across all unrelated `agy` sessions; `agy` uses the workspace plugin instead.

---

## Progressive disclosure for manifests and skills

Split `src/brain79/templates/AGENTS.md` (`13,439` bytes) into an `always_on` root manifest (`<= 6,500` bytes) and an on-demand Antigravity skill (`src/brain79/templates/SKILL.md`):

### Always-on `AGENTS.md` template requirements

- **Size cap**: `<= 6,500` bytes (under `agy`'s `24,000`-byte per-file limit and less than half the prior token footprint).
- **Mandatory compatibility anchors** (must remain verbatim so `sync_agents_manifest()` and existing tests stay green):
  - `<!-- brain79:start v{{VERSION}} -->` and `<!-- brain79:end -->`
  - `# Brain-79 AI memory protocol`
  - `pi-mcp-adapter` (inside the `pi` prerequisite bullet)
  - `brain79_index` (mentioned as index-only fallback or quick lookup)
  - `No-Op Idempotence` and `Zero-Modification Rule` (in the session knowledge triage rule)
  - `## Project notes` (outside the delimited block at the bottom)
- **Corrected `agy` prerequisite line**:
  - Separate `agy` from `.mcp.json`: state that `brain79 init` configures `.agents/plugins/brain79/` automatically for `agy` (or register globally once via `agy mcp add brain79 -- brain79 --project-root .`), while `opencode`, `claude`, and `cursor` use `.mcp.json` or `.cursor/mcp.json`.
- **Retained core rules**: cold start (`brain79_orient`, `brain79_bootstrap`), on-demand handoff policy and freshness decay, session knowledge triage (Amnesia Test Type A/B/C), atomic `brain79_session_commit`, `brain79_lint`, clean B2 prose, sentence case policy, and a pointer to the `brain79-wiki` skill (or `brain79 schema` / `brain79 --help`) for detailed command tables.

### On-demand `src/brain79/templates/SKILL.md` requirements

- Must begin with valid Antigravity skill YAML frontmatter:
  - `name: brain79-wiki`
  - `description`: concise third-person trigger describing when to load the skill (for example, authoring or migrating `.brain-79/` articles, resolving `brain79 lint` diagnostics, running `brain79_session_commit`, or checking CLI/MCP flags).
- Must contain the detailed reference sections moved out of `AGENTS.md`:
  1. Complete MCP-to-CLI core operations table (16 operations).
  2. Organizational enforcement and governance table (`lint`, `migrate`, `navigate`, `handoff-purge`).
  3. Canonical `brain79_session_commit` JSON example and 3-call fallback recipe.
  4. Frontmatter `summary:` and backlink footer conventions.
  5. Lint repair workflow, `migrate` safety rules, and `force_validation_skip` usage.

---

## Ancestor root resolution and init isolation

Fix subdirectory execution when MCP clients (including `.agents/plugins/brain79/mcp_config.json`) pass `--project-root .`:

1. **`src/brain79/__main__.py` (`parse_global_flags`)**:
   - Inspect the raw argument passed to `--project-root` (both `--project-root <val>` and `--project-root=<val>`).
   - If the raw value is `"."` or `"./"`, treat it as dynamic working-directory discovery: do **not** call `config.set_project_root(Path(".").resolve())`; leave `_project_root` as `None`.
   - For any other path value, resolve it and call `config.set_project_root(project_root)` as before.
2. **`src/brain79/config.py` (`get_project_root`)**:
   - Resolution order:
     1. Explicit `_project_root` (when set by non-dot `--project-root` or `set_project_root()`).
     2. `BRAIN79_PROJECT_ROOT` environment variable (resolved directly without upward walk).
     3. Ancestor walk from `cwd = Path.cwd().resolve()`:
        - If `(cwd / ".brain-79").is_dir()`, return `cwd`.
        - If `(cwd / ".git").exists()`, stop immediately and return `cwd` (prevents nested Git repositories without `.brain-79/` from escaping into a parent repository).
        - Iterate over `cwd.parents`: if `(parent / ".brain-79").is_dir()`, return `parent`; if `(parent / ".git").exists()`, stop after checking `parent` and fall back to `cwd`.
        - If no `.brain-79/` is found in any ancestor, return `cwd`.
3. **`src/brain79/cli/dispatch.py` (`cmd == "init"`)**:
   - When `parsed.project_root` is `None`, set `target_root = Path.cwd().resolve()` directly instead of calling `get_project_root()`.
   - This guarantees `brain79 init` inside a new subdirectory initializes a fresh `.brain-79/` locally instead of detecting a parent directory's wiki and aborting with `"Wiki already exists"`.

---

## Doctor diagnostics and upgrade parity

Update `src/brain79/core/doctor.py` to validate and repair the `agy` plugin alongside legacy harnesses:

1. **Dirty working tree guard (`run_doctor(..., fix=True)`)**:
   - Add `".agents/plugins/brain79"` to the `git status --porcelain -- ...` path list.
2. **`mcp_harnesses` diagnostic check**:
   - Check `.mcp.json`, `.cursor/mcp.json`, `.agents/mcp_config.json`, `.agents/plugins/brain79/plugin.json`, `.agents/plugins/brain79/mcp_config.json`, and `.agents/plugins/brain79/skills/brain79-wiki/SKILL.md`.
   - Validate that `plugin.json` is a JSON object with a non-empty `"name"`, `mcp_config.json` defines `mcpServers.brain79.command == "brain79"`, and `SKILL.md` exists and is non-empty.
   - If `.agents/mcp_config.json` exists while `.agents/plugins/brain79/plugin.json` is missing, report `warning` with actionable hint: `"Run 'brain79 update-project' or 'brain79 doctor --fix' to register the Antigravity (agy) plugin at .agents/plugins/brain79/."`
3. **Automatic upgrade path**:
   - Because `update_project()` already calls `sync_agents_manifest()` and `sync_project_mcp_configs()`, running `brain79 update-project`, `brain79 init --upgrade`, or `brain79 doctor --fix` upgrades existing projects non-destructively.

---

## Version governance and verification

- Bump `__version__` in `src/brain79/__init__.py` from `"0.9.0"` to `"0.9.1"`, and synchronize `README.md`, root `CHANGELOG.md`, and `.brain-79/changelog/v0-9-1.md` per ADR-013 (`tests/test_version_governance.py`).
- Add and update tests across `tests/test_init_project.py`, `tests/test_project_upgrade_and_doctor.py`, and `tests/test_cli.py` covering:
  1. Fresh `init_project()` creation of `.agents/plugins/brain79/{plugin.json, mcp_config.json, skills/brain79-wiki/SKILL.md}` plus legacy `.agents/mcp_config.json`.
  2. Non-destructive re-run preserving custom keys in `plugin.json` (including `"disabled": true`) and third-party `mcpServers` in `mcp_config.json`.
  3. Corrupt JSON `.bak` backup recovery for both `plugin.json` and `mcp_config.json`.
  4. `dry_run=True` creating zero files or directories under `.agents/plugins/brain79/`.
  5. `AGENTS.md` size `<= 6,500` bytes with all required compatibility anchors intact.
  6. Subdirectory root walk-up via `parse_global_flags(["--project-root", "."])`, `.git` nested-repo isolation, and `brain79 init` local-directory isolation.
  7. `doctor` warning on missing `.agents/plugins/brain79/` and repair via `doctor --fix`.
- Verification gate: `pytest`, `mypy src/`, and `brain79 lint --strict` must all pass with exit code `0`.

---

[← Back to Index](../INDEX.md)
