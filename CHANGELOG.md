# Changelog

All notable changes to `brain-79` will be documented in this file.

## [Unreleased]

## [2.0.0] - 2026-11-03

### Added
- **Phase 5: Single-Source Semantic Versioning & Release Governance**:
  - Established `src/brain79/__init__.py` as the single source of truth for versioning, resolved dynamically by Hatchling (`dynamic = ["version"]`).
  - Added `version=__version__` to `FastMCP("brain79")` initialization for accurate JSON-RPC handshake metadata.
  - Enhanced CLI root help (`brain79 --help` / `brain79 help <subcmd>`) and added `-v` / `--version` flags with strict exit code 2 on unknown commands.
  - Implemented mechanical release parity test suite (`tests/test_version_governance.py`) enforcing SemVer compliance, Hatchling dynamic build configuration, README badge synchronization, and changelog parity across both `.brain-79/changelog/` and root `CHANGELOG.md`.
- **Phase 4: Structural Article Quality & Deterministic Drift Detection**:
  - Enforced document structural integrity with section skeletons per document type (`## Status`, `## Context`, `## Decision`, `## Consequences` for decisions; `## Overview` for features).
  - Automated backlink injection (`[← Volver al Índice](../INDEX.md)`) across all subfolder articles during write normalization.
  - Implemented Git-backed code-to-wiki drift detection (`documentation_drift_suspected`) alerting when workspace source files change after governing documentation `last_updated` dates.
- **Phase 3: Zero-Turn Session Execution (The Two-Call Session Protocol)**:
  - Introduced `brain79_session_commit` (FastMCP) and `brain79 session-commit` (CLI) providing 1-call atomic end-of-session finalization:
    - Pre-flight in-memory simulation and validation of writes, edits, and handoff anti-hallucination constraints with an all-or-nothing rollback guarantee (zero files hit disk on error).
    - Synchronous execution of raw session archiving (`_raw/sessions/`), article writes, partial edits, and immutable handoffs.
    - Single consolidated navigation registry update and index regeneration under lock.
    - Whole-transaction inline health diagnostics receipt (`check_file_health`).
  - Added section-projected reading via `sections` parameter in `brain79_read` / `brain79 read` and batch reading via `brain79_read_batch` / `brain79 read-batch`, eliminating turn tax and reducing context window token consumption.
  - Automatically append governing ADR reference hints (`💡 Linked ADRs: ...`) to article reads.
- **Phase 2: Deterministic Pre-Work Context & Graph-Augmented Cold Start**:
  - Introduced `brain79 orient` (CLI) and `brain79_orient(task?, paths?, max_articles?)` (MCP), consolidating routing table, latest handoff state, promotion alerts, and inlined governing documents into a single tool call.
  - Upgraded context ranking (`rank_context_articles`) to a 3-signal deterministic engine:
    1. *Signal 1*: Exact and glob matching of `applies_to` frontmatter against workspace files.
    2. *Signal 2*: Field-weighted TF-IDF (title $3\times$, summary $2\times$, body $1\times$) with down-ranking of superseded articles.
    3. *Signal 3*: 1-Hop ADR reference graph expansion pulling active governing decisions linked from matched articles.
  - Extended frontmatter schema and templates to recognize `applies_to`, `related`, and `supersedes` across all article types.
  - Updated navigation registry indexing to capture article graph edges (`applies_to`, `related`, and `outgoing_links`).
- **Phase 1: Declarative Schema & Dual Ontology**:
  - Decoupled validation engine (mechanism) from directory/type policies via `load_active_schema` with high-speed mtime caching.
  - Added built-in dual ontologies (`software` and `general`) supported via `brain79 init [--profile software|general]`.
  - Added support for arbitrary custom directories and frontmatter types declared in `.brain-79/SCHEMA.md` (`custom_types`).
  - Added dynamic profile sensitivity to `brain79 schema` / `brain79_schema()`.
  - Added dynamic `session_type` validation for handoffs, enabling general profile session types (`work`, `writing`, `analysis`, `research`).
  - Added schema-aware field preservation in `autofill_deterministic_fields` (preserving declared optional fields like `tags` on `topic` and auto-filling `date` on `log`).
  - Added explicit direct package dependency on `pyyaml` and `types-pyyaml`.
- **Frontmatter `summary` support**: articles can declare an explicit `summary` in YAML frontmatter, indexed directly into `INDEX.md` Quick navigation in $O(1)$ time without relying on body heuristics.
- **Article Backlink Convention**: documented and templated footer navigation links (`[← Volver al Índice](../INDEX.md)`) for seamless reading across editors.
- **Hardened Navigation Fallback**: improved `extract_title_and_summary` to ignore subheadings, bullet items, and trailing colons when no frontmatter summary is defined.
- **Phase 0: Foundation Cleanup & Parity**:
  - Unification of organizational linter with write validation (`validate_frontmatter`).
  - Strict enforcement of ADR-008 (*Pure Routing Table*) in `INDEX_ALLOWED_H2`.
  - Validation alignment for `brain79_bootstrap` manifests and `_raw/sessions/` frontmatter.

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
