# brain-79: deterministic AI memory engine

> **Persistent, curated memory for AI coding assistants. Zero hallucination, zero context rot, and sub-second agent orientation.**

[![Version](https://img.shields.io/badge/version-2.0.2-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-463%20passed-success.svg)](tests/)

---

## The problem: AI memory rot

When AI agents work on software or complex knowledge bases across multiple sessions, two things inevitably happen:

1. **Context amnesia:** every session starts from zero. The agent must re-read dozens of files, burning your token budget just to understand what was done five minutes ago.
2. **Organic wiki decay:** when agents are asked to write documentation, they invent contradictory conventions, leave broken links, duplicate decisions, and dilute the knowledge base over time.

RAG (retrieval-augmented generation) and vector search help find fragments of text, but **they cannot enforce consistency, structure, or logical order**.

---

## The solution: brain-79

`brain-79` provides a **deterministic memory protocol** for AI assistants. It combines the speed of local Markdown files with the strict discipline of mechanical linters and atomic tools.

```
                  ┌────────────────────────────────────────┐
                  │            AI coding agent             │
                  │   (Pi, Cursor, Claude, Devin, etc.)    │
                  └───────────────────┬────────────────────┘
                                      │ JSON-RPC (FastMCP) or CLI
                                      ▼
                  ┌────────────────────────────────────────┐
                  │                brain-79                │
                  │   deterministic AI memory protocol     │
                  └─────────┬────────────────────┬─────────┘
                            │                    │
              Reads & writes│                    │ Mechanical enforcement
                            ▼                    ▼
       ┌───────────────────────────────┐  ┌───────────────────────────────┐
       │       Long-term memory        │  │       Short-term memory       │
       │    (.brain-79/ - the wiki)    │  │     (.brain-79/handoffs/)     │
       │  • Product vision & specs     │  │  • Tactical state snapshot    │
       │  • Architecture & ADRs        │  │  • Completed vs pending tasks │
       │  • Fast, curated navigation   │  │  • Immutable session logs     │
       └───────────────────────────────┘  └───────────────────────────────┘
```

- **Instant cold starts:** an agent reads `INDEX.md` and orients itself in a single turn.
- **Mechanical quality enforcement:** broken links, missing frontmatter, and orphan documents are caught at write time, not discovered later.
- **Deterministic handoffs:** structured transition notes guarantee context continuity from one session to the next.
- **Zero token waste:** fine-grained article edits, batch operations, and cached navigation mean the agent sends and receives only the tokens it actually needs.

---

## Quick start in 60 seconds

### Prerequisites and cross-platform installation

`brain-79` is tested natively across **macOS**, **Linux** (Debian/Ubuntu/Fedora/Arch), and **Windows** (x64/ARM64).

- **Python 3.10+**: runtime environment.
- **[`uv`](https://docs.astral.sh/uv/)**: fast Python package and tool manager.
- **Git (v2.25+)**: recommended. Required for software codebases (`--profile software`) to enable automated code drift detection (`documentation_drift_suspected`) and working-tree code freshness hashing (`code_digest`). In non-git directories and general knowledge workspaces (`--profile general`), `brain-79` operates 100% autonomously without git.

#### Step 1: install uv
- **macOS / Linux:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

#### Step 2: install brain-79 globally
Clone the repository and install `brain79` into your global tool environment:
```bash
git clone https://github.com/xilax79/brain-79.git
cd brain-79

# Universal cross-platform tool installation:
uv tool install --editable .
```
Verify the installation:
```bash
brain79 --version
```

### Initialize in any project
Go to your project repository and initialize the memory protocol:
```bash
cd /path/to/your-project

# For software engineering projects (default):
brain79 init

# Or for general knowledge, research, or writing projects:
brain79 init --profile general
```
This automatically sets up:
- `.brain-79/`: your project's curated knowledge base (articles, decisions, and handoffs).
- `AGENTS.md`: instructions that teach your AI assistant how to orient itself automatically.
- `.mcp.json`: ready-to-use configuration for Claude Desktop, Cursor, Pi, and other tools.
- `.git/hooks/pre-commit`: an automatic check that prevents commits with broken links.

---

## How it works in practice

At its core, `brain-79` gives your AI assistant a permanent, curated memory. Instead of treating each conversation as an isolated chat, your assistant works against a living knowledge base stored directly in your repository.

---

### Part 1: the long-term memory (the living knowledge base)

Whenever your assistant works on a task, it navigates a structured knowledge base (`.brain-79/`) that contains the permanent truth of your project: specifications, architectural decisions (ADRs), domain models, and product requirements.

#### Use case A: software engineering (`--profile software`)
1. **You ask for a feature:** "integrate the Stripe webhook handler."
2. **The assistant consults the knowledge base:** it immediately reads your architecture rules and existing payment decisions. It already knows your error-handling standards, authentication patterns, and retry expectations without you re-explaining them.
3. **The assistant builds and records decisions:** if it makes an architectural choice (such as adopting idempotency keys for webhook events), it documents an Architecture Decision Record (ADR) in the wiki.
4. **The memory stays clean forever:** the mechanical engine verifies that links are valid and structure is compliant. Documentation never rots or drifts out of sync with your code.

#### Use case B: research and complex knowledge projects (`--profile general`)
1. **You ask for multi-session research:** "analyze competitor pricing models and synthesize recommendations."
2. **The assistant queries existing knowledge:** it checks topic articles and background context gathered in previous turns, building upon verified facts rather than starting from zero.
3. **The assistant expands the domain graph:** as new benchmarks or market data are uncovered, it writes structured topic notes and records strategic choices in the knowledge base.
4. **Permanent asset:** months later, any assistant or team member querying the project can instantly locate why a particular strategy was chosen and what data supported it.

---

### Part 2: tactical session bridges (optional handoffs)

While the wiki stores your project's permanent long-term truth, development often pauses mid-task. For these situations, `brain-79` provides an optional, tactical bridge between working turns:

When you want to stop working for the day or switch context, you can simply ask:
> "Wrap up this session and save a handoff."

The assistant creates a lightweight tactical snapshot containing:
- a curated summary of work completed in this specific turn,
- remaining tasks and open technical questions,
- targeted boot instructions for the next session (if applicable).

In the next session, any assistant or teammate picks up immediately where work paused. Zero context amnesia.

---

### Command-line interface (terminal & CI)

You can inspect, search, and audit your project memory directly from your terminal or continuous integration (CI) pipelines:

```bash
# See what knowledge the assistant retrieves for a specific task
brain79 orient --task "integrate Stripe webhook" --paths "src/payments/webhook.py"

# Verify knowledge base health in CI pipelines or pre-commit checks
brain79 lint --strict

# Search across all project documentation instantly
brain79 search "idempotency keys"

# Review the latest tactical handoff note (if one was saved)
brain79 handoff-read latest

# Clean up older session handoffs
brain79 handoff-purge --dry-run
```

---

## Core principles

| Principle | What it means | Why it matters |
|:---|:---|:---|
| **Human and Git first** | plain markdown files in your repository | no proprietary cloud databases, no lock-in. Everything is reviewed in standard Git PRs |
| **Strict 1:1 symmetry** | every CLI command has an exact MCP equivalent | you and the AI use the exact same mental model and capabilities |
| **Mechanical validation** | broken links and schema errors are rejected immediately | prevents documentation from turning into a graveyard of out-of-date notes |
| **Atomic operations** | safe multi-process writes with automated rollback | multiple agents or scripts cannot corrupt files even under unexpected crashes |

---

## Documentation and deep dive

- 📘 [**Architecture and invariants**](ARCHITECTURE.md): detailed system layers, memory hierarchy, and design specifications.
- 🎯 [**Product vision and design**](.brain-79/product/overview.md): why deterministic memory beats ad-hoc documentation.
- 🗺️ [**Industrial scale roadmap**](.brain-79/architecture/roadmap-industrial-scale.md): next steps: multi-domain support, SQLite WAL, and local semantic search.
- 🔄 [**Changelog**](CHANGELOG.md): history of versions and release notes.

---

## Contributing and development

```bash
# Clone the repository
git clone https://github.com/xilax79/brain-79.git
cd brain-79

# Run test suite (460+ tests)
uv run pytest

# Run linting and type verification
uv run ruff check .
uv run mypy src
```

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
