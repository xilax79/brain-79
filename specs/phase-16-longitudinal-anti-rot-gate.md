---
spec_id: SPEC-016
title: Longitudinal anti-rot release gate
target_version: 0.17.0
status: in_progress
owner: xilax
last_updated: 2026-11-26
related_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/polyglot-ast-guards-and-stats.md
  - features/lifecycle-hooks-and-ci-gate.md
  - features/session-triage-and-research-persistence.md
target_wiki:
  - topics/phase-16-anti-rot-benchmark-results.md
  - architecture/roadmap-industrial-scale.md
  - changelog/v0-17-0.md
---

# SPEC-016 — Longitudinal anti-rot release gate

## Problem statement and goal

Before publishing `brain79` to PyPI (Phase 17), the project needs empirical, reproducible proof that `.brain-79/` wikis resist documentation rot across long multi-session LLM development runs and outperform an unmanaged `AGENTS.md` + Markdown baseline. Existing unit, chaos, and single-turn smoke tests validate mechanical correctness in isolation, but do not measure longitudinal durability, real-LLM protocol compliance under low-cost models (`hydrogen low` via `agy`), or blind semantic recall accuracy after 12 independent cold-start sessions.

The goal of this specification is to deliver a self-contained, reproducible longitudinal anti-rot evaluation harness, a polyglot testbed fixture (`LedgerPulse`) with per-session contract tests, deterministic metric collectors, a mechanically enforced blind semantic-recall probe, and an objective `PASS`/`FAIL` release gate report.

## Non-goals (out of scope)

- **Core engine feature expansion**: this specification MUST NOT add new MCP tools (`MCP_TOOLS` remains 9), new CLI subcommands (`WHITELIST` remains 26), or new runtime dependencies to `pyproject.toml`.
- **PyPI publication**: publishing to PyPI via Trusted Publishers is deferred to Phase 17 (`SPEC-017`) and gated on this phase passing.
- **Multi-provider / multi-harness matrix**: Phase 16 executes on Antigravity (`agy`) with `hydrogen low` as the primary cost-constrained harness; comparing Claude Code, Cursor, or frontier models is out of scope.
- **Strawman `CLAUDE.md` control arm**: using `CLAUDE.md` under `agy` is explicitly prohibited because `agy` loads `AGENTS.md` natively; the control arm MUST use a realistic, versioned `AGENTS.md` + `docs/` workflow with parity on read-only (Type A) and research-persistence (Type B) discipline.
- **Running live LLM calls in standard CI (`uv run pytest`)**: the benchmark harness runs on-demand locally; unit tests in `tests/` MUST mock/stub LLM invocations and stay 100% deterministic and offline.

## Dependencies

- **Internal seams**:
  - `brain79 --project-root <dir> stats --format json` (shipped in Phase 15, `v0.16.0`) for deterministic token budget, `orient_chars`, and whole-repo telemetry.
  - `brain79 --project-root <dir> ci-check --format json --enforcement strict` and `brain79 --project-root <dir> lint --strict` (shipped in Phase 14, `v0.15.0`) for structural health, drift count (`drifted_articles == 0`), and organizational lint verification.
  - `brain79 init --profile software --harnesses agents,agy,agy_hooks --no-git-hooks` (shipped in Phase 14) for clean native `agy` plugin and `SessionStart`/`Stop` hook setup without cluttering the workspace with unused harnesses or blocking harness inter-session commits.
  - `brain79[polyglot]` Tree-sitter AST Guard C (shipped in Phase 15) for Python + TypeScript/JavaScript signature verification.
- **External / runtime (benchmark execution only)**:
  - `agy` CLI installed and authenticated locally, supporting non-interactive cold-start execution (`--model`, `--effort low`, `--output-format stream-json`, `--json-schema`, `--print-timeout`).
  - Node.js (`node --test`) and `uv` (`pytest`) available locally to run fixture and contract tests.

## Constraints and invariants

All requirements must preserve the repository's canonical invariants:

- **Versioning**: pre-GA minor versioning (`v0.17.0`) per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md).
- **Concurrency and cross-platform I/O**: POSIX paths and LF line endings per [ADR-014](../.brain-79/decisions/adr-014-centralized-locks-and-cross-platform-io.md).
- **CLI and MCP symmetry**: zero changes to `MCP_TOOLS` (9) or `WHITELIST` (26) per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Documentation style**: sentence case and living manual rules per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **Experimental isolation invariant**: Treatment (Arm A) and Control (Arm B) MUST execute in completely isolated temporary directories cloned from the exact same `commit 0`, with zero shared conversation history across the 12 sessions, clean inter-session `git commit` boundaries, and mechanical pre-flight verification proving zero `brain79*` MCP tools or hooks are exposed in Arm B.

