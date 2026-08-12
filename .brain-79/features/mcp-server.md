---
type: feature
status: shipped
version: 1.0.0
last_updated: 2026-08-11
---

# Feature — FastMCP Integration

## Overview

The Model Context Protocol (MCP) server feature exposes `brain-79` operations as structured tools over JSON-RPC over stdio, integrating seamlessly with AI clients such as Antigravity, Pi, OpenCode, Claude Desktop, and Cursor.

Built using `FastMCP 2.0`, it suppresses standard error banners during initialization to prevent connection handshakes from failing.

## MCP Tools Reference

| MCP Tool | CLI Equivalent | Purpose |
|---|---|---|
| `brain79_index()` | `brain79 index` | Retrieve `INDEX.md` entry point |
| `brain79_read(path)` | `brain79 read <path>` | Read wiki article safely |
| `brain79_write(path, content, force_validation_skip)` | `brain79 write <path>` | Write or update wiki article with validation |
| `brain79_list(section)` | `brain79 list [--section <name>]` | List available wiki articles |
| `brain79_search(query)` | `brain79 search <query>` | High-speed keyword search via ripgrep |
| `brain79_ingest(session_summary, instructions)` | `brain79 ingest` | Ingest raw session summary to `_raw/sessions/` |
| `brain79_handoff_write(...)` | `brain79 handoff-write` | Create structured, immutable session handoff |
| `brain79_handoff_read(ref)` | `brain79 handoff-read` | Read referenced session handoff |
| `brain79_handoff_purge(apply)` | `brain79 handoff-purge` | Purge short-term handoffs |
| `brain79_bootstrap(scope, force)` | `brain79 bootstrap` | Scan repository and return manifest |
| `brain79_navigate(regenerate)` | `brain79 navigate` | Query or update navigation registry |
| `brain79_context(query)` | `brain79 context` | Retrieve relevant articles via TF-IDF |
| `brain79_migrate(apply, dry_run)` | `brain79 migrate` | Migrate legacy articles to frontmatter V3 |

## Usage Examples

In an AI assistant session:
- Call `brain79_index()` at cold-start.
- Call `brain79_read("architecture/mcp-server.md")` to inspect system design.
- Call `brain79_write("decisions/adr-001.md", content)` to persist architectural decisions.

## Known Edge Cases

- Stderr output during handshake drops connection on strict clients (`agy`, `pi`); suppressed via `FASTMCP_SHOW_SERVER_BANNER=false`.
- Writes are guarded by inter-process `filelock` to ensure atomic mutations during concurrent execution.
