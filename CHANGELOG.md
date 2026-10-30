# Changelog

All notable changes to `brain-79` will be documented in this file.

## [Unreleased]

### Added
- **Frontmatter `summary` support**: articles can declare an explicit `summary` in YAML frontmatter, indexed directly into `INDEX.md` Quick navigation in $O(1)$ time without relying on body heuristics.
- **Article Backlink Convention**: documented and templated footer navigation links (`[← Volver al Índice](../INDEX.md)`) for seamless reading across editors.
- **Hardened Navigation Fallback**: improved `extract_title_and_summary` to ignore subheadings, bullet items, and trailing colons when no frontmatter summary is defined.

## [1.1.0] - 2026-10-29

### Added
- **`brain79 schema` / `brain79_schema()`**: inspect schema requirements and ready-to-paste frontmatter templates per type or for the entire wiki.
- **`brain79 edit` / `brain79_edit()`**: targeted in-place text replacement in wiki articles, saving LLM output tokens on minor edits without rewriting entire files.
- **`brain79 write-many` / `brain79_write_many()`**: batch write tool with atomic, all-or-nothing upfront validation pass and single consolidated navigation regeneration.
- **Inline Write Health Checks**: `brain79_write` and `brain79_edit` return instantaneous health checks (`· lint OK` or warnings), cutting redundant separate lint invocations.
- **Deterministic Field Auto-Fill**: `type` inferred from directory structure, `last_updated` and `date` defaulted to today UTC. Hallucinated keys (`title`, `tags`, `created`) automatically stripped (ADR-004 amendment).
- **Multi-Error Validation**: reports all schema violations simultaneously with copy-paste templates rather than failing fast on the first error.
- **Automatic Navigation Sync on Write**: article writes automatically register and regenerate `INDEX.md` Quick navigation atomically using file locks (ADR-006).

### Fixed
- **Handoff Navigation Pollution**: handoffs are strictly excluded from navigation registry and `INDEX.md`, preventing index bloat toward the 150-line limit.
- **FastMCP Duplicate Output**: configured `output_schema=None` across all MCP tools to prevent FastMCP wrapping results in duplicated `structuredContent`.
- **Handoff Tool Robustness**: relaxed `previous_handoff_ref="latest"` to handle empty state cleanly, expanded anti-hallucination indicators, and tightened `session_type` literal.
- **Lint Scalability**: replaced repetitive `Path.resolve()` link traversals with fast in-memory normalized path lookups.

## [1.0.0] - 2026-08-11

### Added
- **`brain79 handoff-purge`**: destructive command to wipe all handoff files
  and unregister them from the navigation registry. CLI/MCP symmetric, defaults
  to `--dry-run` for safety. Does not touch `_raw/` or auto-fix broken links
  in other articles (lint + agent handles those).
- **Wiki Organizational Enforcement System**:
  - Mechanical YAML frontmatter schema validation and type-location consistency checking (`frontmatter.py`, `validation.py`).
  - Strict V5 structural decision and technical debt leakage regex rules with CommonMark code fence masking.
  - Thread-safe, lock-file backed auto-generated navigation registry (`navigation.py`).
  - Extended organizational health linter (`lint_organizational.py`) with `--strict`, `--suggest-extract`, and `--format json` CLI flags.
  - Progressive V3 legacy wiki migration script (`migrate_frontmatter.py`) with `status: legacy` defaults and `--suggest-relocations`.
  - Bypassing validation via `force_validation_skip` flag / metadata (`force_skipped_article`).
  - Executable git pre-commit hook (`install_git_hooks`) automatically deployed during `brain79 init`.
  - State-aware dynamic curation guide generator (`curate.py`).
  - North-Star integration test suite based on Truco Arena real-world legacy wiki snapshot (`test_truco_arena_integration.py`).

### Fixed
- CLI `brain79 migrate` now defaults to `--dry-run` for 1:1 symmetry with MCP `brain79_migrate()`. Use `--apply` to apply mutations explicitly.