## Open questions

All open questions MUST be resolved (`[x]`) before the `owner` transitions this specification from `draft` to `approved`. Agents MUST NOT implement a `draft` specification.

- [x] **Q-1**: Resolved (`xilax`): (a) model ID is `gemini-4-hydrogen-low`, (b) Arm B isolation relies on project-local plugin scoping (`.agents/plugins/brain79/` in Arm A only; `brain79` removed from global `~/.gemini/config/mcp_config.json` via `agy mcp remove brain79`) enforced by the fail-closed pre-flight `agy --output-format stream-json` tool-inventory probe verifying 0 `brain79*` tools in Arm B, and (c) `agy -p` lifecycle hook execution is verified during pre-flight in Arm A.
- [x] **Q-2**: Resolved (`xilax`): Arm A runs with `.brain-79/SCHEMA.md` enforcement set to `strict` during the 12-session `gemini-4-hydrogen-low` run.
- [x] **Q-3**: Resolved (`xilax`): autonomous completion threshold is `>= 10/12` (`83.3%`), initial run is `N = 1` trial, and max `1` automatic retry is permitted strictly on transient API/network errors (0 retries on task/logic failures).

## Requirements (EARS)

### Capability 1 — Self-contained polyglot testbed fixture (`LedgerPulse`) and contract parity

- **R-1.1**: THE benchmark suite SHALL provide a versioned, self-contained polyglot fixture (`benchmarks/anti_rot/fixture/`) implementing `LedgerPulse` (a Python accounting/invoicing core plus a TypeScript/JavaScript report validator/CLI, 12–15 non-test source files under `src/`, zero external network dependencies, deterministic `pytest` + `node --test` unit suites, and hidden per-session contract tests for `S2`–`S12` that pin exact public file paths, exported symbol names/signatures, and business-rule constants to prevent Arm A / Arm B codebase divergence).
- **R-1.2**: WHEN the harness initializes an experimental run, THE workspace initializer SHALL create two isolated temporary Git repositories (Arm A: Treatment, Arm B: Control) from the exact same initial `commit 0` of the fixture.
- **R-1.3**: WHEN initializing Arm A (Treatment), THE workspace initializer SHALL configure `brain79 init --profile software --harnesses agents,agy,agy_hooks --no-git-hooks` so native `agy` MCP tools and `SessionStart`/`Stop` hooks are active without polluting the workspace with unused harnesses or blocking inter-session harness commits.
- **R-1.4**: WHEN initializing Arm B (Control), THE workspace initializer SHALL install a versioned, non-strawman `AGENTS.md` (stored in `benchmarks/anti_rot/control_agents.md`) instructing the agent to maintain `docs/` accurately after every task—with explicit parity on read-only consultation (Type A) and zero-code research persistence (Type B)—and SHALL execute a pre-flight `agy --output-format stream-json` tool-inventory probe verifying that zero `brain79*` MCP tools, `.brain-79/` directories, or `brain79` hooks are present or reachable in Arm B.

### Capability 2 — Longitudinal 12-session cold-start execution harness

- **R-2.1**: THE harness (`scripts/run_anti_rot_benchmark.py`) SHALL support `--mode dry-run|live|evaluate` and SHALL execute a deterministic sequence of 12 independent cold-start sessions (`S1`–`S12`) against both Arm A and Arm B using `agy` pinned to `hydrogen low`, starting each session with zero prior conversation history and committing the workspace state cleanly (`git add -A && git commit`) after each session so Guard C, `orient()` Signal 1, ripple checks, and `S9` diffs operate on clean commit boundaries.
- **R-2.2**: THE 12-session scenario script SHALL cover:
  - `S1`: initial documentation bootstrap of the base repository;
  - `S2`–`S3`: two feature additions touching shared modules;
  - `S4`: critical bugfix plus an architectural decision (ADR);
  - `S5`–`S6`: refactoring that renames/alters pinned public API signatures (exercising Merkle drift and AST Guard C);
  - `S7`: business-rule change that supersedes the `S4` decision;
  - `S8`: polyglot feature spanning Python and TypeScript/JavaScript;
  - `S9`: read-only consultation (Type A — must produce zero permanent documentation churn);
  - `S10`: zero-code domain research/analysis (Type B — must produce zero source mutations and persist a non-empty research document);
  - `S11`: structural module move/rename (exercising `applies_to` and broken-reference detection);
  - `S12`: final multi-module feature and pre-audit freeze.
