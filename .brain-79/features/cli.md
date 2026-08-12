---
type: feature
status: shipped
version: 1.0.0
last_updated: 2026-08-11
---

# Feature — Standalone CLI Interface

## Overview

The Standalone CLI interface provides 13 deterministic command-line subcommands for managing the repository wiki, executing organizational linter checks, performing handoffs, and initializing memory protocols without requiring an active MCP host connection.

It is designed for direct developer interaction in the terminal, shell scripts, CI/CD pipelines, and git hooks.

## Subcommands & Options

| Command | Description | Inputs / Flags | Exit Codes |
|---|---|---|---|
| `brain79 init` | Initialize `.brain-79/` directory structure and protocol manifests | `--project-root`, `--install-git-hooks` / `--no-git-hooks` | `0`, `1`, `2` |
| `brain79 update` | Update editable installation from upstream git repo | `--branch` | `0`, `1` |
| `brain79 index` | Print `INDEX.md` entry point | None | `0`, `3` |
| `brain79 read` | Read a wiki article by relative path | `<path>` | `0`, `3` |
| `brain79 write` | Write or update a wiki article | `<path>`, `--content-file`, `--content-stdin`, `--force-validation-skip` | `0`, `1`, `3` |
| `brain79 list` | List wiki articles | `[--section <name>]` | `0` |
| `brain79 search` | Keyword search across wiki articles | `<query>` | `0` |
| `brain79 ingest` | Save raw session summary | `--summary-file`, `--summary-stdin` | `0`, `3` |
| `brain79 handoff-write` | Write structured session handoff | `--session-type`, `--summary-file`, `--boot-instruction-file` | `0`, `1`, `3` |
| `brain79 handoff-read` | Read latest or referenced handoff | `[<ref>]` | `0`, `3` |
| `brain79 handoff-purge` | Purge short-term handoffs | `[--apply]` | `0` |
| `brain79 navigate` | Query or sync navigation registry | `[--regenerate]` | `0` |
| `brain79 migrate` | Apply or preview V3 frontmatter migration | `[--apply]`, `[--suggest-relocations]` | `0`, `1` |
| `brain79 lint` | Run organizational linter | `[--strict]`, `[--suggest-extract]`, `[--format json]` | `0`, `1` |
| `brain79 bootstrap` | Generate project scan manifest | `[--scope <scope>]`, `[--force]` | `0` |

## Usage Examples

```bash
# Read index
brain79 index

# Write an article from standard input
cat article.md | brain79 write architecture/overview.md --content-stdin

# Run strict linter in CI mode
brain79 lint --strict --format json
```

## Known Edge Cases

- Global flags (`--project-root`, `--debug`) can be placed before or after the subcommand.
- Terminal output for `read` and `index` outputs pure content without decorative headers to facilitate shell piping.
