# brain-79

[![Version](https://img.shields.io/badge/version-0.11.0-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-brightgreen.svg)](https://www.python.org/)

Persistent memory protocol and mechanical guardrails for AI coding assistants.

`brain-79` implements Andrej Karpathy's **LLM-wiki** pattern. Instead of unmaintained `CLAUDE.md` files or vector databases, the assistant maintains a structured Markdown wiki inside `.brain-79/`. Mechanical validators, SHA-256 Merkle drift tracking, and atomic tools prevent documentation rot.

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
- `.brain-79/`: repository wiki with `INDEX.md`, `SCHEMA.md`, and `.drift_manifest.json`.
- `AGENTS.md`: versioned protocol block instructing AI models how to orient.
- Tier 1 MCP harnesses: `.mcp.json`, `.agents/plugins/brain79/` (Antigravity plugin with skill), and `.cursor/mcp.json`.

For non-code research repositories, pass `--profile general`.

### 3. Verify repository health

Run operational diagnostics:

```bash
brain79 doctor
```

To repair missing configurations or template drift safely:

```bash
brain79 doctor --fix
```

### Tool updates vs project template updates

- **`brain79 update`**: updates the installed CLI binary from upstream Git.
- **`brain79 update-project`**: synchronizes `AGENTS.md`, `SCHEMA.md`, and MCP harnesses inside an existing repository.

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
