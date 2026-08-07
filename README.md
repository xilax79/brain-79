# brain-79

Per-project AI memory system based on Karpathy's LLM-Wiki method.

## What it does

brain-79 gives any AI agent persistent, curated knowledge about your project. Instead of re-explaining context every session, the agent reads a structured wiki that lives inside your repo.

At the end of a session, you ask the agent to update the wiki. In future sessions, the agent reads the wiki first and is immediately up to speed.

## How it works

1. **Compile, don't retrieve.** Session knowledge is synthesized into structured markdown articles — not stored as raw logs.
2. **Per-project.** The wiki lives in `.brain-79/` inside your repo, versioned with git.
3. **Agent-navigated.** The agent reads `INDEX.md` first, then fetches only the articles it needs. No full-wiki loads.

## Installation

### Step 1 — Install brain79 as a global tool

```bash
uv tool install --editable /path/to/brain-79
```

This installs `brain79` to `~/.local/bin/brain79`. Run once; updates to the source repo are reflected immediately (editable install).

> Once published to PyPI, this will simplify to `uvx brain79` with no install step.

### Step 2 — Register the MCP server globally (agy)

Create `~/.gemini/config/mcp_config.json` (or add to it if it exists):

```json
{
  "mcpServers": {
    "brain79": {
      "command": "/absolute/path/to/.local/bin/brain79",
      "args": ["--project-root", "."]
    }
  }
}
```

Use an **absolute path** for `command` — `agy` spawns the process with a restricted PATH.
The `"."` resolves to the cwd where you opened the CLI session (i.e., the project root).

Restart `agy` after creating the file.

### Step 3 — Initialize a project

```bash
cd /path/to/your-project
brain79 init
```

This creates:
- `.brain-79/` with `SCHEMA.md` and `INDEX.md`
- `.agents/mcp_config.json` for per-project agy MCP registration (auto-generated)

Done. No manual editing required.

---


## Usage

### End-of-session wiki update

At the end of a development session, tell your agent:

> "Update the wiki. Focus only on the architecture changes — ignore the debugging discussion."

The agent will:
1. Save the raw session summary
2. Read `SCHEMA.md` and `INDEX.md`
3. Update the relevant wiki articles
4. Update `INDEX.md` to reflect the new state

### Start-of-session onboarding

The agent should call `brain79_index()` first, then fetch only the articles relevant to the upcoming task.

## MCP tools

| Tool | Description |
|------|-------------|
| `brain79_index()` | Returns `INDEX.md` — always read first |
| `brain79_read(path)` | Reads a wiki article |
| `brain79_write(path, content)` | Writes or updates an article |
| `brain79_list(section?)` | Lists articles, optionally filtered |
| `brain79_search(query)` | Keyword search across the wiki |
| `brain79_ingest(summary, instructions?)` | Saves session to `_raw/` and returns curation workflow |

## Wiki structure

```
.brain-79/
├── SCHEMA.md        ← curation rules for the LLM (edit this)
├── INDEX.md         ← project entry point (always read first)
├── product/         ← vision, domain, user personas
├── architecture/    ← stack, patterns, ADRs
├── features/        ← one article per feature
├── changelog/       ← chronological evolution
├── decisions/       ← why things were done (decision log)
└── _raw/
    ├── sessions/    ← raw session summaries (immutable)
    └── commits/     ← commit-linked metadata (optional)
```
