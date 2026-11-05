# Brain-79 AI memory protocol

## Prerequisites (one-time setup)
- Ensure `brain79` is in your system PATH (e.g., via `uv tool install --editable .` or `uv tool ensurepath`).
- **If using the `pi` CLI**: install the Pi MCP adapter once:
  ```bash
  pi install npm:pi-mcp-adapter
  ```
- **If using `agy`, `opencode`, `claude`, `cursor`, or other MCP-compatible CLIs**: ensure `brain79` is registered in your client's MCP configuration (`.mcp.json` or global config).

## Cold start (start of task)
1. Always use the `brain79_orient(task?, paths?)` tool to orient yourself in a single turn before touching code (ingests `INDEX.md`, active handoff, and inlined governing articles & ADRs).
2. If working on a project with an empty wiki, call `brain79_bootstrap` to generate a scan manifest and seed the wiki via `brain79_write`.
3. The `.brain-79/` directory contains the ultimate source of truth.

## Mid-session and handoffs (end of task)
- **On-demand handoff policy**: in interactive human-in-the-loop sessions, write a handoff (`brain79_handoff_write` or `brain79_session_commit(handoff=...)`) **only when explicitly requested by the user** (e.g. "save handoff", "wrap up", "haz handoff"). In autonomous headless sub-agent sessions, write a handoff upon terminating the process. Do not write handoffs after every interactive conversational turn.
- To resume a task, `brain79_orient` automatically provides the latest handoff state (or use `brain79_handoff_read` directly).
- **Handoff freshness and authority decay**: a handoff is a perishable transition note, not a source of truth. If a handoff is marked as stale (due to subsequent wiki or code changes) or comes from another branch, treat its pending work and boot instruction as historical context; verify against current code and governing articles before executing instructions.

## Available tools

> [!IMPORTANT]
> Prefer **MCP tools** when the brain79 MCP server is connected (most reliable).
> If MCP is not available, fall back to the **CLI** (`brain79 <subcommand>`). Both
> interfaces are 1:1 symmetric. Use whatever works in your environment.

### Core wiki operations (MCP preferred, CLI fallback)

| Purpose | MCP tool | CLI command |
|---|---|---|
| Complete 1-call cold start | `brain79_orient(task?, paths?)` | `brain79 orient [--task ...] [--paths ...]` |
| Orient yourself (index only) | `brain79_index()` | `brain79 index` |
| 3-signal context search | `brain79_context(task, top_n?, paths?)` | `brain79 context <task> [--paths ...]` |
| Inspect schema and templates | `brain79_schema(type?)` | `brain79 schema [--type <type>]` |
| Find articles | `brain79_search(query)` | `brain79 search <query>` |
| Read article | `brain79_read(path, sections?)` | `brain79 read <path> [--sections ...]` |
| Batch read articles | `brain79_read_batch(requests)` | `brain79 read-batch --file <path>` |
| Write or update article | `brain79_write(path, content)` | `brain79 write <path> --content-file /dev/stdin` |
| Partial edit | `brain79_edit(path, edits)` | `brain79 edit <path> --old-text ... --new-text ...` |
| Batch write | `brain79_write_many(articles)` | `brain79 write-many --file <path>` |
| 1-call atomic session commit | `brain79_session_commit(...)` | `brain79 session-commit --file <path>` |
| Browse sections | `brain79_list(section?)` | `brain79 list [--section <name>]` |
| Save raw session | `brain79_ingest(summary, instructions?)` | `brain79 ingest --summary-file /dev/stdin` |
| Session handoff (write) | `brain79_handoff_write(...)` | `brain79 handoff-write --session-type feature --summary-file /dev/stdin --boot-instruction-file /dev/stdin` |
| Session handoff (read) | `brain79_handoff_read(ref?)` | `brain79 handoff-read [ref]` |
| Bootstrap legacy project | `brain79_bootstrap(scope?, force?)` | `brain79 bootstrap [--scope <scope>] [--force]` |

### Organizational enforcement (Phases 6–10)

The wiki has **mechanical organizational enforcement** that prevents quality
degradation. Always run these checks before declaring wiki work complete.

