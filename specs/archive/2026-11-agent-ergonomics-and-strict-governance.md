---
spec_id: SPEC-202611-agent-ergonomics-and-strict-governance
title: Agent ergonomics, strict bootstrap governance, and batch-read parity
target_version: 0.17.0
status: implemented
owner: xilax79
last_updated: 2026-11-27
related_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/mcp-server.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - features/team-collaboration-and-onboarding.md
  - features/organizational-enforcement.md
  - topics/phase-16-anti-rot-benchmark-results.md
target_wiki:
  - architecture/mcp-server.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - features/mcp-server.md
  - features/team-collaboration-and-onboarding.md
  - features/organizational-enforcement.md
  - topics/phase-16-anti-rot-benchmark-results.md
---

# SPEC-202611-agent-ergonomics-and-strict-governance — Agent ergonomics, strict bootstrap governance, and batch-read parity

## Problem statement and goal

The first calibrated live execution of the Phase 16 longitudinal anti-rot benchmark (`SPEC-016` `AC-6`, `agy 1.5.18` + `gemini-4-hydrogen-low` on `LedgerPulse`, commit `686b9d4`) confirmed 100% autonomous compliance (`12/12`), 0.82% documentation rot (`PASS`), valid `S9`/`S10` triage (`PASS`), and low context overhead (`2,818` `orient_chars`, `PASS`), while isolating three concrete product defects in `brain-79` that prevented release-gate closure:

1. **Bootstrap, orient, and template mismatch on `applies_to:`**: `brain79_bootstrap` defaults `auto_map=False` and prints an `architecture/overview.md` frontmatter example without `applies_to:`, `generate_frontmatter_template()` and `templates/SCHEMA.md` omit `applies_to:`, and `brain79_orient` omits `applies_to` from its `Active Schema Summary`. As a result, budget models create active `architecture/*.md` articles without `applies_to:`, causing cascading `lint --strict` / `ci-check --enforcement strict` failures (`exit 1`), dropping canonical `src/**` coverage to `50.0%`, and blinding Merkle drift detection on ungoverned architecture articles.
2. **Batch-read parameter mismatch (`paths` vs `requests`) and `orient` slot-stealing**: `brain79_read_batch` accepts only `requests: list[dict[str, Any]]` (and CLI `brain79 read-batch` has no `--paths` flag), rejecting `paths: list[str]` with a Pydantic validation error even though `brain79_orient` and `brain79_context` both expose `paths`. Separately, `context.py` allows `INDEX.md` and `SCHEMA.md` to consume `top_n` slots before truncation and downweights rather than excludes inactive articles from living-doc reminders. In blind semantic recall, `gemini-4-hydrogen-low` called `brain79_read_batch(paths=[...])`, failed on schema validation, fell back to partial manual reads, and scored `70.83%` vs Arm B's `87.50%`.
3. **Strict-mode write vs lint asymmetry and thin API contract summaries**: write paths (`brain79_session_commit`, `write_article`, `brain79_edit`, `write_many_articles`) silently succeed and report `lint OK` when committing active `software` `architecture/` or `features/` articles lacking `applies_to:` under `enforcement: strict`, even though `lint --strict` immediately fails on those same files; meanwhile, `templates/AGENTS.md`, `SCHEMA.md`, and bootstrap instructions do not instruct agents to record public signatures (parameter names) and key business constants or thresholds in living manuals.

The goal of this specification is to resolve all three product defects (plus one minor Arm B segment-bounded suffix-path symmetry fix in the Phase 16 evaluator) without expanding the 9-tool MCP surface, adding runtime dependencies, introducing anti-sprawl overlap collisions, or deadlocking pre-implementation (`planned`/`draft`/`proposed`) articles, so that a clean live re-execution of `SPEC-016` passes all 7 release-gate criteria on `gemini-4-hydrogen-low`.

## Non-goals (out of scope)

