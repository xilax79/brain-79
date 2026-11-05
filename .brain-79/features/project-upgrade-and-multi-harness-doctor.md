---
type: feature
summary: non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP setup, and brain79 doctor diagnostics
status: planned
version: 2.1.0
applies_to:
  - src/brain79/core/init_project.py
  - src/brain79/core/migration.py
  - src/brain79/core/orient.py
  - src/brain79/cli/dispatch.py
  - src/brain79/server.py
  - src/brain79/templates/AGENTS.md
  - src/brain79/templates/SCHEMA.md
  - src/brain79/templates/SCHEMA_GENERAL.md
related:
  - architecture/roadmap-industrial-scale.md
  - features/cross-platform-and-lock-isolation.md
last_updated: 2026-11-05
---

# Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics (Phase 7 specification)

## Overview

This specification defines **Phase 7 of the Industrial-Scale Roadmap**: solving the **"Split-Brain" version skew problem** when the global `brain79` binary is upgraded while existing project repositories still contain older `AGENTS.md`, `SCHEMA.md`, `.mcp.json`, git hooks, and v1.x wiki articles. It also introduces zero-config multi-harness MCP registration and the `brain79 doctor` diagnostic command.

---

## Problem statement

### 1. The "split-brain" project skew problem
When `brain79 init` is run on a project under v1.0/v1.1, static protocol files (`AGENTS.md`, `.brain-79/SCHEMA.md`, `.git/hooks/pre-commit`, `.mcp.json`) are stamped into the workspace. When the user later upgrades the `brain79` binary to v2.0+:
- Calling `brain79 init` on an existing project immediately exits (`"Wiki already exists... Delete .brain-79/ manually"`), leaving `AGENTS.md` and `SCHEMA.md` frozen on v1.0 instructions.
- Overwriting `AGENTS.md` or `SCHEMA.md` blindly would destroy user-authored project notes in `AGENTS.md` or custom folder declarations (`custom_types:`) in `SCHEMA.md`.

### 2. Incomplete reconditioning of older wikis (`migration.py` gaps)
Inspecting `src/brain79/core/migration.py` reveals 3 gaps when upgrading a v1.x wiki to v2.0+:
1. **Early Exit on Existing `type` & `summary` (Lines 130–141):** If a v1.0 article already has `type` and `summary`, `migrate_wiki` skips it immediately—even if it is missing its footer backlink (`[← Volver al Índice](../INDEX.md)`), has a broken root `../INDEX.md` link in `SCHEMA.md`, or is missing another required field.
2. **Legacy Prose in `INDEX.md`:** Wikis created before ADR-008 still have `## Project` or `## Roadmap` sections in `INDEX.md`, or lack the `type: navigation` frontmatter header.
3. **Semantic Content Preservation vs. Mechanical Normalization:** Mechanical envelope attributes (frontmatter defaults, `summary`, backlink footers, `INDEX.md` routing table, `.locks/` cleanup) **can and must** be upgraded deterministically, whereas inventing prose sections (`## Context`, `## Consequences`) must **never** be done by a mechanical script (instead, those articles receive `status: legacy` so `lint` exempts them until an agent edits them).

### 3. Multi-harness and GUI client PATH failures
- Desktop GUI clients (Claude Desktop, Cursor, Windsurf, VS Code) on macOS/Windows do not inherit interactive shell `$PATH` (`~/.local/bin`), causing `"command": "brain79"` in `.mcp.json` to fail with `spawn brain79 ENOENT`.
- Different harnesses read different config locations (`.mcp.json`, `.cursor/mcp.json`, `.agents/mcp_config.json`).

---

## Architecture and design (4 pillars)

### Pillar 1: Delimited managed blocks in `AGENTS.md` and non-destructive `SCHEMA.md` sync
1. **Managed Block Markers in `AGENTS.md`:**
   Wrap `src/brain79/templates/AGENTS.md` in explicit versioned HTML comment delimiters:
   ```markdown
   <!-- brain79:start v2.0.1 -->
   # Brain-79 AI Memory Protocol
   ...
   <!-- brain79:end -->
   ```
   - **Upgrade Behavior (`sync_agents_manifest`):**
     - If `AGENTS.md` contains `<!-- brain79:start ... -->` ... `<!-- brain79:end -->`, replace **only** the delimited block with the current template version, preserving 100% of user content before and after the block.
     - If `AGENTS.md` comes from v1.x (lacking markers, containing `# Brain-79 AI Memory Protocol`), locate the `# Brain-79 AI Memory Protocol` section up to `## Project notes` (preserving whatever the user wrote under `## Project notes`) and upgrade it into the delimited block.
2. **Non-Destructive `SCHEMA.md` Upgrade (`sync_schema_file`):**
   - Add `schema_version: "2.0"` (or `brain79_version`) to the YAML frontmatter of `SCHEMA.md` / `SCHEMA_GENERAL.md`.
   - When upgrading `.brain-79/SCHEMA.md`, parse its existing YAML frontmatter first to preserve the project's `profile` (`software` or `general`) and any user-defined `custom_types:`.
   - Render the latest normative body for that profile while re-injecting the preserved frontmatter (`profile` + `custom_types`).

### Pillar 2: Two-tier reconditioning for existing wikis (`migrate_wiki` v2)
To safely bring any v1.0/v1.1 wiki up to v2.0+ compliance without hallucinating prose:

