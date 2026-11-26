---
type: architecture
summary: CLI argument parsing, closed-whitelist subcommand routing across 26 commands, and POSIX exit code mappings
stability: stable
last_updated: 2026-11-26
applies_to:
  - src/brain79/__main__.py
  - src/brain79/cli/dispatch.py
  - src/brain79/cli/io.py
related:
  - architecture/symmetry.md
  - features/cli.md
  - architecture/mcp-server.md
  - features/lifecycle-hooks-and-ci-gate.md
applies_to_digest: "sha256:b3e8c46f190f0c36"
applies_to_count: 3
---

# Architecture — CLI dispatcher

## General description

The CLI dispatcher system in `brain-79` is responsible for parsing global command-line flags and routing user invocations to deterministic CLI subcommands or launching the MCP server fallback.

## Components and entry points

1. **`src/brain79/__main__.py`**: main entry point registered in `pyproject.toml` as `brain79 = "brain79.__main__:main"`.
2. **`src/brain79/cli/dispatch.py`**: implementation of argument parsing, subcommand dispatching, ergonomic `read-batch --paths` / `--stdin` / `--file` parity, profile-aware `bootstrap --auto-map` / `--no-auto-map` handling, and POSIX exit code mappings.
3. **`src/brain79/cli/io.py`**: helper routines for standard input and file-based payload handling (`--content-file`, `--content-stdin`).

## Dual-position flag parsing (`parse_global_flags`)

Global flags can appear before or after subcommands without breaking parsing:
- `--project-root <PATH>` or `--project-root=<PATH>`: sets target project root explicitly.
- `--debug`: enables full traceback emission on unhandled errors.

## Whitelist routing and fallback execution

The dispatcher maintains a strict whitelist (`WHITELIST`) of 26 subcommands:
`init`, `update`, `update-project`, `doctor`, `ci-check`, `stats`, `index`, `read`, `read-batch`, `write`, `edit`, `write-many`, `schema`, `list`, `search`, `ingest`, `handoff-write`, `handoff-read`, `handoff-purge`, `navigate`, `migrate`, `lint`, `bootstrap`, `context`, `orient`, `session-commit`.

Routing order in `src/brain79/__main__.py` (immediately after `parse_global_flags()`):
1. **Removed `--mcp-profile` flag**: emits a `v0.14.0` migration error to `stderr` directing callers to the `brain79 <command>` CLI and exits with code `2`.
2. **Empty arguments** (e.g. `brain79` or `brain79 --project-root .`): launches `_cmd_serve()`, starting the FastMCP server on standard IO.
3. **Help flags/commands** (`-h`, `--help`, `help [subcmd]`): prints domain-agnostic root usage or delegates to `<subcmd> --help` and exits with `0`.
4. **Version flags** (`-v`, `--version`): prints `brain79 <version>` and exits with `0`.
5. **Whitelisted subcommands**: routes to `run_cli(cmd, sub_args, debug)`.
6. **Unknown commands or flags**: emits an actionable error to `stderr` and exits with code `2` (never falling through to the MCP stdio loop).

## Exit code mapping policy

Subcommand execution maps exceptions to deterministic POSIX exit codes:
- `0`: clean success (and all `ci-check --lifecycle-hook` fail-open invocations).
- `1`: validation or operational failure (e.g., linter issues in `--strict` mode or failed `ci-check` gate).
- `2`: invalid argument or missing required parameter (`FileNotFoundError`, as well as `ValueError`, `NotAGitRepoError`, and `GitError` in `ci-check`).
- `3`: file access error or concurrency timeout (`PermissionError`, `TimeoutError`, `OSError`, as well as `GitTimeoutError` in `ci-check`).
- `130`: process interrupted via `KeyboardInterrupt` / `SIGINT`.

---

[← Back to Index](../INDEX.md)