| Purpose | MCP tool | CLI command |
|---|---|---|
| **Lint wiki** (find violations) | `brain79_lint()` | `brain79 lint` |
| **Strict lint** (CI mode, exits 1 on issues) | — | `brain79 lint --strict` |
| **Machine-readable lint** | — | `brain79 lint --strict --format json \| jq '.issues'` |
| **Extraction suggestions** for INDEX.md | — | `brain79 lint --suggest-extract` |
| **Preview migration** (dry-run, safe) | `brain79_migrate()` (dry-run by default) | `brain79 migrate` |
| **Apply migration** (destructive) | `brain79_migrate(dry_run=false)` | `brain79 migrate --apply` |
| **Suggest relocations** (where files should live) | — | `brain79 migrate --suggest-relocations` |
| **Regenerate Quick navigation** from registry | `brain79_navigate(regenerate=true)` | `brain79 navigate --regenerate` |
| **Print current Quick navigation** | `brain79_navigate()` | `brain79 navigate` |
| **Purge all handoffs (preview)** | `brain79_handoff_purge()` (dry-run) | `brain79 handoff-purge` |
| **Purge all handoffs (destructive)** | `brain79_handoff_purge(apply=True)` | `brain79 handoff-purge --apply` |

### The two-call session protocol (industrial recipe: 2 calls)

1. **Cold start**: `brain79_orient(task?, paths?)` — returns routing table (`INDEX.md`), latest handoff state with promotion warnings, and inlines top governing articles and ADRs.
2. **Work phase**: edit codebase, optionally inspect specific sections via `brain79_read(path, sections=[...])` or `brain79_read_batch(requests)`.
3. **Session finalization**: `brain79_session_commit(writes?, edits?, handoff?, session_summary?)` — executes the entire wrap-up in a single atomic all-or-nothing transaction.
   Canonical call pattern:
   ```json
   brain79_session_commit(
     writes=[{"path": "topics/example.md", "content": "..."}],
     handoff={
       "session_type": "research",
       "summary": "...",
       "completed_work": ["..."],
       "pending_work": ["..."],
       "boot_instruction": "..."
     }
   )
   ```

### Fallback multi-call end-of-session recipe (3 calls)

1. `brain79_ingest(summary)` — records raw session notes and outputs curation guide.
2. `brain79_write(path, content)` / `brain79_edit(path, edits)` / `brain79_write_many(articles)` — writes automatically sync navigation and run inline health checks.
3. `brain79_handoff_write(...)` — preserves short-term transition state for the next session.

### Article authoring conventions

When creating or updating wiki articles via `brain79_write`, `brain79_edit`, or `brain79_write_many`:
1. **Frontmatter summary**: provide a concise one-line `summary:` in YAML frontmatter (e.g. `summary: one-line explanation of the article`). This summary is indexed directly into `INDEX.md` Quick navigation.
2. **Back-navigation**: include a backlink at the end of the article (`[← Volver al Índice](../INDEX.md)`) for seamless reading in VS Code, Obsidian, and GitHub.

### When fixing wiki issues (workflow)

1. **Survey**: run `brain79 lint --strict --format json | jq '.issues'` to see all violations.
2. **Group**: pipe through `jq '.issues | group_by(.rule) | map({rule: .[0].rule, count: length})'` to plan batch fixes.
3. **Per rule**: each issue has an `actionable` field with the remediation hint.
4. **Bulk legacy**: use `brain79 migrate --apply` to add missing frontmatter to legacy articles (assigns `status: legacy` for human review).
5. **Sync nav**: when performing manual filesystem edits outside MCP, run `brain79 navigate --regenerate` to update INDEX.md. (Note: `brain79_write`, `brain79_edit`, `brain79_write_many`, and `brain79_session_commit` sync INDEX.md automatically).
6. **Verify**: re-run lint and confirm issue count went down.

### Migration safety notes

- `brain79 migrate` (no flags) is **safe by default** — it only previews changes.
- `brain79 migrate --apply` is **destructive** — it mutates files. Only use after reviewing the dry-run output.
- Migration assigns `status: legacy` (not `accepted`/`planned`/`shipped`) to preserve semantic intent. After human review, promote to the correct status manually.

### Force-skip (last resort)

If you must write an article that violates validation (e.g., importing legacy content):

- MCP: `brain79_write(path, content, force_validation_skip=true)`
- CLI: `brain79 write <path> --content-file /dev/stdin --force-validation-skip`

The article is tagged `force_validation_skipped: true` in its frontmatter and surfaces as a `force_skipped_article` warning in `brain79 lint`. Plan to remediate these in a follow-up.

