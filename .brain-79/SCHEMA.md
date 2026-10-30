# Brain-79 — Wiki Schema (Normative)

This file defines the **enforced rules** for maintaining this project's wiki.
The rules in this file are mechanically validated by `brain79_write` and `brain79_lint`.
Violations will be rejected at write time and reported by the linter.

---

## Quick navigation

| Directory | Required `type` | Required Fields | Allowed Enums | Purpose |
|-----------|-----------------|-----------------|---------------|---------|
| `INDEX.md` | `navigation` | `type`, `last_updated` | — | Automated routing table only (no freeform prose) |
| `handoffs/` | `handoff` | `type`, `session_type`, `previous_ref`, `last_updated` | `session_type`: feature, bugfix, research, brainstorming | Immutable session handoffs |
| `product/` | `product` | `type`, `last_updated` | — | Vision, domain, personas |
| `architecture/` | `architecture` | `type`, `stability`, `last_updated` | `stability`: experimental, stable, legacy | Stack, patterns, topology |
| `features/` | `feature` | `type`, `status`, `version`, `last_updated` | `status`: planned, in_progress, shipped, deprecated, legacy | Feature documentation |
| `decisions/` | `decision` | `type`, `status`, `date`, `deciders`, `last_updated` | `status`: proposed, accepted, superseded, rejected, legacy | Architectural Decision Records |
| `changelog/` | `changelog` | `type`, `version`, `date`, `last_updated` | — | Versioned changes |
| `_raw/sessions/` | `raw_session` | `type`, `session_id`, `session_type`, `last_updated` | `session_type`: feature, bugfix, research, brainstorming | Immutable session summaries |
| `_raw/commits/` | `raw_commit` | `type`, `commit_sha`, `last_updated` | — | Commit metadata |

### Frontmatter Templates

Optional fields accepted across all types: `summary` (single-line article description for `INDEX.md`), `supersedes`, `related`, `owner`.

```yaml
# Feature (features/*.md)
---
type: feature
summary: One-line summary for INDEX.md entry
status: planned  # planned | in_progress | shipped | deprecated | legacy
version: 1.0.0
last_updated: YYYY-MM-DD
---

# Decision (decisions/adr-*.md)
---
type: decision
summary: One-line summary of architectural decision
status: proposed  # proposed | accepted | superseded | rejected | legacy
date: YYYY-MM-DD
deciders: [author]
last_updated: YYYY-MM-DD
---

# Architecture (architecture/*.md)
---
type: architecture
summary: One-line summary of subsystem or pattern
stability: experimental  # experimental | stable | legacy
last_updated: YYYY-MM-DD
---

# Product (product/*.md)
---
type: product
summary: One-line summary of domain or vision
last_updated: YYYY-MM-DD
---
```

### Back-Navigation Links

Articles in subdirectories (`product/`, `architecture/`, `features/`, `decisions/`, `changelog/`) should conclude with a back-navigation link at the bottom of the article to facilitate reading in editors (VS Code, Obsidian, GitHub):

```markdown
---

[← Volver al Índice](../INDEX.md)
```

---

## Writing & Documentation Guidelines (Clean B2)

To ensure the wiki remains accessible to human engineers and easy for LLMs to reason over without high entropy:

1. **Tone & Level (Clean B2):**
   - Write in direct, accessible English (CEFR B2).
   - Use straightforward Subject-Verb-Object sentence structures.
   - Avoid inflated language, baroque adjectives, and convoluted phrasing.
2. **Technical Precision:**
   - Always preserve exact engineering terms (`atomic rename`, `POSIX mutex`, `BFS reachability`, `FastMCP`, `JSON-RPC`, `TF-IDF`, `WAL`).
   - Define technical interactions by explaining *what happens* and *why it matters*.
3. **Visual Structure:**
   - Prefer concise bullet lists, visual ASCII topologies, and structured tables over unbroken blocks of prose.
   - Maintain clear H2/H3 hierarchies to support fast scanning.

---

## Operational Invariants

- **Zero-Modification Idempotence**: Do not mutate wiki files unless concrete repository changes (code, tests, architecture decisions) occurred in the session.
- **Pure Routing Table**: `INDEX.md` is strictly an automated index; freeform prose blocks are forbidden.

---

## Known issues

- Articles without valid YAML frontmatter are rejected at write time.
- Inline decision declarations outside `decisions/` are forbidden.

---

## Roadmap

- Mechanical validation enforced via pre-commit git hooks and MCP tools.
- Progressive migration for legacy articles using `brain79 migrate`.
