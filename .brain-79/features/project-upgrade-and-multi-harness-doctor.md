---
type: feature
summary: non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP and lifecycle hook setup, and brain79 doctor diagnostics
status: shipped
version: 0.16.0
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/init_project.py
  - src/brain79/core/migration.py
  - src/brain79/core/doctor.py
  - src/brain79/core/harnesses/**
  - src/brain79/cli/dispatch.py
  - src/brain79/server.py
  - src/brain79/core/orient.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/symmetry.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
  - features/lifecycle-hooks-and-ci-gate.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
  - decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md
last_updated: 2026-11-24
applies_to_digest: "sha256:97116753fc501d9e"
applies_to_count: 17
---

# Feature — Project upgrade, legacy wiki conditioning, multi-harness setup and doctor diagnostics

## Overview

The project protocol upgrade and multi-harness doctor subsystem provides non-destructive repository maintenance, universal MCP client configuration, opt-in lifecycle hook setup, legacy wiki reconditioning, and operational diagnostics. It guarantees that updating the global `brain79` binary never leaves project templates, schemas, or agent definitions in a split-brain state.

---

## Architectural topology

```
+-----------------------------------------------------------------------------------------+
|                                    brain79 CLI / MCP                                    |
|             brain79 update-project                             brain79 doctor           |
+-----------------------------------------------------------------------------------------+
       |                                                               |
       v                                                               v
+---------------------------+   +---------------------------+   +-------------------------+
|      Protocol sync        |   |    Multi-harness setup    |   |     Diagnostic engine   |
| - sync_agents_manifest    |   | - Tier 1: .mcp.json       |   | - 9-point health check  |
| - sync_schema_file        |   | - Tier 1: .agents/        |   | - POSIX exit codes 0/1/2|
| - Delimited comment block |   | - Tier 1: .cursor/        |   | - Git-aware --fix guard |
| - Extension preservation  |   | - Opt-in lifecycle hooks  |   | - Format text and json  |
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

### 3. Portable multi-harness adapter registry (`core/harnesses/`)
- **Shared delimited engine (`_delimited.py`)**: manages `<!-- brain79:start vX.Y.Z -->` / `<!-- brain79:end -->` blocks non-destructively across `AGENTS.md` (`AgentsMdAdapter`), `CLAUDE.md` (`ClaudeCodeAdapter`), `.cursor/rules/brain79.mdc` (`CursorRulesAdapter` with MDC frontmatter), and `.github/copilot-instructions.md` (`CopilotAdapter`).
- **MCP config adapters**: configures `.mcp.json` (`McpJsonAdapter`), `.agents/plugins/brain79/` (`AntigravityAdapter` with `plugin.json`, `mcp_config.json`, and `SKILL.md`), and `.cursor/mcp.json` (`CursorAdapter`) using portable `"command": "brain79"` + `"args": ["--project-root", "."]`.
- **Opt-in lifecycle hook adapters (`lifecycle_hooks.py`)**: `ClaudeHooksAdapter` (`claude_hooks` in `.claude/settings.json`), `AntigravityHooksAdapter` (`agy_hooks` in `.agents/plugins/brain79/hooks.json`), and `CursorHooksAdapter` (`cursor_hooks` in `.cursor/hooks.json`) merge `SessionStart` / `Stop` entries invoking `brain79 ci-check --lifecycle-hook ...` non-destructively, backing up corrupt JSON to `<filename>.bak` (unless `dry_run=True`), and are registered via `get_lifecycle_hook_adapters()` and `--harnesses hooks`.
- **Selective and opt-in installation**: `brain79 init --harnesses <all|csv>` filters installed adapters; `--install-lifecycle-hooks` on `init` or `update-project` installs all three hook adapters, while `update-project` without `--install-lifecycle-hooks` refreshes only hook adapters already detected on disk.
- **Tier 2 desktop opt-in**: supports safe registration in host desktop configurations (Claude Desktop, Windsurf) via `--include-desktop` using project-scoped server keys (`brain79-<project_name>`).

### 4. Git hook management
- **Third-party manager respect**: detects existing hook managers (Husky, Python `pre-commit`, Lefthook, Overcommit) and leaves them untouched, emitting an advisory notice rather than overwriting.
- **Profile-aware installation**: installs executable `.git/hooks/pre-commit` for software profiles while cleanly omitting hooks for gitless general profiles.

### 5. Full-pass wiki reconditioning (`migrate_wiki` v2)
- **Comprehensive inspection**: evaluates every wiki article without early exit.
- **Field auto-fill and backlink normalization**: completes missing required fields, normalizes summary text, and canonicalizes backlink footers to the active English-first `backlink_label:` from `SCHEMA.md` (default `[← Back to Index](../INDEX.md)` on subfolders and `[← Back to Index](INDEX.md)` on root articles, migrating legacy Spanish footers cleanly).
- **Semantic legacy status exemption**: articles missing required structural sections or exceeding size ceilings are downgraded to `status: legacy` or `stability: legacy`, exempting them from strict CI linting until organic editing occurs.
- **Merkle seeding and transition handoffs**: computes `applies_to_digest` and seeds `.drift_manifest.json`. Passing `--commit-transition` generates a maintenance handoff maintaining `fresh` lifecycle state under ADR-016.

### 6. Subsecond diagnostic engine (`brain79 doctor`)
- **Operational health checks**: evaluates binary/environment (Python >= 3.11 runtime, zero-clone tool installation, and dynamic AST Guard C capabilities from `POLYGLOT_LANGUAGES`), protocol sync (including active `enforcement` tier), wiki structure, MCP/instruction/installed lifecycle hook harnesses, filesystem locks, git hooks, `derived_state_tracking` (warns if derived JSON caches are tracked in Git), `git_merge_driver` (`INDEX.md` merge driver setup), and handoff hygiene in $<50\text{ ms}$.
- **Exit codes and formats**: returns `0` (ok), `2` (warning), or `1` (error) with `--format text` and `--format json` support. Preserves the 9 canonical checks when optional lifecycle hooks and polyglot grammars are absent or healthy, and emits an `ast_guards` warning (`exit_code == 2`) with reinstall instructions if `broken_grammars` is non-empty.
- **Git-aware repair guard**: refuses `--fix` if uncommitted protocol or lifecycle hook files (`.claude/settings.json`, `.cursor/hooks.json`, `.agents/plugins/brain79/`) exist in Git unless `--force` is supplied.

---

[← Back to Index](../INDEX.md)
