"""Offline deterministic unit tests for Stage 3 evaluator, recall, gate, and CLI (SPEC-016 AC-3..AC-5)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmarks.anti_rot.evaluator import (
    MAX_ORIENT_INLINE_CHARS,
    MIN_ACTIVE_DOC_REFS,
    ArmEvaluation,
    evaluate_arm,
)
from benchmarks.anti_rot.gate import (
    BenchmarkVerdict,
    evaluate_release_gate,
    write_gate_reports,
)
from benchmarks.anti_rot.recall import (
    RECALL_ASSERTIONS,
    RECALL_JSON_SCHEMA,
    RECALL_QUESTIONS,
    _extract_structured_result,
    build_src_deny_hook_config,
    get_deny_hook_script_path,
    run_blind_recall_probe,
    run_blind_recall_probe_with_artifacts,
    score_recall_response,
    verify_zero_src_reads,
)
from benchmarks.anti_rot.runner import AgyRunResult, SessionRecord
from benchmarks.anti_rot.scenarios import SCENARIOS
from scripts.run_anti_rot_benchmark import main as cli_main


def _make_record(
    arm: str,
    session_id: str,
    *,
    clean_completion: bool = True,
    doc_read_tokens: int = 100,
    changed_paths: list[str] | None = None,
    orient_chars: int = 4000,
    drifted_articles: list[str] | None = None,
    ci_exit: int = 0,
    lint_exit: int = 0,
) -> SessionRecord:
    scenario = next(s for s in SCENARIOS if s.session_id == session_id)
    return SessionRecord(
        arm=arm,
        session_id=session_id,
        title=scenario.title,
        triage_type=scenario.triage_type,
        prompt_sha256="a" * 64,
        exit_code=0 if clean_completion else 1,
        timed_out=False,
        retries=0,
        duration_seconds=0.1,
        changed_paths=changed_paths if changed_paths is not None else [],
        commit_sha="0" * 40,
        git_diff_stat="",
        pytest_passed=clean_completion,
        node_tests_passed=clean_completion,
        contract_passed=clean_completion,
        contract_errors=[] if clean_completion else ["contract failed"],
        clean_completion=clean_completion,
        conversation_id=f"conv-{arm}-{session_id}",
        input_tokens=200,
        output_tokens=100,
        tool_calls=2,
        doc_read_tokens=doc_read_tokens,
        src_read_paths=[],
        brain79_stats=(
            {
                "context_budget": {"orient_chars": orient_chars},
                "coverage": {"coverage_pct": 50.0, "drifted_articles": drifted_articles or []},
            }
            if arm == "arm_a"
            else None
        ),
        brain79_ci_check=(
            {
                "exit_code": ci_exit,
                "drifted_articles": drifted_articles or [],
                "lint_errors_count": 0 if lint_exit == 0 else 1,
            }
            if arm == "arm_a"
            else None
        ),
        brain79_ci_check_exit_code=ci_exit if arm == "arm_a" else None,
        brain79_lint_exit_code=lint_exit if arm == "arm_a" else None,
        error=None if clean_completion else "failed",
    )


def _make_full_records(
    arm: str,
    *,
    clean_count: int = 12,
    s9_doc_mutation: bool = False,
    s10_src_mutation: bool = False,
) -> list[SessionRecord]:
    records: list[SessionRecord] = []
    for idx, scenario in enumerate(SCENARIOS):
        sid = scenario.session_id
        changed: list[str] = []
        if sid == "S9" and s9_doc_mutation:
            changed = [".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"]
        elif sid == "S10":
            if s10_src_mutation:
                changed = ["src/ledgerpulse/currency.py"]
            else:
                changed = [
                    ".brain-79/topics/multi-currency-rounding-drift.md"
                    if arm == "arm_a"
                    else "docs/research/multi-currency-rounding-drift.md"
                ]
        records.append(
            _make_record(
                arm,
                sid,
                clean_completion=idx < clean_count,
                changed_paths=changed,
            )
        )
    return records


def _build_synthetic_src(workspace: Path) -> None:
    (workspace / "src/ledgerpulse").mkdir(parents=True, exist_ok=True)
    (workspace / "src/reporter").mkdir(parents=True, exist_ok=True)
    (workspace / "src/ledgerpulse/pricing.py").write_text(
        "TIERED_BULK_THRESHOLD = 10\n"
        "TIERED_BULK_DISCOUNT_BPS = 500\n\n"
        "def calculate_bulk_discount(items):\n"
        "    return 0\n\n"
        "def calculate_invoice_grand_total(invoice, include_tax=True):\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (workspace / "src/ledgerpulse/tax.py").write_text(
        "LATE_FEE_BPS = 500\n"
        "LATE_FEE_GRACE_DAYS = 7\n\n"
        "def calculate_late_fee(amount_cents, days_overdue, compound=False):\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (workspace / "src/reporter/schema.mjs").write_text(
        "export function validateSummaryDocument(payload, options = {}) {\n"
        "  return { ok: true };\n"
        "}\n",
        encoding="utf-8",
    )


def _valid_recall_payload() -> dict[str, object]:
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
            "superseded_rule_summary": "Prior policy used 250 bps and 15 grace days without compound parameter.",
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


def test_evaluator_excludes_superseded_and_scores_rot_and_canonical_coverage(tmp_path: Path) -> None:
    assert MAX_ORIENT_INLINE_CHARS == 64_000
    assert MIN_ACTIVE_DOC_REFS == 10

    arm_a = tmp_path / "arm_a"
    _build_synthetic_src(arm_a)

    # Active non-drifted article covering pricing.py & schema.mjs with valid refs + 1 stale symbol
    (arm_a / ".brain-79/architecture").mkdir(parents=True, exist_ok=True)
    (arm_a / ".brain-79/architecture/core.md").write_text(
        "---\n"
        "title: Core architecture\n"
        "type: architecture\n"
        "stability: stable\n"
        "applies_to:\n"
        "  - src/ledgerpulse/pricing.py\n"
        "  - src/reporter/schema.mjs\n"
        "---\n\n"
        "# Core architecture\n\n"
        "Uses `src/ledgerpulse/pricing.py`, `src/reporter/schema.mjs`, "
        "`TIERED_BULK_THRESHOLD`, `TIERED_BULK_DISCOUNT_BPS`, `calculate_bulk_discount`, "
        "`calculate_invoice_grand_total`, `validateSummaryDocument`, `LATE_FEE_BPS`, "
        "`LATE_FEE_GRACE_DAYS`, `calculate_late_fee`, and stale `nonexistent_helper_fn`.\n"
        "Language literals like `True` and `dict` are ignored.\n",
        encoding="utf-8",
    )

    # Drifted article covering tax.py (must NOT count tax.py as covered)
    (arm_a / ".brain-79/features").mkdir(parents=True, exist_ok=True)
    (arm_a / ".brain-79/features/tax.md").write_text(
        "---\n"
        "title: Tax feature\n"
        "type: feature\n"
        "applies_to:\n"
        "  - src/ledgerpulse/tax.py\n"
        "---\n\n"
        "# Tax\n\nUses `src/ledgerpulse/tax.py`.\n",
        encoding="utf-8",
    )

    # Superseded / archived / changelog docs with stale refs (must be excluded from rot)
    (arm_a / ".brain-79/decisions").mkdir(parents=True, exist_ok=True)
    (arm_a / ".brain-79/decisions/adr-001.md").write_text(
        "---\ntitle: Old ADR\ntype: decision\nstatus: superseded\n---\n"
        "Old `compute_invoice_total` and `src/ledgerpulse/reconcile.py`.\n",
        encoding="utf-8",
    )
    (arm_a / ".brain-79/changelog").mkdir(parents=True, exist_ok=True)
    (arm_a / ".brain-79/changelog/v0-1.md").write_text(
        "Removed `legacy_removed_symbol` and `src/ledgerpulse/deleted.py`.\n",
        encoding="utf-8",
    )
    (arm_a / ".brain-79/topics").mkdir(parents=True, exist_ok=True)
    (arm_a / ".brain-79/topics/multi-currency-rounding-drift.md").write_text(
        "# Multi-currency rounding drift\n\nHalf-even rounding prevents systematic bias.\n",
        encoding="utf-8",
    )

    records_a = _make_full_records("arm_a")
    eval_a: ArmEvaluation = evaluate_arm(
        "arm_a",
        arm_a,
        records_a,
        telemetry_override={
            "lint_strict_errors": 0,
            "lint_strict_exit_code": 0,
            "ci_check_exit_code": 1,
            "drifted_articles": [{"article_path": "features/tax.md", "drift_kind": "modified"}],
            "orient_chars": 12000,
            "supplementary_stats_coverage_pct": 42.0,
        },
    )

    assert eval_a.min_density_met is True
    assert eval_a.stale_refs == 1
    assert eval_a.total_refs >= 11
    assert eval_a.rot_rate_pct == pytest.approx((1 / eval_a.total_refs) * 100.0, rel=1e-3)
    # 2 of 3 canonical src/ files covered (pricing.py, schema.mjs); tax.py excluded due to drift
    assert eval_a.canonical_sources_total == 3
    assert eval_a.canonical_sources_covered == 2
    assert eval_a.canonical_coverage_pct == pytest.approx(200.0 / 3.0, rel=1e-3)
    assert eval_a.supplementary_stats_coverage_pct == 42.0
    assert eval_a.s9_passed is True
    assert eval_a.s10_passed is True
    assert eval_a.clean_completions == 12


def test_evaluator_arm_b_and_triage_failures(tmp_path: Path) -> None:
    arm_b = tmp_path / "arm_b"
    _build_synthetic_src(arm_b)
    (arm_b / "docs/archive").mkdir(parents=True, exist_ok=True)
    (arm_b / "docs/research").mkdir(parents=True, exist_ok=True)
    (arm_b / "docs/architecture.md").write_text(
        "# Architecture\n\nUses `src/ledgerpulse/pricing.py` and `src/ledgerpulse/missing.py`.\n",
        encoding="utf-8",
    )
    (arm_b / "docs/archive/old.md").write_text(
        "# Old\n\n`compute_invoice_total`\n",
        encoding="utf-8",
    )
    (arm_b / "docs/research/multi-currency-rounding-drift.md").write_text(
        "# Research\n\nFindings.\n",
        encoding="utf-8",
    )

    records_b = _make_full_records("arm_b", clean_count=10, s9_doc_mutation=True, s10_src_mutation=True)
    eval_b = evaluate_arm("arm_b", arm_b, records_b)
    assert eval_b.canonical_sources_total == 3
    assert eval_b.canonical_sources_covered == 1
    assert eval_b.stale_refs == 1
    assert eval_b.min_density_met is False
    assert eval_b.s9_passed is False
    assert eval_b.s10_passed is False
    assert eval_b.clean_completions == 10


def test_evaluator_calibration_valid_refs_and_true_stale_detection(tmp_path: Path) -> None:
    arm_a = tmp_path / "arm_a"
    (arm_a / "src/ledgerpulse").mkdir(parents=True, exist_ok=True)
    (arm_a / "src/reporter").mkdir(parents=True, exist_ok=True)
    (arm_a / "pyproject.toml").write_text("[project]\nname='ledgerpulse'\n", encoding="utf-8")
    (arm_a / "src/ledgerpulse/models.py").write_text(
        "from dataclasses import dataclass\n"
        "from enum import Enum\n\n"
        "class InvoiceStatus(str, Enum):\n"
        '    VOID = "void"\n\n'
        "@dataclass\n"
        "class LineItem:\n"
        "    amount_cents: int\n"
        "    tax_rate_bps: int\n",
        encoding="utf-8",
    )
    (arm_a / "src/ledgerpulse/tax.py").write_text(
        "from decimal import Decimal, ROUND_HALF_EVEN\n\n"
        "def calculate_late_fee(amount_cents: int, days_overdue: int, compound: bool = False) -> int:\n"
        '    return {"schema_version": "2.0", "invoice_count": 1}["invoice_count"]\n',
        encoding="utf-8",
    )
    (arm_a / "src/reporter/schema.mjs").write_text(
        "export function validateSummaryDocument(payload, options = {}) {\n"
        '  return { "schema_version": "2.0" };\n'
        "}\n",
        encoding="utf-8",
    )

    (arm_a / ".brain-79/architecture").mkdir(parents=True, exist_ok=True)
    (arm_a / ".brain-79/architecture/valid.md").write_text(
        "---\n"
        "title: Valid calibrated refs\n"
        "type: architecture\n"
        "applies_to:\n"
        "  - src/**\n"
        "---\n\n"
        "# Valid calibrated refs\n\n"
        "Files: `models.py`, `pyproject.toml`, `schema.mjs`.\n"
        "Symbols: `amount_cents`, `InvoiceStatus.VOID`, `bundle.schema_version`, "
        "`item.tax_rate_bps`, `Decimal`, `ROUND_HALF_EVEN`, `calculate_late_fee`, "
        "`validateSummaryDocument`, `days_overdue`, `payload`, `options`.\n",
        encoding="utf-8",
    )
    (arm_a / ".brain-79/topics").mkdir(parents=True, exist_ok=True)
    (arm_a / ".brain-79/topics/multi-currency-rounding-drift.md").write_text(
        "# Research\n\nHalf-even.\n", encoding="utf-8"
    )

    records = _make_full_records("arm_a")
    valid_eval = evaluate_arm(
        "arm_a",
        arm_a,
        records,
        telemetry_override={
            "lint_strict_errors": 0,
            "lint_strict_exit_code": 0,
            "ci_check_exit_code": 0,
            "drifted_articles": [],
            "orient_chars": 5000,
        },
    )
    assert valid_eval.stale_refs == 0, f"Unexpected stale refs: {valid_eval.stale_details}"
    assert valid_eval.rot_rate_pct == 0.0
    assert valid_eval.min_density_met is True

    # Now add true rot items and verify all 4 are flagged
    (arm_a / ".brain-79/architecture/valid.md").write_text(
        (arm_a / ".brain-79/architecture/valid.md").read_text(encoding="utf-8")
        + "\nStale: `reconcile.py`, `compute_invoice_total`, `InvoiceStatus.ARCHIVED`, `bundle.nonexistent_field`.\n",
        encoding="utf-8",
    )
    stale_eval = evaluate_arm(
        "arm_a",
        arm_a,
        records,
        telemetry_override={
            "lint_strict_errors": 0,
            "lint_strict_exit_code": 0,
            "ci_check_exit_code": 0,
            "drifted_articles": [],
            "orient_chars": 5000,
        },
    )
    assert stale_eval.stale_refs == 4
    joined = "\n".join(stale_eval.stale_details)
    assert "reconcile.py" in joined
    assert "compute_invoice_total" in joined
    assert "InvoiceStatus.ARCHIVED" in joined
    assert "bundle.nonexistent_field" in joined


def test_recall_probe_assertions_hook_script_and_zero_src_read_check(tmp_path: Path) -> None:
    assert 8 <= len(RECALL_QUESTIONS) <= 10
    assert len(RECALL_ASSERTIONS) >= 20
    assert isinstance(RECALL_JSON_SCHEMA, dict)
    assert RECALL_JSON_SCHEMA.get("type") == "object"

    # Verify Antigravity hooks.json structure and invoke deny_src_reads.py via subprocess
    script_path = get_deny_hook_script_path()
    assert script_path.is_file()
    cfg = build_src_deny_hook_config(script_path)
    pre_tool = cfg["blind-recall-src-guard"]["PreToolUse"]
    assert isinstance(pre_tool, list) and pre_tool
    assert pre_tool[0]["matcher"] == "*"

    # Verify RECALL_JSON_SCHEMA defines all fields expected by RECALL_ASSERTIONS
    valid_payload = _valid_recall_payload()
    schema_props = RECALL_JSON_SCHEMA["properties"]
    for section_key, section_val in valid_payload.items():
        assert section_key in RECALL_JSON_SCHEMA["required"]
        assert section_key in schema_props
        sub_schema = schema_props[section_key]
        assert isinstance(section_val, dict)
        for field_name in section_val:
            assert field_name in sub_schema["properties"], f"Missing {section_key}.{field_name} in schema"
            assert field_name in sub_schema["required"], f"Missing {section_key}.{field_name} in required"

    # Verify run_blind_recall_probe installs .agents/hooks.json without --settings and cleans up
    probe_ws = tmp_path / "probe_ws"
    probe_ws.mkdir()
    observed_cmds: list[list[str]] = []

    def _ok_runner(cmd: list[str], cwd: Path, timeout_s: int) -> AgyRunResult:
        observed_cmds.append(cmd)
        assert (cwd / ".agents/hooks.json").is_file()
        assert "--settings" not in cmd
        return AgyRunResult(
            exit_code=0,
            stdout=json.dumps({"type": "result", "result": valid_payload}) + "\n",
            stderr="",
        )

    probe_score = run_blind_recall_probe(probe_ws, agy_runner=_ok_runner)
    assert probe_score.accuracy_pct == 100.0
    assert not (probe_ws / ".agents").exists()

    # Verify cleanup on exception and preservation of pre-existing .agents/hooks.json
    (probe_ws / ".agents").mkdir()
    (probe_ws / ".agents/hooks.json").write_text('{"existing": true}\n', encoding="utf-8")

    def _boom_runner(cmd: list[str], cwd: Path, timeout_s: int) -> AgyRunResult:
        raise RuntimeError("simulated agy crash")

    with pytest.raises(RuntimeError, match="simulated agy crash"):
        run_blind_recall_probe(probe_ws, agy_runner=_boom_runner)
    assert (probe_ws / ".agents/hooks.json").read_text(encoding="utf-8") == '{"existing": true}\n'

    # Verify _extract_structured_result handles fenced JSON in result and assistant message.content blocks
    fenced_json = "```json\n" + json.dumps(valid_payload) + "\n```"
    fenced_result_score = run_blind_recall_probe(
        probe_ws,
        agy_runner=lambda cmd, cwd, ts: AgyRunResult(
            exit_code=0,
            stdout=json.dumps({"type": "result", "result": fenced_json}) + "\n",
            stderr="",
        ),
    )
    assert fenced_result_score.accuracy_pct == 100.0

    assistant_block_score = run_blind_recall_probe(
        probe_ws,
        agy_runner=lambda cmd, cwd, ts: AgyRunResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": fenced_json}]},
                }
            )
            + "\n",
            stderr="",
        ),
    )
    assert assistant_block_score.accuracy_pct == 100.0

    # Verify real agy nested wire format (init + step_update + result.structured_output & result.response)
    real_agy_stream_structured = "\n".join(
        [
            json.dumps({"event": "init", "conversation_id": "conv-real-1", "init": {"tools": ["read_file"]}}),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {"step_type": "agent_response", "text_delta": json.dumps(valid_payload)},
                }
            ),
            json.dumps(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": "conv-real-1",
                        "status": "SUCCESS",
                        "response": json.dumps(valid_payload) + "\n",
                        "structured_output": valid_payload,
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                    },
                }
            ),
        ]
    )
    assert _extract_structured_result(real_agy_stream_structured) == valid_payload
    real_score_1, real_payload_1, _ = run_blind_recall_probe_with_artifacts(
        probe_ws,
        agy_runner=lambda cmd, cwd, ts: AgyRunResult(
            exit_code=0, stdout=real_agy_stream_structured, stderr=""
        ),
    )
    assert real_score_1.accuracy_pct == 100.0
    assert real_payload_1 == valid_payload

    real_agy_stream_response_only = "\n".join(
        [
            json.dumps({"event": "init", "conversation_id": "conv-real-2"}),
            json.dumps(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": "conv-real-2",
                        "status": "SUCCESS",
                        "response": json.dumps(valid_payload) + "\n",
                    },
                }
            ),
        ]
    )
    assert _extract_structured_result(real_agy_stream_response_only) == valid_payload
    real_score_2, _, _ = run_blind_recall_probe_with_artifacts(
        probe_ws,
        agy_runner=lambda cmd, cwd, ts: AgyRunResult(
            exit_code=0, stdout=real_agy_stream_response_only, stderr=""
        ),
    )
    assert real_score_2.accuracy_pct == 100.0

    deny_payload = json.dumps(
        {
            "toolCall": {
                "id": "call-1",
                "name": "read_file",
                "args": {"path": "src/ledgerpulse/tax.py"},
            }
        }
    )
    deny_proc = subprocess.run(
        [sys.executable, str(script_path)],
        input=deny_payload,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(deny_proc.stdout)["decision"] == "deny"

    deny_cmd_payload = json.dumps(
        {
            "toolCall": {
                "id": "call-2",
                "name": "run_command",
                "args": {"CommandLine": "cat src/ledgerpulse/pricing.py"},
            }
        }
    )
    deny_cmd_proc = subprocess.run(
        [sys.executable, str(script_path)],
        input=deny_cmd_payload,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(deny_cmd_proc.stdout)["decision"] == "deny"

    allow_payload = json.dumps(
        {
            "toolCall": {
                "id": "call-3",
                "name": "read_file",
                "args": {"path": ".brain-79/INDEX.md"},
            }
        }
    )
    allow_proc = subprocess.run(
        [sys.executable, str(script_path)],
        input=allow_payload,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(allow_proc.stdout)["decision"] == "allow"

    # Score valid response with zero src reads
    clean_stream = json.dumps({"type": "tool_use", "name": "read_file", "input": {"path": ".brain-79/INDEX.md"}})
    ok, violations = verify_zero_src_reads(clean_stream)
    assert ok is True and violations == []

    score = score_recall_response(_valid_recall_payload(), stream_stdout=clean_stream)
    assert score.total_assertions >= 20
    assert score.passed_assertions == score.total_assertions
    assert score.accuracy_pct == 100.0
    assert score.zero_src_reads is True

    # Negative checks: stale S4 constants, removed S5 symbol, removed S11 path must fail
    stale_payload = _valid_recall_payload()
    stale_payload["s4_s7_late_fee_current"] = {
        "module_path": "src/ledgerpulse/tax.py",
        "function_name": "calculate_late_fee",
        "params": ["amount_cents", "days_overdue"],
        "late_fee_bps": 250,
        "grace_days": 15,
    }
    stale_payload["s5_pricing_refactor"] = {
        "module_path": "src/ledgerpulse/pricing.py",
        "current_function_name": "compute_invoice_total",
        "params": ["invoice"],
        "include_tax_default": False,
    }
    stale_payload["s11_reconciliation_move"] = {
        "current_module_path": "src/ledgerpulse/reconcile.py",
        "function_name": "reconcile_payments",
        "report_class_name": "ReconciliationReport",
    }
    stale_score = score_recall_response(stale_payload, stream_stdout=clean_stream)
    assert stale_score.passed_assertions < stale_score.total_assertions
    assert stale_score.accuracy_pct < 80.0

    # Fail closed if src/ read detected in stream-json
    dirty_stream = json.dumps({"type": "tool_use", "name": "read_file", "input": {"path": "src/ledgerpulse/tax.py"}})
    dirty_score = score_recall_response(_valid_recall_payload(), stream_stdout=dirty_stream)
    assert dirty_score.zero_src_reads is False
    assert dirty_score.src_read_violations == ["src/ledgerpulse/tax.py"]


def _arm_eval(
    arm: str,
    *,
    rot: float = 0.0,
    min_density: bool = True,
    cov: float = 95.0,
    orient_chars: int = 12000,
    clean: int = 12,
    lint_err: int = 0,
    ci_exit: int = 0,
    drifted: int = 0,
    s9: bool = True,
    s10: bool = True,
) -> ArmEvaluation:
    return ArmEvaluation(
        arm=arm,
        active_doc_count=5,
        total_refs=20 if min_density else 3,
        stale_refs=0 if rot == 0 else 1,
        stale_details=[],
        min_density_met=min_density,
        rot_rate_pct=rot,
        canonical_sources_total=13,
        canonical_sources_covered=round(13 * cov / 100.0),
        canonical_coverage_pct=cov,
        supplementary_stats_coverage_pct=45.0,
        orient_chars=orient_chars,
        total_doc_read_tokens=1200,
        mean_doc_read_tokens=100.0,
        lint_strict_errors=lint_err,
        lint_strict_exit_code=0 if lint_err == 0 else 1,
        ci_check_exit_code=ci_exit,
        drifted_articles=["features/x.md"] * drifted,
        drifted_articles_count=drifted,
        s9_passed=s9,
        s10_passed=s10,
        clean_completions=clean,
        total_sessions=12,
        autonomous_compliance_pct=round((clean / 12) * 100.0, 2),
    )


def test_release_gate_verdict_and_edge_cases(tmp_path: Path) -> None:
    clean_stream = json.dumps({"type": "tool_use", "name": "read_file", "input": {"path": ".brain-79/INDEX.md"}})
    rec_a_100 = score_recall_response(_valid_recall_payload(), stream_stdout=clean_stream)
    rec_b_60 = score_recall_response({}, stream_stdout=clean_stream)

    # 1. All criteria passing -> PASS
    verdict_pass: BenchmarkVerdict = evaluate_release_gate(
        _arm_eval("arm_a", rot=0.0, cov=95.0),
        _arm_eval("arm_b", rot=0.0, cov=85.0),
        rec_a_100,
        rec_b_60,
    )
    assert verdict_pass.verdict == "PASS"
    assert verdict_pass.failed_criteria == []

    # 2. Drift > 0 -> FAIL
    verdict_drift = evaluate_release_gate(
        _arm_eval("arm_a", ci_exit=1, drifted=1),
        _arm_eval("arm_b", rot=10.0, cov=50.0),
        rec_a_100,
        rec_b_60,
    )
    assert verdict_drift.verdict == "FAIL"
    assert "arm_a_structural_and_drift" in verdict_drift.failed_criteria

    # 3. Zero-safe rot edge case: rot_B == 0 and rot_A == 2.0 -> FAIL
    verdict_rot = evaluate_release_gate(
        _arm_eval("arm_a", rot=2.0),
        _arm_eval("arm_b", rot=0.0),
        rec_a_100,
        rec_b_60,
    )
    assert verdict_rot.verdict == "FAIL"
    assert "arm_a_rot_rate" in verdict_rot.failed_criteria

    # 4. Ceiling-aware recall edge case: acc_B == 70%, acc_A == 80% (+10pp < +15pp) -> FAIL
    rec_a_80 = score_recall_response(
        {**_valid_recall_payload(), "s12_audit_freeze": {}}, stream_stdout=clean_stream
    )
    # Build a 70% recall score for B by using partial payload
    rec_b_70 = score_recall_response(
        {
            "s2_bulk_discount": _valid_recall_payload()["s2_bulk_discount"],
            "s3_void_invoice": _valid_recall_payload()["s3_void_invoice"],
            "s4_s7_late_fee_current": _valid_recall_payload()["s4_s7_late_fee_current"],
            "s5_pricing_refactor": _valid_recall_payload()["s5_pricing_refactor"],
            "s6_js_validator": _valid_recall_payload()["s6_js_validator"],
            "s8_polyglot_export": _valid_recall_payload()["s8_polyglot_export"],
        },
        stream_stdout=clean_stream,
    )
    if rec_b_70.accuracy_pct <= 80.0 and rec_a_80.accuracy_pct < rec_b_70.accuracy_pct + 15.0:
        verdict_rec = evaluate_release_gate(
            _arm_eval("arm_a"),
            _arm_eval("arm_b"),
            rec_a_80,
            rec_b_70,
        )
        assert verdict_rec.verdict == "FAIL"
        assert "arm_a_blind_recall" in verdict_rec.failed_criteria

    # 5. Compliance < 10/12 -> FAIL
    verdict_comp = evaluate_release_gate(
        _arm_eval("arm_a", clean=9),
        _arm_eval("arm_b"),
        rec_a_100,
        rec_b_60,
    )
    assert verdict_comp.verdict == "FAIL"
    assert "arm_a_autonomous_compliance" in verdict_comp.failed_criteria

    # 6. Write results.json & report.md
    results_path, report_path = write_gate_reports(
        tmp_path,
        verdict_comp,
        records=_make_full_records("arm_a") + _make_full_records("arm_b"),
        metadata={"model": "gemini-4-hydrogen-low", "agy_version": "0.1.0", "brain79_version": "0.16.0", "git_sha": "abc"},
    )
    assert results_path.is_file()
    assert report_path.is_file()
    loaded = json.loads(results_path.read_text(encoding="utf-8"))
    assert loaded["verdict"] == "FAIL"
    assert "arm_a_autonomous_compliance" in loaded["failed_criteria"]
    md_text = report_path.read_text(encoding="utf-8")
    assert "FAIL" in md_text
    assert "arm_a_autonomous_compliance" in md_text


def test_cli_dry_run_and_error_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Missing fixture -> exit 2, zero temp dirs created
    missing_fixture = tmp_path / "does_not_exist"
    out_missing = tmp_path / "out_missing"
    rc_missing = cli_main(
        ["--mode", "dry-run", "--fixture-dir", str(missing_fixture), "--output-dir", str(out_missing)]
    )
    assert rc_missing == 2
    assert not out_missing.exists()

    # 2. Dry-run full pipeline -> exit 0, emits results.json + report.md + recall_results.json
    out_dry = tmp_path / "out_dry"
    rc_dry = cli_main(["--mode", "dry-run", "--output-dir", str(out_dry)])
    assert rc_dry == 0
    assert (out_dry / "results.json").is_file()
    assert (out_dry / "report.md").is_file()
    assert (out_dry / "sessions.jsonl").is_file()
    assert (out_dry / "recall_results.json").is_file()

    # 2b. --mode evaluate reproduces recall score from saved recall_results.json and exits 4 on FAIL
    out_eval_fail = tmp_path / "out_eval_fail"
    rc_eval_fail = cli_main(
        [
            "--mode",
            "evaluate",
            "--sessions-jsonl",
            str(out_dry / "sessions.jsonl"),
            "--arm-a-dir",
            str(out_dry / "workspace/arm_a"),
            "--arm-b-dir",
            str(out_dry / "workspace/arm_b"),
            "--output-dir",
            str(out_eval_fail),
        ]
    )
    assert rc_eval_fail == 4
    eval_results = json.loads((out_eval_fail / "results.json").read_text(encoding="utf-8"))
    assert eval_results["verdict"] == "FAIL"
    assert eval_results["recall_a"]["accuracy_pct"] == 100.0

    # 2c. --mode evaluate exits 0 when release gate verdict is PASS
    out_eval_pass = tmp_path / "out_eval_pass"
    pass_verdict = evaluate_release_gate(
        _arm_eval("arm_a", rot=0.0, cov=95.0),
        _arm_eval("arm_b", rot=10.0, cov=50.0),
        score_recall_response(_valid_recall_payload()),
        score_recall_response({}),
    )
    with (
        patch("scripts.run_anti_rot_benchmark.evaluate_arm", side_effect=[pass_verdict.arm_a, pass_verdict.arm_b]),
        patch("scripts.run_anti_rot_benchmark.evaluate_release_gate", return_value=pass_verdict),
    ):
        rc_eval_pass = cli_main(
            [
                "--mode",
                "evaluate",
                "--sessions-jsonl",
                str(out_dry / "sessions.jsonl"),
                "--arm-a-dir",
                str(out_dry / "workspace/arm_a"),
                "--arm-b-dir",
                str(out_dry / "workspace/arm_b"),
                "--output-dir",
                str(out_eval_pass),
            ]
        )
    assert rc_eval_pass == 0
    assert json.loads((out_eval_pass / "results.json").read_text(encoding="utf-8"))["verdict"] == "PASS"

    # 3. --mode evaluate with incomplete session indices (missing S12) -> exit 1
    incomplete_jsonl = tmp_path / "incomplete.jsonl"
    lines = (out_dry / "sessions.jsonl").read_text(encoding="utf-8").splitlines()[:-1]
    incomplete_jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_eval_bad = tmp_path / "out_eval_bad"
    rc_eval_bad = cli_main(
        [
            "--mode",
            "evaluate",
            "--sessions-jsonl",
            str(incomplete_jsonl),
            "--arm-a-dir",
            str(tmp_path),
            "--arm-b-dir",
            str(tmp_path),
            "--output-dir",
            str(out_eval_bad),
        ]
    )
    assert rc_eval_bad == 1
    assert not (out_eval_bad / "results.json").exists()

    # 4. PermissionError / OSError -> exit 3
    with patch("scripts.run_anti_rot_benchmark.run_dry_run_mode", side_effect=PermissionError("denied")):
        rc_perm = cli_main(["--mode", "dry-run", "--output-dir", str(tmp_path / "out_perm")])
    assert rc_perm == 3

    # 5. KeyboardInterrupt -> exit 130
    with patch("scripts.run_anti_rot_benchmark.run_dry_run_mode", side_effect=KeyboardInterrupt()):
        rc_int = cli_main(["--mode", "dry-run", "--output-dir", str(tmp_path / "out_int")])
    assert rc_int == 130

    # 6. Direct subprocess invocation without PYTHONPATH -> exit 2 (no ModuleNotFoundError)
    clean_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_anti_rot_benchmark.py",
            "--mode",
            "dry-run",
            "--fixture-dir",
            str(tmp_path / "missing_fixture"),
        ],
        env=clean_env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "ModuleNotFoundError" not in proc.stderr
