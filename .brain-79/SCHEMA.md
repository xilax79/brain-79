# Brain-79 — Wiki Schema (Normative)

This file defines the **enforced rules** for maintaining this project's wiki.
The rules in this file are mechanically validated by `brain79_write` and `brain79_lint`.
Violations will be rejected at write time and reported by the linter.

---

## Project

This section defines the scope and governing standards of the wiki schema.

---

## Current focus

Maintain strict organizational health and high signal-to-noise ratio across all wiki articles.

---

## Quick navigation

| Directory | Required `type` | Purpose |
|-----------|-----------------|---------|
| `INDEX.md` | `navigation` | Topological index only |
| `handoffs/` | `handoff` | Immutable session handoffs |
| `product/` | `product` | Vision, domain, personas |
| `architecture/` | `architecture` | Stack, patterns, topology |
| `features/` | `feature` | Feature documentation |
| `decisions/` | `decision` | Architectural Decision Records |
| `changelog/` | `changelog` | Versioned changes |
| `_raw/sessions/` | `raw_session` | Immutable session summaries |
| `_raw/commits/` | `raw_commit` | Commit metadata |

---

## Known issues

- Articles without valid YAML frontmatter are rejected at write time.
- Inline decision declarations outside `decisions/` are forbidden.

---

## Roadmap

- Mechanical validation enforced via pre-commit git hooks and MCP tools.
- Progressive migration for legacy articles using `brain79 migrate`.
