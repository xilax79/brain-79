---
type: architecture
summary: enforces MCP-subset / CLI-superset symmetry between the 9 focused FastMCP tools and 25 CLI subcommands
stability: stable
last_updated: 2026-11-24
applies_to:
  - src/brain79/cli/dispatch.py
  - src/brain79/server.py
  - tests/test_symmetry.py
related:
  - architecture/current-state.md
  - features/cli.md
  - features/mcp-server.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
applies_to_digest: "sha256:ac2b1c0ec4d78eff"
applies_to_count: 3
---

# Architecture — CLI and MCP symmetry

## General description

`brain-79` enforces an **MCP-subset / CLI-superset** symmetry invariant (ADR-020). The CLI exposes the complete 25-subcommand operational, CI, and administrative surface (`WHITELIST`), while the FastMCP server exposes a focused 9-tool hot-path subset (`MCP_TOOLS`).

## Symmetry guarantee and enforcement

Symmetry is automatically validated by `tests/test_symmetry.py`. The test suite inspects:
- `len(WHITELIST) == 25` CLI subcommands.
- Every tool registered on `create_mcp_server()` and module-level `mcp` equals `MCP_TOOLS` (9 tools) and maps 1:1 into `WHITELIST` (`mcp_cli_names.issubset(WHITELIST)`).
- Parameter signatures and defaults for retained MCP tools (`brain79_session_commit`, `brain79_bootstrap`) match their `brain79.core.*` implementations.

## Operational mapping table

| Operational purpose | CLI subcommand (25) | MCP tool (9) |
|---|---|---|
| Initialize wiki protocol | `brain79 init` | *(CLI only)* |
| Self-update installation | `brain79 update` | *(CLI only)* |
| Complete 1-call cold start | `brain79 orient [--task ...] [--paths ...]` | `brain79_orient(task?, paths?)` |
| Read `INDEX.md` entrypoint | `brain79 index` | *(CLI only; included in `orient`)* |
| Inspect schema and templates | `brain79 schema [--type <t>]` | *(CLI only; summary in `orient`)* |
| Read wiki article | `brain79 read <path> [--sections ...]` | `brain79_read(path, sections?)` |
| Batch read articles | `brain79 read-batch --file <f>` | `brain79_read_batch(requests)` |
| Write wiki article | `brain79 write <path>` | *(Use `brain79_session_commit`)* |
| Partial in-place edit | `brain79 edit <path>` | `brain79_edit(path, edits, ...)` |
| Batch write articles | `brain79 write-many --file <f>` | *(Use `brain79_session_commit`)* |
| 1-call atomic session commit | `brain79 session-commit --file <f>` | `brain79_session_commit(...)` |
| List articles | `brain79 list [--section <name>]` | *(CLI only)* |
| Search articles | `brain79 search <query>` | `brain79_search(query)` |
| Ingest session summary | `brain79 ingest` | *(Use `brain79_session_commit`)* |
| Write session handoff | `brain79 handoff-write` | *(Use `brain79_session_commit`)* |
| Read session handoff | `brain79 handoff-read [ref]` | *(CLI only; included in `orient`)* |
| Purge session handoffs | `brain79 handoff-purge [--apply]` | *(CLI only)* |
| Bootstrap legacy project | `brain79 bootstrap` | `brain79_bootstrap(scope?, force?, auto_map?, max_modules?)` |
| Sync navigation registry | `brain79 navigate [--regenerate]` | *(CLI only)* |
| Query relevant context | `brain79 context <query>` | `brain79_context(task, top_n?, paths?)` |
| Migrate legacy frontmatter | `brain79 migrate [--apply]` | *(CLI only)* |
| Lint wiki organization | `brain79 lint [--strict]` | `brain79_lint()` |
| CI PR gate and lifecycle hooks | `brain79 ci-check` | *(CLI only; ADR-020 / ADR-021)* |
| Upgrade project protocol | `brain79 update-project` | *(CLI only)* |
| Operational diagnostics | `brain79 doctor [--fix]` | *(CLI only)* |

## Dry-run default invariant

To ensure safety in the CLI, destructive administrative actions default to dry-run preview:
- `brain79 handoff-purge` defaults to preview (requires `--apply` to execute deletions).
- `brain79 migrate` defaults to dry-run preview (requires `--apply` to apply frontmatter mutations).

---

[← Back to Index](../INDEX.md)
