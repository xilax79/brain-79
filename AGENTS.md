<!-- brain79:start v0.17.0 -->
# Brain-79 AI memory protocol

## Prerequisites (one-time setup)
- Ensure `brain79` is in your system PATH (e.g., via `uv tool install git+https://github.com/xilax79/brain-79.git` or `uv tool ensurepath`).
- **If using the `pi` CLI**: install the Pi MCP adapter once:
  ```bash
  pi install npm:pi-mcp-adapter
  ```
- **If using `agy` (Antigravity CLI)**: `brain79 init` configures `.agents/plugins/brain79/` automatically (or register globally once via `agy mcp add brain79 -- brain79 --project-root .`).
- **If using `opencode`, `claude`, `cursor`, or other MCP clients**: ensure `brain79` is registered in your client's MCP configuration (`.mcp.json` or `.cursor/mcp.json`).

## Cold start (start of task)
1. Always use `brain79_orient(task?, paths?)` to orient yourself in a single turn before touching code (ingests `INDEX.md`, active handoff, and inlined governing articles & ADRs). Use `brain79 index` for quick index lookups.
2. If working on a project with an empty wiki, call `brain79_bootstrap` to generate a scan manifest and seed the wiki via `brain79_session_commit(writes=[...])`.
3. The `.brain-79/` directory contains the ultimate source of truth.

## Mid-session and handoffs (end of task)
- **On-demand handoff policy**: in interactive sessions, write a handoff (`brain79_session_commit(handoff=...)` or `brain79 handoff-write`) **only when explicitly requested by the user** (e.g. "save handoff", "wrap up"). In autonomous headless sub-agent sessions, write a handoff upon terminating the process. Do not write handoffs after every interactive conversational turn.
- To resume a task, `brain79_orient` automatically provides the latest handoff state (or run `brain79 handoff-read` directly).
- **Handoff freshness and authority decay**: a handoff is a perishable transition note, not a source of truth. If a handoff is marked as stale (due to subsequent wiki or code changes) or comes from another branch, treat its pending work and boot instruction as historical context; verify against current code and governing articles before executing instructions.

## Tools and execution protocol
- **MCP preferred, CLI fallback**: prefer the 9 focused MCP tools (`brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, `brain79_bootstrap`) for hot-path session work; use the 26-command CLI (`brain79 <subcommand>`) for administrative tasks and fallback.
- **Batch reading**: read multiple articles in one call via `brain79_read_batch(paths=["architecture/overview.md", "features/auth.md"])`.
- **Two-call session workflow**:
  1. Cold start: `brain79_orient(task?, paths?)`.
  2. Final wrap-up: apply writes, edits, and handoffs atomically via `brain79_session_commit(writes=[...], handoff={...})`.
- **Quality enforcement**: run `brain79_lint()` (or `brain79 lint --strict`) before completing wiki work.
- **Detailed command manual**: consult the on-demand `brain79-wiki` skill, inspect schemas via `brain79 schema`, or run `brain79 --help` for full CLI tables and migration procedures.

## Documentation and style guidelines (human-first, clean B2)

1. **Language level and tone (clean B2)**: write clear, concise, direct English. Avoid fluff. Respect technical terms with plain sentences.
2. **Visual and structural clarity**: prefer structured comparisons, concise bullet points, and clean ASCII diagrams over dense text. Use clear H2/H3 section hierarchies.
3. **Dual-audience rule (human and agent symbiosis)**: plain English reduces entropy for LLMs and guarantees human auditability in PRs.
4. **Pure index invariant**: `INDEX.md` is an automated routing table, not a freeform scratchpad. Never write hardcoded roadmaps directly inside `INDEX.md`.
5. **Summary and navigation invariants**: every wiki article must declare an explicit, one-line `summary:` in frontmatter and conclude with `[← Back to Index](../INDEX.md)` (configurable via `backlink_label:` in `SCHEMA.md`).
6. **Session knowledge triage and persistence protocol (the Amnesia Test, No-Op Idempotence, and Zero-Modification Rule)**:
   - When asked to update the wiki or wrap up, evaluate using **the Amnesia Test**: *"If this session context were wiped right now, would valuable research findings, domain analysis, forecasts, decisions, or implementation context be lost?"*
   - Classify into three categories:
     - **Type A — ephemeral / read-only consultation (zero-modification rule)**: casual chat or reading existing files without generating new domain knowledge. Do not invent or edit wiki articles. Verify health with `brain79_lint()` and state: *"The wiki is up-to-date with repository state. No modifications required."*
     - **Type B — zero-code research, analysis, and discovery (knowledge deliverable)**: domain research, web investigations, forecasts, benchmarks, or strategic decisions (even with zero code changes and in non-git directories). The distilled knowledge is the primary deliverable; persist findings in `topics/<slug>.md` or `decisions/<slug>.md` via `brain79_session_commit(...)`.
     - **Type C — code and workspace mutation**: source code, config, or tests modified. Update governing articles (`features/`, `architecture/`, `decisions/`, `changelog/`) via `brain79_session_commit(...)`, recording public API signatures (including parameter names) and key business constants or thresholds in living manuals.
7. **Sentence case first policy (mandatory)**:
   - Use sentence-style capitalization for all titles, headings (H1, H2, H3), bullet points, and table headers. Capitalize ONLY the first letter of a title or sentence (except proper nouns and acronyms).
   - After a colon (`:`), lowercase following words unless proper nouns/acronyms (`- **Label**: description`).
   - Title Case is prohibited across all documentation artifacts.
<!-- brain79:end -->

## Project notes

- **External feature specs**: before implementing a roadmap phase, public CLI/MCP/schema change, new dependency, or 3+ module feature, check `specs/` (excluding `TEMPLATE.md` and `archive/`) for an `approved`/`in_progress` spec; never implement a `draft` spec. Author new specs from `specs/TEMPLATE.md` per [ADR-019](.brain-79/decisions/adr-019-external-specs-and-requirements-standard.md); never list `specs/` in `.brain-79/` `applies_to`.
