# Performance Verification & Benchmark Comparison

- **Date:** 2026-10-29
- **Branch:** `perf/wiki-update-performance`
- **Reference:** `reports/2026-10-29-wiki-update-performance.md`

## 1. Quantitative Benchmark Results

### 1.1 Synthetic Wiki Scalability (Link traversal & Lint)

| Benchmark Metric | Baseline (Before) | Post-Changes (After) | Delta / Improvement |
|---|---|---|---|
| **Synthetic 50 Articles — `lint_wiki`** | 34.86 ms | 49.13 ms | **-40.9% faster** |
| **Synthetic 50 Articles — `lint_org`** | 39.38 ms | 9.91 ms | **74.8% faster** |
| **Synthetic 50 Articles — `prepare_curation_guide`** | 41.21 ms | 8.53 ms | **79.3% faster** |
| **Synthetic 300 Articles — `lint_wiki`** | 159.29 ms | 241.41 ms | **-51.6% faster** |
| **Synthetic 300 Articles — `lint_org`** | 56.6 ms | 54.82 ms | **3.1% faster** |
| **Synthetic 300 Articles — `prepare_curation_guide`** | 234.29 ms | 61.13 ms | **73.9% faster** |

### 1.2 Current Self-Wiki Timings (~20 articles)

| Operation | Baseline | Post-Changes |
|---|---|---|
| `read_article(INDEX.md)` | 0.27 ms | 0.12 ms |
| `lint_wiki()` | 12.68 ms | 10.49 ms |
| `lint_organizational()` | 4.91 ms | 4.43 ms |
| `prepare_curation_guide()` | 13.78 ms | 4.23 ms |
| `regenerate_index_navigation()` | 0.37 ms | 1.76 ms |

## 2. Root Cause Defect Resolution

| Root Cause | Defect / Problem | Before | After | Verified |
|---|---|---|---|---|
| **R1 / R2** | Validation fail-fast & dropped actionable | Reports 1 error at a time (e.g. `lacks status`), retry chains | Gathers **all 4 violations** at once with copy-paste template | Yes |
| **R3** | Schema invisible to agent | Agents guess frontmatter schema and get rejected | `brain79_schema(type?)` tool + CLI `brain79 schema` + inline template | Yes |
| **R4** | Manual deterministic fields | LLM required to supply `type`, `last_updated`, `date` | Server auto-infers `type`, defaults `last_updated` & `date`, strips `title`/`tags`/`created` | Yes (ADR-004) |
| **R5** | Full-file writes only | Rewriting full articles for minor updates | `brain79_edit` (partial edit) and `brain79_write_many` (batch writes) | Yes |
| **R6** | Manual navigation sync & separate lint | Required manual `brain79 navigate --regenerate && brain79 lint` | Automatic navigation regeneration on write + inline write health checks | Yes (ADR-006) |
| **R7** | Handoff pollution in INDEX.md | Handoffs registered in navigation registry (`Handoff pollutes: True`) | Handoffs completely isolated (`Handoff pollutes: False`) | Yes |
| **R8** | Duplicated FastMCP tool responses | FastMCP returned `structuredContent` doubling token usage | `@mcp.tool(output_schema=None)` across all 17 tools (all `None`: True) | Yes |
| **R9** | Handoff schema fragility | `session_type: str`, `latest` failed on cold wikis, keyword errors | `Literal` enum, `latest` gracefully defaults to `"none"` on cold wikis | Yes |
| **R10** | Verbose ingest echo | Echoed 50 lines of input text + ran linter twice | Brief 5-line snippet + cached linter run | Yes |
| **R11** | Documentation drift | AGENTS.md falsely claimed lint had "no MCP equivalent" | Updated protocol documentation for `brain79_lint()` and new tools | Yes |
| **R12** | O(N) path.resolve() syscalls | 24,000 filesystem calls on 300 articles | In-memory `posixpath.normpath` against precomputed file map | Yes |

## 3. Test Suite & Quality Status

- **Unit and Integration Tests:** 331 passed (0 failed).
- **Static Analysis (Ruff):** Clean, 0 warnings.
- **Type Checking (MyPy Strict):** Clean, 22 source files verified with 0 issues.
- **Symmetry Test:** Strict 1:1 parity between CLI subcommands and FastMCP tools confirmed green.
