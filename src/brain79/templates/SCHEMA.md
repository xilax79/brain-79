---
profile: software
---
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
| `product/` | `product` | `type`, `summary`, `last_updated` | — | Vision, domain, personas |
| `architecture/` | `architecture` | `type`, `summary`, `stability`, `last_updated` | `stability`: experimental, stable, legacy | Stack, patterns, topology |
| `features/` | `feature` | `type`, `summary`, `status`, `version`, `last_updated` | `status`: planned, in_progress, shipped, deprecated, legacy | Feature documentation |
| `decisions/` | `decision` | `type`, `summary`, `status`, `date`, `deciders`, `last_updated` | `status`: proposed, accepted, superseded, rejected, legacy | Architectural Decision Records |
| `changelog/` | `changelog` | `type`, `summary`, `version`, `date`, `last_updated` | — | Versioned changes |
| `_raw/sessions/` | `raw_session` | `type`, `session_id`, `session_type`, `last_updated` | `session_type`: feature, bugfix, research, brainstorming | Immutable session summaries |
| `_raw/commits/` | `raw_commit` | `type`, `commit_sha`, `last_updated` | — | Commit metadata |

### Frontmatter Templates

Optional fields accepted across types: `supersedes`, `related`, `owner` (plus `summary` on `navigation` and `handoff`).

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

Articles in subdirectories (`product/`, `architecture/`, `features/`, `decisions/`, `changelog/`) automatically conclude with a back-navigation link to facilitate reading in editors (VS Code, Obsidian, GitHub). This is enforced and auto-injected during write normalization:

```markdown
---

[← Volver al Índice](../INDEX.md)
```

### Document Structural Skeletons & Required Sections

Articles must include standard structural sections per document type:
- `decision`: Requires `## Status`, `## Context`, `## Decision`, `## Consequences`.
- `feature`: Requires `## Overview`.
- `architecture`: Requires `## Overview`, `## General Description`, or `## State`.
- `product`: Requires `## Overview`, `## Problem`, or `## Executive Summary`.

Inspect complete document skeletons via `brain79_schema(type)`.

### Deterministic Drift Detection (`applies_to`)

Articles declaring `applies_to` paths or globs in frontmatter are continuously checked against git commit timestamps and filesystem modification dates. Stale articles surface as `documentation_drift_suspected` warnings in `brain79 lint` and `brain79_orient`.

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
