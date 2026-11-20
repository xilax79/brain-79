---
type: feature
summary: non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP setup, and brain79 doctor diagnostics
status: shipped
version: 0.9.2
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/init_project.py
  - src/brain79/core/migration.py
  - src/brain79/core/doctor.py
  - src/brain79/cli/dispatch.py
  - src/brain79/server.py
  - src/brain79/core/orient.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/symmetry.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
last_updated: 2026-11-17
applies_to_digest: "sha256:80d8b73173e1a9fd"
applies_to_count: 6
---

# Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics

## Overview

The project protocol upgrade and multi-harness doctor subsystem provides non-destructive repository maintenance, universal MCP client configuration, legacy wiki reconditioning, and operational diagnostics. It guarantees that updating the global `brain79` binary never leaves project templates, schemas, or agent definitions in a split-brain state.

---

## Architectural topology

```
+-----------------------------------------------------------------------------------------+
|                                    brain79 CLI / MCP                                    |
|             brain79 update-project                             brain79 doctor                   |
+-----------------------------------------------------------------------------------------+
       |                                                               |
       v                                                               v
+---------------------------+   +---------------------------+   +-------------------------+
|      Protocol sync        |   |    Multi-harness setup    |   |     Diagnostic engine   |
| - sync_agents_manifest    |   | - Tier 1: .mcp.json       |   | - 7-point health check  |
| - sync_schema_file        |   | - Tier 1: .agents/        |   | - POSIX exit codes 0/1/2|
| - Delimited comment block |   | - Tier 1: .cursor/        |   | - Git-aware --fix guard |
| - Extension preservation  |   | - Tier 2: desktop opt-in  |   | - Format text and json  |
+---------------------------+   +---------------------------+   +-------------------------+
       |                                                               |
       +-----------------------------------+---------------------------+
                                           v
                        +-------------------------------------+
                        |     Wiki reconditioning (v2)        |
                        | - Full-pass article inspection      |
                        | - Field defaults completion         |
                        | - Semantic legacy status downgrade  |
                        | - Merkle applies_to digest seeding  |
                        | - Commit transition handoff         |
                        +-------------------------------------+
```

---

## Subsystem capabilities

### 1. Delimited managed blocks in `AGENTS.md`
- **Managed delimiter markers**: protocol instructions are wrapped between `<!-- brain79:start v{version} -->` and `<!-- brain79:end -->`.
- **User content preservation**: all custom content before the start marker (e.g. persona directives) and after the end marker (e.g. `## Project notes`) is preserved without modification.
- **Corruption guard**: `sync_agents_manifest` aborts immediately if delimiters are mismatched, duplicated, or corrupted, protecting user content from silent truncation.
- **Markerless conversion**: legacy manifests lacking delimiters are wrapped safely, detecting the start of the memory protocol and preserving trailing project notes.

### 2. Schema synchronization
- **Schema versioning**: elevates `.brain-79/SCHEMA.md` to `schema_version: 2`.
- **Frontmatter and extension preservation**: retains existing `profile` (`software` or `general`), `custom_types`, and custom YAML keys. Trailing `## Project-specific schema extensions` sections are preserved intact.

### 3. Portable Tier 1 multi-harness registration
- **Universal project files**: configures `.mcp.json` (Pi, Claude Code, Zed, OpenCode), `.agents/plugins/brain79/` (Antigravity workspace plugin with `plugin.json`, `mcp_config.json`, and `SKILL.md`), `.agents/mcp_config.json` (legacy Antigravity fallback), and `.cursor/mcp.json` (Cursor IDE).
- **Portable execution**: sets `"command": "brain79"` with `"args": ["--project-root", "."]`, automatically sanitizing machine-specific absolute binary paths.
- **Non-destructive JSON merge**: preserves third-party MCP servers, custom plugin metadata, and creates automated `.bak` backups on corrupted files.
- **Tier 2 desktop opt-in**: supports safe registration in host desktop configurations (Claude Desktop, Windsurf) via `--include-desktop` using project-scoped server keys (`brain79-<project_name>`).

### 4. Git hook management
- **Third-party manager respect**: detects existing hook managers (Husky, Python `pre-commit`, Lefthook, Overcommit) and leaves them untouched, emitting an advisory notice rather than overwriting.
- **Profile-aware installation**: installs executable `.git/hooks/pre-commit` for software profiles while cleanly omitting hooks for gitless general profiles.

### 5. Full-pass wiki reconditioning (`migrate_wiki` v2)
- **Comprehensive inspection**: evaluates every wiki article without early exit.
- **Field auto-fill and backlink normalization**: completes missing required fields, normalizes summary text, and ensures backlink footers use `[← Volver al Índice](../INDEX.md)` on subfolders and `[← Volver al Índice](INDEX.md)` on root articles.
- **Semantic legacy status exemption**: articles missing required structural sections or exceeding size ceilings are downgraded to `status: legacy` or `stability: legacy`, exempting them from strict CI linting until organic editing occurs.
- **Merkle seeding and transition handoffs**: computes `applies_to_digest` and seeds `.drift_manifest.json`. Passing `--commit-transition` generates a maintenance handoff maintaining `fresh` lifecycle state under ADR-016.

### 6. Subsecond diagnostic engine (`brain79 doctor`)
- **Seven health checks**: evaluates binary/environment (Python >= 3.11 runtime and zero-clone tool installation), protocol sync, wiki structure, MCP harnesses, filesystem locks, git hooks, and handoff hygiene in $<50\text{ ms}$.
- **Exit codes and formats**: returns `0` (ok), `2` (warning), or `1` (error) with `--format text` and `--format json` support.
- **Git-aware repair guard**: refuses `--fix` if uncommitted protocol files exist in Git unless `--force` is supplied.

---

[← Volver al Índice](../INDEX.md)
