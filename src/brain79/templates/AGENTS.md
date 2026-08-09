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
2. The `.brain-79/` directory contains the ultimate source of truth.

## Mid-Session and Handoffs (End of task)
- Before concluding a session, use `brain79_handoff_write` to store progress.
- To resume a task, use `brain79_handoff_read` immediately.

## Available tools
- `brain79_index` — orient yourself first
- `brain79_search(query)` — find articles
- `brain79_read(path)` / `brain79_write(path, content)` — read/edit articles
- `brain79_list(section?)` — browse the wiki
- `brain79_ingest(summary, instructions?)` — promote learnings
- `brain79_handoff_write(...)` / `brain79_handoff_read(ref?)` — session continuity