- **R-2.3**: THE harness SHALL deliver byte-identical functional task prompts (including pinned public paths/signatures/constants) to Arm A and Arm B for every session `S1`–`S12`, without mentioning `brain79` or `docs/` in the task prompt itself.
- **R-2.4**: WHEN each session completes, THE harness SHALL record a per-session telemetry snapshot into a structured JSONL log containing: exit status, wall-clock duration, git diff stats, fixture unit + per-session contract test pass/fail, `stream-json` token/tool-call usage, and for Arm A: `brain79 --project-root <dir> stats --format json` and `brain79 --project-root <dir> ci-check --format json --enforcement strict` output.
- **R-2.5**: IF a session fails due to an unrecoverable CLI error, contract test failure, or timeout, THEN THE harness SHALL record the failure explicitly in the JSONL log, preserve workspace state for forensic inspection, and SHALL NOT silently fabricate or skip the session.

### Capability 3 — Deterministic anti-rot and context-efficiency evaluator

- **R-3.1**: WHEN `S12` completes (or in `--mode evaluate`), THE evaluator SHALL compute deterministic metrics for both arms against each arm's verified final source code AST and filesystem:
  - **Structural and drift health (Arm A)**: `brain79 lint --strict` error count AND `brain79 ci-check --enforcement strict` exit code and `drifted_articles` count.
  - **Documentation rot rate (Arm A & Arm B)**: deterministic extraction of backticked file paths and Python `ast` / Tree-sitter TS/JS public symbol references across **active living documentation only** (excluding superseded/deprecated/archived articles, `changelog/`, `handoffs/`, `_raw/`), computing the percentage of references that are missing, renamed, or contradicted by final code, paired with a minimum reference-density check (preventing empty-doc 0% rot gaming).
  - **Governance coverage (Arm A & Arm B)**: percentage of canonical non-test source files (`src/**`) covered by up-to-date active documentation (requiring zero drift on governing articles in Arm A, and valid active file references in Arm B; `brain79 stats` whole-repo coverage is logged as supplementary telemetry).
  - **Context budget efficiency (Arm A & Arm B)**: Arm A's `orient_chars` (`<= 64,000` chars `MAX_ORIENT_INLINE_CHARS` ceiling via `brain79 stats --format json`) plus per-session documentation-read token footprint extracted from `stream-json` logs for both arms across `S1`–`S12`.
  - **Session triage discipline (Arm A & Arm B)**: `S9` (Type A) produces zero mutations to permanent documentation articles and `INDEX.md`; `S10` (Type B) produces zero `src/` mutations and persists a non-empty research document.
  - **Autonomous compliance rate (Arm A & Arm B)**: fraction of `S1`–`S12` sessions satisfying the clean-completion predicate (exit code `0`, fixture unit tests pass, per-session contract tests pass, zero manual intervention).

### Capability 4 — Mechanically enforced blind semantic-recall probe

- **R-4.1**: WHEN `S12` completes, THE evaluator SHALL run a blind semantic-recall probe consisting of 8–10 predefined technical and architectural questions (covering cross-module impact, superseded `S4`/`S7` decisions, renamed `S5`/`S6` signatures, `S10` research findings, and `S11` moved modules) using fresh cold-start `hydrogen low` sessions where read access to `src/` is mechanically blocked via an `agy` `PreToolUse` deny-hook (keeping `src/` intact on disk so `brain79` emits zero fake missing-file drift) and verified via `stream-json` zero-source-read assertions.
- **R-4.2**: THE evaluator SHALL request structured answers via `agy --json-schema` and score at least 20 atomic factual assertions (including negative checks verifying superseded `S4` rules are not reported as current) using deterministic Python assertion matching against the pinned contract + verified arm state, producing an exact accuracy percentage for Arm A and Arm B.

### Capability 5 — Objective release gate verdict and reproducible report

