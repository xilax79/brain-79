---
type: feature
summary: session knowledge triage (Amnesia Test), zero-code research persistence guard, profile-aware curation guide, path prefix normalization, and handoff schema ergonomics
status: shipped
version: 0.8.0
applies_to:
  - src/brain79/core/session_commit.py
  - src/brain79/core/curate.py
  - src/brain79/core/orient.py
  - src/brain79/core/context.py
  - src/brain79/core/wiki.py
  - src/brain79/core/bootstrap.py
  - src/brain79/core/init_project.py
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/defect-backlog.md
  - features/handoff-continuity.md
last_updated: 2026-11-26
applies_to_digest: "sha256:94b32953d9bfb2f3"
applies_to_count: 7
---

# Feature — Session knowledge triage and research persistence

## Overview

The Session Knowledge Triage and Research Persistence system guarantees that valuable knowledge produced during AI development and research sessions is never lost. It replaces git-bound no-op rules with the three-way Amnesia Test, enforces mechanical persistence guards on research sessions, normalizes redundant path prefixes, and provides native parameter ergonomics across MCP and CLI interfaces.

## Subsystem architecture (4 pillars)

### 1. The Amnesia Test (3-way session knowledge triage)
At the conclusion of each session, knowledge is triaged into three deterministic categories:
- **Type A — Ephemeral or read-only consultation**: casual interaction or read-only queries producing zero durable findings. Governed by the zero-modification rule: no wiki files are edited or invented.
- **Type B — Zero-code research, analysis, and discovery**: domain research, benchmarks, market forecasts, or strategic decisions where zero source code files changed. The distilled knowledge is the primary deliverable and must be persisted into structured wiki articles (`topics/`, `decisions/`, etc.) via `brain79_session_commit`.
- **Type C — Workspace and code mutation**: source code, tests, or configuration were modified. Governing articles (`features/`, `architecture/`, `decisions/`, `changelog/`) must be updated and committed atomically.

### 2. Unpersisted research engine guard
In `handoff.py` and `session_commit.py`, attempting to finalize a session of type `research`, `brainstorming`, `analysis`, or `writing` without writing or updating at least one wiki article is blocked mechanically unless:
1. One or more items are flagged in `knowledge_pending_promotion`, or
2. An explicit operational justification is supplied in `wiki_deviation_justification`.

### 3. Handoff schema ergonomics and path tolerance
- **Native parameter aliases**: FastMCP, core engines, and CLI dispatch accept `decisions` (merged into `completed_work`), `next_steps` (merged into `pending_work`), and `open_questions` (merged into `gotchas`).
- **Filler and placeholder filtering**: conversational placeholders (such as `"None"`, `"Ninguna"`, or `"Wait for user"`) are stripped automatically so empty queues remain truly empty.
- **Path prefix normalization (`normalize_wiki_rel_path`) & batch ergonomics (`wiki.py`)**: strips redundant leading `.brain-79/` or `./.brain-79/` prefixes so paths passed by agents resolve seamlessly; `normalize_batch_requests()` and `format_batch_results()` power ergonomic `paths`/`requests` batch reads.

### 4. Profile-aware curation guide (`curate.py`)
`prepare_curation_guide()` inspects `load_active_schema(wiki_root)` dynamically to:
- Output profile-specific target directories (e.g. `topics/`, `entities/`, `sources/` for `general` profile vs. `features/`, `architecture/` for `software` profile).
- Exclude internal `.locks/` files from article counts.
- Present the Amnesia Test decision rubric to guide the incoming agent during raw session digestion.

---

[← Back to Index](../INDEX.md)