## Documentation and style guidelines (human-first, clean B2)

To maintain consistent, high-quality documentation across all agent and human interactions:

1. **Language level and tone (clean B2)**:
   - Write clear, concise, direct English (CEFR B2 level). Avoid convoluted prose, academic fluff, and excessive jargon.
   - Respect precise technical terms (`atomic rename`, `POSIX mutex`, `BFS reachability`, `JSON-RPC`, `FastMCP`, `TF-IDF`), but explain concepts using plain subject-verb-object sentences.
2. **Visual and structural clarity**:
   - Prefer structured comparisons, concise bullet points, and clean ASCII/text diagrams over dense walls of text.
   - Use clear H2/H3 section hierarchies that allow quick scanning.
3. **Dual-audience rule (human and agent symbiosis)**:
   - While documentation is indexed and consumed by LLMs, it is reviewed and audited by human engineers in Git PRs.
   - Never write cryptic, machine-only shorthand. Plain, clean English reduces entropy for LLM reasoning and guarantees human auditability.
4. **Pure index invariant**:
   - `INDEX.md` is an automated routing table, not a freeform scratchpad. Never write hardcoded roadmaps, task lists, or status paragraphs directly inside `INDEX.md`. Detailed planning belongs in `architecture/`, `product/`, or `decisions/` and is referenced through the index.
5. **Summary and navigation invariants**:
   - Every wiki article must declare an explicit, one-line `summary:` in its frontmatter.
   - Every subfolder article must conclude with the standard back-navigation footer (`[← Volver al Índice](../INDEX.md)`).
6. **Session knowledge triage and persistence protocol (the Amnesia Test, No-Op Idempotence, and Zero-Modification Rule)**:
   - When asked to "update the wiki", "sync docs", or wrap up/close a session, evaluate the conversation using **the Amnesia Test**:
     *"If this session context were wiped right now, would the user lose valuable research findings, domain analysis, forecasts, decisions, or implementation context that took effort to produce?"*
   - Classify the session into one of three categories:
     - **Type A — ephemeral / read-only consultation (zero-modification rule)**: casual chat, greetings, or answering a quick question by reading existing files without generating new domain knowledge or code changes.
       -> **Action**: do not invent or artificially edit wiki articles. Verify health with `brain79_lint()` and state clearly: *"The wiki is up-to-date with repository state. No modifications required."*
     - **Type B — zero-code research, analysis, and discovery (knowledge deliverable)**: domain research, web investigations, forecasts, benchmarks, trade-off analyses, or strategic decisions—**even when zero code files were modified and even in non-Git directories**.
       -> **Action**: in these sessions, **the distilled knowledge is the primary deliverable**. Even if the research or analysis is about an external topic, sports, market data, or non-code domain unrelated to source files, if the user researched it during the session and asks to update the wiki or close the session, you must persist a structured article in `topics/<slug>.md` (or `decisions/<slug>.md`). Never dismiss user research as 'external' or 'non-code'. Persist and commit findings atomically via `brain79_session_commit(writes=[...], handoff={...})`. Never dump raw chat transcripts; distill clean headings, tables, conclusions, and sources.
     - **Type C — code and workspace mutation**: source code, configuration, or tests were created or modified.
       -> **Action**: update or create the corresponding governing articles (`features/`, `architecture/`, `decisions/`, `changelog/`) and commit via `brain79_session_commit(...)`.
7. **Sentence case first policy (mandatory)**:
   - Use sentence-style capitalization for all titles, headings (H1, H2, H3), bullet points, and table headers across documentation, manifests, and wiki generation.
   - Capitalize ONLY the first letter of a title or sentence. The rest must be lowercase.
   - The only exceptions are proper nouns (e.g., Python, Stripe, Docker, Linux, macOS, Boca Juniors, Palmeiras) and acronyms (e.g., ADR, MCP, API, CI, JSON, POSIX, LF, CRLF, TF-IDF, BFS).
   - After a colon (`:`), the following word must start with a lowercase letter unless it is a proper noun or acronym (e.g., `- Item 1: description`, not `- Item 1: Description`).
   - Place colons outside bold formatting: `- **Label**: description`, never `- **Label:** Description`.
   - Never use Title Case (capitalizing every major word). Title Case is prohibited across all documentation artifacts.

## Project notes

> Add project-specific guidance here: coding conventions, deployment steps,
> common gotchas, links to runbooks, etc.