- **R-5.1**: THE evaluator SHALL compute a binary `PASS` or `FAIL` release gate verdict according to the following mandatory criteria:
  - Arm A `brain79 lint --strict` errors `== 0` AND `brain79 ci-check --enforcement strict` exit code `== 0` (`drifted_articles == 0`);
  - Arm A documentation rot rate `<= 5%` (with minimum reference density met) AND satisfies zero-safe superiority over Arm B (`rot_A <= 0.5 * rot_B` when `rot_B > 5%`, or `rot_A <= rot_B` when `rot_B <= 5%`);
  - Arm A canonical source governance coverage `>= 85%` AND `>=` Arm B's coverage;
  - Arm A `orient_chars` stays within `<= 64,000` chars (`MAX_ORIENT_INLINE_CHARS`);
  - Arm A autonomous compliance rate `>= 10/12` (`83.3%`, max 1 retry strictly on transient API/network errors);
  - Arm A blind semantic-recall accuracy `>= 80%` AND satisfies ceiling-aware superiority over Arm B (`acc_A >= acc_B + 15pp` when `acc_B <= 80%`, or `acc_A >= acc_B` when `acc_B > 80%`);
  - Arm A passes both `S9` (0 permanent doc mutations) and `S10` (0 source mutations + persisted research).
- **R-5.2**: THE harness SHALL emit a machine-readable JSON report (`results.json`) and a human-readable Markdown summary (`report.md`) containing methodology, environment metadata (model, `agy` version, `brain79` version, commit SHA), per-session telemetry, recall scores, and the final `PASS`/`FAIL` verdict.
- **R-5.3**: IF the release gate verdict is `FAIL`, THEN THE report SHALL enumerate every failed criterion and its forensic evidence, and Phase 17 (PyPI release) SHALL remain blocked until remediated and re-verified.

## Interface and error contract

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `scripts/run_anti_rot_benchmark.py --mode dry-run` | Invalid scenario file or missing fixture (`FileNotFoundError`) | Emit actionable error to stderr; create zero temp dirs | Exit `2` |
| `scripts/run_anti_rot_benchmark.py --mode live` | `agy` binary missing or Arm B pre-flight probe detects `brain79*` MCP leakage | Abort before `S1` with explicit isolation error | Exit `1` |
| `scripts/run_anti_rot_benchmark.py --mode evaluate` | Corrupt or incomplete session log JSONL | Report missing/corrupt session indices; refuse to emit `PASS` | Exit `1` |
| Filesystem / subprocess I/O | Permission error, disk full, or OS error (`PermissionError`/`OSError`) | Preserve partial telemetry safely; surface structured error | Exit `3` |
| Operator interrupt | `KeyboardInterrupt` / `SIGINT` during live run | Terminate active child process cleanly; preserve workspace state | Exit `130` |
| Subprocess timeout during `S1`–`S12` | `agy` session exceeds `--print-timeout` | Terminate child process cleanly, log timeout, preserve workspace | Recorded in JSONL; gate `FAIL` if compliance `< 10/12` |

## Migration and rollout

- **Default behavior**: zero changes to `brain79` CLI, MCP server, or `.brain-79/` schema.
- **Upgrade path**: none required for existing repositories.
- **Rollback safety**: 100% safe; all Phase 16 artifacts live under `benchmarks/anti_rot/`, `scripts/`, `tests/`, and `.brain-79/topics/`.

## Acceptance criteria (Given / When / Then)

### AC-1 — Fixture integrity, contract tests, and dual-arm isolation
- **Verifies**: `R-1.1`, `R-1.2`, `R-1.3`, `R-1.4`
- **Method**: `test`
- **Test ref**: `tests/test_phase16_fixture_and_isolation.py`
- **Given**: the `benchmarks/anti_rot/fixture/` directory and `benchmarks/anti_rot/control_agents.md` in a clean checkout.
- **When**: the workspace initializer prepares Arm A and Arm B in temporary directories.
- **Then**: both arms share the exact same `commit 0` SHA, fixture unit tests pass in both arms, Arm A has `.brain-79/` and `agents,agy,agy_hooks` configured without git pre-commit hook interference, and Arm B passes the pre-flight tool-inventory probe with zero `brain79*` MCP tools or `.brain-79/` directories.

