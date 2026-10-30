# Brain-79 AI Memory Protocol

## Prerequisites (one-time setup)
- Ensure `brain79` is in your system PATH (e.g., via `uv tool install --editable .` or `uv tool ensurepath`).
- **If using the `pi` CLI:** Install the Pi MCP adapter once:
  ```bash
  pi install npm:pi-mcp-adapter
  ```
- **If using `agy`, `opencode`, `claude`, `cursor`, or other MCP-compatible CLIs:** Ensure `brain79` is registered in your client's MCP configuration (`.mcp.json` or global config).

## Cold Start (Start of task)
1. ALWAYS use the `brain79_index` tool to orient yourself before touching code.
2. If working on a project with an empty wiki, call `brain79_bootstrap` to generate a scan manifest and seed the wiki via `brain79_write`.
3. The `.brain-79/` directory contains the ultimate source of truth.

## Mid-Session and Handoffs (End of task)
- Before concluding a session, use `brain79_handoff_write` to store progress.
- To resume a task, use `brain79_handoff_read` immediately.

## Available tools

> [!IMPORTANT]
> Prefer **MCP tools** when the brain79 MCP server is connected (most reliable).
> If MCP is not available, fall back to the **CLI** (`brain79 <subcommand>`). Both
> interfaces are 1:1 symmetric. Use whatever works in your environment.

### Core wiki operations (MCP preferred, CLI fallback)

| Purpose | MCP tool | CLI command |
|---|---|---|
| Orient yourself | `brain79_index()` | `brain79 index` |
| Inspect schema & templates | `brain79_schema(type?)` | `brain79 schema [--type <type>]` |
| Find articles | `brain79_search(query)` | `brain79 search <query>` |
| Read article | `brain79_read(path)` | `brain79 read <path>` |
| Write/update article | `brain79_write(path, content)` | `brain79 write <path> --content-file /dev/stdin` |
| Partial edit | `brain79_edit(path, edits)` | `brain79 edit <path> --old-text ... --new-text ...` |
| Batch write | `brain79_write_many(articles)` | `brain79 write-many --file <path>` |
| Browse sections | `brain79_list(section?)` | `brain79 list [--section <name>]` |
| Save raw session | `brain79_ingest(summary, instructions?)` | `brain79 ingest --summary-file /dev/stdin` |
| Session handoff (write) | `brain79_handoff_write(...)` | `brain79 handoff-write --session-type feature --summary-file /dev/stdin --boot-instruction-file /dev/stdin` |
| Session handoff (read) | `brain79_handoff_read(ref?)` | `brain79 handoff-read [ref]` |
| Bootstrap legacy project | `brain79_bootstrap(scope?, force?)` | `brain79 bootstrap [--scope <scope>] [--force]` |

### Organizational enforcement (Phase 6-10)

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

### Fast End-of-Session Recipe (Target: 2-3 calls)

1. `brain79_ingest(summary)` — Records raw session notes and outputs curation guide.
2. `brain79_write(path, content)` / `brain79_edit(path, edits)` / `brain79_write_many(articles)` — Writes automatically sync navigation and run inline health checks.
3. `brain79_handoff_write(...)` — Preserves short-term transition state for the next session.


### Article authoring conventions

When creating or updating wiki articles via `brain79_write`, `brain79_edit`, or `brain79_write_many`:
1. **Frontmatter Summary**: Provide a concise one-line `summary:` in YAML frontmatter (e.g. `summary: One-line explanation of the article`). This summary is indexed directly into `INDEX.md` Quick navigation.
2. **Back-Navigation**: Include a backlink at the end of the article (`[← Volver al Índice](../INDEX.md)`) for seamless reading in VS Code, Obsidian, and GitHub.

### When fixing wiki issues (workflow)

1. **Survey**: run `brain79 lint --strict --format json | jq '.issues'` to see all violations.
2. **Group**: pipe through `jq '.issues | group_by(.rule) | map({rule: .[0].rule, count: length})'` to plan batch fixes.
3. **Per rule**: each issue has an `actionable` field with the remediation hint.
4. **Bulk legacy**: use `brain79 migrate --apply` to add missing frontmatter to legacy articles (assigns `status: legacy` for human review).
5. **Sync nav**: after writing articles, run `brain79 navigate --regenerate` to update INDEX.md.
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

## Documentation & Style Guidelines (Human-First, Clean B2)

To maintain consistent, high-quality documentation across all agent and human interactions:

1. **Language Level & Tone (Clean B2):**
   - Write clear, concise, direct English (CEFR B2 level). Avoid convoluted prose, academic fluff, and excessive jargon.
   - Respect precise technical terms (`atomic rename`, `POSIX mutex`, `BFS reachability`, `JSON-RPC`, `FastMCP`, `TF-IDF`), but explain concepts using plain subject-verb-object sentences.
2. **Visual & Structural Clarity:**
   - Prefer structured comparisons, concise bullet points, and clean ASCII/text diagrams over dense walls of text.
   - Use clear H2/H3 section hierarchies that allow quick scanning.
3. **Dual-Audience Rule (Human & Agent Symbiosis):**
   - While documentation is indexed and consumed by LLMs, it is reviewed and audited by human engineers in Git PRs.
   - Never write cryptic, machine-only shorthand. Plain, clean English reduces entropy for LLM reasoning and guarantees human auditability.
3. **Pure Index Invariant**: `INDEX.md` is an automated routing table, not a freeform scratchpad. Never write hardcoded roadmaps, task lists, or status paragraphs directly inside `INDEX.md`. Detailed planning belongs in `architecture/`, `product/`, or `decisions/` and is referenced through the index.
4. **Summary & Navigation Invariants**:
   - Every wiki article must declare an explicit, one-line `summary:` in its frontmatter.
   - Every subfolder article must conclude with the standard back-navigation footer (`[← Volver al Índice](../INDEX.md)`).

## Project notes

> Add project-specific guidance here: coding conventions, deployment steps,
> common gotchas, links to runbooks, etc.
