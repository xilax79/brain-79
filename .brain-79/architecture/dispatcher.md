---
type: architecture
summary: CLI argument parsing, closed-whitelist subcommand routing across 27 commands, and POSIX exit code mappings
stability: stable
last_updated: 2026-11-27
applies_to:
  - src/brain79/__main__.py
  - src/brain79/cli/dispatch.py
  - src/brain79/cli/io.py
related:
  - architecture/symmetry.md
  - features/cli.md
  - architecture/mcp-server.md
  - features/lifecycle-hooks-and-ci-gate.md
  - decisions/adr-023-external-drift-lockfile.md
---

# Architecture — CLI dispatcher

## General description

The CLI dispatcher system in `brain-79` is responsible for parsing global command-line flags and routing user invocations to deterministic CLI subcommands or launching the MCP server fallback.

## Components and entry points

1. **`src/brain79/__main__.py`**: main entry point registered in `pyproject.toml` as `brain79 = "brain79.__main__:main"`.
2. **`src/brain79/cli/dispatch.py`**: implementation of argument parsing, subcommand dispatching, `merge-drift-lock` 3-way merge driver CLI wiring, ergonomic `read-batch --paths` / `--stdin` / `--file` parity, profile-aware `bootstrap --auto-map` / `--no-auto-map` handling, and POSIX exit code mappings.
3. **`src/brain79/cli/io.py`**: helper routines for standard input and file-based payload handling (`--content-file`, `--content-stdin`).

## Dual-position flag parsing (`parse_global_flags`)

Global flags can appear before or after subcommands without breaking parsing:
- `--project-root <PATH>` or `--project-root=<PATH>`: sets target project root explicitly.
- `--debug`: enables full traceback emission on unhandled errors.

## Whitelist routing and fallback execution

The dispatcher maintains a strict whitelist (`WHITELIST`) of 27 subcommands:
`init`, `update`, `update-project`, `doctor`, `ci-check`, `stats`, `index`, `read`, `read-batch`, `write`, `edit`, `write-many`, `schema`, `list`, `search`, `ingest`, `handoff-write`, `handoff-read`, `handoff-purge`, `navigate`, `merge-drift-lock`, `migrate`, `lint`, `bootstrap`, `context`, `orient`, `session-commit`.

Routing order in `src/brain79/__main__.py` (immediately after `parse_global_flags()`):
1. **Removed `--mcp-profile` flag**: emits a `v0.14.0` migration error to `stderr` directing callers to the `brain79 <command>` CLI and exits with code `2`.
2. **Empty arguments** (e.g. `brain79` or `brain79 --project-root .`): launches `_cmd_serve()`, starting the FastMCP server on standard IO.
3. **Help flags/commands** (`-h`, `--help`, `help [subcmd]`): prints domain-agnostic root usage or delegates to `<subcmd> --help` and exits with `0`.
4. **Version flags** (`-v`, `--version`): prints `brain79 <version>` and exits with `0`.
5. **Whitelisted subcommands**: routes to `run_cli(cmd, sub_args, debug)`.
6. **Unknown commands or flags**: emits an actionable error to `stderr` and exits with code `2` (never falling through to the MCP stdio loop).

## Exit code mapping policy

Subcommand execution maps exceptions to deterministic POSIX exit codes:
- `0`: clean success (including `ci-check --lifecycle-hook` fail-open invocations and `merge-drift-lock` clean or sentinel-resolved merges).
- `1`: validation or operational failure (e.g., linter issues in `--strict` mode, failed `ci-check` gate, `ValidationError` such as `corrupt_drift_lock`, and corrupt/empty `<ours>` or `<theirs>` in `merge-drift-lock`). Note: `ci-check` catches `ValidationError` and `json.JSONDecodeError` strictly before `ValueError` so corrupt `.brain-79/drift.lock` returns Exit `1` rather than Exit `2`.
- `2`: invalid argument or missing required parameter (`FileNotFoundError`, invalid `--wiki-root` in `merge-drift-lock`, as well as `ValueError`, `NotAGitRepoError`, and `GitError` in `ci-check`).
- `3`: file access error or concurrency timeout (`PermissionError`, `TimeoutError`, `OSError`, write failures in `merge-drift-lock`, as well as `GitTimeoutError` in `ci-check`).
- `130`: process interrupted via `KeyboardInterrupt` / `SIGINT`.

---

[← Back to Index](../INDEX.md)
