# User and protocol guide

How-to workflows, MCP communication protocol, and operational reference for `brain-79`.

---

## 1. How assistants connect to brain-79

`brain-79` connects AI coding assistants to your repository through the Model Context Protocol (MCP) and an instruction contract declared in `AGENTS.md`.

```
+-----------------------------------------------------------------------------------+
| Assistant harness (Cursor, Claude Desktop, Antigravity, Pi)                       |
+-----------------------------------------------------------------------------------+
       |                                              |
       | 1. Reads instructions on boot                | 2. Invokes JSON-RPC tools
       v                                              v
+-----------------------------+               +-------------------------------------+
| AGENTS.md (Protocol block)  |               | brain-79 FastMCP server (server.py) |
| - Cold start: orient()      |               | - 22 registered tools               |
| - Wrap up: session_commit() |               | - Bounded context ranking           |
| - On-demand handoff policy  |               | - Mechanical write validation       |
+-----------------------------+               +-------------------------------------+
                                                      |
                                                      v
                                              +-------------------------------------+
                                              | .brain-79/ repository wiki          |
                                              | - INDEX.md pure routing table       |
                                              | - Merkle drift manifest             |
                                              | - Governed Markdown articles        |
                                              +-------------------------------------+
```

### Connection mechanics

1. **Harness registration**: running `brain79 init` in your project root creates standard, machine-independent configurations:
   - `.mcp.json`: standard project-level MCP definition for Claude Desktop and generic clients.
   - `.agents/plugins/brain79/`: native workspace plugin with on-demand skill documentation for Antigravity (`agy`).
   - `.cursor/mcp.json`: workspace configuration for Cursor.
2. **Instruction anchoring (`AGENTS.md`)**: `brain79 init` inserts a version-delimited comment block (`<!-- brain79:start v0.9.2 -->` ... `<!-- brain79:end -->`). The block instructs assistants to execute a two-call workflow:
   - Call `brain79_orient` once at session start before reading or editing code.
   - Call `brain79_session_commit` atomically at the end of the session to commit documentation updates.
3. **Transport**: the assistant communicates with `brain-79` via standard input/output (`stdio`) JSON-RPC messages managed by `FastMCP`.

---

## 2. Concrete protocol scenarios

### Scenario 1 — Cold-start orientation

When starting any task, the assistant sends a single `brain79_orient` call passing the user prompt and any files mentioned:

```json
{
  "task": "add refund endpoint",
  "paths": ["src/payments.py"]
}
```

The engine inspects the workspace, resolves active handoffs, calculates code-to-doc drift, and ranks relevant articles using three signals (direct code binding, weighted BM25, and 1-hop ADR expansion). It returns a single structured markdown response:

```markdown
# Brain-79 — Session Cold Start Orientation

## 🗺️ Project Index (Routing Table)
- [Feature — Payment processing](features/payments.md)
- [Architecture — System current state](architecture/current-state.md)
- [ADR-001 — Idempotency keys](decisions/adr-001-idempotency.md)

## 📐 Active Schema Summary
Profile: software. Managed types: architecture, decisions, features, handoffs, product.

## ⏱️ Active handoff state: fresh (HEAD = 4b1c8f)
Completed: implemented webhook listener. Next steps: expose refund endpoint.

## 📖 Governing Knowledge Articles
### === Article: features/payments.md ===
*Relevance Score: 12.0 | Match Signals: direct code binding to src/payments.py*
... [inlined content] ...

### === Article: decisions/adr-001-idempotency.md ===
*Relevance Score: 8.5 | Match Signals: 1-hop ADR expansion from features/payments.md*
... [inlined content] ...
```

#### Bounded context ceiling and the Mandatory Reading Manifest

To prevent context window exhaustion, `orient` limits inlined articles to 64 KB (`MAX_ORIENT_INLINE_CHARS = 64_000`). If governing articles exceed this ceiling, the engine stops inlining and appends a structured reading manifest directing the assistant to batch-read the remaining files using `requests=[...]`:

```markdown
---

## 🚨 Mandatory Reading Manifest (Must Read Before Editing)

The governing context exceeds the 64,000-character inline budget. The following governing articles must be read using `brain79_read_batch(requests=[...])` before modifying code or documentation:

- **`architecture/current-state.md`**: high-level system overview and runtime invariants
  - **Governs (`applies_to`)**: `README.md`, `src/brain79/**/*.py`
  - **Key Sections**: Active subsystem topology, System invariants
```

---

### Scenario 2 — Stale documentation protection

`brain-79` enforces synchronization between code and documentation using AST signature verification and dependency ripple gates.

#### AST Guard C: signature mutation blocks rubber-stamping

If an assistant changes a public Python function or class signature in `src/payments.py` (such as adding a required parameter to `refund_transaction`), it cannot bypass documentation updates by adding the article to `verified_articles`. Pass 2c parses the code AST and rejects the transaction:

```json
{
  "verified_articles": [
    {
      "path": "features/payments.md",
      "reason": "Internal refactoring only; payment interface unchanged"
    }
  ]
}
```

Response:
```
Commit Validation Failed:
Cannot verify article 'features/payments.md' without documentation update: public function 'refund_transaction' signature changed.

Action: Update the article content in writes or edits to document the public API changes.
```

#### Pass 2d: Hard Session Ripple Gate blocks incomplete commits

When the assistant updates `features/payments.md`, the change affects upstream umbrella articles that govern the subsystem (such as `architecture/current-state.md`). If the assistant attempts to commit the leaf update while leaving the umbrella drifted, Pass 2d halts the transaction:

```json
{
  "writes": [
    {
      "path": "features/payments.md",
      "content": "---\ntype: feature\nsummary: payment processing engine\n..."
    }
  ]
}
```

Response:
```
Commit Validation Failed:
Holistic update required: your session changes impacted governing/umbrella article(s) ['architecture/current-state.md'], which remain drifted. Update their prose in 'edits' (or include eligible internal code refactors in 'verified_articles') within this same session_commit.

Action: Update drifted articles or pass internal refactors in verified_articles to ensure holistic consistency.
```

#### Atomic commit resolution

Once all drifted articles are updated or legitimately verified, `brain79_session_commit` commits all changes atomically under an inter-process file lock:

```json
{
  "writes": [
    {
      "path": "features/payments.md",
      "content": "..."
    },
    {
      "path": "architecture/current-state.md",
      "content": "..."
    }
  ]
}
```

Response:
```markdown
# Brain-79 — Session Commit Receipt

- **Status**: ✅ Transaction Committed Successfully
- **Written Articles (2)**: `features/payments.md`, `architecture/current-state.md`
- **Inline Health**: `ok`
```

#### Quality gate integration

Before merging a branch or opening a pull request, run the mechanical linter to verify full repository hygiene:

```bash
brain79 lint --strict
```

---

### Scenario 3 — Research and decisions without Git (`--profile general`)

For non-software workspaces or pure research turns, `brain-79` operates without git tracking or code targets.

#### Initializing a general workspace

```bash
brain79 init --profile general
```

This configures schemas for `topics/`, `decisions/`, and `context/`, omitting code-centric requirements like `applies_to`.

#### The Amnesia Test for knowledge triage

When closing a research session, the assistant applies the Amnesia Test:
*"If this session context were wiped right now, would valuable research findings, domain analysis, or decisions be lost?"*

- **Type A (ephemeral consultation)**: casual conversation or reading existing files without creating new domain knowledge. No wiki modifications are made (zero-modification rule).
- **Type B (research and analysis)**: domain investigations, technical comparisons, or benchmarks. The assistant persists findings in `topics/<slug>.md` or `decisions/<slug>.md`.
- **Type C (code and workspace changes)**: governed articles are updated to reflect workspace modifications.

#### Persisting research via MCP

```json
{
  "writes": [
    {
      "path": "topics/competitor-analysis.md",
      "content": "---\ntype: topic\nsummary: benchmark of competitor pricing and api models\nlast_updated: 2026-11-17\n---\n\n# Competitor analysis\n\n## Overview\nComparative analysis of leading memory architectures...\n\n---\n\n[← Volver al Índice](../INDEX.md)"
    }
  ]
}
```

---

### Scenario 4 — On-demand handoffs and freshness tracking

#### On-demand handoff policy