- **Tier 1 — 100% Deterministic Mechanical Reconditioning (Applied by `brain79 init --upgrade` and `brain79 migrate --apply`):**
  1. **Frontmatter & Backlink Repair on All Articles:** Even if an article already has `type:` and `summary:`, check and repair missing required fields (using `_TYPE_DEFAULTS`) and run `normalize_backlink_footer()` so every subfolder article gets `[← Volver al Índice](../INDEX.md)` if missing.
  2. **Root `SCHEMA.md` & `INDEX.md` Repair:** Normalize `SCHEMA.md` and regenerate `INDEX.md` navigation table and frontmatter (`type: navigation`, `last_updated`).
  3. **Lock & Registry Cleanup:** Purge legacy inline `*.lock` files and prune stale `handoffs/` entries from `.navigation_registry.json`.
- **Tier 2 — Semantic Structure Exemption (`status: legacy`):**
  - If an older article lacks new v2.0 `## H2` structural sections (e.g., an old decision without `## Consequences`), the migrator **never invents fake text**. Articles tagged `status: legacy` or `stability: legacy` are already exempted by `check_article_structural_sections()` (`lint_organizational.py:482`) until a human or agent naturally edits them in a future session.

### Pillar 3: `brain79 init --upgrade` and passive skew detection
1. **`brain79 init --upgrade` (and re-running `brain79 init` idempotently):**
   - Instead of aborting when `.brain-79/` exists, `brain79 init --upgrade` (or `brain79 init` on an existing wiki) safely performs an in-place upgrade:
     - Updates the managed block in `AGENTS.md` to `v{__version__}`.
     - Updates `.brain-79/SCHEMA.md` (preserving `profile` and `custom_types`).
     - Updates `.git/hooks/pre-commit` and MCP config files (`.mcp.json`, `.cursor/mcp.json`, `.agents/mcp_config.json`).
     - Runs Tier 1 mechanical wiki migration (`migrate_wiki(wiki_root, dry_run=False)` + `regenerate_index_navigation`).
2. **Passive Version Skew Alert in `orient()`:**
   - During `brain79_orient`, check if `AGENTS.md` lacks the current `<!-- brain79:start v{__version__} -->` marker or if `SCHEMA.md` has legacy broken links. If skewed, append a 1-line notice:
     `> ℹ️ **Protocol Upgrade Available**: Project templates predate brain79 v{__version__}. Run 'brain79 init --upgrade' to sync AGENTS.md and SCHEMA.md.`

### Pillar 4: Multi-harness zero-config and `brain79 doctor` (`brain79_doctor`)
1. **Absolute Executable Path Resolution in MCP Configs:**
   - Resolve `shutil.which("brain79")` to its absolute path (e.g. `/Users/xilax/.local/bin/brain79`) when writing `.mcp.json`, `.cursor/mcp.json`, and `.agents/mcp_config.json` so GUI harnesses without terminal `$PATH` never fail with `ENOENT`.
2. **Diagnostic Command (`brain79 doctor [--fix]` / `brain79_doctor(fix=False)`):**
   - Inspects and reports 6 operational checks in $<50\text{ ms}$:
     1. **Binary & Version:** `brain79` version and PATH resolution.
     2. **Wiki Structure & Schema:** `.brain-79/` directories, `SCHEMA.md` profile validity, and `INDEX.md` routing table health.
     3. **Protocol Sync (`AGENTS.md` & `SCHEMA.md`):** Verifies managed block version matches `brain79.__version__`.
     4. **MCP Harness Configs:** Verifies `.mcp.json` / `.agents/mcp_config.json` valid JSON and executable command path.
     5. **Lock & Filesystem Health:** Verifies `.brain-79/.locks/` write/lock acquisition and zero stale inline `.lock` files.
     6. **Git Pre-Commit Hook:** Verifies `.git/hooks/pre-commit` is installed, executable (`+x`), and has cross-platform PATH export.
   - Passing `--fix` (`fix=True`) automatically executes the non-destructive `init --upgrade` and legacy lock cleanup.

---

## Implementation checklist (developer agent — Phase 7)

1. **Managed Block Templates (`src/brain79/templates/AGENTS.md`, `SCHEMA.md`, `SCHEMA_GENERAL.md`):** Add `<!-- brain79:start -->` / `<!-- brain79:end -->` markers and `schema_version` metadata.
2. **Non-Destructive Upgrader (`src/brain79/core/init_project.py`):** Implement `sync_agents_manifest()`, `sync_schema_file()`, and `--upgrade` flag in `brain79 init` (making re-running `init` safe and non-destructive).
3. **Complete Legacy Wiki Reconditioning (`src/brain79/core/migration.py`):** Ensure `migrate_wiki` also repairs missing backlink footers on articles that already have `type`/`summary`, fixes root `SCHEMA.md` backlinks, and cleans inline locks.
4. **Diagnostics Engine (`src/brain79/core/doctor.py`, `cli/dispatch.py`, `server.py`):** Implement `brain79 doctor [--fix]` and MCP `brain79_doctor(fix=False)` (preserving 1:1 CLI/MCP symmetry).
5. **Tests:** Add `tests/test_project_upgrade_and_doctor.py` verifying user customizations in `AGENTS.md` and `custom_types` in `SCHEMA.md` survive `--upgrade` untouched, v1.0 wikis upgrade cleanly to `[Status: OK]`, and `doctor --fix` repairs skewed projects.

---

[← Volver al Índice](../INDEX.md)
