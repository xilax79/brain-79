---
type: architecture
stability: stable
last_updated: 2026-08-11
---

# Architecture — CLI & MCP Symmetry

## General Description

`brain-79` enforces strict 1:1 symmetry between CLI subcommands and MCP server tools. Any capability available to a human user in the terminal via `brain79 <subcommand>` is equally accessible to an AI agent via `brain79_<tool>()`.

## Symmetry Guarantee & Enforcement

Symmetry is automatically validated by `tests/test_symmetry.py`. The test suite inspects:
- Every subcommand in `WHITELIST` (`dispatch.py`) has a corresponding `@mcp.tool()` definition in `server.py`.
- Parameter mappings, default values, and operational semantics match identically across interfaces.

## Operational Mapping Table

| Operational Purpose | CLI Subcommand | MCP Tool |
|---|---|---|
| Initialize wiki protocol | `brain79 init` | (CLI only setup step) |
| Self-update installation | `brain79 update` | (CLI only setup step) |
| Read INDEX.md entrypoint | `brain79 index` | `brain79_index()` |
| Read wiki article | `brain79 read <path>` | `brain79_read(path)` |
| Write wiki article | `brain79 write <path>` | `brain79_write(path, content)` |
| List articles | `brain79 list [--section <name>]` | `brain79_list(section)` |
| Search articles | `brain79 search <query>` | `brain79_search(query)` |
| Ingest session summary | `brain79 ingest` | `brain79_ingest(session_summary)` |
| Write session handoff | `brain79 handoff-write` | `brain79_handoff_write(...)` |
| Read session handoff | `brain79 handoff-read [ref]` | `brain79_handoff_read(ref)` |
| Purge session handoffs | `brain79 handoff-purge [--apply]` | `brain79_handoff_purge(apply)` |
| Bootstrap legacy project | `brain79 bootstrap` | `brain79_bootstrap(scope, force)` |
| Sync navigation registry | `brain79 navigate [--regenerate]` | `brain79_navigate(regenerate)` |
| Query relevant context | `brain79 context <query>` | `brain79_context(query)` |
| Migrate legacy frontmatter | `brain79 migrate [--apply]` | `brain79_migrate(dry_run, apply)` |
| Lint wiki organization | `brain79 lint [--strict]` | (CLI primary, called via hooks & scripts) |

## Dry-Run Default Invariant

To ensure safety across both interfaces, destructive actions default to dry-run preview:
- `brain79 handoff-purge` defaults to preview (requires `--apply` or `apply=True` to execute deletions).
- `brain79 migrate` defaults to dry-run preview (requires `--apply` or `apply=True` to apply frontmatter mutations).
