"""Tests for SPEC-202611 R-5.1 / AC-5: segment-bounded suffix matching in Phase 16 evaluator."""

from __future__ import annotations

from pathlib import Path

from benchmarks.anti_rot.evaluator import evaluate_arm
from benchmarks.anti_rot.runner import SessionRecord


def _dummy_records(arm: str) -> list[SessionRecord]:
    def _rec(sid: str, changed: list[str]) -> SessionRecord:
        return SessionRecord(
            arm=arm,
            session_id=sid,
            title=sid,
            triage_type="C",
            prompt_sha256="a" * 64,
            exit_code=0,
            timed_out=False,
            retries=0,
            duration_seconds=0.1,
            changed_paths=changed,
            commit_sha="0" * 40,
            git_diff_stat="",
            pytest_passed=True,
            node_tests_passed=True,
            contract_passed=True,
            contract_errors=[],
            clean_completion=True,
            conversation_id=f"conv-{arm}-{sid}",
            input_tokens=100,
            output_tokens=50,
            tool_calls=1,
            doc_read_tokens=100,
            src_read_paths=[],
        )

    return [
        _rec("S1", []),
        _rec("S9", []),
        _rec("S10", [".brain-79/topics/t.md" if arm == "arm_a" else "docs/research/t.md"]),
    ]


def _setup_synthetic_workspace(tmp_path: Path, *, arm: str) -> Path:
    ws = tmp_path / f"ws_{arm}"
    (ws / "src" / "ledgerpulse" / "reconciliation").mkdir(parents=True)
    (ws / "src" / "a" / "utils").mkdir(parents=True)
    (ws / "src" / "b" / "utils").mkdir(parents=True)

    (ws / "src" / "ledgerpulse" / "reconciliation" / "matcher.py").write_text(
        "def match_invoices():\n    return True\n", encoding="utf-8"
    )
    (ws / "src" / "a" / "utils" / "helpers.py").write_text(
        "def format_amount(x):\n    return str(x)\n", encoding="utf-8"
    )
    (ws / "src" / "b" / "utils" / "helpers.py").write_text(
        "def parse_date(x):\n    return x\n", encoding="utf-8"
    )

    if arm == "arm_a":
        doc_dir = ws / ".brain-79" / "features"
        doc_dir.mkdir(parents=True)
        (ws / ".brain-79" / "topics").mkdir(parents=True)
        (ws / ".brain-79" / "topics" / "t.md").write_text("# Research\n", encoding="utf-8")
        doc_path = doc_dir / "reconciliation.md"
        doc_path.write_text(
            "---\n"
            "type: feature\n"
            "status: shipped\n"
            "summary: Reconciliation module.\n"
            "applies_to:\n"
            "  - src/ledgerpulse/reconciliation/matcher.py\n"
            "---\n\n"
            "# Reconciliation\n\n"
            "- Unique suffix: `reconciliation/matcher.py`\n"
            "- Ambiguous suffix: `utils/helpers.py`\n"
            "- Non-segment-bounded stale: `old_reconciliation/matcher.py`\n"
            "- Missing path stale: `reconciliation/legacy.py`\n"
            "- Missing basename stale: `reconcile.py`\n",
            encoding="utf-8",
        )
    else:
        doc_dir = ws / "docs"
        doc_dir.mkdir(parents=True)
        (ws / "docs" / "research").mkdir(parents=True)
        (ws / "docs" / "research" / "t.md").write_text("# Research\n", encoding="utf-8")
        doc_path = doc_dir / "reconciliation.md"
        doc_path.write_text(
            "# Reconciliation\n\n"
            "- Unique suffix: `reconciliation/matcher.py`\n"
            "- Ambiguous suffix: `utils/helpers.py`\n"
            "- Non-segment-bounded stale: `old_reconciliation/matcher.py`\n"
            "- Missing path stale: `reconciliation/legacy.py`\n"
            "- Missing basename stale: `reconcile.py`\n",
            encoding="utf-8",
        )
    return ws


def test_ac5_arm_b_suffix_matching_and_canonical_coverage(tmp_path: Path) -> None:
    ws = _setup_synthetic_workspace(tmp_path, arm="arm_b")
    res = evaluate_arm("arm_b", ws, _dummy_records("arm_b"))

    # 5 refs total: reconciliation/matcher.py (valid), utils/helpers.py (valid),
    # old_reconciliation/matcher.py (stale), reconciliation/legacy.py (stale), reconcile.py (stale)
    assert res.total_refs == 5
    assert res.stale_refs == 3
    stale_joined = "\n".join(res.stale_details)
    assert "`old_reconciliation/matcher.py`" in stale_joined
    assert "`reconciliation/legacy.py`" in stale_joined
    assert "`reconcile.py`" in stale_joined
    assert "`reconciliation/matcher.py`" not in stale_joined
    assert "`utils/helpers.py`" not in stale_joined

    # Only unique match (reconciliation/matcher.py -> src/ledgerpulse/reconciliation/matcher.py)
    # is credited to canonical coverage; utils/helpers.py (2 matches) is NOT credited.
    assert res.canonical_sources_total == 3
    assert res.canonical_sources_covered == 1


def test_ac5_arm_a_suffix_matching(tmp_path: Path) -> None:
    ws = _setup_synthetic_workspace(tmp_path, arm="arm_a")
    res = evaluate_arm(
        "arm_a",
        ws,
        _dummy_records("arm_a"),
        telemetry_override={
            "lint_strict_errors": 0,
            "lint_strict_exit_code": 0,
            "ci_check_exit_code": 0,
            "drifted_articles": [],
            "orient_chars": 500,
        },
    )

    assert res.total_refs == 5
    assert res.stale_refs == 3
    stale_joined = "\n".join(res.stale_details)
    assert "`old_reconciliation/matcher.py`" in stale_joined
    assert "`reconciliation/legacy.py`" in stale_joined
    assert "`reconcile.py`" in stale_joined
    assert "`reconciliation/matcher.py`" not in stale_joined
    assert "`utils/helpers.py`" not in stale_joined


def test_r5_1_doc_exclusion_invariance_and_dot_slash_normalization(tmp_path: Path) -> None:
    ws = tmp_path / "ws_doc_excl"
    (ws / "src" / "pkg").mkdir(parents=True)
    (ws / "src" / "pkg" / "app.py").write_text("x = 1\n", encoding="utf-8")

    # Place a matching file ONLY under docs/ and .brain-79/ — must NOT count as non-doc match!
    (ws / "docs" / "reconciliation").mkdir(parents=True)
    (ws / "docs" / "reconciliation" / "matcher.py").write_text("# doc\n", encoding="utf-8")
    (ws / ".brain-79" / "reconciliation").mkdir(parents=True)
    (ws / ".brain-79" / "reconciliation" / "matcher.py").write_text("# wiki\n", encoding="utf-8")

    # Dotfile path under .github/ must preserve its leading dot (F-2)
    (ws / ".github" / "workflows").mkdir(parents=True)
    (ws / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    (ws / "docs" / "guide.md").write_text(
        "# Guide\n\n"
        "- Doc-only path: `reconciliation/matcher.py`\n"
        "- Dot-slash path: `./pkg/app.py`\n"
        "- Dotfile path: `.github/workflows/ci.yml`\n",
        encoding="utf-8",
    )

    res = evaluate_arm("arm_b", ws, _dummy_records("arm_b"))
    assert res.total_refs == 3
    assert res.stale_refs == 1
    assert any("reconciliation/matcher.py" in d for d in res.stale_details)
    assert res.canonical_sources_covered == 1
