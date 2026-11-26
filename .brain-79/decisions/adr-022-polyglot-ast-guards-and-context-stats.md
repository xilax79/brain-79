---
type: decision
summary: "isolate optional Tree-sitter polyglot AST guards behind brain79[polyglot] and ship read-only brain79 stats telemetry"
status: accepted
date: 2026-11-24
deciders:
  - xilax
related:
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
last_updated: 2026-11-24
---

# ADR-022 — Polyglot AST guards and context budget telemetry

## Status

Accepted (2026-11-24).

## Context

Prior to `v0.16.0`, Guard C public signature verification in `session_commit()` inspected only Python files via stdlib `ast`, while non-Python repositories relied solely on file-level Merkle drift. Meanwhile, teams had no read-only CLI command to inspect `orient()` token budgets, active vs. superseded wiki footprint, or governance coverage.

## Decision

1. **Zero-dependency core with optional `brain79[polyglot]` extra**: core `brain79` keeps its minimal dependency footprint (`fastmcp`, `filelock`, `pyyaml`) and built-in `PythonInspector`. Deep AST signature verification for 10 additional parsers (`typescript`, `tsx`, `javascript`, `go`, `rust`, `java`, `c_sharp`, `php`, `ruby`, `bash`) lives behind `[project.optional-dependencies] polyglot` (`tree-sitter>=0.25,<0.26` and 9 grammar packages).
2. **Metadata-only discovery and lock-guarded lazy initialization**: `discover_polyglot_inspectors()` uses `importlib.util.find_spec()` without importing C extensions at startup, and `TreeSitterInspector` validates `Language()` lazily under a `threading.Lock`, unregistering broken grammars cleanly.
3. **Read-only CLI-only `brain79 stats`**: `compute_stats()` and `brain79 stats` (`WHITELIST` expands from 25 to 26; `MCP_TOOLS` remains fixed at 9 per ADR-020) compute deterministic token budgets and coverage metrics without creating or mutating `.brain-79/` caches.

## Consequences

- **Positive**: non-Python and polyglot repositories gain mechanical AST Guard C protection without penalizing core install speed, and teams gain deterministic context-budget visibility.
- **Negative**: polyglot AST parsing requires installing `brain79[polyglot]`; environments without it fall back gracefully to file-level Merkle drift.

---

[← Back to Index](../INDEX.md)
