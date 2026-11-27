---
type: decision
summary: relocate drift digests and per-file leaf hashes into Git-tracked .brain-79/drift.lock with a 3-way merge driver while keeping Markdown frontmatter hash-free
status: accepted
date: 2026-11-27
deciders:
  - xilax79
related:
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
  - features/transitive-drift-and-ripple-guards.md
  - features/team-collaboration-and-onboarding.md
last_updated: 2026-11-27
---

# ADR-023 — External drift lockfile and hash-free Markdown frontmatter

## Status

Accepted (2026-11-27).

## Context

Prior to `v0.18.0`, `brain-79` stored `applies_to_digest` and `applies_to_count` inside every governing Markdown article's YAML frontmatter and stored per-file leaf hashes in a git-ignored `.brain-79/.drift_manifest.json`. That coupling caused two recurring problems:
1. Internal refactors verified via AST Guard C (`verified_articles`) had to re-stamp `applies_to_digest` inside `.md` files, creating hash-only diff noise and frontmatter merge conflicts.
2. Fresh CI clones lacked `.drift_manifest.json`, degrading per-file drift attribution whenever a master digest changed.

## Decision

1. **Git-tracked `.brain-79/drift.lock` (`version: "2.0"`)**: relocate all machine-managed `digest`, `count`, and leaf `targets` into a single deterministic, LF-only, sorted-key JSON file guarded by `_drift_lock.lock` in `LOCK_HIERARCHY` and un-ignored via `!drift.lock` strictly after `*.lock` in `.brain-79/.gitignore`.
2. **Hash-free Markdown frontmatter & zero-diff `verified_articles`**: all write/edit/commit/migrate paths strip `applies_to_digest` and `applies_to_count` from `.md` files; `verified_articles` updates only `.brain-79/drift.lock`.
3. **3-way Git merge driver (`brain79 merge-drift-lock`) & conflict sentinel**: expand CLI `WHITELIST` from 26 to 27 (`MCP_TOOLS` remains 9 per ADR-020). Disjoint/identical/0-byte-`<base>` merges resolve cleanly (`Exit 0`); same-key modify/modify or delete/modify conflicts revert to `base[k]`; conflicting `add/add` keys emit `"conflict": true` sentinels blocked from `verified_articles` under `strict`/`balanced`.
4. **Dual-read backward compatibility & Guard C baseline integrity**: `check_article_drift()` resolves `drift.lock` -> legacy frontmatter + read-only `.drift_manifest.json` -> `last_updated`, while `resolve_article_baseline_commit()` skips pure migration commits and falls back to article-only history beyond 50 lockfile commits.

## Consequences

- **Positive**: eliminates hash-only `.md` churn, restores exact per-file CI drift attribution on fresh clones, eliminates `orient()` manifest rebuilds on tracked repos, and keeps legacy wikis 100% readable.
- **Negative**: adds `.brain-79/drift.lock` and the `brain79-drift-lock` merge driver configuration to Git-tracked repositories.

---

[← Back to Index](../INDEX.md)
