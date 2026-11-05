---
type: feature
summary: non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP setup, and brain79 doctor diagnostics
status: planned
version: 2.1.0
applies_to:
  - src/brain79/core/init_project.py
  - src/brain79/core/migration.py
  - src/brain79/core/orient.py
  - src/brain79/core/doctor.py
  - src/brain79/cli/dispatch.py
  - src/brain79/server.py
  - src/brain79/templates/AGENTS.md
  - src/brain79/templates/SCHEMA.md
  - src/brain79/templates/SCHEMA_GENERAL.md
related:
  - architecture/roadmap-industrial-scale.md
  - features/cross-platform-and-lock-isolation.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
last_updated: 2026-11-05
---

# Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics (Phase 7 specification)

## Overview

This specification defines **Phase 7 of the Industrial-Scale Roadmap**: resolving the **"Split-Brain" version skew problem** when the global `brain79` binary is updated while existing project repositories still host older `AGENTS.md`, `SCHEMA.md`, `.mcp.json`, git hooks, and legacy wiki articles.

It establishes a non-destructive project protocol upgrader (`brain79 update-project` / `brain79 init --upgrade`), a resilient multi-harness MCP registration model, two-tier wiki reconditioning, and the `brain79 doctor` diagnostic engine.

---

## Problem statement

### 1. The "split-brain" project skew problem
When `brain79 init` runs on a project under an older version, static protocol files (`AGENTS.md`, `.brain-79/SCHEMA.md`, `.git/hooks/pre-commit`, `.mcp.json`) are stamped into the repository. When the global `brain79` binary is later upgraded:
- Calling `brain79 init` on an existing project aborts with `"Wiki already exists... Delete .brain-79/ manually"`, leaving `AGENTS.md` and `SCHEMA.md` frozen on obsolete instructions.
- Overwriting `AGENTS.md` or `SCHEMA.md` blindly destroys user-authored project notes, custom persona directives, or custom folder/field declarations (`custom_types:`) in `SCHEMA.md`.

### 2. Incomplete reconditioning of older wikis (`migration.py` gaps)
Existing `src/brain79/core/migration.py` has 4 architectural gaps when upgrading a legacy wiki:
1. **Early exit on existing `type` and `summary`:** If a legacy article already possesses `type` and `summary`, `migrate_wiki` skips it immediately—leaving missing backlink footers, invalid relative paths (`../INDEX.md` inside root files), or missing type-specific fields uncorrected.
2. **Legacy prose in `INDEX.md`:** Wikis created before ADR-008 retain legacy `## Project` or `## Roadmap` sections in `INDEX.md`, or lack the `type: navigation` frontmatter header.
3. **Semantic preservation vs. mechanical normalization:** Mechanical envelope attributes (frontmatter defaults, `summary`, backlink footers, `INDEX.md` routing table, `.locks/` cleanup) must be upgraded deterministically. Inventing prose sections (`## Context`, `## Consequences`) must never occur mechanically; legacy articles must receive `status: legacy` or `stability: legacy` so `lint` exempts them until an agent or human naturally edits them.
4. **Authority decay and handoff invalidation (ADR-016):** Mass-migrating articles alters `compute_wiki_digest(wiki_root)`, turning active handoffs `stale`. The upgrader must provide an explicit transition path so authority decay does not leave agents stranded without active context.

### 3. Multi-harness scope and portability hazards
- **Portability hazard (absolute machine paths in git):** Writing machine-specific absolute binary paths (e.g., `/Users/xilax/.local/bin/brain79`) into committed repository files (`.mcp.json`, `.cursor/mcp.json`, `.agents/mcp_config.json`) breaks cross-developer portability. When another developer on Linux (`/home/dev/...`) or Windows clones the repository, their MCP client fails with `ENOENT`.
- **Harness proliferation and maintenance boundaries:** Attempting to mutate configuration files across all arbitrary desktop GUI apps creates unbounded maintenance debt. Project-level tools must maintain clear scope boundaries: automate project-level files inside the repository, and provide diagnostic guidance for user-level global configurations.

---

## Architectural design (5 pillars)

### Pillar 1: Delimited managed blocks in `AGENTS.md` and schema preservation
1. **Managed block markers in `AGENTS.md`:**
   Wrap the core protocol instructions inside versioned HTML comment delimiters:
   ```markdown
   <!-- brain79:start v2.1.0 -->
   # Brain-79 AI memory protocol
   ...
   <!-- brain79:end -->
   ```
   - **Parser and synchronization rules (`sync_agents_manifest`):**
     - **Tolerant regex:** Match delimiters using whitespace-insensitive patterns:
       `r"<!--\s*brain79:start(?:\s+v?[0-9\.]+)?\s*-->"` and `r"<!--\s*brain79:end\s*-->"`.
     - **Corruption guard:** If an opening marker exists without a closing marker, **abort with an actionable error** rather than guessing or truncating user content.
     - **Idempotence:** Replacing the delimited block must preserve 100% of content before and after the block (persona overrides, project notes, team guidelines).
     - **Legacy fallback (v1.x without markers):** If no delimiters exist but `# Brain-79 AI memory protocol` is present, locate that header and replace up to `## Project notes` (or end of file), wrapping the replacement in standard delimiters and preserving everything under `## Project notes`.

