---
type: feature
summary: non-destructive project protocol upgrade (managed AGENTS.md blocks, SCHEMA.md sync, legacy wiki reconditioning), multi-harness MCP and lifecycle hook setup, and brain79 doctor diagnostics
status: shipped
version: 0.18.0
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
  - decisions/adr-023-external-drift-lockfile.md
last_updated: 2026-11-27
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
                        | - drift.lock zero-masking migration |
                        | - Commit transition handoff         |
                        +-------------------------------------+
```

---

## Subsystem capabilities

### 1. Delimited managed blocks in `AGENTS.md`
- **Managed delimiter markers**: protocol instructions are wrapped between `<!-- brain79:start v{version} -->` and `<!-- brain79:end -->`.
- **User content preservation**: all custom content before the start marker and after the end marker is preserved without modification.
- **Corruption guard**: `sync_agents_manifest` aborts immediately if delimiters are mismatched, duplicated, or corrupted.

### 2. Schema synchronization
- **Schema versioning**: elevates `.brain-79/SCHEMA.md` to `schema_version: 2`, documenting `.brain-79/drift.lock` as primary drift storage while preserving `profile`, `custom_types`, custom YAML keys, and `## Project-specific schema extensions`.

### 3. Portable multi-harness adapter registry (`core/harnesses/`)
- **Shared delimited engine (`_delimited.py`)**: manages `<!-- brain79:start vX.Y.Z -->` / `<!-- brain79:end -->` blocks across `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, and `.github/copilot-instructions.md`.
- **MCP config adapters**: configures `.mcp.json`, `.agents/plugins/brain79/`, and `.cursor/mcp.json` using `"command": "brain79"` + `"args": ["--project-root", "."]`.
- **Opt-in lifecycle hook adapters (`lifecycle_hooks.py`)**: `ClaudeHooksAdapter`, `AntigravityHooksAdapter`, and `CursorHooksAdapter` merge `SessionStart` / `Stop` entries invoking `brain79 ci-check --lifecycle-hook ...` non-destructively.
- **Tier 2 desktop opt-in**: supports host desktop configurations (Claude Desktop, Windsurf) via `--include-desktop`.

### 4. Git hook & merge driver management
- **Third-party manager respect**: detects existing hook managers (Husky, Python `pre-commit`, Lefthook, Overcommit) and leaves them untouched.
- **Pre-commit & merge drivers**: installs executable `.git/hooks/pre-commit` matching `^\.brain-79/(.*\.md|drift\.lock)$` and configures both `INDEX.md merge=brain79-index` and `drift.lock merge=brain79-drift-lock` in `.brain-79/.gitattributes` and local `.git/config`.

### 5. Full-pass wiki reconditioning (`migrate_wiki` v2)
- **Comprehensive inspection & fail-closed lockfile load**: evaluates every wiki article without early exit and loads `.brain-79/drift.lock` fail-closed (`corrupt_drift_lock`).
- **Field auto-fill and backlink normalization**: completes missing required fields, normalizes summary text, and canonicalizes backlink footers to the active English-first `backlink_label:` from `SCHEMA.md`.
- **Semantic legacy status exemption**: articles missing required structural sections or exceeding size ceilings are downgraded to `status: legacy` or `stability: legacy` in Paso B.
- **Zero-masking `drift.lock` migration (Paso D)**: runs strictly after Paso B, preserves existing `drift.lock` entries, copies stale baselines without masking code or `last_updated` drift, strips legacy/malformed `applies_to_digest` and `applies_to_count` keys from `.md` frontmatter, prunes deleted/inactive/demoted entries, and skips `regenerate_index_navigation()` on no-op runs for strict 2nd-run idempotency.

### 6. Subsecond diagnostic engine (`brain79 doctor`)
- **Operational health checks**: evaluates binary/environment, protocol sync, wiki structure, MCP/instruction/installed lifecycle hook harnesses, `locks_and_filesystem` (excluding top-level `.brain-79/drift.lock` from legacy inline lock warnings), git hooks, `derived_state_tracking` (via `git_check_ignore()` in Git repos and `.brain-79/.gitignore` rule-ordering fallback outside Git repos to verify `!drift.lock` is un-ignored while derived caches remain untracked), `git_merge_driver` (verifying both `brain79-index` and `brain79-drift-lock` in `.gitattributes` and `.git/config`), and handoff hygiene.
- **Single-pass `--fix` surfacing**: `doctor --fix` surfaces `gitignore_updated` and `migration_report` changes directly from `update_project()` into `DoctorReport.fixed` without running a redundant second `migrate_wiki(dry_run=False)` pass.
- **Exit codes and formats**: returns `0` (ok), `2` (warning), or `1` (error) with `--format text` and `--format json`, refusing `--fix` when protocol or hook files have uncommitted Git changes unless `--force` is supplied.

---

[← Back to Index](../INDEX.md)
