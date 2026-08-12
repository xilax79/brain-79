---
type: architecture
stability: stable
last_updated: 2026-08-11
---

# Architecture — MCP Server

## General Description

The Model Context Protocol (MCP) server integration in `brain-79` enables AI assistants (such as Antigravity, Pi, OpenCode, Claude, Cursor) to interact with repository memory via standard JSON-RPC tools.

## Components & Server Lifecycle

1. **`src/brain79/server.py`**: Declares the `FastMCP("brain79")` instance and registers all `brain79_*` tools.
2. **`src/brain79/__main__.py`**: Invokes `_cmd_serve()` when no subcommand is provided.

## Startup Banner & Logging Suppression

MCP client hosts (like `agy` or `pi`) interpret any standard error (`stderr`) output emitted during the handshake phase as an initialization failure.

To prevent connection drops:
- `FASTMCP_SHOW_SERVER_BANNER=false` is set in `__main__.py` before importing `fastmcp`.
- Loggers for `fastmcp` and `mcp` are configured to level `WARNING` in `server.py`.

## Tool Definitions

All MCP tools are named with the `brain79_` prefix:
- `brain79_index()`: Returns contents of `INDEX.md`.
- `brain79_read(path)`: Reads a wiki article safely.
- `brain79_write(path, content, force_validation_skip)`: Validates and writes a wiki article.
- `brain79_list(section)`: Lists wiki articles.
- `brain79_search(query)`: High-speed keyword search.
- `brain79_ingest(session_summary, instructions)`: Saves raw session log to `_raw/sessions/`.
- `brain79_handoff_write(...)`: Creates an immutable session handoff.
- `brain79_handoff_read(ref)`: Reads a session handoff note.
- `brain79_handoff_purge(apply)`: Purges short-term handoffs.
- `brain79_bootstrap(scope, force)`: Scans repository and returns bootstrap manifest.
- `brain79_navigate(regenerate)`: Queries or regenerates navigation registry.
- `brain79_context(...)`: Performs TF-IDF relevance scoring across articles.
- `brain79_migrate(apply, dry_run)`: Migrates legacy articles to V3 frontmatter schema.

## File Descriptor Teardown (`mcp.close()`)

During shutdown or client disconnection, `FastMCP` closes associated file descriptors cleanly to prevent socket or lock leaks.
