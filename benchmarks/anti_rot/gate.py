"""Binary release gate verdict engine and results.json / report.md generator (SPEC-016 R-5.1..R-5.3)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from benchmarks.anti_rot.evaluator import MAX_ORIENT_INLINE_CHARS, ArmEvaluation
from benchmarks.anti_rot.recall import RecallScore
from benchmarks.anti_rot.runner import SessionRecord


@dataclass(frozen=True)
class BenchmarkVerdict:
    """Binary release gate verdict with per-criterion breakdown and forensic reasons."""

    verdict: str  # "PASS" | "FAIL"
    criteria: dict[str, bool]
    failed_criteria: list[str]
    failure_reasons: dict[str, str]
    arm_a: ArmEvaluation
    arm_b: ArmEvaluation
    recall_a: RecallScore
    recall_b: RecallScore


def evaluate_release_gate(
    arm_a: ArmEvaluation,
    arm_b: ArmEvaluation,
    recall_a: RecallScore,
    recall_b: RecallScore,
) -> BenchmarkVerdict:
    """Evaluate all 7 mandatory `SPEC-016` R-5.1 release gate criteria."""
    criteria: dict[str, bool] = {}
    reasons: dict[str, str] = {}

    # 1. Structural & drift health
    c1 = (
        arm_a.lint_strict_errors == 0
        and arm_a.ci_check_exit_code == 0
        and arm_a.drifted_articles_count == 0
    )
    criteria["arm_a_structural_and_drift"] = c1
    if not c1:
        reasons["arm_a_structural_and_drift"] = (
            f"lint_strict_errors={arm_a.lint_strict_errors}, "
            f"ci_check_exit_code={arm_a.ci_check_exit_code}, "
            f"drifted_articles={arm_a.drifted_articles}"
        )

    # 2. Zero-safe documentation rot rate
    rot_rel_ok = (
        arm_a.rot_rate_pct <= 0.5 * arm_b.rot_rate_pct
        if arm_b.rot_rate_pct > 5.0
        else arm_a.rot_rate_pct <= arm_b.rot_rate_pct
    )
    c2 = arm_a.min_density_met and arm_a.rot_rate_pct <= 5.0 and rot_rel_ok
    criteria["arm_a_rot_rate"] = c2
    if not c2:
        reasons["arm_a_rot_rate"] = (
            f"min_density_met={arm_a.min_density_met} (refs={arm_a.total_refs}), "
            f"rot_A={arm_a.rot_rate_pct}%, rot_B={arm_b.rot_rate_pct}%, "
            f"stale_details={arm_a.stale_details[:5]}"
        )

    # 3. Canonical source governance coverage
    c3 = (
        arm_a.canonical_coverage_pct >= 85.0
        and arm_a.canonical_coverage_pct >= arm_b.canonical_coverage_pct
    )
    criteria["arm_a_canonical_coverage"] = c3
    if not c3:
        reasons["arm_a_canonical_coverage"] = (
            f"cov_A={arm_a.canonical_coverage_pct}% "
            f"({arm_a.canonical_sources_covered}/{arm_a.canonical_sources_total}), "
            f"cov_B={arm_b.canonical_coverage_pct}%"
        )

    # 4. Context budget ceiling
    c4 = arm_a.orient_chars <= MAX_ORIENT_INLINE_CHARS
    criteria["arm_a_context_budget"] = c4
    if not c4:
        reasons["arm_a_context_budget"] = (
            f"orient_chars={arm_a.orient_chars} > MAX_ORIENT_INLINE_CHARS={MAX_ORIENT_INLINE_CHARS}"
        )

    # 5. Autonomous compliance
    c5 = arm_a.clean_completions >= 10
    criteria["arm_a_autonomous_compliance"] = c5
    if not c5:
        reasons["arm_a_autonomous_compliance"] = (
            f"clean_completions_A={arm_a.clean_completions}/{arm_a.total_sessions} (< 10/12)"
        )

    # 6. Ceiling-aware blind semantic recall
    recall_rel_ok = (
        recall_a.accuracy_pct >= recall_b.accuracy_pct + 15.0
        if recall_b.accuracy_pct <= 80.0
        else recall_a.accuracy_pct >= recall_b.accuracy_pct
    )
    c6 = recall_a.zero_src_reads and recall_a.accuracy_pct >= 80.0 and recall_rel_ok
    criteria["arm_a_blind_recall"] = c6
    if not c6:
        reasons["arm_a_blind_recall"] = (
            f"zero_src_reads_A={recall_a.zero_src_reads} "
            f"(violations={recall_a.src_read_violations}), "
            f"acc_A={recall_a.accuracy_pct}%, acc_B={recall_b.accuracy_pct}%"
        )

    # 7. Session triage (S9 + S10)
    c7 = arm_a.s9_passed and arm_a.s10_passed
    criteria["arm_a_session_triage"] = c7
    if not c7:
        reasons["arm_a_session_triage"] = (
            f"s9_passed_A={arm_a.s9_passed}, s10_passed_A={arm_a.s10_passed}"
        )

    failed = [name for name, ok in criteria.items() if not ok]
    verdict = "PASS" if not failed else "FAIL"
    return BenchmarkVerdict(
        verdict=verdict,
        criteria=criteria,
        failed_criteria=failed,
        failure_reasons=reasons,
        arm_a=arm_a,
        arm_b=arm_b,
        recall_a=recall_a,
        recall_b=recall_b,
    )


def _render_markdown_report(
    verdict: BenchmarkVerdict,
    records: list[SessionRecord],
    metadata: dict[str, Any],
) -> str:
    lines: list[str] = [
        "# Phase 16 longitudinal anti-rot release gate report",
        "",
        f"- **Verdict**: **{verdict.verdict}**",
        f"- **Model**: `{metadata.get('model', 'unknown')}`",
        f"- **Agy version**: `{metadata.get('agy_version', 'unknown')}`",
        f"- **Brain79 version**: `{metadata.get('brain79_version', 'unknown')}`",
        f"- **Git SHA**: `{metadata.get('git_sha', 'unknown')}`",
        "",
        "## Methodology",
        "",
        "Two isolated Git repositories (Arm A: `.brain-79/` with strict enforcement; Arm B: `AGENTS.md` + `docs/`) "
        "were initialized from identical `commit 0` of `LedgerPulse` and driven through 12 cold-start sessions (`S1`–`S12`) "
        "followed by a mechanically enforced blind semantic-recall probe (`PreToolUse` `src/` deny hook).",
        "",
        "## Release gate criteria",
        "",
        "| Criterion | Status | Evidence |",
        "|---|---|---|",
    ]
    for name, ok in verdict.criteria.items():
        status = "PASS" if ok else "FAIL"
        evidence = verdict.failure_reasons.get(name, "Met threshold")
        lines.append(f"| `{name}` | {status} | {evidence} |")

    lines.extend(
        [
            "",
            "## Arm comparison summary",
            "",
            "| Metric | Arm A (brain-79) | Arm B (control) |",
            "|---|---|---|",
            f"| Active living docs | {verdict.arm_a.active_doc_count} | {verdict.arm_b.active_doc_count} |",
            f"| Documentation rot rate | {verdict.arm_a.rot_rate_pct}% ({verdict.arm_a.stale_refs}/{verdict.arm_a.total_refs}) | {verdict.arm_b.rot_rate_pct}% ({verdict.arm_b.stale_refs}/{verdict.arm_b.total_refs}) |",
            f"| Canonical `src/**` coverage | {verdict.arm_a.canonical_coverage_pct}% ({verdict.arm_a.canonical_sources_covered}/{verdict.arm_a.canonical_sources_total}) | {verdict.arm_b.canonical_coverage_pct}% ({verdict.arm_b.canonical_sources_covered}/{verdict.arm_b.canonical_sources_total}) |",
            f"| Orient chars | {verdict.arm_a.orient_chars} | N/A |",
            f"| Total doc-read tokens | {verdict.arm_a.total_doc_read_tokens} | {verdict.arm_b.total_doc_read_tokens} |",
            f"| Autonomous compliance | {verdict.arm_a.clean_completions}/{verdict.arm_a.total_sessions} ({verdict.arm_a.autonomous_compliance_pct}%) | {verdict.arm_b.clean_completions}/{verdict.arm_b.total_sessions} ({verdict.arm_b.autonomous_compliance_pct}%) |",
            f"| Blind semantic recall | {verdict.recall_a.accuracy_pct}% ({verdict.recall_a.passed_assertions}/{verdict.recall_a.total_assertions}) | {verdict.recall_b.accuracy_pct}% ({verdict.recall_b.passed_assertions}/{verdict.recall_b.total_assertions}) |",
            "",
            "## Per-session telemetry",
            "",
            "| Arm | Session | Triage | Clean | Exit | Contract | Doc-read tokens |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for rec in records:
        lines.append(
            f"| `{rec.arm}` | `{rec.session_id}` | `{rec.triage_type}` | "
            f"{rec.clean_completion} | {rec.exit_code} | {rec.contract_passed} | {rec.doc_read_tokens} |"
        )

    if verdict.failed_criteria:
        lines.extend(["", "## Failed criteria and forensic evidence", ""])
        for crit in verdict.failed_criteria:
            lines.append(f"- **{crit}**: {verdict.failure_reasons.get(crit, 'Failed')}")

    return "\n".join(lines) + "\n"


def write_gate_reports(
    output_dir: Path,
    verdict: BenchmarkVerdict,
    *,
    records: list[SessionRecord],
    metadata: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Emit `results.json` and `report.md` into `output_dir`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    meta = metadata or {}
    payload = {
        "verdict": verdict.verdict,
        "criteria": verdict.criteria,
        "failed_criteria": verdict.failed_criteria,
        "failure_reasons": verdict.failure_reasons,
        "metadata": meta,
        "arm_a": asdict(verdict.arm_a),
        "arm_b": asdict(verdict.arm_b),
        "recall_a": asdict(verdict.recall_a),
        "recall_b": asdict(verdict.recall_b),
        "sessions": [asdict(r) for r in records],
    }
    results_path = output_dir / "results.json"
    report_path = output_dir / "report.md"
    results_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    report_path.write_text(_render_markdown_report(verdict, records, meta), encoding="utf-8", newline="\n")
    return results_path, report_path


__all__ = [
    "BenchmarkVerdict",
    "evaluate_release_gate",
    "write_gate_reports",
]