- **No MCP tool additions or removals**: `MCP_TOOLS` MUST remain exactly 9 focused tools and CLI `WHITELIST` MUST remain 26 subcommands per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md).
- **No new runtime dependencies**: core `brain79` remains zero-extra-dependency (only existing `fastmcp`, `filelock`, `pyyaml`).
- **No blocking of `balanced`, `advisory`, `general` profile, or pre-implementation/inactive articles**: repositories running under `balanced` or `advisory` enforcement, the `general` profile, or writing articles whose `status` or `stability` is in `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES` MUST NOT be blocked for missing `applies_to:`.
- **No PyPI publishing or version bump in this spec alone**: cutting `v0.17.0` and archiving `SPEC-016` occur only after the live `AC-6` re-run emits `PASS`.
- **No model-specific prompts or pruned MCP names in templates**: guidance must remain model-agnostic, concise, and free of any pruned MCP tool names enforced by `tests/test_mcp_server.py`.

## Dependencies

- **Internal seams**:
  - `src/brain79/core/bootstrap.py` and `src/brain79/core/auto_map.py` (shipped in Phase 12).
  - `src/brain79/core/orient.py`, `src/brain79/core/context.py`, and `src/brain79/core/frontmatter.py` (shipped in Phase 10 / 15).
  - `src/brain79/core/session_commit.py`, `src/brain79/core/wiki.py`, `src/brain79/core/validation.py`, and `src/brain79/core/lint_organizational.py` (shipped in Phase 11 / 12).
  - `src/brain79/server.py`, `src/brain79/cli/dispatch.py`, and `src/brain79/templates/{AGENTS.md,SCHEMA.md,SKILL.md}`.
  - `benchmarks/anti_rot/evaluator.py` (shipped in Phase 16 harness).
- **External / optional**: none.

## Constraints and invariants

All requirements must preserve the repository's canonical invariants:

- **Versioning**: pre-GA minor versioning per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md).
- **Concurrency and cross-platform I/O**: lock hierarchy and atomic LF writes per [ADR-014](../.brain-79/decisions/adr-014-centralized-locks-and-cross-platform-io.md).
- **CLI and MCP symmetry**: 1:1 parity per [ADR-001](../.brain-79/decisions/adr-001-hybrid-cli.md) and [symmetry.md](../.brain-79/architecture/symmetry.md).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Documentation style**: sentence case and living manual rules per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **FastMCP wire-schema simplicity**: MCP tool parameter annotations MUST avoid nested `anyOf` union schemas inside array items that degrade tool calling on budget models; generated schemas MUST be verified via `mcp.list_tools()`.
- **Backward compatibility**: existing callers invoking `brain79_read_batch(requests=[{"path": "...", "sections": [...]}])`, `brain79 read-batch --file/--stdin`, `brain79 bootstrap --auto-map`, or `brain79_session_commit` under `balanced`/`advisory` tiers or `general` profile MUST continue working without breaking changes.

## Open questions

All open questions MUST be resolved (`[x]`) before the `owner` transitions this specification from `draft` to `approved`. Agents MUST NOT implement a `draft` specification.

- [x] **Q-1**: Under `enforcement: strict` and `profile: software`, should `unanchored_governance_article` pre-flight rejection apply uniformly across all write paths (`commit_session`, `write_article` / `brain79_edit`, and `write_many_articles` — matching how `applies_to_target_missing` and `check_anti_sprawl_overlap` already work, with `force_validation_skip=True` bypass and warning-only in `balanced`/`advisory`), or only in `commit_session` plus a `check_file_health()` warning? **Decision (`xilax79`)**: enforce uniformly across all write paths AND add the warning to `check_file_health()` so `brain79_edit` can never strip `applies_to:` and report `lint OK`.
- [x] **Q-2**: Should `auto_map: bool | None = None` default to `True` when `active_schema.profile == "software"` and `False` when `active_schema.profile == "general"` across `run_bootstrap`, `brain79_bootstrap`, and CLI `brain79 bootstrap` (adding `--no-auto-map` opt-out and updating `tests/test_symmetry.py`)? **Decision (`xilax79`)**: yes.
- [x] **Q-3**: After implementing this spec and verifying `PASS` on `gemini-4-hydrogen-low`, should `v0.17.0` be gated on `gemini-4-hydrogen-low` while logging one higher-tier run (e.g., `gemini-4-neon-medium`) as supplementary telemetry? **Decision (`xilax79`)**: yes.

## Requirements (EARS)

