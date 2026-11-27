# brain-79

[![Version](https://img.shields.io/badge/version-0.18.0-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-brightgreen.svg)](https://www.python.org/)

Persistent memory protocol and mechanical guardrails for AI coding assistants.

`brain-79` implements Andrej Karpathy's **LLM-wiki** pattern. Instead of unmaintained `CLAUDE.md` files or vector databases, the assistant maintains a structured Markdown wiki inside `.brain-79/`. Mechanical validators, SHA-256 Merkle drift tracking, and atomic tools prevent documentation rot.

**Language-agnostic by design**: Merkle SHA-256 drift tracking, `orient()`, lifecycle hooks, and CI governance gates work in any repository regardless of programming language. Built-in **AST Guard C** verifies Python signatures out of the box, supports **10 additional language parsers** (TypeScript, TSX, JavaScript/JSX, Go, Rust, Java, C#, PHP, Ruby, and Bash) via the optional `brain79[polyglot]` extra, and exposes a pluggable `LanguageInspector` registry for custom languages.

---

## The problem: raw LLM wikis degrade

Language models generate clear documentation in single sessions. Over repeated sessions, unmanaged wikis degrade across four failure modes:

| Failure mode | Without brain-79 (raw wiki / CLAUDE.md) | With brain-79 (mechanical protocol) |
|:---|:---|:---|
| **Startup context amnesia** | Agent dumps thousands of lines into prompt context or misses past project rules. | `brain79 orient` bounds startup context to 64 KB, inlining the index, active handoff, and governing docs. |
| **Silent code-to-doc drift** | Source code changes; documentation remains stale until human review catches it. | Merkle leaf manifest (`.drift_manifest.json`) tracks source SHA-256 digests and propagates drift up the DAG. |
| **Wiki sprawl & duplication** | Agents generate redundant files with overlapping scopes. | Anti-sprawl validation performs Jaccard overlap and target subsumption checks at write time. |
| **Obsolete session notes** | Outdated handoffs describe completed or abandoned tasks. | Cryptographic git provenance stamps handoffs as `fresh`, `stale`, or `foreign_branch`. |

---

## What a session looks like

You install brain-79 once per project. After that, you talk to your AI assistant as you always do. The assistant uses brain-79 on its own.

Say you ask your assistant:

> Add a refund endpoint to the payments module.

Here is what happens:

1. **The assistant reads the project first.** Before it touches any code, it asks brain-79 for context. brain-79 returns the project index, the notes from the last session, and the docs that cover `src/payments.py`. The assistant starts with the right background, not a blank page.

2. **The assistant writes the code.** You work with it as usual.

3. **The assistant updates the docs.** When it finishes, it sends the documentation changes to brain-79. brain-79 checks them before saving.

4. **brain-79 blocks lazy documentation.** Suppose the assistant changed the signature of `refund_transaction` but did not update `features/payments.md`. brain-79 rejects the commit:

   ```
   Commit Validation Failed:
   Cannot verify article 'features/payments.md' without documentation
   update: public function 'refund_transaction' signature changed.
   ```

   The assistant has to fix the docs before it can finish.

5. **You choose when to save session notes.** If you say "wrap up", the assistant writes a short handoff. The next session starts from it. brain-79 marks the handoff as `stale` if the code changed since then, so the assistant knows not to trust it blindly.

You never call these tools yourself. They run through the Model Context Protocol (MCP), and `brain79 init` sets that up for Claude Desktop, Cursor, Antigravity, and Pi. For the full details, see the [User and protocol guide](USER_GUIDE.md).

## Where you can use it

**In a code repository.** Architecture notes, feature docs, and decisions stay close to the code. Each time the assistant changes public code, brain-79 requires the matching docs to change too.

**In a folder without code.** Run `brain79 init --profile general` to keep research notes, comparisons, and decisions in an organized wiki. It works in folders that are not git repositories.

---

## Quick start

### 1. Install tool globally

Install `brain79` into your user environment with `uv` (requires Python 3.11+):

```bash
uv tool install git+https://github.com/xilax79/brain-79.git
```

To enable deep polyglot AST Guard C verification across TypeScript, TSX, JavaScript/JSX, Go, Rust, Java, C#, PHP, Ruby, and Bash, install the optional `polyglot` extra:

```bash
uv tool install "brain79[polyglot] @ git+https://github.com/xilax79/brain-79.git"
```

Verify the installation:

```bash
brain79 --version
```

### 2. Initialize your repository

Run `init` in your project root:

```bash
cd /path/to/project
brain79 init
```

This command creates:
- `.brain-79/`: repository wiki with `INDEX.md`, `SCHEMA.md`, and `.drift_manifest.json` (articles default to English `[← Back to Index](../INDEX.md)` footers; customize via `backlink_label:` in `SCHEMA.md`).
- Native instruction harnesses with non-destructive `<!-- brain79:start vX.Y.Z -->` / `<!-- brain79:end -->` blocks: `AGENTS.md`, `CLAUDE.md` (Claude Code), `.cursor/rules/brain79.mdc` (Cursor MDC), and `.github/copilot-instructions.md` (GitHub Copilot).
- Tier 1 MCP harnesses: `.mcp.json`, `.agents/plugins/brain79/` (Antigravity plugin with skill), and `.cursor/mcp.json`.

To install only a subset of harnesses, pass `--harnesses` (for example, `brain79 init --harnesses agents,claude`). For non-code research repositories, pass `--profile general`.

### Focused MCP surface and CLI superset

The FastMCP server exposes a single focused surface of **9 hot-path tools** (`brain79_orient`, `brain79_session_commit`, `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_context`, `brain79_search`, `brain79_lint`, `brain79_bootstrap`) to minimize per-turn LLM schema token overhead.

Administrative, CI, telemetry, and operational commands (`ci-check`, `stats`, `migrate`, `doctor`, `update-project`, `navigate`, `handoff-read`, `handoff-purge`, `schema`, `write`, `write-many`, `index`, `list`, `ingest`, `init`, `update`) are exposed through the **26-command `brain79 <command>` CLI**.

### 3. Verify repository health and context budgets

Run operational diagnostics and read-only token budget telemetry:

```bash
brain79 doctor
brain79 stats
```

To repair missing configurations or template drift safely:

```bash
brain79 doctor --fix
```

### Tool updates vs project template updates

- **`brain79 update`**: updates the installed CLI binary from upstream Git.
- **`brain79 update-project`**: synchronizes `AGENTS.md`, `SCHEMA.md`, `.brain-79/.gitignore`, `.brain-79/.gitattributes`, the local `INDEX.md` Git merge driver, and MCP/instruction harnesses inside an existing repository.

### Team-safe Git collaboration and brownfield onboarding

- **Merge-conflict-free derived state**: `.navigation_registry.json`, `.drift_manifest.json`, and `.bootstrap_state.json` are git-ignored via `.brain-79/.gitignore` and reconstructed deterministically on demand (`brain79 navigate --regenerate --rebuild`).
- **Deterministic `INDEX.md` Git merge driver**: `brain79 init` and `brain79 update-project` configure `.brain-79/.gitattributes` and local `.git/config` with `brain79 navigate --merge-driver %O %A %B` so concurrent PRs touching `INDEX.md` merge cleanly without manual conflict resolution.
- **Brownfield auto-mapping**: `brain79 bootstrap --auto-map --max-modules N` (and MCP `brain79_bootstrap(auto_map=True)`) detects package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`), ranks modules by Git churn, and emits pairwise zero-overlap `applies_to` governance proposals.
- **Configurable enforcement tiers and dual-tier CI gate**: set `enforcement: strict | balanced | advisory` in `.brain-79/SCHEMA.md` (or pass `brain79 init --enforcement <tier>`) for low-friction local iteration, and run `brain79 ci-check` (which defaults to `strict` and surfaces PR diff impact + governing ADRs) or the composite GitHub Action (`action.yml`) in pull request workflows.
- **Opt-in passive lifecycle hooks**: pass `--install-lifecycle-hooks` to `brain79 init` or `brain79 update-project` (or `--harnesses hooks`) to configure native `SessionStart` / `Stop` hooks for Claude Code (`.claude/settings.json`), Antigravity (`.agents/plugins/brain79/hooks.json`), and Cursor (`.cursor/hooks.json`) backed by `brain79 ci-check --lifecycle-hook`.

---

## Limitations and trade-offs

`brain-79` is a pre-GA (`0.y.z`) developer tool built around explicit trade-offs:

- **Python 3.11+ and `uv` runtime**: requires Python 3.11+ (typically installed via `uv tool install`) rather than a single standalone native binary.
- **Language-agnostic core with optional `brain79[polyglot]` AST Guard C**: Merkle drift tracking, `orient()`, hooks, and CI gates work in any language repository. Public signature verification (AST Guard C) includes built-in Python support, optional Tree-sitter parsers for 10 additional languages (`TypeScript`, `TSX`, `JavaScript/JSX`, `Go`, `Rust`, `Java`, `C#`, `PHP`, `Ruby`, `Bash`) via `brain79[polyglot]`, and a pluggable `LanguageInspector` registry for community extensions; unconfigured extensions degrade gracefully to file-level Merkle drift.
- **Agent protocol adherence**: unless opt-in lifecycle hooks (`--install-lifecycle-hooks`) and the CI PR gate (`brain79 ci-check` / `action.yml`) are enabled, runtime compliance relies on the AI client following instruction files (`AGENTS.md`, `CLAUDE.md`, `.cursor/rules/brain79.mdc`, `.github/copilot-instructions.md`) and calling MCP tools.
- **Local Git merge driver setup per clone**: while `.brain-79/.gitattributes` and `.brain-79/.gitignore` are committed to Git, each developer clone must run `brain79 update-project` (or `brain79 doctor --fix`) once to register the local `merge.brain79-index.driver` in `.git/config`.
- **Deterministic retrieval vs. semantic embeddings**: `brain79_orient` and `brain79_context` use deterministic path matching, weighted TF-IDF, and 1-hop ADR graph traversal with zero external model calls. This guarantees speed, offline reproducibility, and zero API cost, at the trade-off of not performing dense semantic vector search.

---

## Documentation and technical reference

- [User and protocol guide](USER_GUIDE.md): how MCP harnesses connect to your assistant, concrete code-verified workflows, and command reference.
- [Architecture and technical specifications](ARCHITECTURE.md): system layers, 28-file module map, and runtime invariants.
- [Changelog](CHANGELOG.md): release history and migration notes.

---

## Contributing

```bash
git clone https://github.com/xilax79/brain-79.git
cd brain-79

uv run pytest
uv run mypy src tests
uv run brain79 lint --strict
```

---

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
