---
type: architecture
stability: stable
last_updated: 2026-08-11
---

# Architecture — CLI Dispatcher

## General Description

The CLI dispatcher system in `brain-79` is responsible for parsing global command-line flags and routing user invocations to deterministic CLI subcommands or launching the MCP server fallback.

## Components & Entry Points

1. **`src/brain79/__main__.py`**: Main entry point registered in `pyproject.toml` as `brain79 = "brain79.__main__:main"`.
2. **`src/brain79/cli/dispatch.py`**: Implementation of argument parsing, subcommand dispatching, and POSIX exit code mappings.
3. **`src/brain79/cli/io.py`**: Helper routines for standard input and file-based payload handling (`--content-file`, `--content-stdin`).

## Dual-Position Flag Parsing (`parse_global_flags`)

Global flags can appear before or after subcommands without breaking parsing:
- `--project-root <PATH>` or `--project-root=<PATH>`: Sets target project root explicitly.
- `--debug`: Enables full traceback emission on unhandled errors.

## Whitelist Routing & Fallback Execution

The dispatcher maintains a strict whitelist (`WHITELIST`) of subcommands:
`init`, `update`, `index`, `read`, `write`, `list`, `search`, `ingest`, `handoff-write`, `handoff-read`, `handoff-purge`, `navigate`, `migrate`, `lint`, `bootstrap`.

If `sys.argv[1:]` starts with a whitelisted command, execution routes to `run_cli(cmd, sub_args, debug)`.
If no subcommand is provided (e.g. `brain79 --project-root .`), execution falls back to `_cmd_serve()`, launching the FastMCP server on standard IO.

## Exit Code Mapping Policy

Subcommand execution maps exceptions to deterministic POSIX exit codes:
- `0`: Clean success.
- `1`: Validation or operational failure (e.g., linter issues in `--strict` mode).
- `2`: Invalid argument or missing required parameter.
- `3`: File access error or path containment violation (`FileNotFoundError`, `OSError`).
- `4`: Concurrent file lock timeout (`TimeoutError`).
- `130`: Process interrupted via `KeyboardInterrupt` / `SIGINT`.