### Capability 1 — Governance-complete bootstrap, disjoint partitioning, and orient/template parity

- **R-1.1**: WHERE the active wiki schema has `profile == "software"` and the caller leaves `auto_map` unset (`auto_map: bool | None = None` in `run_bootstrap()` / `brain79_bootstrap()`, or neither `--auto-map` nor `--no-auto-map` passed to CLI `brain79 bootstrap`), THE bootstrap engine SHALL resolve `auto_map` to `True` and append zero-overlap `applies_to:` module proposals; WHERE `profile == "general"` or `auto_map=False` / `--no-auto-map` is passed, THE bootstrap engine SHALL leave `auto_map` disabled.
- **R-1.2**: WHEN `brain79_bootstrap` renders the bootstrap scan manifest for a `software` wiki, THE bootstrap generator SHALL enforce disjoint `applies_to:` partitioning in its instructions and dynamically derived frontmatter examples so bootstrapped articles never trigger `check_anti_sprawl_overlap` (`duplicate_governance_target`) or `applies_to_target_missing`:
  - `architecture/overview.md` SHALL use an intra-wiki umbrella pattern (e.g., `.brain-79/features/*.md`, which `check_anti_sprawl_overlap` exempts) and/or detected root documentation (e.g., `README.md`) derived from scanned root signals, never a hardcoded `src/**` glob, and SHALL use sentence case in `summary:`.
  - `architecture/stack.md` SHALL govern detected manifest/configuration files only (e.g., `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`), disjoint from `auto_map`'s source-code proposals.
  - Module articles proposed by `auto_map` SHALL govern disjoint source directories; when `total_code_files == 0` (empty repo) or `force=True` on an existing wiki, THE bootstrap manifest SHALL degrade gracefully without proposing overlapping or non-existent patterns and SHALL note `allow_overlapping_governance: true` for intentional cross-cutting architecture docs.
- **R-1.3**: WHEN `brain79_orient` renders the `Active Schema Summary` section for a `software` wiki, THE orient orchestrator SHALL explicitly indicate `applies_to` as required under `enforcement: strict` (and recommended under `balanced`/`advisory`) for `architecture/` and `features/` managed directories so the orient summary never contradicts `lint --strict` or `ci-check --enforcement strict`.
- **R-1.4**: WHEN `brain79_bootstrap` or `src/brain79/templates/SCHEMA.md` (software profile) provides authoring guidance for `architecture/` and `features/` living manuals, THE templates SHALL instruct agents to document public function/method signatures (including parameter names) and key business constants or thresholds rather than bare symbol name lists.
- **R-1.5**: WHEN `generate_frontmatter_template()` (`src/brain79/core/frontmatter.py`) or `src/brain79/templates/SCHEMA.md` renders a frontmatter skeleton for `architecture` or `feature` articles under `profile == "software"`, THE template generator SHALL include an `applies_to:` field placeholder (preserving the existing required-fields error summary format), AND `src/brain79/templates/AGENTS.md` SHALL include one concise, model-agnostic guideline instructing agents to record public API signatures (parameter names) and key business constants/thresholds in living manuals during code-mutation sessions.

### Capability 2 — Ergonomic `brain79_read_batch` normalization and CLI/MCP parity

