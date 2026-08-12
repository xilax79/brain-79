---
type: feature
status: shipped
version: 1.0.0
last_updated: 2026-08-11
---

# Feature — Handoff Purge Operations

## Overview

`brain79 handoff-purge` provides an explicit operational exception to handoff immutability. It allows developers and agents to clean up tactical short-term handoffs (`.brain-79/handoffs/handoff-*.md`) upon completing sprint iterations, resetting demo repositories, or purging legacy session history.

By default, the command operates in `--dry-run` preview mode to prevent accidental data loss.

## Operations & Scope

- **What it purges**: All matching `handoffs/handoff-*.md` files.
- **Registry cleanup**: Unregisters deleted handoff paths from `.navigation_registry.json`.
- **What it leaves untouched**: Raw session logs (`_raw/sessions/`), commit logs (`_raw/commits/`), and long-term wiki articles (`product/`, `architecture/`, `features/`, `decisions/`, `changelog/`).

## Commands & Tools

| Interface | Method | Flags / Parameters | Default Behavior |
|---|---|---|---|
| CLI | `brain79 handoff-purge` | `[--apply]` | Dry-run preview |
| MCP | `brain79_handoff_purge(apply)` | `apply=False` | Dry-run preview |

## Usage Examples

```bash
# Preview handoffs to be purged
brain79 handoff-purge

# Apply deletion explicitly
brain79 handoff-purge --apply
```

## Known Edge Cases

- Purging handoffs does not automatically rewrite markdown links in other articles that reference purged handoff files.
- Re-running `brain79 lint` after purge will flag any broken local links to deleted handoffs, allowing the agent or developer to clean them up via `brain79_write`.
