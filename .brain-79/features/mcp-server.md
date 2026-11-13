---
type: feature
summary: Model Context Protocol server exposing wiki operations as JSON-RPC tools with token de-duplication
status: shipped
version: 0.9.0
last_updated: 2026-11-13
applies_to:
  - src/brain79/server.py
related:
  - architecture/symmetry.md
  - architecture/mcp-server.md
applies_to_digest: "sha256:d1f7568c7f9bcb4e"
applies_to_count: 1
---

# Feature — FastMCP integration

## Overview

The Model Context Protocol (MCP) server feature exposes `brain-79` operations as structured tools over JSON-RPC over stdio, integrating seamlessly with AI clients such as Antigravity, Pi, OpenCode, Claude Desktop, and Cursor.

Built using `FastMCP 2.0+`, it suppresses standard error banners during initialization and configures `output_schema=None` across tools to prevent redundant response wrapping, saving token bandwidth in AI harnesses.

## MCP tools reference

| MCP Tool | CLI Equivalent | Purpose |
|---|---|---|
| `brain79_orient(task?, paths?)` | `brain79 orient` | Collapsed 1-call cold start orientation with inlined governing context |
| `brain79_index()` | `brain79 index` | Retrieve `INDEX.md` entry point |
| `brain79_schema(target_type?)` | `brain79 schema` | Inspect schema constraints and copy-paste templates |
| `brain79_read(path, sections?)` | `brain79 read <path>` | Read wiki article safely with section projection |
| `brain79_read_batch(requests)` | `brain79 read-batch` | Read multiple articles in a single call |
| `brain79_write(path, content, ...)` | `brain79 write <path>` | Write or update wiki article with validation and auto-navigation |
| `brain79_edit(path, edits, ...)` | `brain79 edit <path>` | Targeted text replacement without re-emitting entire article |
| `brain79_write_many(articles, ...)` | `brain79 write-many` | Batch validate and atomically write multiple articles |
| `brain79_session_commit(...)` | `brain79 session-commit` | 1-call atomic session finalization with Hard Session Ripple Gate |
| `brain79_list(section?)` | `brain79 list [--section <name>]` | List available wiki articles |
| `brain79_search(query)` | `brain79 search <query>` | High-speed keyword search via ripgrep |
| `brain79_ingest(session_summary, ...)` | `brain79 ingest` | Ingest raw session summary to `_raw/sessions/` |
| `brain79_handoff_write(...)` | `brain79 handoff-write` | Create structured, immutable session handoff |
| `brain79_handoff_read(ref?)` | `brain79 handoff-read` | Read referenced session handoff |
| `brain79_handoff_purge(apply?)` | `brain79 handoff-purge` | Purge short-term handoffs |
| `brain79_lint()` | `brain79 lint` | Run deterministic health check scan |
| `brain79_bootstrap(scope?, force?)` | `brain79 bootstrap` | Scan repository and return manifest |
| `brain79_navigate(regenerate?)` | `brain79 navigate` | Query or update navigation registry |
| `brain79_context(task, top_n?, paths?)` | `brain79 context` | Retrieve relevant articles via 3-signal ranking |
| `brain79_migrate(apply?, dry_run?)` | `brain79 migrate` | Migrate legacy articles to frontmatter V3 |
| `brain79_update_project(...)` | `brain79 update-project` | Non-destructively upgrade templates, schemas, and MCP harnesses |
| `brain79_doctor(fix?, force?, ...)` | `brain79 doctor` | Run 7-point operational diagnostic checks and auto-repair |

## Usage examples

In an AI assistant session:
- Call `brain79_index()` at cold-start.
- Call `brain79_read("architecture/mcp-server.md")` to inspect system design.
- Call `brain79_write("decisions/adr-001.md", content)` to persist architectural decisions.

## Known edge cases

- Stderr output during handshake drops connection on strict clients (`agy`, `pi`); suppressed via `FASTMCP_SHOW_SERVER_BANNER=false`.
- Writes are guarded by inter-process `filelock` to ensure atomic mutations during concurrent execution.

---

[← Volver al Índice](../INDEX.md)