- **R-2.1**: WHEN a caller invokes `brain79_read_batch` with `paths: list[str]` (either top-level or inside nested `args`), THE MCP server SHALL delegate to centralized normalization in `src/brain79/core/wiki.py` (`read_batch_articles`), normalize `.brain-79/` prefixes, and return the same formatted multi-article markdown output as `requests=[{"path": ...}]`.
- **R-2.2**: WHEN a caller passes string elements inside `requests` (e.g., `requests=["architecture/overview.md"]`) or passes both `requests` and `paths`, THE batch reader SHALL accept both forms deterministically, deduplicate identical `(normalized_path, tuple(sections) or None)` entries while preserving first-seen order, and preserve 100% backward compatibility with dict requests containing `path` and optional `sections`. To preserve simple FastMCP JSON schemas for budget models, `brain79_read_batch` SHALL avoid nested `anyOf` union types in `array.items` (exposing flat `paths: list[Any] | None = None` and `requests: list[Any] | None = None` or equivalent non-`anyOf` schema verified via `mcp.list_tools()`).
- **R-2.3**: IF a caller passes an empty batch (neither `requests` nor `paths` provided, or empty lists) OR an invalid element type inside `requests`/`paths` (such as an `int` or dict missing `"path"`), THEN THE `brain79_read_batch` tool SHALL return an actionable usage error string showing both accepted forms (`paths=[...]` and `requests=[{"path": ..., "sections": [...]}]`) without raising an unhandled exception.
- **R-2.4**: WHEN `brain79_orient` renders the batch-read guidance or `src/brain79/templates/{AGENTS.md,SKILL.md}` documents hot-path MCP tools, THE protocol text SHALL include a concise one-line example of `brain79_read_batch(paths=[...])` without re-introducing any pruned MCP tool names.
- **R-2.5**: WHEN a user invokes CLI `brain79 read-batch`, THE CLI dispatcher (`src/brain79/cli/dispatch.py`) SHALL maintain 1:1 symmetry with `brain79_read_batch` per [ADR-001](../.brain-79/decisions/adr-001-hybrid-cli.md) by supporting `--paths <p1> [<p2> ...]` as well as JSON arrays of strings or request dicts via `--file` and `--stdin`.

### Capability 3 — Strict-mode pre-flight parity across write paths

- **R-3.1**: WHILE the active wiki schema declares `profile == "software"` and `enforcement: strict`, WHEN a write path (`commit_session`, `write_article` / `brain79_edit`, or `write_many_articles`) validates an article whose `doc_type` is `"architecture"` or `"feature"` AND whose `status` and `stability` are neither in `INACTIVE_STATUSES` (`superseded`, `deprecated`, `archived`, `rejected`, `legacy`) nor in `PRE_IMPLEMENTATION_STATUSES` (`planned`, `draft`, `proposed`), THE validator SHALL reject any article missing a non-empty `applies_to` list with `ValidationError(rule="unanchored_governance_article")` before modifying any file on disk — matching `check_unanchored_governance()` in `src/brain79/core/lint_organizational.py` 1:1.
- **R-3.2**: WHERE `enforcement` is `"balanced"` or `"advisory"`, OR `profile == "general"`, OR `force_validation_skip=True` is explicitly passed, OR the article's `status`/`stability` is in `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES`, THE write path SHALL allow the commit and (for active `software` articles under `balanced`/`advisory` or `force_validation_skip=True`) surface the missing `applies_to:` diagnostic as an inline advisory warning.
- **R-3.3**: WHEN `commit_session` or `write_many_articles` rejects one or more articles under `R-3.1`, THE error message SHALL enumerate every offending article path and a concrete `applies_to:` remediation hint in a single atomic response so the caller can resolve all violations in one retry.
- **R-3.4**: WHEN `check_file_health()` (`src/brain79/core/wiki.py`) inspects a written or edited active `software` `architecture/` or `features/` article lacking `applies_to:`, THE health checker SHALL emit an explicit `unanchored_governance_article` warning so `brain79_edit` and `brain79_session_commit` under `balanced`/`advisory`/`force_validation_skip=True` never falsely report `lint OK`.

### Capability 4 — Clean context discovery for documentation-only queries

- **R-4.1**: WHEN `brain79_orient(task=...)` is invoked with a non-empty `task` and no `paths`, THE 3-signal context ranker (`src/brain79/core/context.py` and `src/brain79/core/orient.py`) SHALL:
  1. Exclude `INDEX.md` and `SCHEMA.md` **before** `top_n` truncation so navigation/schema files never steal inline article slots.
  2. Exclude `INACTIVE_STATUSES` (`superseded`, `deprecated`, `archived`, `rejected`) from the unread-active-articles reminder and prefer active articles over inactive articles for inline slots when active matches exist.
  3. Inline up to `max_articles` top-ranked active articles within `MAX_ORIENT_INLINE_CHARS` and append a bounded reminder of remaining unread active article paths fetchable via `brain79_read_batch(paths=[...])`, capped at `<= 20` paths (with `(+N more in INDEX.md)` when truncated) to protect `orient_chars` on large wikis.

### Capability 5 — Symmetric package-relative suffix resolution and Phase 16 live re-verification