In interactive sessions with humans, handoffs are written **only when explicitly requested** (e.g., "save handoff", "wrap up session"). In headless sub-agent workflows, handoffs are written upon process termination. Assistants do not write handoffs after every turn.

#### Cryptographic provenance and authority decay

Every handoff written via `brain79_handoff_write` or `brain79_session_commit(handoff=...)` records cryptographic provenance in its frontmatter:

```yaml
---
type: handoff
created_at: 2026-11-17T14:30:00Z
git_branch: feat/payments
git_head: 4b1c8f39a0d2
wiki_digest: sha256:8f4b...
code_digest: sha256:3c2a...
---
```

When an incoming assistant runs `orient`, the engine calculates freshness against the current repository state:

- **`fresh`**: the current git commit and file digests match the handoff. Instructions are active.
- **`stale`**: subsequent commits or wiki edits changed the repository state. The handoff is demoted to historical context, alerting the assistant to verify actual code before executing past instructions.
- **`foreign_branch`**: the handoff originated on a different branch. The assistant is warned not to assume branch-specific progress.
- **`unverified`**: non-git workspace where git head tracking is unavailable.

#### Purging historical handoffs

Handoffs are ephemeral transition bridges. When closing a major milestone, purge historical handoff files:

```bash
brain79 handoff-purge
```

Or via MCP (`brain79_handoff_purge`):
```json
{}
```

---

## 3. Interface reference: MCP tools and CLI subcommands

`brain-79` maintains 1:1 symmetry between terminal subcommands and FastMCP tools.

| Category | FastMCP server tool | CLI subcommand | Purpose |
|:---|:---|:---|:---|
| **Session & workflow** | `brain79_orient` | `orient` | Cold-start orientation and budgeted context assembly. |
| | `brain79_session_commit` | `session-commit` | Atomic commit of writes, edits, and handoffs with ripple check. |
| | `brain79_context` | `context` | 3-Signal context search for specific tasks or paths. |
| | `brain79_index` | `index` | Quick read of `INDEX.md` routing table. |
| | `brain79_ingest` | `ingest` | Ingest external session notes into `_raw/sessions/`. |
| **Handoff continuity** | `brain79_handoff_write` | `handoff-write` | Write an immutable, provenance-stamped session handoff. |
| | `brain79_handoff_read` | `handoff-read` | Read the latest handoff with computed freshness state. |
| | `brain79_handoff_purge` | `handoff-purge` | Purge archived handoff files. |
| **Reading & writing** | `brain79_read` | `read` | Read a single wiki article by relative path. |
| | `brain79_read_batch` | `read-batch` | Read multiple wiki articles in one turn with section projection. |
| | `brain79_write` | `write` | Write or overwrite a single wiki article with schema validation. |
| | `brain79_write_many` | `write-many` | Atomically write multiple articles with schema validation. |
| | `brain79_edit` | `edit` | Apply targeted string replacements to a wiki article. |
| | `brain79_list` | `list` | List all tracked wiki articles with metadata. |
| | `brain79_search` | `search` | Full-text search across all managed wiki articles. |
| **Governance & health** | `brain79_lint` | `lint` | Run structural, organizational, and drift lint checks. |
| | `brain79_schema` | `schema` | Inspect active schema rules and required frontmatter keys. |
| | `brain79_navigate` | `navigate` | Regenerate navigation registry and `INDEX.md`. |
| | `brain79_migrate` | `migrate` | Add frontmatter and normalize legacy markdown files. |
| | `brain79_bootstrap` | `bootstrap` | Generate repository scan manifest and seed wiki. |
| | `brain79_doctor` | `doctor` | Run 7-point operational diagnostic suite (`--fix` in CLI). |
| | `brain79_update_project`| `update-project` | Upgrade `AGENTS.md`, `SCHEMA.md`, and MCP harnesses. |
| **Host CLI only** | *N/A* | `init` | Initialize `.brain-79/` wiki and configure MCP harnesses. |
| | *N/A* | `update` | Upgrade installed `brain79` binary from upstream Git. |

---

## 4. Technical specifications and storage internals

For technical details on the 28-file module architecture, Merkle leaf manifest computation, centralized lock isolation, and cross-platform concurrency invariants, see [Architecture and technical specifications](ARCHITECTURE.md).
