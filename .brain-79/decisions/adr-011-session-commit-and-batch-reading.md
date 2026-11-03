---
type: decision
summary: 1-Call atomic session finalization and section-projected batch reading
status: accepted
date: 2026-11-02
deciders:
  - xilax
applies_to:
  - "src/brain79/core/session_commit.py"
  - "src/brain79/core/wiki.py"
  - "src/brain79/server.py"
  - "src/brain79/cli/dispatch.py"
related:
  - "decisions/adr-010-orient-and-3-signal-context-ranking.md"
  - "decisions/adr-006-auto-navigation-and-batch-operations.md"
  - "architecture/roadmap-industrial-scale.md"
last_updated: 2026-11-02
---

# ADR-011 — Two-Call Session Protocol: 1-Call Atomic Session Commit & Section-Projected Batch Reading

## Status

Accepted

## Context

Prior to Phase 3 of the Industrial-Scale Roadmap, agents experienced high turn tax and unnecessary context token consumption in two critical workflows:
1. **Mid-Session Exploration Turn Tax**: When inspecting multiple wiki articles or large documents (300+ lines), calling `brain79_read` sequentially required $N$ round trips, and reading entire documents when only a single subsection was needed wasted context window tokens.
2. **End-of-Session Wrap-Up Turn Tax**: Wrapping up a session required 3 to 5 sequential round trips:
   - `brain79_ingest` for raw session logs.
   - `brain79_write` / `brain79_edit` / `brain79_write_many` for article mutations.
   - `brain79_handoff_write` for immutable transition records.
   - Separate verification via `brain79_lint`.

If a late step failed (e.g. an invalid `session_type` or broken handoff constraint), earlier articles were already written to disk, leaving the wiki in a partially committed state.

## Decision

We introduced **Phase 3: Zero-Turn Session Execution**, completing the Two-Call Session Protocol (`brain79_orient` $\rightarrow$ work $\rightarrow$ `brain79_session_commit`):

1. **Section-Projected & Batch Reading (`brain79_read` with `sections` & `brain79_read_batch`)**:
   - `read_article(path, sections=[...])`: Extracts only YAML frontmatter, `# H1`, and the requested `## H2` sections (case-insensitive substring/equality matching).
   - `read_batch_articles(requests)`: Reads multiple articles in a single call, supporting section projection per request.
   - **Governing ADR Hints**: Both single and batch reads automatically append active governing ADR hints (`💡 Linked ADRs: decisions/adr-...`) extracted from `related` frontmatter and markdown links.

2. **1-Call Atomic Session Finalization (`brain79_session_commit` / `brain79 session-commit`)**:
   - Executes raw session archiving (`_raw/sessions/`), article writes, article partial edits, and immutable handoffs in a single all-or-nothing transaction.
   - **Pre-Flight In-Memory Simulation**: All writes are validated against schema rules, all edits are simulated sequentially in memory and validated, and all handoff anti-hallucination constraints are verified *before* disk mutation.
   - **Rollback Guarantee**: If *any* write, edit, or handoff fails validation, **zero files on disk are modified**.
   - **Single Navigation Synchronization**: Synchronizes `.navigation_registry.json` and regenerates `INDEX.md` once under lock for all touched articles.
   - **Unified Inline Receipt**: Evaluates inline health diagnostics (`check_file_health`) across all touched articles and returns a structured commit receipt with health warnings (if any).

3. **Strict 1:1 Symmetry**:
   - FastMCP tools: `brain79_read` (with `sections`), `brain79_read_batch`, `brain79_session_commit`.
   - CLI subcommands: `brain79 read <path> [--sections ...]`, `brain79 read-batch (--file JSON | --stdin)`, `brain79 session-commit (--file JSON | --stdin)`.

## Consequences

- **Positive**: End-of-session turn tax drops from 3–5 turns down to **1 single turn**.
- **Positive**: Total session lifecycle completes in **2 calls** (`brain79_orient` at start, `brain79_session_commit` at conclusion).
- **Positive**: Zero partial-write corruption on invalid handoff or article schemas.
- **Positive**: Context window tokens saved during mid-session inspection via section projection.
- **Positive**: 100% test coverage and static type safety maintained.

---

[← Volver al Índice](../INDEX.md)