- **R-5.1**: WHEN `benchmarks/anti_rot/evaluator.py` evaluates a backticked relative file path containing `/` that does not exist directly from repository root (such as `reconciliation/matcher.py`), THE evaluator SHALL test path-segment-bounded suffix matching (`rel == pref or rel.endswith("/" + pref)`) against the arm's non-doc repository files (same exclusion set as `_collect_repo_basenames`):
  - If one or more non-doc files match, THE reference SHALL be counted as valid (not stale).
  - If and only if the match is unique (`len(matches) == 1`), THE evaluator SHALL record the resolved repo-relative path in `valid_paths_in_doc` for Arm B canonical coverage.
  - If zero files match (e.g., `reconciliation/legacy.py` or `reconcile.py`), THE reference SHALL be counted as stale.
- **R-5.2**: WHEN `scripts/run_anti_rot_benchmark.py --mode live` is re-executed after `R-1.1` through `R-5.1` are implemented, THE benchmark harness SHALL verify that Arm A achieves `PASS` (exit code `0`) across all 7 mandatory `SPEC-016` release-gate criteria on `gemini-4-hydrogen-low`.

## Interface and error contract

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `brain79_read_batch(paths=[...])` | List of relative wiki paths (with or without `.brain-79/` prefix) | Normalize prefixes, deduplicate preserving order, return formatted markdown | Return markdown string |
| `brain79_read_batch(requests=[...], paths=[...])` | Empty input or invalid item type (e.g., `int`, dict without `"path"`) | Return actionable error with exact `paths` and `requests` syntax examples | Return `"Error: ..."` string (MCP safe) |
| `brain79 read-batch --paths a.md b.md` | Missing paths/file/stdin or invalid JSON payload | Emit actionable error to stderr; make zero disk mutations | Exit `2` (invalid arg) / Exit `1` (parse error) |
| `brain79 bootstrap` (`software` vs `general`) | `auto_map=None` (default) vs `--no-auto-map` / `auto_map=False` | Resolve `None -> (profile == "software")`; empty repo degrades gracefully | Exit `0` |
| `commit_session` / `write_article` / `write_many_articles` (`software`, `strict`) | Active `architecture/` or `features/` article lacks `applies_to:` | Fail pre-flight atomically; modify zero files; list all offending paths | `ValidationError(rule="unanchored_governance_article")` / Exit `1` |
| `commit_session` / `write_article` (`balanced`/`advisory`/`general`/`planned`/`superseded` or `force_validation_skip=True`) | Article lacks `applies_to:` | Commit atomically; append `unanchored_governance_article` warning via `check_file_health()` for active `software` articles | Return receipt with warning / Exit `0` |

## Migration and rollout

- **Default behavior**:
  - `brain79_read_batch` and `brain79 read-batch` remain 100% backward-compatible with `requests=[{"path": "...", "sections": [...]}]` and `--file`/`--stdin`.
  - Existing repositories using `enforcement: balanced` or `enforcement: advisory`, or `profile: general`, or pre-implementation (`planned`/`draft`/`proposed`) and inactive (`superseded`/`deprecated`/`archived`/`legacy`/`rejected`) articles experience zero blocking changes.
  - Existing repositories using `enforcement: strict` under `profile: software` that already pass `brain79 lint --strict` experience zero blocking changes; writes that would break `lint --strict` now fail fast at commit time with actionable remediation.
- **Intentional test-fixture updates (disclosed upfront)**:
  - `tests/test_symmetry.py` (`auto_map` default assertion updated from `False` to `None` across `run_bootstrap` and `brain79_bootstrap`).
  - Existing strict-mode test fixtures that intentionally write `status: shipped` or `stability: stable` `architecture`/`feature` articles without `applies_to:` (such as `tests/test_phase3_session_execution.py` and `tests/test_phase3_adversarial.py`, plus any direct `write_article` tests under `strict`) MUST be updated to either supply `applies_to:` or configure `advisory` / `planned` explicitly.
- **Upgrade path**: existing repositories can run `brain79 update-project` to refresh `AGENTS.md`, `SCHEMA.md`, and `SKILL.md` guidance text; no destructive migration or schema version bump is required.
- **Rollback safety**: 100% safe; `.brain-79/` on-disk layout and frontmatter format are unchanged.