2. **Non-destructive `SCHEMA.md` upgrade (`sync_schema_file`):**
   - **Frontmatter preservation:** Parse existing YAML frontmatter first. Retain `profile` (`software` or `general`), `custom_types:`, and update or inject `schema_version: "2.1"`.
   - **Body preservation:** Core normative tables and rules are updated to the latest standard. If the user defined a `## Project-specific schema extensions` section, that section is preserved intact at the end of the file.

---

### Pillar 2: Resilient multi-harness MCP registration
To avoid maintenance debt and guarantee empirical testability in CI without GUI dependencies, harness integration is partitioned into two distinct tiers:

#### Tier 1: Project-level auto-registration (automated by default and tested in CI)
The upgrader deterministically configures and updates exactly 3 standardized project-level files within the repository root on every `init` and `update-project`:
1. `.mcp.json` — Universal standard used by **Pi**, **Claude Code CLI**, **OpenCode**, and **Zed**.
2. `.agents/mcp_config.json` — **Antigravity (`agy`)** standard.
3. `.cursor/mcp.json` — **Cursor IDE** project standard.

**Cross-platform portability invariant:**
- Committed project configs must use `"command": "brain79"` with `"args": ["--project-root", "."]`.
- Absolute machine paths (e.g. `/Users/...`) must **never** be written to committed repository files.
- To accommodate desktop GUI clients on macOS/Windows whose environments do not inherit login shell `$PATH`, `brain79` documents standard wrapper techniques and checks PATH resolution in `brain79 doctor`.

#### Tier 2: Machine-level desktop harness integration (informational by default, opt-in auto-configuration)
Covers desktop GUI harnesses whose configuration lives in user-level OS paths outside the project repository (e.g., Claude Desktop at `~/Library/Application Support/Claude/claude_desktop_config.json` or `%APPDATA%\Claude\claude_desktop_config.json`, and Windsurf at `~/.codeium/windsurf/mcp_config.json`):
1. **Default mode (informational and safe):**
   - By default, `init` and `update-project` **never silently mutate files outside the repository**.
   - `brain79 doctor` inspects whether these desktop applications are installed on the host. If present but unconfigured, it displays their status and outputs the exact JSON snippet to copy.
2. **Opt-in auto-configuration (`--include-desktop`):**
   - If the user explicitly invokes `brain79 update-project --include-desktop` or `brain79 doctor --fix --include-desktop`, the tool performs safe, non-destructive registration in the user's desktop config:
     - Automatically creates a timestamped `.bak` backup file before editing.
     - Merges a scoped entry under `"mcpServers"` (e.g. `"brain79-<project_name>"` to avoid collisions across multiple workspaces), pointing `"command"` to the absolute binary path (`shutil.which("brain79")`) and `"args"` to the absolute project directory.
     - Preserves all pre-existing third-party MCP servers in the user's global config.

---

### Pillar 3: Respectful Git hook integration
1. **Non-destructive hook inspection:**
   - When inspecting `.git/hooks/pre-commit`:
     - If the file does not exist, write the standard `PRE_COMMIT_HOOK_SCRIPT` and set executable permissions (`chmod +x`).
     - If the file exists and contains the `# brain-79 pre-commit hook` marker, update only the brain-79 block.
     - If the file exists and belongs to a third-party hook manager (**Husky**, Python **pre-commit**, **Lefthook**, **Overcommit**), **do not overwrite it**. Emit an informational notice explaining how to append `brain79 lint --strict` to the existing manager.

---

### Pillar 4: Two-tier wiki reconditioning (`migrate_wiki` v2)
1. **Tier 1 — Deterministic mechanical normalization:**
   - **Backlink footer normalization:** Check all subfolder articles. If missing a backlink, append `[← Volver al Índice](../INDEX.md)`. For root-level articles (e.g. `SCHEMA.md`), do not inject `../INDEX.md`. If an article already possesses an equivalent backlink (e.g. `[← Back to Index](../INDEX.md)`), do not inject a duplicate.
   - **Frontmatter field completion:** Populate missing `last_updated`, `status: legacy`, or default values without altering existing semantic fields.
   - **Index and lock cleanup:** Regenerate `INDEX.md` routing table and prune stale inline locks.
2. **Tier 2 — Semantic structure exemption:**
   - Articles missing specific H2 headings (e.g., ADRs lacking `## Consequences`) are assigned `status: legacy`. The linter exempts legacy articles from strict section requirements until an agent or engineer edits them.
