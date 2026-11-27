<!-- brain79:start v0.18.0 -->
# Brain-79 AI memory protocol

This repository uses **Brain-79** (`.brain-79/`) as its persistent engineering knowledge base. Follow this 2-call session workflow:

1. **Cold start**: call `brain79_orient(task?, paths?)` (or `brain79 orient`) before editing code to load `INDEX.md`, active handoffs, and governing articles/ADRs.
2. **Finalization**: persist knowledge updates and optional handoffs atomically via `brain79_session_commit(writes?, edits?, handoff?)`.
3. **Quality gate**: run `brain79_lint()` (or `brain79 lint --strict`) before completing wiki work.

## Key rules
- **Source of truth**: `.brain-79/` is the authoritative wiki; `AGENTS.md` and `.brain-79/SCHEMA.md` define full conventions and frontmatter schemas.
- **Amnesia Test**: skip wiki edits for ephemeral Q&A (Type A); persist non-code research/decisions into `topics/` or `decisions/` (Type B); sync governing articles when code changes (Type C).
- **On-demand handoffs**: in interactive sessions, write a handoff only when explicitly asked (e.g. "save handoff", "wrap up"). In autonomous sub-agent sessions, write one on exit.
- **Style**: clean B2 English, sentence case headings, one-line `summary:` in frontmatter, and `[← Back to Index](../INDEX.md)` footer.
<!-- brain79:end -->
