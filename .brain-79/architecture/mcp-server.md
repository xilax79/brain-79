---
type: architecture
summary: FastMCP server architecture, logging suppression, focused 9-tool surface, and lifecycle management
stability: stable
last_updated: 2026-11-26
applies_to:
  - src/brain79/server.py
  - src/brain79/__main__.py
related:
  - architecture/symmetry.md
  - features/mcp-server.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
applies_to_digest: "sha256:ab96c29b4631f1ec"
applies_to_count: 2
---

# Architecture — MCP server

## General description

The Model Context Protocol (MCP) server integration in `brain-79` enables AI assistants (such as Antigravity, Pi, OpenCode, Claude, Cursor) to interact with repository memory via a focused 9-tool JSON-RPC surface.

## Components and server lifecycle

1. **`src/brain79/server.py`**: declares `FastMCP("brain79", version=__version__, instructions=_SERVER_INSTRUCTIONS)` and registers the 9 `MCP_TOOLS` with `output_schema=None` to prevent redundant response payloads. Implements `_unpack_nested_args` to unpack double-wrapped JSON arguments from proxy callers.
2. **`src/brain79/__main__.py`**: invokes `_cmd_serve()` when no subcommand is provided, silently ignoring legacy `BRAIN79_MCP_PROFILE` env vars.

## Startup banner and logging suppression

MCP client hosts (like `agy` or `pi`) interpret any standard error (`stderr`) output emitted during the handshake phase as an initialization failure.

To prevent connection drops:
- `FASTMCP_SHOW_SERVER_BANNER=false` is set in `__main__.py` before importing `fastmcp`.
- Loggers for `fastmcp` and `mcp` are configured to level `WARNING` in `server.py`.

## Tool definitions (`MCP_TOOLS`)

The 9 focused MCP tools are named with the `brain79_` prefix:
- `brain79_orient(task?, paths?, max_articles?)`: 1-call cold start orientation with inlined governing articles, `Active Schema Summary` `applies_to` strictness parity, bounded unread-active-articles reminder, and handoff freshness.
- `brain79_session_commit(...)`: 1-call atomic session finalization with Hard Session Ripple Gate and strict-mode `unanchored_governance_article` pre-flight parity.
- `brain79_read(path, sections?)`: reads a wiki article safely with optional section projection.
- `brain79_read_batch(requests?, paths?)`: reads multiple articles in a single call; exposes flat `requests: list[Any] | None = None` and `paths: list[Any] | None = None` (avoiding nested `anyOf` wire schemas), normalizes `.brain-79/` prefixes, deduplicates preserving order, and returns actionable usage errors on empty or invalid inputs.
- `brain79_edit(path, edits, force_validation_skip?)`: performs targeted in-place text replacements without re-emitting entire articles, enforcing strict-mode `unanchored_governance_article` pre-flight validation and `check_file_health()` warnings.
- `brain79_context(task, top_n?, paths?)`: performs 3-signal context ranking across articles.
- `brain79_search(query)`: high-speed keyword search.
- `brain79_lint()`: runs full health check scan across the entire wiki.
- `brain79_bootstrap(scope?, force?, auto_map?, max_modules?)`: scans repository and returns bootstrap manifest with profile-aware `auto_map: bool | None = None` (resolving to `True` for `software` and `False` for `general`).

Administrative operations (`migrate`, `doctor`, `update-project`, `navigate`, `handoff-read`, `handoff-purge`, `schema`, `write`, `write-many`, `index`, `list`, `ingest`) are served exclusively via the `brain79 <command>` CLI.

## File descriptor teardown (`mcp.close()`)

During shutdown or client disconnection, `FastMCP` closes associated file descriptors cleanly to prevent socket or lock leaks.

---

[← Back to Index](../INDEX.md)
