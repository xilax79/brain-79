# brain-79

Per-project AI memory system based on Karpathy's LLM-Wiki method.

## What it does

brain-79 gives your AI coding assistants persistent, curated memory about your codebase across sessions:

- **Long-Term Memory (Wiki):** Curated documentation about architecture, domain rules, and features stored in `.brain-79/`.
- **Short-Term Memory (Handoffs):** Tactical transition notes stored in `.brain-79/handoffs/` to pass work smoothly between sessions.

Instead of re-explaining project context every time you chat with an AI agent, brain-79 allows the agent to orient itself immediately.

---

## Quick Start

### Step 1 — Install brain79 as a global tool

```bash
uv tool install --editable /path/to/brain-79 --force
```

This installs `brain79` to `~/.local/bin/brain79` and syncs all dependencies. Source code edits are reflected immediately, and using `--force` ensures newly added package dependencies are installed into the tool environment.

### Step 2 — Initialize your project

```bash
cd /path/to/your-project
brain79 init
```

This creates the `.brain-79/` directory structure, deploys `AGENTS.md` (universal cold-start protocol), and configures `.mcp.json` / `.agents/mcp_config.json` automatically.

### Step 3 — Multi-CLI Configuration

#### Using with `agy`
For global access across all projects, add `brain79` to `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "brain79": {
      "command": "/path/to/.local/bin/brain79",
      "args": ["--project-root", "."]
    }
  }
}
```

#### Using with `pi` (Minimax / Orca CLI)
1. Install the MCP adapter for `pi` (one-time setup):
   ```bash
   pi install npm:pi-mcp-adapter
   ```
2. Running `brain79 init` automatically creates or merges `.mcp.json` in your project root with the server definition:
   ```json
   {
     "mcpServers": {
       "brain79": {
         "command": "brain79",
         "args": ["--project-root", "."]
       }
     }
   }
   ```
   *Note on `pi` precedence:* `pi` resolves MCP definitions in order: `~/.config/mcp/mcp.json` → `~/.agents/mcp.json` → `~/.agents/mcp/mcp.json` → `~/.pi/agent/mcp.json` → `.mcp.json` → `.pi/mcp.json`.

---

## How to Use brain-79

### 🧠 Using the Wiki (Long-Term Memory)

The Wiki stores curated, enduring knowledge about your project.

- **Starting a task:** Tell your agent:
  > "Review the wiki to orient yourself before starting."
  *(The agent calls `brain79_index()` and reads only the necessary wiki articles).*

- **Updating project documentation:** Tell your agent:
  > "Update the wiki with our new architectural decision."
  *(The agent saves raw session notes via `brain79_ingest` and updates relevant wiki articles).*

### 🤝 Using Handoffs (Short-Term Memory)

Handoffs bridge consecutive work sessions for specific tasks.

- **Ending a session:** Tell your agent:
  > "Write a handoff for the next session."
  *(The agent creates an immutable handoff note with completed work, pending tasks, and instructions for the next agent).*

- **Resuming work:** Tell your agent:
  > "Read the latest handoff and resume work."
  *(The agent calls `brain79_handoff_read("latest")` and picks up right where you left off).*

---

## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `brain79_index()` | Returns `INDEX.md` — project entry point (read first) |
| `brain79_read(path)` | Reads a wiki article by relative path |
| `brain79_write(path, content)` | Writes or updates a wiki article |
| `brain79_list(section?)` | Lists wiki articles, optionally filtered by section |
| `brain79_search(query)` | Keyword search across all wiki articles |
| `brain79_ingest(summary, instructions?)` | Ingests session summary into raw sources and returns curation guide |
| `brain79_handoff_write(...)` | Writes a structured, immutable session handoff |
| `brain79_handoff_read(ref?)` | Reads a handoff (`"latest"`, `"none"`, timestamp prefix, or filename) |
| `brain79_lint()` | Deterministic health check scan diagnosing broken links, namespace violations, structural errors, and orphans |


---

## Wiki Structure

```
.brain-79/
├── SCHEMA.md        ← Curation rules for the LLM (edit to customize)
├── INDEX.md         ← Project entry point (always read first)
├── handoffs/        ← Tactical session handoffs (handoff-<timestamp>.md)
├── product/         ← Vision, domain rules, user requirements
├── architecture/    ← Stack, design patterns, ADRs
├── features/        ← Feature documentation
├── decisions/       ← Decision logs
└── _raw/
    ├── sessions/    ← Raw session summaries (immutable)
    └── commits/     ← Commit metadata
```

---

## Technical Architecture

For detailed technical specifications, validation contracts, and memory hierarchy rules, see [ARCHITECTURE.md](file:///Users/xilax/Documents/GitHub/brain-79/ARCHITECTURE.md).

---

## License

This project is licensed under the MIT License.
