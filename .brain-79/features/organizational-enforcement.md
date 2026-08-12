---
type: feature
status: shipped
version: 1.0.0
last_updated: 2026-08-11
---

# Feature — Wiki Organizational Enforcement

## Overview

The Organizational Enforcement system prevents organic quality degradation of repository wikis. It automatically enforces frontmatter metadata schemas, checks type-location consistency, blocks structural decision leakage in non-decision folders, detects oversized or non-atomic articles, and identifies unfilled template placeholders in `INDEX.md`.

## Subsystem Architecture

1. **Schema & Location Validation (`validation.py`, `frontmatter.py`)**: Enforces required fields (`type`, `last_updated`, `status`, `version`, `stability`) matching file locations.
2. **Structural Decision & Tech Debt Leakage (`lint_organizational.py`)**: Uses CommonMark code-fence masking (`_mask_code_fences`) to search for un-nested decision bullets while ignoring code examples.
3. **Thread-Safe Navigation Registry (`navigation.py`)**: Maintains `.navigation_registry.json` under `filelock` and updates `INDEX.md` Quick navigation.
4. **Git Pre-Commit Hook (`init_project.py`)**: Deploys `.git/hooks/pre-commit` during `brain79 init` to execute `brain79 lint --strict` before commits are accepted.
5. **Unfilled Placeholder Detection (`check_unfilled_placeholders`)**: Scans `INDEX.md` for default template comments (e.g. `<!-- project name -->`) and flags them as warnings.

## Commands & Tools

| Interface | Command / Tool | Description |
|---|---|---|
| CLI | `brain79 lint [--strict] [--suggest-extract] [--format json]` | Run organizational linter |
| CLI | `brain79 navigate [--regenerate]` | Query or sync navigation registry |
| MCP | `brain79_navigate(regenerate)` | Query or sync navigation registry via MCP |

## Usage Examples

```bash
# Run strict linter in CI or pre-commit hook
brain79 lint --strict --format json

# Get extraction suggestions for oversized INDEX.md
brain79 lint --suggest-extract
```

## Known Edge Cases

- Force skip flag (`--force-validation-skip` or `force_validation_skipped: true`) bypasses write-time validation, but surfaces as `force_skipped_article` warning in `brain79 lint`.
