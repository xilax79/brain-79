"""Mechanically enforced blind semantic-recall probe and assertion scorer (SPEC-016 R-4.1, R-4.2)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmarks.anti_rot import ANTI_ROT_ROOT
from benchmarks.anti_rot.runner import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    AgyRunResult,
    SessionAgyRunner,
    default_live_agy_runner,
    parse_stream_json_telemetry,
)


@dataclass(frozen=True)
class RecallQuestion:
    """Single structured blind-recall question."""

    question_id: str
    prompt: str


@dataclass(frozen=True)
class RecallAssertion:
    """Atomic deterministic Python assertion against structured recall JSON."""

    assertion_id: str
    description: str
    predicate: Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class AssertionOutcome:
    """Result of evaluating one atomic recall assertion."""

    assertion_id: str
    description: str
    passed: bool


@dataclass(frozen=True)
class RecallScore:
    """Scored blind semantic-recall outcome with zero-src-read enforcement."""

    total_assertions: int
    passed_assertions: int
    accuracy_pct: float
    zero_src_reads: bool
    src_read_violations: list[str] = field(default_factory=list)
    details: list[AssertionOutcome] = field(default_factory=list)


RECALL_QUESTIONS: tuple[RecallQuestion, ...] = (
    RecallQuestion("Q1", "S2 bulk discount: module path, function name, threshold, and discount_bps."),
    RecallQuestion("Q2", "S3 invoice voiding: module path, class name, method name, and max_reason_len."),
    RecallQuestion("Q3", "S4/S7 current late fee: module path, function name, params, bps, grace days, and superseded summary."),
    RecallQuestion("Q4", "S5 pricing refactor: module path, current grand-total function name, params, and whether include_tax defaults to True."),
    RecallQuestion("Q5", "S6 JS validator: schema module path, index module path, function name, and params."),
    RecallQuestion("Q6", "S8 polyglot export: Python module/function, schema_version, and JS module/function."),
    RecallQuestion("Q7", "S10 rounding research: topic, currencies, and rounding strategy."),
    RecallQuestion("Q8", "S11 reconciliation move: current matcher module file path (.py), function name, and report class name."),
    RecallQuestion("Q9", "S12 pre-audit freeze: Python module/function, audit_freeze_tag, and JS module/function."),
)

RECALL_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "s2_bulk_discount",
        "s3_void_invoice",
        "s4_s7_late_fee_current",
        "s5_pricing_refactor",
        "s6_js_validator",
        "s8_polyglot_export",
        "s10_rounding_research",
        "s11_reconciliation_move",
        "s12_audit_freeze",
    ],
    "properties": {
        "s2_bulk_discount": {
            "type": "object",
            "required": ["module_path", "function_name", "threshold", "discount_bps"],
            "properties": {
                "module_path": {"type": "string"},
                "function_name": {"type": "string"},
                "threshold": {"type": "integer"},
                "discount_bps": {"type": "integer"},
            },
        },
        "s3_void_invoice": {
            "type": "object",
            "required": ["module_path", "class_name", "method_name", "max_reason_len"],
            "properties": {
                "module_path": {"type": "string"},
                "class_name": {"type": "string"},
                "method_name": {"type": "string"},
                "max_reason_len": {"type": "integer"},
            },
        },
        "s4_s7_late_fee_current": {
            "type": "object",
            "required": [
                "module_path",
                "function_name",
                "params",
                "late_fee_bps",
                "grace_days",
                "superseded_rule_summary",
            ],
            "properties": {
                "module_path": {"type": "string"},
                "function_name": {"type": "string"},
                "params": {"type": "array", "items": {"type": "string"}},
                "late_fee_bps": {"type": "integer"},
                "grace_days": {"type": "integer"},
                "superseded_rule_summary": {"type": "string"},
            },
        },
        "s5_pricing_refactor": {
            "type": "object",
            "required": ["module_path", "current_function_name", "params", "include_tax_default"],
            "properties": {
                "module_path": {"type": "string"},
                "current_function_name": {"type": "string"},
                "params": {"type": "array", "items": {"type": "string"}},
                "include_tax_default": {"type": "boolean"},
            },
        },
        "s6_js_validator": {
            "type": "object",
            "required": ["schema_module_path", "index_module_path", "function_name", "params"],
            "properties": {
                "schema_module_path": {"type": "string"},
                "index_module_path": {"type": "string"},
                "function_name": {"type": "string"},
                "params": {"type": "array", "items": {"type": "string"}},
            },
        },
        "s8_polyglot_export": {
            "type": "object",
            "required": [
                "python_module_path",
                "python_function_name",
                "schema_version",
                "js_module_path",
                "js_function_name",
            ],
            "properties": {
                "python_module_path": {"type": "string"},
                "python_function_name": {"type": "string"},
                "schema_version": {"type": "string"},
                "js_module_path": {"type": "string"},
                "js_function_name": {"type": "string"},
            },
        },
        "s10_rounding_research": {
            "type": "object",
            "required": ["topic", "currencies", "rounding_strategy"],
            "properties": {
                "topic": {"type": "string"},
                "currencies": {"type": "array", "items": {"type": "string"}},
                "rounding_strategy": {"type": "string"},
            },
        },
        "s11_reconciliation_move": {
            "type": "object",
            "required": ["current_module_path", "function_name", "report_class_name"],
            "properties": {
                "current_module_path": {"type": "string"},
                "function_name": {"type": "string"},
                "report_class_name": {"type": "string"},
            },
        },
        "s12_audit_freeze": {
            "type": "object",
            "required": [
                "python_module_path",
                "python_function_name",
                "audit_freeze_tag",
                "js_module_path",
                "js_function_name",
            ],
            "properties": {
                "python_module_path": {"type": "string"},
                "python_function_name": {"type": "string"},
                "audit_freeze_tag": {"type": "string"},
                "js_module_path": {"type": "string"},
                "js_function_name": {"type": "string"},
            },
        },
    },
}


def _sec(data: dict[str, Any], key: str) -> dict[str, Any]:
    val = data.get(key)
    return val if isinstance(val, dict) else {}


def _norm_str(val: object) -> str:
    return str(val).strip() if val is not None else ""


RECALL_ASSERTIONS: tuple[RecallAssertion, ...] = (
    RecallAssertion(
        "A01",
        "S2 module path is src/ledgerpulse/pricing.py",
        lambda d: _norm_str(_sec(d, "s2_bulk_discount").get("module_path")) == "src/ledgerpulse/pricing.py",
    ),
    RecallAssertion(
        "A02",
        "S2 function name is calculate_bulk_discount",
        lambda d: _norm_str(_sec(d, "s2_bulk_discount").get("function_name")) == "calculate_bulk_discount",
    ),
    RecallAssertion(
        "A03",
        "S2 threshold == 10 and discount_bps == 500",
        lambda d: _sec(d, "s2_bulk_discount").get("threshold") == 10
        and _sec(d, "s2_bulk_discount").get("discount_bps") == 500,
    ),
    RecallAssertion(
        "A04",
        "S3 void_invoice lives on Ledger in src/ledgerpulse/ledger.py",
        lambda d: _norm_str(_sec(d, "s3_void_invoice").get("module_path")) == "src/ledgerpulse/ledger.py"
        and _norm_str(_sec(d, "s3_void_invoice").get("class_name")) == "Ledger"
        and _norm_str(_sec(d, "s3_void_invoice").get("method_name")) == "void_invoice",
    ),
    RecallAssertion(
        "A05",
        "S3 max_reason_len == 200",
        lambda d: _sec(d, "s3_void_invoice").get("max_reason_len") == 200,
    ),
    RecallAssertion(
        "A06",
        "S7 current late fee module is src/ledgerpulse/tax.py and function is calculate_late_fee",
        lambda d: _norm_str(_sec(d, "s4_s7_late_fee_current").get("module_path")) == "src/ledgerpulse/tax.py"
        and _norm_str(_sec(d, "s4_s7_late_fee_current").get("function_name")) == "calculate_late_fee",
    ),
    RecallAssertion(
        "A07",
        "S7 current calculate_late_fee includes compound parameter",
        lambda d: _sec(d, "s4_s7_late_fee_current").get("params") == ["amount_cents", "days_overdue", "compound"],
    ),
    RecallAssertion(
        "A08",
        "S7 current LATE_FEE_BPS is 500 (negative check: NOT superseded 250)",
        lambda d: _sec(d, "s4_s7_late_fee_current").get("late_fee_bps") == 500
        and _sec(d, "s4_s7_late_fee_current").get("late_fee_bps") != 250,
    ),
    RecallAssertion(
        "A09",
        "S7 current LATE_FEE_GRACE_DAYS is 7 (negative check: NOT superseded 15)",
        lambda d: _sec(d, "s4_s7_late_fee_current").get("grace_days") == 7
        and _sec(d, "s4_s7_late_fee_current").get("grace_days") != 15,
    ),
    RecallAssertion(
        "A10",
        "S5 current pricing function is calculate_invoice_grand_total (NOT compute_invoice_total)",
        lambda d: _norm_str(_sec(d, "s5_pricing_refactor").get("current_function_name"))
        == "calculate_invoice_grand_total",
    ),
    RecallAssertion(
        "A11",
        "S5 calculate_invoice_grand_total params are [invoice, include_tax]",
        lambda d: _sec(d, "s5_pricing_refactor").get("params") == ["invoice", "include_tax"],
    ),
    RecallAssertion(
        "A12",
        "S5 pricing module is src/ledgerpulse/pricing.py and include_tax defaults to True (NOT removed compute_invoice_total)",
        lambda d: _norm_str(_sec(d, "s5_pricing_refactor").get("module_path")) == "src/ledgerpulse/pricing.py"
        and _sec(d, "s5_pricing_refactor").get("include_tax_default") is True
        and _norm_str(_sec(d, "s5_pricing_refactor").get("current_function_name")) != "compute_invoice_total",
    ),
    RecallAssertion(
        "A13",
        "S6 JS validator paths are src/reporter/schema.mjs and src/reporter/index.mjs",
        lambda d: _norm_str(_sec(d, "s6_js_validator").get("schema_module_path")) == "src/reporter/schema.mjs"
        and _norm_str(_sec(d, "s6_js_validator").get("index_module_path")) == "src/reporter/index.mjs",
    ),
    RecallAssertion(
        "A14",
        "S6 JS validator function is validateSummaryDocument(payload, options)",
        lambda d: _norm_str(_sec(d, "s6_js_validator").get("function_name")) == "validateSummaryDocument"
        and _sec(d, "s6_js_validator").get("params") == ["payload", "options"],
    ),
    RecallAssertion(
        "A15",
        "S8 Python export is export_audit_bundle in src/ledgerpulse/export.py",
        lambda d: _norm_str(_sec(d, "s8_polyglot_export").get("python_module_path"))
        == "src/ledgerpulse/export.py"
        and _norm_str(_sec(d, "s8_polyglot_export").get("python_function_name")) == "export_audit_bundle",
    ),
    RecallAssertion(
        "A16",
        "S8 SCHEMA_VERSION is 2.0",
        lambda d: _norm_str(_sec(d, "s8_polyglot_export").get("schema_version")) == "2.0",
    ),
    RecallAssertion(
        "A17",
        "S8 JS formatter is formatAuditBanner in src/reporter/formatter.mjs",
        lambda d: _norm_str(_sec(d, "s8_polyglot_export").get("js_module_path"))
        == "src/reporter/formatter.mjs"
        and _norm_str(_sec(d, "s8_polyglot_export").get("js_function_name")) == "formatAuditBanner",
    ),
    RecallAssertion(
        "A18",
        "S10 research covers USD, EUR, GBP currencies",
        lambda d: {"USD", "EUR", "GBP"}.issubset(
            {str(c).upper() for c in (_sec(d, "s10_rounding_research").get("currencies") or [])}
        ),
    ),
    RecallAssertion(
        "A19",
        "S10 research identifies round_half_even / half-even rounding",
        lambda d: "half" in _norm_str(_sec(d, "s10_rounding_research").get("rounding_strategy")).lower(),
    ),
    RecallAssertion(
        "A20",
        "S11 current reconciliation matcher module path is src/ledgerpulse/reconciliation/matcher.py (NOT reconcile.py)",
        lambda d: _norm_str(_sec(d, "s11_reconciliation_move").get("current_module_path"))
        == "src/ledgerpulse/reconciliation/matcher.py",
    ),
    RecallAssertion(
        "A21",
        "S11 reconciliation exposes reconcile_payments and ReconciliationReport (NOT removed reconcile.py)",
        lambda d: _norm_str(_sec(d, "s11_reconciliation_move").get("function_name")) == "reconcile_payments"
        and _norm_str(_sec(d, "s11_reconciliation_move").get("report_class_name")) == "ReconciliationReport"
        and _norm_str(_sec(d, "s11_reconciliation_move").get("current_module_path"))
        != "src/ledgerpulse/reconcile.py",
    ),
    RecallAssertion(
        "A22",
        "S12 Python audit check is verify_audit_readiness in src/ledgerpulse/validation.py",
        lambda d: _norm_str(_sec(d, "s12_audit_freeze").get("python_module_path"))
        == "src/ledgerpulse/validation.py"
        and _norm_str(_sec(d, "s12_audit_freeze").get("python_function_name")) == "verify_audit_readiness",
    ),
    RecallAssertion(
        "A23",
        "S12 AUDIT_FREEZE_TAG is v1-audit-ready",
        lambda d: _norm_str(_sec(d, "s12_audit_freeze").get("audit_freeze_tag")) == "v1-audit-ready",
    ),
    RecallAssertion(
        "A24",
        "S12 JS CLI check is verifyBundleCli in src/reporter/cli.mjs",
        lambda d: _norm_str(_sec(d, "s12_audit_freeze").get("js_module_path")) == "src/reporter/cli.mjs"
        and _norm_str(_sec(d, "s12_audit_freeze").get("js_function_name")) == "verifyBundleCli",
    ),
)


def get_deny_hook_script_path() -> Path:
    """Return the path to the deterministic `PreToolUse` `src/` deny hook script."""
    return ANTI_ROT_ROOT / "deny_src_reads.py"


def build_src_deny_hook_config(hook_script_path: Path) -> dict[str, Any]:
    """Build an Antigravity `.agents/hooks.json` configuration blocking all `src/` tool reads."""
    import sys

    return {
        "blind-recall-src-guard": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{sys.executable} {hook_script_path}",
                            "timeout": 10,
                        }
                    ],
                }
            ]
        }
    }


def verify_zero_src_reads(stream_stdout: str) -> tuple[bool, list[str]]:
    """Fail closed if any `src/` read or command reference appears in `stream-json` logs."""
    if not stream_stdout.strip():
        return True, []
    telemetry = parse_stream_json_telemetry(stream_stdout)
    violations = list(telemetry.src_read_paths)
    return len(violations) == 0, violations


def score_recall_response(
    response_data: dict[str, Any],
    *,
    stream_stdout: str = "",
) -> RecallScore:
    """Deterministically score structured recall answers and verify zero `src/` reads."""
    zero_src, violations = verify_zero_src_reads(stream_stdout)
    outcomes: list[AssertionOutcome] = []
    passed = 0
    for assertion in RECALL_ASSERTIONS:
        try:
            ok = bool(assertion.predicate(response_data))
        except Exception:
            ok = False
        if ok:
            passed += 1
        outcomes.append(
            AssertionOutcome(
                assertion_id=assertion.assertion_id,
                description=assertion.description,
                passed=ok,
            )
        )
    total = len(RECALL_ASSERTIONS)
    acc = round((passed / total) * 100.0, 2) if total > 0 else 0.0
    return RecallScore(
        total_assertions=total,
        passed_assertions=passed,
        accuracy_pct=acc,
        zero_src_reads=zero_src,
        src_read_violations=violations,
        details=outcomes,
    )


_EXPECTED_RECALL_KEYS: frozenset[str] = frozenset(RECALL_JSON_SCHEMA["properties"].keys())


def _parse_json_candidate(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw if raw else None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```"):
            end_idx = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[1:end_idx]).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed:
        return parsed
    return None


def _extract_structured_result(stdout: str) -> dict[str, Any]:
    matched_recall: dict[str, Any] = {}
    fallback_dict: dict[str, Any] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue

        candidates: list[object] = []
        result_obj = ev.get("result")
        if isinstance(result_obj, dict):
            candidates.append(result_obj.get("structured_output"))
            candidates.append(result_obj.get("response"))
        step_obj = ev.get("step_update")
        if isinstance(step_obj, dict):
            candidates.append(step_obj.get("text_delta"))

        candidates.extend(
            [
                ev.get("structured_output"),
                ev.get("result"),
                ev.get("text"),
                ev.get("content"),
            ]
        )
        message = ev.get("message")
        if isinstance(message, dict):
            msg_content = message.get("content")
            candidates.append(msg_content)
            if isinstance(msg_content, list):
                for block in msg_content:
                    if isinstance(block, dict):
                        candidates.append(block.get("text"))
                        candidates.append(block.get("content"))
                    else:
                        candidates.append(block)
        if isinstance(ev.get("content"), list):
            for block in ev["content"]:
                if isinstance(block, dict):
                    candidates.append(block.get("text"))
                    candidates.append(block.get("content"))
                else:
                    candidates.append(block)
        candidates.append(ev)

        for cand in candidates:
            parsed = _parse_json_candidate(cand)
            if parsed is None:
                continue
            if parsed.keys() & _EXPECTED_RECALL_KEYS:
                matched_recall = parsed
            elif not matched_recall:
                fallback_dict = parsed
    return matched_recall or fallback_dict


def run_blind_recall_probe_with_artifacts(
    workspace: Path,
    *,
    agy_runner: SessionAgyRunner | None = None,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    timeout_seconds: int = 180,
) -> tuple[RecallScore, dict[str, Any], str]:
    """Run a cold-start blind recall probe with `.agents/hooks.json` `PreToolUse` deny hook."""
    runner = agy_runner or default_live_agy_runner
    question_lines = "\n".join(f"- {q.question_id}: {q.prompt}" for q in RECALL_QUESTIONS)
    prompt = (
        "Answer the following questions about the current repository state using ONLY project "
        "documentation. Do NOT read or inspect any file under src/.\n\n" + question_lines
    )

    agents_dir = workspace / ".agents"
    hooks_path = agents_dir / "hooks.json"
    agents_dir_existed = agents_dir.exists()
    prior_hooks_bytes = hooks_path.read_bytes() if hooks_path.is_file() else None

    try:
        agents_dir.mkdir(parents=True, exist_ok=True)
        hooks_path.write_text(
            json.dumps(build_src_deny_hook_config(get_deny_hook_script_path()), indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        with tempfile.TemporaryDirectory(prefix="brain79_recall_") as tmp_dir:
            schema_path = Path(tmp_dir) / "schema.json"
            schema_path.write_text(json.dumps(RECALL_JSON_SCHEMA, indent=2), encoding="utf-8")

            cmd = [
                "agy",
                "-p",
                prompt,
                "--model",
                model,
                "--effort",
                effort,
                "--output-format",
                "stream-json",
                "--json-schema",
                str(schema_path),
                "--dangerously-skip-permissions",
                "--print-timeout",
                f"{timeout_seconds}s",
            ]
            result: AgyRunResult = runner(cmd, workspace, timeout_seconds)
    finally:
        if prior_hooks_bytes is not None:
            hooks_path.write_bytes(prior_hooks_bytes)
        elif hooks_path.exists():
            hooks_path.unlink()
        if not agents_dir_existed and agents_dir.is_dir():
            try:
                agents_dir.rmdir()
            except OSError:
                pass

    payload = _extract_structured_result(result.stdout)
    score = score_recall_response(payload, stream_stdout=result.stdout)
    return score, payload, result.stdout


def run_blind_recall_probe(
    workspace: Path,
    *,
    agy_runner: SessionAgyRunner | None = None,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    timeout_seconds: int = 180,
) -> RecallScore:
    """Run a cold-start blind recall probe with `PreToolUse` `src/` deny hook enforced."""
    score, _, _ = run_blind_recall_probe_with_artifacts(
        workspace,
        agy_runner=agy_runner,
        model=model,
        effort=effort,
        timeout_seconds=timeout_seconds,
    )
    return score


__all__ = [
    "AssertionOutcome",
    "RECALL_ASSERTIONS",
    "RECALL_JSON_SCHEMA",
    "RECALL_QUESTIONS",
    "RecallAssertion",
    "RecallQuestion",
    "RecallScore",
    "build_src_deny_hook_config",
    "get_deny_hook_script_path",
    "run_blind_recall_probe",
    "run_blind_recall_probe_with_artifacts",
    "score_recall_response",
    "verify_zero_src_reads",
]
