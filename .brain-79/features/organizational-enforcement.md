---
type: feature
summary: prevent organic wiki degradation through frontmatter schema validation, decision leakage detection, unified lint collection, and navigation indexing
status: shipped
version: 0.16.0
last_updated: 2026-11-26
applies_to:
  - src/brain79/core/lint.py
  - src/brain79/core/lint_organizational.py
  - src/brain79/core/validation.py
  - src/brain79/core/frontmatter.py
  - src/brain79/core/navigation.py
  - src/brain79/core/migration.py
  - src/brain79/templates/__init__.py
related:
  - decisions/adr-004-strict-write-validation.md
  - decisions/adr-006-auto-navigation-and-batch-operations.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-018-living-manuals-and-temporal-decontamination.md
applies_to_digest: "sha256:4e413b5f5a10c34e"
applies_to_count: 7
---

# Feature — Wiki organizational enforcement

## Overview

The Organizational Enforcement system prevents organic quality degradation of repository wikis. It automatically enforces frontmatter metadata schemas, checks type-location consistency, blocks structural decision leakage in non-decision folders, detects oversized or non-atomic articles, identifies unfilled template placeholders in `INDEX.md`, flags unanchored governance articles, enforces target existence, prevents duplicate governance target sprawl, and cleanses temporal project management debris from living manuals.

## Subsystem architecture

1. **Schema & location validation (`validation.py`, `frontmatter.py`)**: enforces required fields (`type`, `last_updated`, `status`, `version`, `stability`) matching file locations, supports standardized optional fields (`summary`, `applies_to`, `applies_to_digest`, `applies_to_count`), and includes `applies_to:` placeholders in `generate_frontmatter_template()` for `architecture` and `feature` articles under `profile: software`. `templates/SCHEMA.md` and `templates/AGENTS.md` also instruct agents to document public API signatures (parameter names) and key business constants in living manuals.
2. **Anti-sprawl governance (`validation.py`)**: `check_anti_sprawl_overlap` prevents creating redundant articles whose target files are already subsumed by an existing active article without declaring `supersedes`.
3. **Target existence & unanchored governance (`lint_organizational.py`, `session_commit.py`, `wiki.py`)**: centralizes unanchored checks via `has_non_empty_applies_to()`, `is_unanchored_governance_article()`, `unanchored_governance_message()`, `unanchored_governance_actionable()`, and `build_unanchored_batch_error()`. Enforces that active `software` `architecture/` and `features/` articles (excluding `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES`) declare non-empty `applies_to` (`unanchored_governance_article`) and validates that governed files resolve to real workspace files (`applies_to_target_missing`). Under `enforcement: strict`, `commit_session()`, `write_article()` / `brain79_edit`, and `write_many_articles()` enforce `unanchored_governance_article` pre-flight parity atomically (enumerating all offending paths before any disk mutation), while `balanced`, `advisory`, `general` profile, and `force_validation_skip=True` allow writes and surface explicit `unanchored_governance_article` warnings via `check_file_health()`.
4. **Structural decision & tech debt leakage (`lint_organizational.py`)**: uses CommonMark code-fence masking (`_mask_code_fences`) to search for un-nested decision bullets while ignoring code examples.
5. **Unified structural + organizational lint collection (`lint.py`, `lint_organizational.py`)**: `collect_wiki_lint_results()` returns a typed `WikiLintResult` combining `lint_wiki` structural/link checks and `lint_organizational` checks using an optionally shared `WorkspaceIndex` so `brain79 lint` and `brain79 ci-check` share identical issue counts and status parity.
6. **Thread-safe navigation registry (`navigation.py`)**: maintains `.navigation_registry.json` under `filelock` and updates `INDEX.md` Quick navigation atomically, prioritizing frontmatter `summary:` declarations with hardened fallback heuristics.
7. **Git pre-commit hook (`init_project.py`)**: deploys `.git/hooks/pre-commit` during `brain79 init` to execute `brain79 lint --strict` before commits are accepted.
8. **Back-navigation convention**: standardizes footer back-links (`[← Back to Index](../INDEX.md)`) for high-connectivity graphs and seamless editor navigation.
9. **Temporal decontamination & living manual governance (`lint_organizational.py`)**: enforces rule `temporal_contamination_in_title` on living manual ontologies (`features/`, `architecture/`, `product/`), ensuring titles, summaries, and headings remain evergreen and free of temporal project management milestone tags (`Phase X`, `Sprint Y`, `WIP`), while exempting immutable audit folders and roadmaps (ADR-018).

## Commands and tools

| Interface | Command / tool | Description |
|---|---|---|
| CLI | `brain79 lint [--strict] [--suggest-extract] [--format json]` | Run organizational linter |
| CLI | `brain79 navigate [--regenerate]` | Query or sync navigation registry |
| MCP | `brain79_lint()` | Run organizational health scan via MCP |

## Usage examples

```bash
# Run strict linter in CI or pre-commit hook
brain79 lint --strict --format json

# Get extraction suggestions for oversized INDEX.md
brain79 lint --suggest-extract
```

## Index synchronization check

- `check_index_desync()` (`index_desync` rule) compares on-disk indexable `.md` files against `INDEX.md` `## Quick navigation` links and flags missing or stale entries (blocking under `lint --strict`, remediated with `brain79 navigate --regenerate --rebuild`).

## Known edge cases

- Force skip flag (`--force-validation-skip` or `force_validation_skipped: true`) bypasses write-time validation, but surfaces as `force_skipped_article` (and `unanchored_governance_article` when applicable) warning in `brain79 lint` and `check_file_health()`.

---

[← Back to Index](../INDEX.md)
