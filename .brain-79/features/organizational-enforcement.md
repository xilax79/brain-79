---
type: feature
summary: prevent organic wiki degradation through frontmatter schema validation, decision leakage detection, and navigation indexing
status: shipped
version: 0.8.1
last_updated: 2026-11-13
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
applies_to_digest: "sha256:f47ed46397419d06"
applies_to_count: 7
---

# Feature — Wiki organizational enforcement

## Overview

The Organizational Enforcement system prevents organic quality degradation of repository wikis. It automatically enforces frontmatter metadata schemas, checks type-location consistency, blocks structural decision leakage in non-decision folders, detects oversized or non-atomic articles, identifies unfilled template placeholders in `INDEX.md`, flags unanchored governance articles, enforces target existence, prevents duplicate governance target sprawl, and cleanses temporal project management debris from living manuals.

## Subsystem architecture

1. **Schema & Location Validation (`validation.py`, `frontmatter.py`)**: Enforces required fields (`type`, `last_updated`, `status`, `version`, `stability`) matching file locations, while supporting standardized optional fields such as `summary`, `applies_to`, `applies_to_digest`, and `applies_to_count`.
2. **Anti-Sprawl Governance (`validation.py`)**: `check_anti_sprawl_overlap` prevents creating redundant articles whose target files are already subsumed by an existing active article without declaring `supersedes`.
3. **Target Existence & Unanchored Governance (`lint_organizational.py`)**: Enforces that strictly active software articles declare `applies_to` (`unanchored_governance_article`) and validates that governed files resolve to real workspace files (`applies_to_target_missing`).
4. **Structural Decision & Tech Debt Leakage (`lint_organizational.py`)**: uses CommonMark code-fence masking (`_mask_code_fences`) to search for un-nested decision bullets while ignoring code examples.
5. **Thread-Safe Navigation Registry (`navigation.py`)**: maintains `.navigation_registry.json` under `filelock` and updates `INDEX.md` Quick navigation atomically, prioritizing frontmatter `summary:` declarations with hardened fallback heuristics.
6. **Git Pre-Commit Hook (`init_project.py`)**: Deploys `.git/hooks/pre-commit` during `brain79 init` to execute `brain79 lint --strict` before commits are accepted.
7. **Back-Navigation Convention**: Standardizes footer back-links (`[← Back to Index](../INDEX.md)`) for high-connectivity graphs and seamless editor navigation.
8. **Temporal Decontamination & Living Manual Governance (`lint_organizational.py`)**: Enforces rule `temporal_contamination_in_title` on living manual ontologies (`features/`, `architecture/`, `product/`), ensuring titles, summaries, and headings remain evergreen and free of temporal project management milestone tags (`Phase X`, `Sprint Y`, `WIP`), while exempting immutable audit folders and roadmaps (ADR-018).

## Commands and tools

| Interface | Command / Tool | Description |
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

- Force skip flag (`--force-validation-skip` or `force_validation_skipped: true`) bypasses write-time validation, but surfaces as `force_skipped_article` warning in `brain79 lint`.

---

[← Back to Index](../INDEX.md)
