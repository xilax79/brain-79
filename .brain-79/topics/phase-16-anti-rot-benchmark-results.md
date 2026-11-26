---
type: topic
summary: phase 16 longitudinal anti-rot benchmark harness, LedgerPulse testbed, deterministic evaluator, blind recall probe, and pending AC-6 UAT runbook
status: active
applies_to:
  - benchmarks/anti_rot/*.py
  - benchmarks/anti_rot/control_agents.md
  - scripts/run_anti_rot_benchmark.py
related:
  - architecture/roadmap-industrial-scale.md
  - features/polyglot-ast-guards-and-stats.md
  - features/lifecycle-hooks-and-ci-gate.md
  - features/session-triage-and-research-persistence.md
last_updated: 2026-11-26
---

# Phase 16 — Longitudinal anti-rot benchmark harness and release gate

## Live benchmark status: PENDING UAT EXECUTION (`AC-6`)

The Phase 16 evaluation harness (`benchmarks/anti_rot/` and `scripts/run_anti_rot_benchmark.py`) is implemented and verified offline across unit, dry-run, and static type checks. Live 12-session `agy` execution against `gemini-4-hydrogen-low` (`AC-6`) has **not** been executed yet and remains pending user UAT. Phase 17 (PyPI release) stays blocked until live UAT produces a `PASS` verdict.

### UAT runbook (`AC-6`)

1. Remove any global `brain79` MCP registration so Arm B remains strictly isolated:
   ```bash
   agy mcp remove brain79
   ```
2. Execute the live 12-session dual-arm benchmark and blind recall probe:
   ```bash
   uv run python scripts/run_anti_rot_benchmark.py --mode live --output-dir /tmp/phase16-live-run
   ```
3. Inspect `/tmp/phase16-live-run/results.json`, `/tmp/phase16-live-run/report.md`, and `/tmp/phase16-live-run/recall_results.json`.

---

## Harness architecture

The benchmark suite lives under `benchmarks/anti_rot/` and is orchestrated by `scripts/run_anti_rot_benchmark.py` (`--mode dry-run|live|evaluate`, POSIX exit codes `0`, `1`, `2`, `3`, `130`):

- **`workspace.py`**: clones the `LedgerPulse` fixture into two isolated temporary Git repositories (`arm_a` and `arm_b`) from an identical `commit 0`, configures Arm A via `brain79 init --profile software --harnesses agents,agy,agy_hooks --no-git-hooks` with `strict` enforcement, installs `control_agents.md` (`AGENTS.md` + `docs/`) in Arm B, and runs fail-closed pre-flight probes (`agy --output-format stream-json` tool inventory verifying zero `brain79*` tools in Arm B and active lifecycle hooks in Arm A).
- **`scenarios.py` and `runner.py`**: defines the 12-session sequence (`S1`–`S12`) with byte-identical functional prompts, executes cold-start `agy` sessions (`gemini-4-hydrogen-low`, `--effort low`), commits cleanly between sessions (`git add -A && git commit`), collects `stream-json` token/tool telemetry, runs fixture unit + hidden contract tests, and records Arm A `brain79 stats --format json` and `brain79 ci-check --format json --enforcement strict` snapshots into JSONL.
- **`evaluator.py`**: computes active-doc rot rate (excluding superseded/archived/changelog docs, paired with minimum reference-density checks), canonical `src/**` governance coverage, `orient_chars` and doc-read token footprint, `S9` (Type A) / `S10` (Type B) triage compliance, and autonomous completion rate.
- **`recall.py` and `deny_src_reads.py`**: executes blind semantic-recall probes using a temporary `.agents/hooks.json` `PreToolUse` hook that denies `src/` reads while keeping `src/` intact on disk, requests structured `--json-schema` responses (`RECALL_JSON_SCHEMA`), verifies zero `src/` reads in `stream-json`, and scores 24 atomic factual assertions (including negative checks against superseded `S4` rules).
- **`gate.py`**: evaluates the 7 mandatory release gate criteria and writes `results.json` and `report.md`.

---

## LedgerPulse polyglot testbed and 12-session protocol

`benchmarks/anti_rot/fixture/` implements `LedgerPulse` with zero external runtime dependencies:

- **Canonical sources (13 files)**: 9 Python modules under `src/ledgerpulse/` and 4 JavaScript modules under `src/reporter/`, verified by `pytest` (`tests/test_ledgerpulse.py`), `node --test` (`tests/reporter.test.mjs`), and Tree-sitter AST Guard C.
- **Hidden contracts (`benchmarks/anti_rot/contracts/`)**: pinned per-session tests (`S2`–`S12`) locking public paths, exported signatures, and business constants so Arm A and Arm B cannot diverge silently.
- **Session progression (`S1`–`S12`)**:
  - `S1`: initial repository documentation bootstrap.
  - `S2`–`S3`: feature additions touching shared modules.
  - `S4`: critical late-fee bugfix plus architectural decision.
  - `S5`–`S6`: public API refactors across Python and `.mjs` exercising Merkle drift and AST Guard C.
  - `S7`: business-rule change superseding the `S4` decision.
  - `S8`: polyglot export feature spanning Python and JavaScript.
  - `S9`: read-only Type A consultation (zero permanent doc churn).
  - `S10`: zero-code Type B research on multi-currency rounding drift (zero `src/` mutations, persisted research doc).
  - `S11`: structural module move (`reconcile.py` to `reconciliation/matcher.py`) exercising `applies_to` and broken-reference checks.
  - `S12`: final multi-module validation feature and pre-audit freeze.

---

## Release gate criteria (`gate.py`)

`evaluate_release_gate()` emits `PASS` only when all 7 criteria hold simultaneously:

| Criterion | Threshold |
|---|---|
| Structural and drift health (Arm A) | `brain79 lint --strict` errors `== 0`, `ci-check --enforcement strict` exit `== 0`, `drifted_articles == 0` |
| Documentation rot rate | Minimum reference density met, `rot_A <= 5%`, and `rot_A <= 0.5 * rot_B` (if `rot_B > 5%`) or `rot_A <= rot_B` |
| Canonical governance coverage | `cov_A >= 85%` of `src/**` and `cov_A >= cov_B` |
| Context budget ceiling | `orient_chars <= 64,000` (`MAX_ORIENT_INLINE_CHARS`) |
| Autonomous compliance | `>= 10/12` (`83.3%`) clean completions (max 1 retry strictly on transient API/network errors) |
| Blind semantic recall | Zero `src/` reads, `acc_A >= 80%`, and `acc_A >= acc_B + 15pp` (if `acc_B <= 80%`) or `acc_A >= acc_B` |
| Session triage discipline | Arm A passes both `S9` (zero permanent doc churn) and `S10` (zero `src/` edits + persisted research) |

---

## Offline dry-run verification summary

- **Offline test coverage**: `tests/test_phase16_fixture_and_isolation.py`, `tests/test_phase16_runner.py`, and `tests/test_phase16_evaluator_and_gate.py` verify fixture integrity, Arm B isolation probes, 12-session `--mode dry-run` execution with simulated timeout logging, rot/coverage/triage scoring, 24-assertion recall scoring with `.agents/hooks.json` cleanup, and `--mode evaluate` report reproduction.
- **Type safety**: `uv run mypy src tests benchmarks/anti_rot scripts/run_anti_rot_benchmark.py` verifies strict typing across the harness and tests.

---

[← Back to Index](../INDEX.md)
