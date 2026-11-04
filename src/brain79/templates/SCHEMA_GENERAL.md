---
profile: general
---
# Brain-79 — Wiki Schema (General Knowledge & Research)

This file defines the **enforced rules** for maintaining this project's wiki under the `general` profile.
The rules are mechanically validated by `brain79_write` and `brain79_lint`.

---

## Quick navigation

| Directory | Required `type` | Required Fields | Allowed Enums | Purpose |
|-----------|-----------------|-----------------|---------------|---------|
| `INDEX.md` | `navigation` | `type`, `last_updated` | — | Automated routing table only (no freeform prose) |
| `handoffs/` | `handoff` | `type`, `session_type`, `previous_ref`, `last_updated` | `session_type`: work, general, writing, analysis, research, feature, bugfix, brainstorming | Immutable session handoffs |
| `context/` | `context` | `type`, `summary`, `last_updated` | — | Goals, scope, background, principles |
| `topics/` | `topic` | `type`, `summary`, `last_updated` | `status`: draft, active, archived, legacy | Domain notes, research, entities, synthesis |
| `decisions/` | `decision` | `type`, `summary`, `status`, `date`, `last_updated` | `status`: proposed, accepted, superseded, rejected, legacy | Key decisions, criteria, trade-offs |
| `log/` | `log` | `type`, `summary`, `date`, `last_updated` | — | Chronological milestones and progress |
| `_raw/sessions/` | `raw_session` | `type`, `session_id`, `session_type`, `last_updated` | `session_type`: work, general, writing, analysis, research, feature, bugfix, brainstorming | Raw session summaries |
| `_raw/commits/` | `raw_commit` | `type`, `commit_sha`, `last_updated` | — | Commit / revision metadata |

### Frontmatter Templates

Optional fields accepted across types: `supersedes`, `related`, `owner` (plus `tags` on `topic`, `scope` on `context`).

```yaml
# Topic (topics/*.md)
---
type: topic
summary: One-line summary of this topic
status: active  # draft | active | archived | legacy
last_updated: YYYY-MM-DD
---

# Decision (decisions/adr-*.md)
---
type: decision
summary: One-line summary of decision
status: proposed  # proposed | accepted | superseded | rejected | legacy
date: YYYY-MM-DD
last_updated: YYYY-MM-DD
---

# Context (context/*.md)
---
type: context
summary: One-line summary of project context
last_updated: YYYY-MM-DD
---

# Log (log/*.md)
---
type: log
summary: One-line summary of milestone
date: YYYY-MM-DD
last_updated: YYYY-MM-DD
---
```

---

[← Volver al Índice](INDEX.md)
