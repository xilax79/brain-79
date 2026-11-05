---
profile: software
---
# Brain-79 — Wiki schema (normative)

This file defines the **enforced rules** for maintaining this project's wiki.
The rules in this file are mechanically validated by `brain79_write` and `brain79_lint`.
Violations will be rejected at write time and reported by the linter.

---

## Quick navigation

| Directory | Required `type` | Required Fields | Allowed Enums | Purpose |
|-----------|-----------------|-----------------|---------------|---------|
| `INDEX.md` | `navigation` | `type`, `last_updated` | — | Automated routing table only (no freeform prose) |
| `handoffs/` | `handoff` | `type`, `session_type`, `previous_ref`, `last_updated` | `session_type`: feature, bugfix, research, brainstorming, architecture, refactor, maintenance, work, general, writing, analysis | Immutable session handoffs |
| `product/` | `product` | `type`, `summary`, `last_updated` | — | Vision, domain, personas |
| `architecture/` | `architecture` | `type`, `summary`, `stability`, `last_updated` | `stability`: experimental, stable, legacy | Stack, patterns, topology |
| `features/` | `feature` | `type`, `summary`, `status`, `version`, `last_updated` | `status`: planned, in_progress, shipped, deprecated, legacy | Feature documentation |
| `decisions/` | `decision` | `type`, `summary`, `status`, `date`, `deciders`, `last_updated` | `status`: proposed, accepted, superseded, rejected, legacy | Architectural Decision Records |
| `changelog/` | `changelog` | `type`, `summary`, `version`, `date`, `last_updated` | — | Versioned changes |
| `topics/` | `topic` | `type`, `summary`, `last_updated` | `status`: active, archived, draft, legacy | Research, benchmarks, domain analysis |
| `_raw/sessions/` | `raw_session` | `type`, `session_id`, `session_type`, `last_updated` | `session_type`: feature, bugfix, research, brainstorming, architecture, refactor, maintenance, work, general, writing, analysis | Immutable session summaries |
| `_raw/commits/` | `raw_commit` | `type`, `commit_sha`, `last_updated` | — | Commit metadata |

### Frontmatter templates

Optional fields accepted across types: `supersedes`, `related`, `owner` (plus `summary` on `navigation` and `handoff`).

```yaml
# Feature (features/*.md)
---
type: feature
summary: one-line summary for INDEX.md entry
status: planned  # planned | in_progress | shipped | deprecated | legacy
version: 1.0.0
last_updated: YYYY-MM-DD
---

# Decision (decisions/adr-*.md)
---
type: decision
summary: one-line summary of architectural decision
status: proposed  # proposed | accepted | superseded | rejected | legacy
date: YYYY-MM-DD
deciders: [author]
last_updated: YYYY-MM-DD
---

# Architecture (architecture/*.md)
---
type: architecture
summary: one-line summary of subsystem or pattern
stability: experimental  # experimental | stable | legacy
last_updated: YYYY-MM-DD
---

# Product (product/*.md)
---
type: product
summary: one-line summary of domain or vision
last_updated: YYYY-MM-DD
---

# Topic (topics/*.md)
---
type: topic
summary: one-line summary of research, benchmark, or domain topic
status: active  # active | archived | draft | legacy
last_updated: YYYY-MM-DD
---
```

### Back-navigation links

Articles in subdirectories (`product/`, `architecture/`, `features/`, `decisions/`, `changelog/`, `topics/`) automatically conclude with a back-navigation link to facilitate reading in editors (VS Code, Obsidian, GitHub). This is enforced and auto-injected during write normalization:

```markdown
---

[← Volver al Índice](../INDEX.md)
```

### Document structural skeletons and required sections

Articles must include standard structural sections per document type:
- `decision`: Requires `## Status`, `## Context`, `## Decision`, `## Consequences`.
- `feature`: Requires `## Overview`.
- `architecture`: Requires `## Overview`, `## General Description`, or `## State`.
- `product`: Requires `## Overview`, `## Problem`, or `## Executive Summary`.

Inspect complete document skeletons via `brain79_schema(type)`.

### Deterministic drift detection (`applies_to`)

Articles declaring `applies_to` paths or globs in frontmatter are continuously checked against git commit timestamps and filesystem modification dates. Stale articles surface as `documentation_drift_suspected` warnings in `brain79 lint` and `brain79_orient`.

---

## Operational invariants

- **The Amnesia Test & Zero-Modification Idempotence (Session Knowledge Triage)**: Do not invent wiki files on ephemeral chat (Type A no-op). For zero-code research, benchmarks, or decisions (Type B), you MUST persist findings into `topics/<slug>.md` or `decisions/<slug>.md`. For code mutations (Type C), sync governing articles.
- **Pure Routing Table**: `INDEX.md` is strictly an automated index; freeform prose blocks are forbidden.

---

## Known issues

- Articles without valid YAML frontmatter are rejected at write time.
- Inline decision declarations outside `decisions/` are forbidden.

---

## Roadmap

- Mechanical validation enforced via pre-commit git hooks and MCP tools.
- Progressive migration for legacy articles using `brain79 migrate`.
