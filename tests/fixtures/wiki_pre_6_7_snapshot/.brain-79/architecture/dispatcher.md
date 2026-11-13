---
type: architecture
summary: CLI argument parsing, closed-whitelist subcommand routing, and POSIX exit code mappings
stability: stable
last_updated: 2026-10-29
---

# Architecture — CLI dispatcher

## General description

The CLI dispatcher system in `brain-79` is responsible for parsing global command-line flags and routing user invocations to deterministic CLI subcommands or launching the MCP server fallback.

## Components and entry points

1. **`src/brain79/__main__.py`**: Main entry point registered in `pyproject.toml` as `brain79 = "brain79.__main__:main"`.
2. **`src/brain79/cli/dispatch.py`**: Implementation of argument parsing, subcommand dispatching, and POSIX exit code mappings.
3. **`src/brain79/cli/io.py`**: Helper routines for standard input and file-based payload handling (`--content-file`, `--content-stdin`).

## Dual-position flag parsing (`parse_global_flags`)

Global flags can appear before or after subcommands without breaking parsing:
- `--project-root <PATH>` or `--project-root=<PATH>`: Sets target project root explicitly.
- `--debug`: Enables full traceback emission on unhandled errors.

## Whitelist routing and fallback execution

The dispatcher maintains a strict whitelist (`WHITELIST`) of 22 subcommands:
`init`, `update`, `index`, `read`, `read-batch`, `write`, `edit`, `write-many`, `schema`, `list`, `search`, `ingest`, `handoff-write`, `handoff-read`, `handoff-purge`, `navigate`, `migrate`, `lint`, `bootstrap`, `context`, `orient`, `session-commit`.

Routing order in `src/brain79/__main__.py`:
1. **Empty arguments** (e.g. `brain79` or `brain79 --project-root .`): Launches `_cmd_serve()`, starting the FastMCP server on standard IO.
2. **Help flags/commands** (`-h`, `--help`, `help [subcmd]`): Prints domain-agnostic root usage or delegates to `<subcmd> --help` and exits with `0`.
3. **Version flags** (`-v`, `--version`): Prints `brain79 <version>` and exits with `0`.
4. **Whitelisted subcommands**: Routes to `run_cli(cmd, sub_args, debug)`.
5. **Unknown commands or flags**: Emits an actionable error to `stderr` and exits with code `2` (never falling through to the MCP stdio loop).

## Exit code mapping policy

Subcommand execution maps exceptions to deterministic POSIX exit codes:
- `0`: Clean success.
- `1`: Validation or operational failure (e.g., linter issues in `--strict` mode).
- `2`: Invalid argument or missing required parameter (`FileNotFoundError` also maps to 2).
- `3`: File access error or concurrency timeout (`PermissionError`, `TimeoutError`, `OSError`).
- `130`: Process interrupted via `KeyboardInterrupt` / `SIGINT`.

---

[← Volver al Índice](../INDEX.md)
