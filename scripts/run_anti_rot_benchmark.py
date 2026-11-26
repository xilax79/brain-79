"""CLI entrypoint for the Phase 16 longitudinal anti-rot benchmark (SPEC-016)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.anti_rot import CONTROL_AGENTS_PATH, FIXTURE_DIR, resolve_git_bin
from benchmarks.anti_rot.evaluator import evaluate_arm
from benchmarks.anti_rot.gate import evaluate_release_gate, write_gate_reports
from benchmarks.anti_rot.recall import (
    RecallScore,
    run_blind_recall_probe_with_artifacts,
    score_recall_response,
)
from benchmarks.anti_rot.runner import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    SessionRecord,
    TelemetryError,
    create_dry_run_runner,
    load_session_records,
    run_benchmark_sessions,
)
from benchmarks.anti_rot.scenarios import SCENARIOS
from benchmarks.anti_rot.workspace import (
    FixtureError,
    IsolationError,
    initialize_arms,
    run_preflight_checks,
)

GATE_FAIL_EXIT_CODE: int = 4


def _dry_run_recall_payload() -> dict[str, Any]:
    return {
        "s2_bulk_discount": {
            "module_path": "src/ledgerpulse/pricing.py",
            "function_name": "calculate_bulk_discount",
            "threshold": 10,
            "discount_bps": 500,
        },
        "s3_void_invoice": {
            "module_path": "src/ledgerpulse/ledger.py",
            "class_name": "Ledger",
            "method_name": "void_invoice",
            "max_reason_len": 200,
        },
        "s4_s7_late_fee_current": {
            "module_path": "src/ledgerpulse/tax.py",
            "function_name": "calculate_late_fee",
            "params": ["amount_cents", "days_overdue", "compound"],
            "late_fee_bps": 500,
            "grace_days": 7,
        },
        "s5_pricing_refactor": {
            "module_path": "src/ledgerpulse/pricing.py",
            "current_function_name": "calculate_invoice_grand_total",
            "params": ["invoice", "include_tax"],
            "include_tax_default": True,
        },
        "s6_js_validator": {
            "schema_module_path": "src/reporter/schema.mjs",
            "index_module_path": "src/reporter/index.mjs",
            "function_name": "validateSummaryDocument",
            "params": ["payload", "options"],
        },
        "s8_polyglot_export": {
            "python_module_path": "src/ledgerpulse/export.py",
            "python_function_name": "export_audit_bundle",
            "schema_version": "2.0",
            "js_module_path": "src/reporter/formatter.mjs",
            "js_function_name": "formatAuditBanner",
        },
        "s10_rounding_research": {
            "topic": "multi-currency rounding drift",
            "currencies": ["USD", "EUR", "GBP"],
            "rounding_strategy": "round_half_even",
        },
        "s11_reconciliation_move": {
            "current_module_path": "src/ledgerpulse/reconciliation/matcher.py",
            "function_name": "reconcile_payments",
            "report_class_name": "ReconciliationReport",
        },
        "s12_audit_freeze": {
            "python_module_path": "src/ledgerpulse/validation.py",
            "python_function_name": "verify_audit_readiness",
            "audit_freeze_tag": "v1-audit-ready",
            "js_module_path": "src/reporter/cli.mjs",
            "js_function_name": "verifyBundleCli",
        },
    }


def _collect_env_metadata(model: str) -> dict[str, Any]:
    agy_ver = "dry-run"
    if shutil.which("agy"):
        proc = subprocess.run(["agy", "--version"], capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            agy_ver = proc.stdout.strip().splitlines()[0]

    b79_proc = subprocess.run(
        [sys.executable, "-m", "brain79", "--version"],
        capture_output=True,
        text=True,
    )
    b79_ver = b79_proc.stdout.strip() if b79_proc.returncode == 0 else "unknown"

    git_proc = subprocess.run(
        [resolve_git_bin(), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    git_sha = git_proc.stdout.strip() if git_proc.returncode == 0 else "unknown"
    return {
        "model": model,
        "agy_version": agy_ver,
        "brain79_version": b79_ver,
        "git_sha": git_sha,
    }


def _validate_session_completeness(records: list[SessionRecord]) -> None:
    expected_ids = [s.session_id for s in SCENARIOS]
    missing: list[str] = []
    for arm in ("arm_a", "arm_b"):
        present = {r.session_id for r in records if r.arm == arm}
        for sid in expected_ids:
            if sid not in present:
                missing.append(f"{arm}:{sid}")
    if missing:
        raise TelemetryError(f"Incomplete session log; missing session indices: {missing}")


def run_dry_run_mode(args: argparse.Namespace) -> int:
    fixture_dir = Path(args.fixture_dir)
    control_agents = Path(args.control_agents)
    if not fixture_dir.is_dir():
        raise FixtureError(f"Fixture directory does not exist: {fixture_dir}")
    if not control_agents.is_file():
        raise FixtureError(f"Control AGENTS.md baseline does not exist: {control_agents}")

    output_dir = Path(args.output_dir)
    workspace_base = output_dir / "workspace"
    ws = initialize_arms(
        workspace_base,
        fixture_dir=fixture_dir,
        control_agents_path=control_agents,
    )
    runner = create_dry_run_runner()
    records = run_benchmark_sessions(
        ws,
        output_dir,
        agy_runner=runner,
        model=args.model,
        effort=args.effort,
        timeout_seconds=args.print_timeout,
    )
    eval_a = evaluate_arm("arm_a", ws.arm_a, records)
    eval_b = evaluate_arm("arm_b", ws.arm_b, records)
    clean_stream = json.dumps(
        {"type": "tool_use", "name": "read_file", "input": {"path": ".brain-79/INDEX.md"}}
    )
    payload_a = _dry_run_recall_payload()
    payload_b: dict[str, Any] = {}
    (output_dir / "recall_results.json").write_text(
        json.dumps(
            {
                "arm_a": {"response": payload_a, "stream_stdout": clean_stream},
                "arm_b": {"response": payload_b, "stream_stdout": clean_stream},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    recall_a = score_recall_response(payload_a, stream_stdout=clean_stream)
    recall_b = score_recall_response(payload_b, stream_stdout=clean_stream)
    verdict = evaluate_release_gate(eval_a, eval_b, recall_a, recall_b)
    write_gate_reports(
        output_dir,
        verdict,
        records=records,
        metadata=_collect_env_metadata(args.model),
    )
    print(f"Verdict: {verdict.verdict} (failed: {', '.join(verdict.failed_criteria) or 'none'})")
    return 0


def run_live_mode(args: argparse.Namespace) -> int:
    if shutil.which("agy") is None:
        raise IsolationError("agy CLI binary not found on PATH")
    fixture_dir = Path(args.fixture_dir)
    control_agents = Path(args.control_agents)
    if not fixture_dir.is_dir():
        raise FixtureError(f"Fixture directory does not exist: {fixture_dir}")
    if not control_agents.is_file():
        raise FixtureError(f"Control AGENTS.md baseline does not exist: {control_agents}")

    output_dir = Path(args.output_dir)
    ws = initialize_arms(
        output_dir / "workspace",
        fixture_dir=fixture_dir,
        control_agents_path=control_agents,
    )
    run_preflight_checks(ws, model=args.model, effort=args.effort)
    records = run_benchmark_sessions(
        ws,
        output_dir,
        model=args.model,
        effort=args.effort,
        timeout_seconds=args.print_timeout,
    )
    eval_a = evaluate_arm("arm_a", ws.arm_a, records)
    eval_b = evaluate_arm("arm_b", ws.arm_b, records)
    recall_a, payload_a, stream_a = run_blind_recall_probe_with_artifacts(
        ws.arm_a, model=args.model, effort=args.effort
    )
    recall_b, payload_b, stream_b = run_blind_recall_probe_with_artifacts(
        ws.arm_b, model=args.model, effort=args.effort
    )
    (output_dir / "recall_results.json").write_text(
        json.dumps(
            {
                "arm_a": {"response": payload_a, "stream_stdout": stream_a},
                "arm_b": {"response": payload_b, "stream_stdout": stream_b},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    verdict = evaluate_release_gate(eval_a, eval_b, recall_a, recall_b)
    write_gate_reports(
        output_dir,
        verdict,
        records=records,
        metadata=_collect_env_metadata(args.model),
    )
    print(f"Verdict: {verdict.verdict} (failed: {', '.join(verdict.failed_criteria) or 'none'})")
    return 0 if verdict.verdict == "PASS" else GATE_FAIL_EXIT_CODE


def _load_recall_scores(recall_json_path: Path | None) -> tuple[RecallScore, RecallScore]:
    if recall_json_path is None or not recall_json_path.is_file():
        zero = RecallScore(
            total_assertions=24,
            passed_assertions=0,
            accuracy_pct=0.0,
            zero_src_reads=True,
        )
        return zero, zero
    try:
        raw = json.loads(recall_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TelemetryError(f"Corrupt recall JSON at {recall_json_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TelemetryError(f"Expected JSON object in {recall_json_path}")

    scores: list[RecallScore] = []
    for arm in ("arm_a", "arm_b"):
        entry = raw.get(arm)
        if not isinstance(entry, dict):
            scores.append(
                RecallScore(total_assertions=24, passed_assertions=0, accuracy_pct=0.0, zero_src_reads=True)
            )
            continue
        resp = entry.get("response")
        stream = entry.get("stream_stdout", "")
        scores.append(
            score_recall_response(
                resp if isinstance(resp, dict) else {},
                stream_stdout=stream if isinstance(stream, str) else "",
            )
        )
    return scores[0], scores[1]


def run_evaluate_mode(args: argparse.Namespace) -> int:
    if not args.sessions_jsonl:
        raise ValueError("--sessions-jsonl is required in --mode evaluate")
    if not args.arm_a_dir or not args.arm_b_dir:
        raise ValueError("--arm-a-dir and --arm-b-dir are required in --mode evaluate")

    sessions_path = Path(args.sessions_jsonl)
    records = load_session_records(sessions_path)
    _validate_session_completeness(records)

    arm_a_dir = Path(args.arm_a_dir)
    arm_b_dir = Path(args.arm_b_dir)
    eval_a = evaluate_arm("arm_a", arm_a_dir, records)
    eval_b = evaluate_arm("arm_b", arm_b_dir, records)

    recall_path = (
        Path(args.recall_json)
        if getattr(args, "recall_json", None)
        else (sessions_path.parent / "recall_results.json")
    )
    recall_a, recall_b = _load_recall_scores(recall_path)
    verdict = evaluate_release_gate(eval_a, eval_b, recall_a, recall_b)
    write_gate_reports(
        Path(args.output_dir),
        verdict,
        records=records,
        metadata=_collect_env_metadata(args.model),
    )
    print(f"Verdict: {verdict.verdict} (failed: {', '.join(verdict.failed_criteria) or 'none'})")
    return 0 if verdict.verdict == "PASS" else GATE_FAIL_EXIT_CODE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 16 longitudinal anti-rot benchmark.")
    parser.add_argument("--mode", required=True, choices=["dry-run", "live", "evaluate"])
    parser.add_argument("--output-dir", default="benchmarks/anti_rot/out")
    parser.add_argument("--fixture-dir", default=str(FIXTURE_DIR))
    parser.add_argument("--control-agents", default=str(CONTROL_AGENTS_PATH))
    parser.add_argument("--arm-a-dir")
    parser.add_argument("--arm-b-dir")
    parser.add_argument("--sessions-jsonl")
    parser.add_argument("--recall-json")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--print-timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    try:
        if args.mode == "dry-run":
            return run_dry_run_mode(args)
        if args.mode == "live":
            return run_live_mode(args)
        return run_evaluate_mode(args)
    except KeyboardInterrupt:
        print("Interrupted by operator (SIGINT).", file=sys.stderr)
        return 130
    except (FixtureError, FileNotFoundError, ValueError) as exc:
        print(f"Configuration/fixture error: {exc}", file=sys.stderr)
        return 2
    except (IsolationError, TelemetryError) as exc:
        print(f"Isolation/telemetry error: {exc}", file=sys.stderr)
        return 1
    except (PermissionError, OSError) as exc:
        print(f"Filesystem/subprocess error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