## Acceptance criteria (Given / When / Then)

### AC-1 — Profile-aware `auto_map` default, disjoint bootstrap examples, and template guidance
- **Verifies**: `R-1.1`, `R-1.2`, `R-1.4`, `R-1.5`
- **Method**: `test`
- **Test ref**: `tests/test_phase17_bootstrap_orient_templates.py`
- **Given**: repositories initialized with `brain79 init --profile software` (containing Python/JS files under `src/`, plus a flat non-`src/` repo and an empty repo) and `brain79 init --profile general`.
- **When**: `brain79_bootstrap()` and CLI `brain79 bootstrap` are called with default arguments (`auto_map=None`), with explicit `auto_map=False` / `--no-auto-map`, and `generate_frontmatter_template()` is called for `architecture` and `feature`.
- **Then**: default `software` bootstrap resolves `auto_map=True`, emits disjoint partitioning guidance (`overview.md` umbrella `.brain-79/features/*.md` / `README.md`, `stack.md` manifest files, `auto_map` source modules) with zero hardcoded `src/**` failures on flat/empty repos and sentence-case `summary:`; `general` profile and `--no-auto-map` skip `auto_map`; `generate_frontmatter_template()`, `templates/SCHEMA.md`, and `templates/AGENTS.md` include `applies_to:` and concise public-signature/constants guidance without re-introducing pruned MCP tool names.

### AC-2 — `brain79_orient` schema parity, slot-stealing fix, and bounded unread-article reminder
- **Verifies**: `R-1.3`, `R-2.4`, `R-4.1`
- **Method**: `test`
- **Test ref**: `tests/test_phase17_bootstrap_orient_templates.py`
- **Given**: a `software` wiki configured with `enforcement: strict` containing `INDEX.md`, `SCHEMA.md`, 6 active articles, 1 `superseded` article, and a second large-wiki fixture with 25 active articles.
- **When**: `brain79_orient(task="review pricing and late fee rules")` is called without `paths`.
- **Then**: `Active Schema Summary` marks `applies_to` as strict-required for `architecture/` and `features/`; `INDEX.md` and `SCHEMA.md` do not steal `top_n` inline slots; active articles are inlined over the `superseded` article within `MAX_ORIENT_INLINE_CHARS`; the output appends a `brain79_read_batch(paths=[...])` reminder excluding `INACTIVE_STATUSES` and capped at `<= 20` paths with `(+N more in INDEX.md)` on the 25-article wiki.

### AC-3 — `brain79_read_batch` MCP and CLI normalization, wire-schema check, and error handling
- **Verifies**: `R-2.1`, `R-2.2`, `R-2.3`, `R-2.5`
- **Method**: `test`
- **Test ref**: `tests/test_phase17_read_batch_parity.py`
- **Given**: a wiki with 3 articles, the FastMCP server (`mcp.list_tools()`), and CLI `brain79 read-batch`.
- **When**: invoked via `brain79_read_batch(paths=[...])`, `brain79_read_batch(requests=["a.md", {"path": "b.md", "sections": ["Overview"]}])`, nested `args={"paths": [...]}`, overlapping `paths` + `requests`, empty/malformed inputs (`[123]`, `[{}]`), and CLI `brain79 read-batch --paths a.md b.md` + `--stdin` string array.
- **Then**: valid calls return deterministic deduplicated markdown in both MCP and CLI; invalid or empty calls return an actionable usage error without unhandled exceptions; `await mcp.list_tools()` confirms `brain79_read_batch` exposes a flat schema free of nested `anyOf` inside `array.items`; `MCP_TOOLS` remains 9 and CLI `WHITELIST` remains 26.

