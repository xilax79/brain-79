---
name: brain79-wiki
description: Comprehensive operational manual and command reference for the brain-79 persistent memory protocol, MCP tools, CLI workflows, and wiki governance.
---

# Brain-79 operational reference and command manual

## Available tools

> [!IMPORTANT]
> Prefer **MCP tools** when the brain79 MCP server is connected (most reliable).
> The MCP server exposes **9 focused hot-path tools**: `brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, and `brain79_bootstrap`.
> For administrative, CI, and operational commands, use the **26-command CLI** (`brain79 <subcommand>`).

### Session & knowledge operations (MCP preferred, CLI superset)

| Purpose | MCP tool | CLI command |
|---|---|---|
| Complete 1-call cold start | `brain79_orient(task?, paths?)` | `brain79 orient [--task ...] [--paths ...]` |
| Orient yourself (index only) | — (CLI only) | `brain79 index` |
| 3-signal context search | `brain79_context(task, top_n?, paths?)` | `brain79 context <task> [--paths ...]` |
| Inspect schema and templates | — (CLI only) | `brain79 schema [--type <type>]` |
| Find articles | `brain79_search(query)` | `brain79 search <query>` |
| Read article | `brain79_read(path, sections?)` | `brain79 read <path> [--sections ...]` |
| Batch read articles | `brain79_read_batch(paths=["architecture/overview.md", "features/auth.md"])` | `brain79 read-batch --paths <p1> [<p2> ...] \| --file <path>` |
| Write or update article | Use `brain79_session_commit(writes=[...])` | `brain79 write <path> --content-file /dev/stdin` |
| Partial edit | `brain79_edit(path, edits)` | `brain79 edit <path> --old-text ... --new-text ...` |
| Batch write | Use `brain79_session_commit(writes=[...])` | `brain79 write-many --file <path>` |
| 1-call atomic session commit | `brain79_session_commit(...)` | `brain79 session-commit --file <path>` |
| Browse sections | — (CLI only) | `brain79 list [--section <name>]` |
| Save raw session | Pass `session_summary` to `brain79_session_commit` | `brain79 ingest --summary-file /dev/stdin` |
| Session handoff (write) | Pass `handoff` to `brain79_session_commit` | `brain79 handoff-write --session-type feature --summary-file /dev/stdin --boot-instruction-file /dev/stdin` |
| Session handoff (read) | Included in `brain79_orient` | `brain79 handoff-read [ref]` |
| Bootstrap legacy project | `brain79_bootstrap(scope?, force?)` | `brain79 bootstrap [--scope <scope>] [--force]` |

### Organizational enforcement and wiki governance

The wiki has **mechanical organizational enforcement** that prevents quality
degradation. Always run these checks before declaring wiki work complete.

| Purpose | MCP tool | CLI command |
|---|---|---|
| **Lint wiki** (find violations) | `brain79_lint()` | `brain79 lint` |
| **Strict lint** (CI mode, exits 1 on issues) | — | `brain79 lint --strict` |
| **CI governance & PR gate** | — | `brain79 ci-check [--base <ref>] [--enforcement <tier>]` |
| **Context & budget telemetry** | — | `brain79 stats [--task ...] [--paths ...]` |
| **Opt-in lifecycle hooks** | — | `brain79 update-project --install-lifecycle-hooks` |
| **Machine-readable lint** | — | `brain79 lint --strict --format json \| jq '.issues'` |
| **Extraction suggestions** for INDEX.md | — | `brain79 lint --suggest-extract` |
| **Preview migration** (dry-run, safe) | — | `brain79 migrate` |
| **Apply migration** (destructive) | — | `brain79 migrate --apply` |
| **Suggest relocations** (where files should live) | — | `brain79 migrate --suggest-relocations` |
| **Regenerate Quick navigation** from registry | — | `brain79 navigate --regenerate` |
| **Print current Quick navigation** | — | `brain79 navigate` |
| **Purge all handoffs (preview)** | — | `brain79 handoff-purge` |
| **Purge all handoffs (destructive)** | — | `brain79 handoff-purge --apply` |

### The two-call session protocol (industrial recipe: 2 calls)

1. **Cold start**: `brain79_orient(task?, paths?)` — returns routing table (`INDEX.md`), latest handoff state with promotion warnings, and inlines top governing articles and ADRs.
2. **Work phase**: edit codebase, optionally inspect specific sections via `brain79_read(path, sections=[...])` or `brain79_read_batch(paths=[...])`.
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

### Fallback CLI multi-call recipe (3 calls)

1. `brain79 ingest --summary-file /dev/stdin` — records raw session notes and outputs curation guide.
2. `brain79 write <path> ...` / `brain79 edit <path> ...` / `brain79 write-many --file ...` — writes automatically sync navigation and run inline health checks.
3. `brain79 handoff-write ...` — preserves short-term transition state for the next session.

### Article authoring conventions

When creating or updating wiki articles via `brain79_session_commit` or `brain79_edit`:
1. **Frontmatter summary**: provide a concise one-line `summary:` in YAML frontmatter (e.g. `summary: one-line explanation of the article`). This summary is indexed directly into `INDEX.md` Quick navigation.
2. **Back-navigation**: include a backlink at the end of the article (`[← Back to Index](../INDEX.md)`, configurable via `backlink_label:` in `SCHEMA.md`) for seamless reading in VS Code, Obsidian, and GitHub.

### When fixing wiki issues (workflow)

1. **Survey**: run `brain79 lint --strict --format json | jq '.issues'` to see all violations.
2. **Group**: pipe through `jq '.issues | group_by(.rule) | map({rule: .[0].rule, count: length})'` to plan batch fixes.
3. **Per rule**: each issue has an `actionable` field with the remediation hint.
4. **Bulk legacy**: use `brain79 migrate --apply` to add missing frontmatter to legacy articles (assigns `status: legacy` for human review).
5. **Sync nav**: when performing manual filesystem edits outside MCP/CLI, run `brain79 navigate --regenerate` to update `INDEX.md`. (Note: `brain79_edit`, `brain79_session_commit`, and `brain79 write`/`write-many` sync `INDEX.md` automatically).
6. **Verify**: re-run lint and confirm issue count went down.

### Migration safety notes

- `brain79 migrate` (no flags) is **safe by default** — it only previews changes.
- `brain79 migrate --apply` is **destructive** — it mutates files. Only use after reviewing the dry-run output.
- Migration assigns `status: legacy` (not `accepted`/`planned`/`shipped`) to preserve semantic intent. After human review, promote to the correct status manually.

### Force-skip (last resort)

If you must write an article that violates validation (e.g., importing legacy content):

- MCP: `brain79_session_commit(writes=[{"path": "...", "content": "..."}], force_validation_skip=true)`
- CLI: `brain79 write <path> --content-file /dev/stdin --force-validation-skip`

The article is tagged `force_validation_skipped: true` in its frontmatter and surfaces as a `force_skipped_article` warning in `brain79 lint`. Plan to remediate these in a follow-up.
