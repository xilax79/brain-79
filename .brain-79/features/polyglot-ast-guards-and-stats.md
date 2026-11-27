---
type: feature
summary: optional Tree-sitter polyglot AST Guard C for 10 language parsers, shared two-pass Guard C baseline resolution, and read-only brain79 stats telemetry
status: shipped
version: 0.18.0
applies_to:
  - src/brain79/core/ast_guards/treesitter_inspector.py
  - src/brain79/core/ast_guards/polyglot.py
  - src/brain79/core/stats.py
related:
  - decisions/adr-022-polyglot-ast-guards-and-context-stats.md
  - decisions/adr-023-external-drift-lockfile.md
  - features/transitive-drift-and-ripple-guards.md
  - features/cli.md
last_updated: 2026-11-27
---

# Feature — Polyglot AST guards and context budget telemetry

## Overview

This subsystem extends Guard C public API verification across 10 optional Tree-sitter language parsers (`brain79[polyglot]`), anchors Guard C baseline commits across both `.brain-79/drift.lock` and legacy frontmatter history, and provides read-only context budget telemetry through `brain79 stats` and `orient()`.

## Polyglot AST Guard C (`treesitter_inspector.py`, `polyglot.py`)

- **Supported parsers (10 polyglot + Python = 11 total)**: `typescript` (`.ts`, `.mts`, `.cts`), `tsx` (`.tsx`), `javascript` (`.js`, `.jsx`, `.mjs`, `.cjs`), `go` (`.go`), `rust` (`.rs`), `java` (`.java`), `c_sharp` (`.cs`), `php` (`.php`), `ruby` (`.rb`), and `bash` (`.sh`, `.bash`).
- **Lazy discovery and fault isolation**: `discover_polyglot_inspectors()` checks package presence via `find_spec()` without importing native extensions until an extension is inspected, then initializes `Language()` under a `threading.Lock` and isolates broken grammars into `broken_grammars`.
- **AST-accurate normalization**: `TreeSitterInspector` strips comment AST nodes while keeping string/literal tokens atomic, skips payloads above `MAX_AST_SOURCE_BYTES` (2 MB), enforces 3-branch syntax-error safety, and uses qualified overload-safe symbol keys.

## Shared Guard C baseline resolution (`resolve_article_baseline_commit`)

Both `has_public_api_changes()` (`orchestrator.py`) and `has_public_python_api_changes()` (`python_inspector.py`) delegate to `resolve_article_baseline_commit()` using bounded first-parent Git history (`git_first_parent_log()`, `max_commits = 50`, cached in `GitSessionCache`):
- **Pass 1 (combined walk)**: walks `--first-parent --format=%H %P` across `<wiki_rel>/drift.lock` and `<wiki_rel>/<rel_article>`, resolving true parent `P` strictly from `%P` (`None` only at root/shallow boundaries). Selects commit `C` on (1) substantive `.md` digest change (`compute_wiki_article_digest`), (2) non-migration `drift.lock` digest change (skipping pure `migrate --apply` commits that copy an unchanged legacy digest), or (3) legacy frontmatter `applies_to_digest` update.
- **Pass 2 (article-only fallback)**: when >50 unrelated `drift.lock` commits push an article's history past Pass 1's window, runs a bounded walk exclusive to `<wiki_rel>/<rel_article>` applying Rules 1 and 3 before falling back to the oldest reached commit or `HEAD`.
- **Error contract**: returns `(False, "")` outside Git repositories (`NotAGitRepoError`) and fails closed with `ValidationError(rule="ast_verification_failed")` on `GitTimeoutError`, `GitError`, or `OSError`.

## Read-only context budget telemetry & `orient()` fast path (`stats.py`, `orient.py`)

- **Zero-mutation guarantee**: `compute_stats()` reuses a single `WorkspaceIndex` and `GitSessionCache` without creating `.brain-79/drift.lock`, `.drift_manifest.json`, `.navigation_registry.json`, or `.locks/`.
- **Zero-rebuild `orient()` fast path**: when active articles are tracked in `.brain-79/drift.lock`, `orient()` resolves baselines directly from `drift.lock` without calling `rebuild_drift_manifest()`, keeping cold-start latency within SLA-1 budgets across Ubuntu, macOS, and Windows.
- **Deterministic token and coverage metrics**: reports `estimate_tokens(text)` (`ceil(len(lf_text) / 4)`), `orient()` startup footprint vs. `64_000`-character budget utilization, active vs. inactive article counts, `over_limit` living manuals, and governed vs. ungoverned workspace file coverage.
- **CLI output**: `brain79 stats` supports `--format text|json`, `--task`, `--paths`, `--max-articles`, and `--project-root`.

---

[← Back to Index](../INDEX.md)