### AC-4 — Strict-mode `unanchored_governance_article` pre-flight parity and `check_file_health`
- **Verifies**: `R-3.1`, `R-3.2`, `R-3.3`, `R-3.4`
- **Method**: `test`
- **Test ref**: `tests/test_phase17_strict_preflight_parity.py`
- **Given**: test wikis under `software` (`strict`, `balanced`, `advisory`) and `general` (`strict`).
- **When**: `commit_session`, `write_article` / `brain79_edit`, and `write_many_articles` attempt to commit active `architecture/` and `features/` articles lacking `applies_to:`, as well as `status: planned` / `status: superseded` / `stability: deprecated` articles and `force_validation_skip=True` writes.
- **Then**: under `software` + `strict`, active unanchored writes fail atomically with `ValidationError(rule="unanchored_governance_article")`, zero disk mutations, and all offending paths listed in one response; `planned`/`superseded`/`deprecated`, `general` profile, `balanced`/`advisory`, and `force_validation_skip=True` succeed, with `check_file_health()` emitting an explicit `unanchored_governance_article` warning (never false `lint OK`) for active `software` articles lacking `applies_to:`.

### AC-5 — Segment-bounded suffix matching and unique Arm B canonical coverage in Phase 16 evaluator
- **Verifies**: `R-5.1`
- **Method**: `test`
- **Test ref**: `tests/test_phase17_evaluator_suffix_matching.py`
- **Given**: a synthetic workspace containing `src/ledgerpulse/reconciliation/matcher.py`, `src/a/utils/helpers.py`, and `src/b/utils/helpers.py`, with active docs referencing `reconciliation/matcher.py`, `old_reconciliation/matcher.py`, `utils/helpers.py`, `reconciliation/legacy.py`, and `reconcile.py`.
- **When**: `evaluate_arm()` runs.
- **Then**: `reconciliation/matcher.py` is valid AND credited to `valid_paths_in_doc` (`len(matches) == 1`); `utils/helpers.py` is not stale but is NOT credited to canonical coverage (`len(matches) == 2`, ambiguous); `old_reconciliation/matcher.py`, `reconciliation/legacy.py`, and `reconcile.py` are all flagged as stale.

### AC-6 — Live Phase 16 anti-rot release gate re-verification (`PASS`)
- **Verifies**: `R-5.2`
- **Method**: `demo`
- **Test ref**: `/tmp/phase16-live-reverify-v3-reeval/results.json` (`Verdict: PASS`, 7/7 on `gemini-4-hydrogen-low`)
- **Given**: `agy` configured with `gemini-4-hydrogen-low`, zero global `brain79` MCP registration, and the updated `brain79[polyglot]` installed.
- **When**: `uv run python scripts/run_anti_rot_benchmark.py --mode live --output-dir /tmp/phase16-live-reverify` executes.
- **Then**: the CLI exits with code `0`, `results.json` records `verdict: "PASS"` across all 7 mandatory `SPEC-016` criteria, and results are distilled into `.brain-79/topics/phase-16-anti-rot-benchmark-results.md`.

## Wiki impact map

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/server.py`, `src/brain79/core/wiki.py` | `architecture/mcp-server.md` | `update` |
| `src/brain79/server.py`, `src/brain79/templates/SKILL.md` | `features/mcp-server.md` | `update` |
| `src/brain79/cli/dispatch.py` | `architecture/dispatcher.md` | `update` |
| `src/brain79/cli/dispatch.py`, `src/brain79/server.py` | `architecture/symmetry.md` | `update` |
| `src/brain79/core/bootstrap.py`, `src/brain79/core/orient.py`, `src/brain79/core/context.py` | `features/team-collaboration-and-onboarding.md` | `update` |
| `src/brain79/core/session_commit.py`, `src/brain79/core/frontmatter.py`, `src/brain79/templates/SCHEMA.md`, `src/brain79/templates/AGENTS.md` | `features/organizational-enforcement.md` | `update` |
| `benchmarks/anti_rot/evaluator.py` | `topics/phase-16-anti-rot-benchmark-results.md` | `update` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
uv run pytest
uv run mypy src tests benchmarks/anti_rot scripts/run_anti_rot_benchmark.py
uv run brain79 lint --strict
uv run brain79 ci-check --enforcement strict
uv run brain79 doctor
```

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| — | — | No amendments recorded yet. | — |

## Wiki distillation checklist (post-implementation)

- [x] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [x] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [x] Record any new architectural decision in `.brain-79/decisions/adr-XXX.md` (if applicable).
- [x] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-17-0.md`.
- [x] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [x] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
