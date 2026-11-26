---
type: feature
summary: optional Tree-sitter polyglot AST Guard C for 10 language parsers and read-only brain79 stats context budget telemetry
status: shipped
version: 0.16.0
applies_to:
  - src/brain79/core/ast_guards/treesitter_inspector.py
  - src/brain79/core/ast_guards/polyglot.py
  - src/brain79/core/stats.py
related:
  - decisions/adr-022-polyglot-ast-guards-and-context-stats.md
  - features/transitive-drift-and-ripple-guards.md
  - features/cli.md
last_updated: 2026-11-24
applies_to_digest: "sha256:cec6d2569d6846e8"
applies_to_count: 3
---

# Feature — Polyglot AST guards and context budget telemetry

## Overview

This subsystem extends Guard C public API verification across 10 optional Tree-sitter language parsers (`brain79[polyglot]`) and provides read-only context budget and governance telemetry through `brain79 stats`.

## Polyglot AST Guard C (`treesitter_inspector.py`, `polyglot.py`)

- **Supported parsers (10 polyglot + Python = 11 total)**: `typescript` (`.ts`, `.mts`, `.cts`), `tsx` (`.tsx`), `javascript` (`.js`, `.jsx`, `.mjs`, `.cjs`), `go` (`.go`), `rust` (`.rs`), `java` (`.java`), `c_sharp` (`.cs`), `php` (`.php`), `ruby` (`.rb`), and `bash` (`.sh`, `.bash`).
- **Lazy discovery and fault isolation**: `discover_polyglot_inspectors()` checks package presence via `find_spec()` without importing native extensions until an extension is inspected, then initializes `Language()` under a `threading.Lock` and isolates broken grammars into `broken_grammars`.
- **AST-accurate normalization**: `TreeSitterInspector` strips comment AST nodes while keeping string/literal tokens atomic, skips payloads above `MAX_AST_SOURCE_BYTES` (2 MB), enforces 3-branch syntax-error safety, and uses qualified overload-safe symbol keys.

## Read-only context budget telemetry (`stats.py`, `brain79 stats`)

- **Zero-mutation guarantee**: `compute_stats()` reuses a single `WorkspaceIndex` and `GitSessionCache` without creating `.drift_manifest.json`, `.navigation_registry.json`, or `.locks/`.
- **Deterministic token and coverage metrics**: reports `estimate_tokens(text)` (`ceil(len(lf_text) / 4)`), `orient()` startup footprint vs. `64_000`-character budget utilization, active vs. inactive article counts, `over_limit` living manuals, and governed vs. ungoverned workspace file coverage.
- **CLI output**: `brain79 stats` supports `--format text|json`, `--task`, `--paths`, `--max-articles`, and `--project-root`.

---

[← Back to Index](../INDEX.md)