### AC-2 — 12-session scenario contract, inter-session commits, and prompt parity
- **Verifies**: `R-2.1`, `R-2.2`, `R-2.3`, `R-2.4`, `R-2.5`
- **Method**: `test`
- **Test ref**: `tests/test_phase16_runner.py`
- **Given**: a mocked `agy` runner and the 12-session scenario definition.
- **When**: the harness runs `S1`–`S12` in `--mode dry-run` with one simulated timeout fault.
- **Then**: both arms receive byte-identical functional prompts, zero conversation IDs are reused across turns, a clean git commit is created after each session, per-session telemetry JSONL (including `stats --format json` and `ci-check --format json`) is written, and the simulated timeout is logged without fabricating a pass.

### AC-3 — Deterministic rot, canonical coverage, context budget, and triage scoring
- **Verifies**: `R-3.1`
- **Method**: `test`
- **Test ref**: `tests/test_phase16_evaluator_and_gate.py::test_evaluator_excludes_superseded_and_scores_rot_and_canonical_coverage, tests/test_phase16_evaluator_and_gate.py::test_evaluator_arm_b_and_triage_failures`
- **Given**: synthetic post-`S12` Arm A and Arm B snapshots with known stale symbols, archived/superseded articles, missing file references, and `S9`/`S10` diffs.
- **When**: the evaluator runs in `--mode evaluate`.
- **Then**: it excludes archived/superseded/changelog docs from rot calculation, computes exact rot rate, canonical `src/**` governance coverage (requiring zero drift in Arm A), `orient_chars` + doc-read token footprint, and `S9`/`S10` triage pass/fail matching ground truth.

### AC-4 — Mechanically enforced blind semantic-recall probe and assertion scoring
- **Verifies**: `R-4.1`, `R-4.2`
- **Method**: `test`
- **Test ref**: `tests/test_phase16_evaluator_and_gate.py::test_recall_probe_assertions_hook_script_and_zero_src_read_check`
- **Given**: predefined recall questions, `>= 20` atomic ground-truth assertions (including negative checks for superseded `S4` rules), and stubbed `--json-schema` recall responses.
- **When**: the recall evaluator scores Arm A and Arm B.
- **Then**: it verifies zero `src/` tool reads via `stream-json` logs and produces deterministic accuracy percentages for both arms.

### AC-5 — Release gate verdict and report generation
- **Verifies**: `R-5.1`, `R-5.2`, `R-5.3`
- **Method**: `test`
- **Test ref**: `tests/test_phase16_evaluator_and_gate.py::test_release_gate_verdict_and_edge_cases, tests/test_phase16_evaluator_and_gate.py::test_cli_dry_run_and_error_exit_codes`
- **Given**: evaluation metrics meeting all thresholds vs. metrics failing individual thresholds (e.g., `ci-check` drift `> 0`, zero-baseline rot edge case, ceiling-aware recall edge case, or compliance `< 10/12`).
- **When**: the gate evaluator renders `results.json` and `report.md`.
- **Then**: it emits `PASS` only when all criteria hold, and `FAIL` with explicit failed-criterion enumeration otherwise.

### AC-6 — Live longitudinal execution on `agy` + `hydrogen low`
- **Verifies**: `R-2.1`, `R-4.1`, `R-5.1`, `R-5.2`
- **Method**: `demo`
- **Test ref**: `scripts/run_anti_rot_benchmark.py --mode live`
- **Given**: local `agy` CLI configured with `hydrogen low` and `brain79[polyglot]` installed.
- **When**: the full 12-session live benchmark + blind recall probe is executed against Arm A and Arm B.
- **Then**: `results.json` and `report.md` are produced, distilled into `.brain-79/topics/phase-16-anti-rot-benchmark-results.md`, and the release gate verdict is recorded.

## Wiki impact map

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `benchmarks/anti_rot/` and `scripts/run_anti_rot_benchmark.py` | `topics/phase-16-anti-rot-benchmark-results.md` | `create` |
| `benchmarks/anti_rot/` (Phase 16 completion & `CLAUDE.md` → `AGENTS.md` wording update) | `architecture/roadmap-industrial-scale.md` | `update` |
| `CHANGELOG.md` | `changelog/v0-17-0.md` | `create` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
uv run pytest
uv run mypy src tests benchmarks/anti_rot scripts/run_anti_rot_benchmark.py
uv run brain79 lint --strict
uv run brain79 doctor
```

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| — | — | No amendments recorded yet. | — |

## Wiki distillation checklist (post-implementation)

- [ ] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [ ] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [ ] Record any new architectural decision in `.brain-79/decisions/adr-XXX.md` (if applicable).
- [ ] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-17-0.md`.
- [ ] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [ ] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