3. **Handoff freshness transition (ADR-016 integration):**
   - When running a migration that modifies wiki content, `update-project` warns that active handoffs will transition to `stale`.
   - Passing `--commit-transition` automatically commits the changes and writes a transition handoff (`session_type: maintenance`, `summary: upgrade project to brain79 v...`), preserving an unbroken `fresh` state for the next session.

---

### Pillar 5: Project upgrader and `brain79 doctor` diagnostic engine

#### 1. CLI command unification: `brain79 update-project`
- **Canonical command:** `brain79 update-project [--project-root <path>] [--dry-run] [--commit-transition]`
- **Idempotent alias:** `brain79 init --upgrade` (and running `brain79 init` on an existing wiki invokes `update-project` safely rather than erroring out).
- **Passive alert in `orient()`:** When `orient()` detects an older `AGENTS.md` block or legacy schema version, it emits a non-blocking one-line notice:
  `> ℹ️ **Protocol update available**: Project templates predate brain79 v{__version__}. Run 'brain79 update-project' to sync AGENTS.md and SCHEMA.md.`

#### 2. Diagnostic engine (`brain79 doctor [--fix]` / `brain79_doctor(fix=False)`)
Inspects 7 operational health categories in $<50\text{ ms}$:
1. **Binary and environment:** CLI binary resolution, python environment, and system PATH availability.
2. **Protocol synchronization:** `AGENTS.md` managed block version and `SCHEMA.md` `schema_version` parity with running binary.
3. **Wiki structure and schema:** Directory layout, valid profile, and clean navigation index.
4. **MCP harness registration:** Verification of `.mcp.json`, `.agents/mcp_config.json`, and `.cursor/mcp.json` validity and tool prefix definitions.
5. **Lock engine and filesystem:** Lock acquisition latency in `.brain-79/.locks/` and absence of legacy inline `.lock` files.
6. **Git hooks integration:** Presence, executable mode, and integrity of `.git/hooks/pre-commit`.
7. **Handoff freshness and hygiene:** Status of latest handoff (fresh/stale/unverified) and count of unpurged legacy handoffs.

**POSIX exit codes and formatting:**
- `0`: All operational checks pass.
- `1`: Critical failures detected (e.g., filesystem lock failure, malformed JSON, corrupted schema).
- `2`: Warnings or skew detected (e.g., protocol version skew, uninstalled hooks).
- Supports `--format text` (human-readable with symbols) and `--format json` (machine-readable for CI/CD pipelines).

**Safety guard for `--fix`:**
- Running `brain79 doctor --fix` (or MCP `brain79_doctor(fix=True)`) checks `git status --porcelain`. If uncommitted changes exist in the working tree, `--fix` refuses to proceed unless `--force` is supplied.

---

## Implementation checklist (Phase 7)

1. **Delimited Templates (`src/brain79/templates/`):**
   - Add `<!-- brain79:start -->` and `<!-- brain79:end -->` markers to `AGENTS.md`.
   - Add `schema_version: "2.1"` to `SCHEMA.md` and `SCHEMA_GENERAL.md`.
2. **Manifest and Schema Upgrader (`src/brain79/core/init_project.py`):**
   - Implement `sync_agents_manifest()` with tolerant regex and corruption guards.
   - Implement `sync_schema_file()` preserving custom extensions and frontmatter.
   - Implement respectful Git hook updater avoiding Husky/pre-commit collisions.
   - Wire `brain79 update-project` and `brain79 init --upgrade` (with Tier 1 project auto-registration and Tier 2 `--include-desktop` opt-in support).
3. **Deterministic Wiki Reconditioning (`src/brain79/core/migration.py`):**
   - Update `migrate_wiki` to repair backlinks without language conflicts or duplicate footers.
   - Ensure root files do not receive broken `../INDEX.md` links.
   - Implement transition handoff support to preserve ADR-016 freshness.
4. **Diagnostic Command and Tool (`src/brain79/core/doctor.py`, `dispatch.py`, `server.py`):**
   - Implement 7-point health check suite.
   - Implement `--format json` and standard POSIX exit codes (`0`, `1`, `2`).
   - Add MCP `brain79_doctor(fix=False)` tool with working tree safety guard.
5. **Verification and Tests (`tests/test_project_upgrade_and_doctor.py`):**
   - Test non-destructive upgrades of `AGENTS.md` and `SCHEMA.md` with user notes.
   - Test Tier 1 multi-harness configuration (.mcp.json, .agents, .cursor) and Tier 2 opt-in registration with backup.
   - Test third-party Git hook preservation.
   - Test `doctor` checks and JSON formatting in clean and skewed environments.

---

[← Volver al Índice](../INDEX.md)
