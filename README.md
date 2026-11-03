# brain-79: Deterministic AI Memory Engine

> **Persistent, curated memory for AI coding assistants. Zero hallucination, zero context rot, and sub-second agent orientation.**

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-433%20passed-success.svg)](tests/)

---

## The Problem: AI Memory Rot

When AI agents work on software or complex knowledge bases across multiple sessions, two things inevitably happen:

1. **Context Amnesia:** Every session starts from zero. The agent must re-read dozens of files, burning your token budget just to understand what was done five minutes ago.
2. **Organic Wiki Decay:** When agents are asked to write documentation, they invent contradictory conventions, leave broken links, duplicate decisions, and dilute the knowledge base over time.

RAG (Retrieval-Augmented Generation) and vector search help find fragments of text, but **they cannot enforce consistency, structure, or logical order**.

---

## The Solution: brain-79

`brain-79` provides a **deterministic memory protocol** for AI assistants. It combines the speed of local Markdown files with the strict discipline of mechanical linters and atomic tools.

```
                  ┌────────────────────────────────────────┐
                  │            AI Coding Agent             │
                  │   (Pi, Cursor, Claude, Devin, etc.)    │
                  └───────────────────┬────────────────────┘
                                      │ JSON-RPC (FastMCP) or CLI
                                      ▼
                  ┌────────────────────────────────────────┐
                  │                brain-79                │
                  │  Deterministic AI Memory Protocol      │
                  └─────────┬────────────────────┬─────────┘
                            │                    │
              Reads & Writes│                    │ Mechanical Enforcement
                            ▼                    ▼
       ┌───────────────────────────────┐  ┌───────────────────────────────┐
       │       Long-Term Memory        │  │       Short-Term Memory       │
       │    (.brain-79/ - The Wiki)    │  │     (.brain-79/handoffs/)     │
       │  • Product vision & Specs     │  │  • Tactical state snapshot    │
       │  • Architecture & ADRs        │  │  • Completed vs Pending tasks │
       │  • Fast, curated navigation   │  │  • Immutable session logs     │
       └───────────────────────────────┘  └───────────────────────────────┘
```

- **Instant Cold Starts:** An agent reads `INDEX.md` and orients itself in a single turn.
- **Mechanical Quality Enforcement:** Broken links, missing frontmatter, and orphan documents are caught at write time, not discovered later.
- **Deterministic Handoffs:** Structured transition notes guarantee context continuity from one session to the next.
- **Zero Token Waste:** Fine-grained article edits, batch operations, and cached navigation mean the agent sends and receives only the tokens it actually needs.

---

## Quick Start in 60 Seconds

### Prerequisites
You need [`uv`](https://docs.astral.sh/uv/) installed (the modern, fast Python package manager):
```bash
curl -sSf https://astral.sh/uv/install.sh | sh
```

### 1. Install brain-79 Globally
Run the automated installer to set up an editable, high-speed CLI:
```bash
uv run scripts/install.py
```

### 2. Initialize in Any Project
Go to your project repository and initialize the memory protocol:
```bash
cd /path/to/your-project

# For software engineering projects (default):
brain79 init

# Or for general knowledge, research, or writing projects:
brain79 init --profile general
```
This automatically sets up:
- `.brain-79/` directory structure with seed templates matched to the chosen ontology.
- `AGENTS.md` (universal cold-start instructions for LLMs).
- `.mcp.json` / FastMCP server definitions for your editor and agent harness.

---

## How It Works in Practice

### For AI Agents (via MCP)
When integrated with tools like **Pi**, **Claude Code**, **Cursor**, or **Devin**, the agent uses dedicated MCP tools:

1. **Instant Orientation (1-Call Cold Start):** The agent calls `brain79_orient(task=..., paths=[...])` to ingest the routing table (`INDEX.md`), latest handoff state, and the full text of governing architecture articles and ADRs in a single round-trip.
2. **Focused & Projected Reading:** Calls `brain79_read("features/auth.md", sections=["Endpoints"])` or `brain79_read_batch(requests)`.
3. **Surgical Updates:** Modifies sections cleanly using `brain79_edit` or writes new specs using `brain79_write`.
4. **Atomic Session Wrap-Up:** Calls `brain79_session_commit(...)` to archive raw logs, apply article writes/edits, and generate the immutable handoff in a single all-or-nothing transaction.

### For Developers (via CLI)
Everything available to the agent is equally accessible to you in the terminal with 100% feature symmetry:

```bash
# Instant orientation for a task and files
brain79 orient --task "implement JWT rotation" --paths "src/auth/jwt.py"

# Check wiki health (broken links, schema violations, orphans)
brain79 lint --strict

# Search across documentation at instant speed
brain79 search "session recovery"

# Review the most recent handoff left by an agent
brain79 handoff-read latest

# Clean up older session handoffs
brain79 handoff-purge --dry-run
```

---

## Core Principles

| Principle | What it means | Why it matters |
|:---|:---|:---|
| **Human & Git First** | Plain Markdown files in your repository. | No proprietary cloud databases, no lock-in. Everything is reviewed in standard Git PRs. |
| **Strict 1:1 Symmetry** | Every CLI command has an exact MCP equivalent. | You and the AI use the exact same mental model and capabilities. |
| **Mechanical Validation** | Broken links and schema errors are rejected immediately. | Prevents documentation from turning into a graveyard of out-of-date notes. |
| **Atomic Operations** | Safe multi-process writes with automated rollback. | Multiple agents or scripts cannot corrupt files even under unexpected crashes. |

---

## Documentation & Deep Dive

- 📘 [**Architecture & Invariants**](ARCHITECTURE.md): Detailed system layers, memory hierarchy, and design specifications.
- 🎯 [**Product Vision & Design**](.brain-79/product/overview.md): Why deterministic memory beats ad-hoc documentation.
- 🗺️ [**Industrial Scale Roadmap**](.brain-79/architecture/roadmap-industrial-scale.md): Next steps: multi-domain support, SQLite WAL, and local semantic search.
- 🔄 [**Changelog**](CHANGELOG.md): History of versions and release notes.

---

## Contributing & Development

```bash
# Clone the repository
git clone https://github.com/xilax79/brain-79.git
cd brain-79

# Run test suite (330+ tests)
uv run pytest

# Run linting and type verification
uv run ruff check .
uv run mypy src
```

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
