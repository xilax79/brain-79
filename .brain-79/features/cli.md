---
type: feature
summary: 25 deterministic CLI subcommands for managing wiki knowledge, CI governance, lifecycle hooks, linters, and handoffs
status: shipped
version: 0.15.0
last_updated: 2026-11-24
applies_to:
  - src/brain79/cli/dispatch.py
  - src/brain79/cli/io.py
  - src/brain79/cli/__init__.py
related:
  - architecture/symmetry.md
  - architecture/dispatcher.md
  - features/lifecycle-hooks-and-ci-gate.md
applies_to_digest: "sha256:cecd6a5b3f9fb6ce"
applies_to_count: 3
---

# Feature — Standalone CLI interface

## Overview

The Standalone CLI interface provides 25 deterministic command-line subcommands for managing the repository wiki, executing organizational linter and CI PR gate checks, running passive lifecycle hooks, performing handoffs, diagnosing environment health, upgrading project configurations, and initializing memory protocols without requiring an active MCP host connection.

It is designed for direct developer interaction in the terminal, shell scripts, CI/CD pipelines, and git/agent hooks.

## Subcommands and options

| Command | Description | Inputs / Flags | Exit Codes |
|---|---|---|---|
| `brain79 init` | Initialize `.brain-79/` directory structure and protocol manifests | `--project-root`, `--harnesses`, `--install-lifecycle-hooks`, `--install-git-hooks` / `--no-git-hooks`, `--upgrade`, `--include-desktop` | `0`, `1`, `2` |
| `brain79 update-project` | Non-destructively upgrade templates, schemas, and harnesses | `[--project-root]`, `[--install-lifecycle-hooks]`, `[--dry-run]`, `[--commit-transition]`, `[--include-desktop]` | `0`, `1` |
| `brain79 doctor` | Run 9-point operational diagnostic checks and auto-repair | `[--project-root]`, `[--fix]`, `[--force]`, `[--include-desktop]`, `[--format text\|json]` | `0`, `1`, `2` |
| `brain79 update` | Update the installed brain79 CLI tool from upstream Git or local development checkout | `[--branch]` | `0`, `1`, `3`, `4` |
| `brain79 ci-check` | Run read-only CI governance PR gate or passive lifecycle hook handler | `[--base <ref>]`, `[--head <ref>]`, `[--enforcement <tier>]`, `[--fail-on-warnings]`, `[--format markdown\|text\|json]`, `[--summary-file <path>]`, `[--write-step-summary]`, `[--lifecycle-hook <session-start\|stop>]`, `[--client <auto\|claude\|agy\|cursor>]` | `0`, `1`, `2`, `3` |
| `brain79 orient` | Collapsed 1-call cold start orientation with inlined governing context | `[--task <t>]`, `[--paths ...]` | `0`, `3` |
| `brain79 index` | Print `INDEX.md` entry point | None | `0`, `3` |
| `brain79 schema` | Print schema rules and frontmatter templates | `[--type <type>]` | `0` |
| `brain79 read` | Read a wiki article by relative path | `<path>`, `[--sections ...]` | `0`, `3` |
| `brain79 read-batch` | Batch read multiple articles from JSON payload file | `--file` | `0`, `1`, `3` |
| `brain79 write` | Write or update a wiki article | `<path>`, `--content-file`, `--content-stdin`, `--force-validation-skip` | `0`, `1`, `3` |
| `brain79 edit` | Partial in-place text replacement in an article | `<path>`, `--old-text`, `--new-text`, `--edits-file` | `0`, `1`, `3` |
| `brain79 write-many` | Batch validate and atomically write multiple articles | `--file`, `--stdin` | `0`, `1`, `3` |
| `brain79 session-commit` | 1-call atomic session finalization with Hard Session Ripple Gate | `--file`, `--stdin` | `0`, `1`, `3` |
| `brain79 list` | List wiki articles | `[--section <name>]` | `0` |
| `brain79 search` | Keyword search across wiki articles | `<query>` | `0` |
| `brain79 ingest` | Save raw session summary | `--summary-file`, `--summary-stdin` | `0`, `3` |
| `brain79 handoff-write` | Write structured session handoff | `--session-type`, `--summary-file`, `--boot-instruction-file` | `0`, `1`, `3` |
| `brain79 handoff-read` | Read latest or referenced handoff | `[<ref>]` | `0`, `3` |
| `brain79 handoff-purge` | Purge short-term handoffs | `[--apply]` | `0` |
| `brain79 navigate` | Query or sync navigation registry | `[--regenerate]`, `[--rebuild]` | `0` |
| `brain79 context` | Retrieve relevant articles via 3-signal ranking | `<task>`, `[--paths ...]` | `0` |
| `brain79 migrate` | Apply or preview V3 frontmatter migration | `[--apply]`, `[--suggest-relocations]` | `0`, `1` |
| `brain79 lint` | Run organizational linter | `[--strict]`, `[--fail-on-warnings]`, `[--suggest-extract]`, `[--format json]` | `0`, `1` |
| `brain79 bootstrap` | Generate project scan manifest | `[--scope <scope>]`, `[--auto-map]`, `[--max-modules <n>]`, `[--force]` | `0` |

## Usage examples

```bash
# Run read-only CI governance PR gate against main
brain79 ci-check --base main --write-step-summary

# Run strict linter in CI mode
brain79 lint --strict --format json

# Install opt-in lifecycle hooks on an existing repository
brain79 update-project --install-lifecycle-hooks
```

## Known edge cases

- Global flags (`--project-root`, `--debug`) can be placed before or after the subcommand.
- Terminal output for `read` and `index` outputs pure content without decorative headers to facilitate shell piping.

---

[← Back to Index](../INDEX.md)
