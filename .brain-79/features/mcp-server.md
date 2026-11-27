---
type: feature
summary: model Context Protocol server exposing 9 focused hot-path tools over stdio JSON-RPC
status: shipped
version: 0.16.0
last_updated: 2026-11-26
applies_to:
  - src/brain79/server.py
related:
  - architecture/symmetry.md
  - architecture/mcp-server.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
---

# Feature — FastMCP integration

## Overview

The Model Context Protocol (MCP) server feature exposes `brain-79` hot-path operations as 9 focused tools over JSON-RPC stdio, integrating with AI clients such as Antigravity, Pi, OpenCode, Claude Desktop, and Cursor.

Built using `FastMCP 2.0+`, it suppresses standard error banners during initialization, configures `output_schema=None` across tools to prevent redundant response wrapping, and keeps per-turn schema token overhead minimal. Administrative commands are invoked through the 26-command `brain79 <command>` CLI.

## MCP tools reference (`MCP_TOOLS`)

| MCP tool | CLI equivalent | Purpose |
|---|---|---|
| `brain79_orient(task?, paths?, max_articles?)` | `brain79 orient` | Collapsed 1-call cold start orientation with inlined governing context |
| `brain79_session_commit(...)` | `brain79 session-commit` | 1-call atomic session finalization with Hard Session Ripple Gate |
| `brain79_read(path, sections?)` | `brain79 read <path>` | Read wiki article safely with section projection |
| `brain79_read_batch(requests?, paths?)` | `brain79 read-batch` | Read multiple articles in a single call via `paths=[...]` or `requests=[...]` |
| `brain79_edit(path, edits, ...)` | `brain79 edit <path>` | Targeted text replacement without re-emitting entire article |
| `brain79_context(task, top_n?, paths?)` | `brain79 context` | Retrieve relevant articles via 3-signal ranking |
| `brain79_search(query)` | `brain79 search <query>` | High-speed keyword search |
| `brain79_lint()` | `brain79 lint` | Run deterministic health check scan |
| `brain79_bootstrap(scope?, force?, auto_map?, max_modules?)` | `brain79 bootstrap` | Scan repository and emit zero-overlap `auto_map` governance proposals (default `None` resolves to `True` on `software`) |

## Usage examples

In an AI assistant session:
- Call `brain79_orient(task=..., paths=...)` at cold-start.
- Call `brain79_read("architecture/mcp-server.md")` or `brain79_read_batch(paths=["architecture/mcp-server.md", "features/mcp-server.md"])` to inspect system design.
- Call `brain79_session_commit(writes=[...], edits=[...], handoff={...})` to persist architectural updates atomically.

## Known edge cases

- Stderr output during handshake drops connection on strict clients (`agy`, `pi`); suppressed via `FASTMCP_SHOW_SERVER_BANNER=false` and silent ignoring of `BRAIN79_MCP_PROFILE`.
- `brain79_read_batch` avoids nested `anyOf` union schemas inside `array.items` by exposing flat `paths` and `requests` parameters, returning an actionable usage error string on empty or malformed payloads.
- Writes are guarded by inter-process `filelock` to ensure atomic mutations during concurrent execution.

---

[← Back to Index](../INDEX.md)
