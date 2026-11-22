---
type: topic
summary: open v0.13.0 defects in navigation registry completeness, lint index desynchronization, and stale MCP version skew detection
status: active
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/cross-platform-and-lock-isolation.md
last_updated: 2026-11-21
---

# Open v0.13.0 defects — Navigation registry completeness, lint index desynchronization, and MCP version skew

## Context and discovery

Discovered during a live session on `v0.13.0` when a legacy pre-`v0.12.0` MCP server process ran `session_commit` against a repository whose `.navigation_registry.json` had been git-ignored in `v0.13.0`. That legacy process overwrote `.navigation_registry.json` with only the 2 articles touched in the transaction and truncated `.brain-79/INDEX.md` from 59 entries to 2.

Auditing `v0.13.0` against that incident exposed three product defects to address in a follow-up patch (`v0.13.1` or `v0.14.0`).

---

## BUG-008 — `load_registry()` accepts incomplete `.navigation_registry.json` caches without disk reconciliation

- **Status**: open.
- **Severity**: high.
- **Location**: `src/brain79/core/navigation.py` (`load_registry`, `register_article`).
- **Symptom**: `load_registry()` triggers `rebuild_navigation_registry()` only when `.navigation_registry.json` is missing or contains invalid JSON. If an existing cache file is structurally valid JSON (`{"articles": [...]}`) but missing indexable `.md` files present on disk (e.g., after a stale process write, interrupted sync, or partial cache), `load_registry()` returns the incomplete list and `regenerate_index_navigation()` persists a truncated `INDEX.md`.
- **Reproduction**:
  1. Write a valid `.brain-79/.navigation_registry.json` containing only 2 entries while 59 indexable `.md` files exist on disk.
  2. Call `brain79 navigate --regenerate` (without `--rebuild`) or `brain79 session-commit`.
  3. Observe that `INDEX.md` remains truncated to 2 entries.
- **Proposed remediation**:
  - Compare cached article paths in `load_registry()` (or before `regenerate_index_navigation()`) against `_scan_indexable_md_files(wiki_root)`.
  - If the path set diverges (missing on-disk articles or stale deleted paths), deterministically reconcile/rebuild the registry from disk before rendering `INDEX.md`.

---

## BUG-009 — `lint --strict` lacks an explicit `index_desync` / `registry_incomplete` check

- **Status**: open.
- **Severity**: high.
- **Location**: `src/brain79/core/lint_organizational.py`, `src/brain79/core/lint.py`.
- **Symptom**: running `uv run brain79 lint --strict` against a truncated `INDEX.md` (2 entries out of 59 indexable `.md` files) reported `Broken Local Links (0)`, `Namespace Violations (0)`, and `Structural Errors & Warnings (0)`. It exited `1` only indirectly because 29 articles with no other inbound links appeared under `[INFO] Orphans (29)`; the other 28 articles linked internally were completely unreported, and no diagnostic indicated that `INDEX.md` was missing 57 entries.
- **Reproduction**:
  1. Truncate `.brain-79/INDEX.md` to 2 entries.
  2. Run `uv run brain79 lint --strict`.
  3. Observe zero `CRITICAL` or `WARNING` structural findings diagnosing the index mismatch.
- **Proposed remediation**:
  - Add a deterministic organizational lint rule `index_desync` (severity: `error` / `CRITICAL` or `warning` under `strict`) comparing `_scan_indexable_md_files(wiki_root)` against the paths linked in `INDEX.md` `## Quick navigation` (and optionally `.navigation_registry.json`), with actionable remediation `Run 'brain79 navigate --regenerate --rebuild'`.

---

## BUG-010 — `orient()` does not detect reverse version skew (running server older than project protocol)

- **Status**: open.
- **Severity**: medium.
- **Location**: `src/brain79/core/orient.py`, `src/brain79/core/init_project.py` (`check_protocol_version_skew`).
- **Symptom**: when a stale long-lived MCP server process (`< 0.13.0`) connected to a repository already upgraded to `v0.13.0` (`<!-- brain79:start v0.13.0 -->`), `orient()` failed to warn that the running server was *older* than the repository's protocol templates (in fact, the older server emitted a misleading *"Project templates predate brain79 v0.9.0"* message).
- **Reproduction**:
  1. Upgrade a repository to `v0.13.0` (`AGENTS.md` marker `v0.13.0`).
  2. Invoke `brain79_orient()` from an older long-lived MCP server process (`< 0.13.0`).
  3. Observe no warning instructing the user to restart the MCP client/server process or upgrade the binary.
- **Proposed remediation**:
  - In `check_protocol_version_skew()`, parse semantic versions symmetrically and emit an explicit high-visibility warning whenever `running_server_version < project_protocol_version`, instructing the user to restart their MCP client/server or run `brain79 update`.

---

[← Back to Index](../INDEX.md)
