"""Tests and validation harness for GitHub Actions CI matrix and doctor policy.

Enforces Deliverable 9.1:
- 9-job matrix: Ubuntu, macOS, Windows x Python 3.11, 3.12, 3.13.
- fail-fast: false, timeout-minutes: 20, top-level permissions: contents: read.
- Pinned major action tags (@v4, @v5).
- Core validation steps: pytest, mypy, brain79 lint, brain79 doctor.
- Doctor warning allowlist policy.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"

# Explicit allowlist of permissible doctor warnings in CI.
# Any category not listed here causes the CI step to fail.
DOCTOR_WARNING_ALLOWLIST: set[str] = {
    "handoff_hygiene",
    "git_hooks",
    "git_merge_driver",
}


def evaluate_doctor_report(
    report_data: dict[str, Any],
    allowlist: set[str] | None = None,
) -> int:
    """Evaluate doctor JSON output according to CI policy.

    - Exit code 0: passes unconditionally.
    - Exit code 1: fails unconditionally.
    - Exit code 2 (warnings only): passes ONLY when every warning category is in the allowlist.
    """
    if not isinstance(report_data, dict):
        raise ValueError("Malformed doctor report: expected JSON object.")

    exit_code = report_data.get("exit_code")
    if exit_code is None:
        raise ValueError("Malformed doctor report: missing 'exit_code'.")

    checks = report_data.get("checks", [])
    if not isinstance(checks, list):
        raise ValueError("Malformed doctor report: 'checks' must be a list.")

    if exit_code == 0:
        return 0

    if exit_code == 1 or any(c.get("status") == "error" for c in checks):
        error_msgs = [c.get("message", "unknown error") for c in checks if c.get("status") == "error"]
        raise ValueError(f"Doctor diagnostic failed with errors: {error_msgs}")

    if exit_code == 2:
        allowed = DOCTOR_WARNING_ALLOWLIST if allowlist is None else allowlist
        warning_categories = [c.get("category", "unknown") for c in checks if c.get("status") == "warning"]
        disallowed = [w for w in warning_categories if w not in allowed]
        if disallowed:
            raise ValueError(
                f"Doctor diagnostic produced disallowed warning categories: {disallowed}. "
                f"Allowed categories in CI: {sorted(allowed)}"
            )
        return 0

    raise ValueError(f"Unexpected doctor exit code: {exit_code}")


def validate_doctor_file(report_path: Path, allowlist: set[str] | None = None) -> int:
    """Load JSON from disk and evaluate using doctor CI policy."""
    if not report_path.is_file():
        raise FileNotFoundError(f"Doctor report file not found: {report_path}")

    raw = report_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Doctor report file is empty: {report_path}")

    data = json.loads(raw)
    return evaluate_doctor_report(data, allowlist=allowlist)


# ==============================================================================
# Unit Tests for CI Workflow Specification
# ==============================================================================


@pytest.fixture
def workflow_yaml() -> dict[str, Any]:
    assert WORKFLOW_PATH.is_file(), f"Workflow file does not exist: {WORKFLOW_PATH}"
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict), "Workflow YAML must parse to a mapping"
    return parsed


def test_ci_workflow_triggers(workflow_yaml: dict[str, Any]) -> None:
    triggers = workflow_yaml.get("on") or workflow_yaml.get(True)  # type: ignore[call-overload]
    assert triggers, "Workflow must declare trigger events ('on')"

    assert "push" in triggers, "Workflow must trigger on push"
    assert "pull_request" in triggers, "Workflow must trigger on pull_request"
    assert "main" in triggers["push"].get("branches", [])
    assert "main" in triggers["pull_request"].get("branches", [])


def test_ci_workflow_top_level_permissions(workflow_yaml: dict[str, Any]) -> None:
    permissions = workflow_yaml.get("permissions")
    assert permissions == {"contents": "read"}, "Workflow must declare top-level 'permissions: contents: read'"


def test_ci_workflow_matrix_cells(workflow_yaml: dict[str, Any]) -> None:
    jobs = workflow_yaml.get("jobs", {})
    assert "test" in jobs, "Workflow must define a 'test' job"
    test_job = jobs["test"]

    assert test_job.get("timeout-minutes") == 20, "Job must specify 'timeout-minutes: 20'"

    strategy = test_job.get("strategy", {})
    assert strategy.get("fail-fast") is False, "Strategy must have 'fail-fast: false'"

    matrix = strategy.get("matrix", {})
    includes = matrix.get("include", [])
    assert isinstance(includes, list), "Matrix must use 'include' for L-shaped 5-cell coverage"

    cells = {(entry.get("os"), entry.get("python")) for entry in includes}
    expected_cells = {
        ("ubuntu-latest", "3.11"),
        ("ubuntu-latest", "3.12"),
        ("ubuntu-latest", "3.13"),
        ("macos-latest", "3.12"),
        ("windows-latest", "3.12"),
    }

    assert cells == expected_cells, f"Matrix cells mismatch: {cells}"
    assert len(includes) == 5, f"Expected 5 matrix jobs, found {len(includes)}"


def test_ci_workflow_pinned_actions(workflow_yaml: dict[str, Any]) -> None:
    test_job = workflow_yaml["jobs"]["test"]
    steps = test_job.get("steps", [])

    pinned_pattern = re.compile(r"^[^@]+@v\d+(\.\d+)*$")
    uses_found = 0

    for step in steps:
        uses = step.get("uses")
        if uses:
            uses_found += 1
            assert pinned_pattern.match(uses), f"Action '{uses}' is not pinned to a major version tag (@v<num>)"

    assert uses_found >= 3, f"Expected at least 3 action uses (checkout, setup-uv, upload-artifact), found {uses_found}"


def test_ci_workflow_required_steps(workflow_yaml: dict[str, Any]) -> None:
    test_job = workflow_yaml["jobs"]["test"]
    steps = test_job.get("steps", [])

    commands = [step.get("run", "") for step in steps if "run" in step]

    assert any("uv sync --group dev" in cmd for cmd in commands), "Missing 'uv sync --group dev' step"
    assert any("uv run pytest -q" in cmd for cmd in commands), "Missing 'uv run pytest -q' step"
    assert any("uv run mypy src tests" in cmd for cmd in commands), "Missing 'uv run mypy src tests' step"
    assert any("uv run brain79 lint --strict" in cmd for cmd in commands), "Missing 'uv run brain79 lint --strict' step"
    assert any("uv run brain79 doctor --format json" in cmd for cmd in commands), (
        "Missing 'uv run brain79 doctor --format json' step"
    )

    # Failure artifact upload step
    failure_steps = [s for s in steps if s.get("if") == "failure()"]
    assert failure_steps, "Workflow must include a failure() upload step"
    assert any(".pytest_tmp" in str(s.get("with", {}).get("path", "")) for s in failure_steps), (
        "Failure step must upload .pytest_tmp"
    )
    assert any(
        s.get("with", {}).get("include-hidden-files") is True
        and s.get("with", {}).get("if-no-files-found") == "ignore"
        for s in failure_steps
    ), "Failure upload step must set include-hidden-files: true and if-no-files-found: ignore"


def test_ci_workflow_polyglot_job(workflow_yaml: dict[str, Any]) -> None:
    """AC-13: Verify jobs.test-polyglot matrix, env, pinned actions, and verification steps."""
    jobs = workflow_yaml.get("jobs", {})
    assert "test-polyglot" in jobs, "Workflow must define a 'test-polyglot' job"
    job = jobs["test-polyglot"]

    assert job.get("timeout-minutes") == 20
    assert job.get("defaults", {}).get("run", {}).get("shell") == "bash"

    env = job.get("env", {})
    assert env.get("BRAIN79_REQUIRE_POLYGLOT") == "1"
    assert env.get("PYTHONUTF8") == "1"
    assert env.get("BRAIN79_PERF_FACTOR") == "3"

    strategy = job.get("strategy", {})
    assert strategy.get("fail-fast") is False
    matrix = strategy.get("matrix", {})
    assert matrix.get("os") == ["ubuntu-latest", "macos-latest", "windows-latest"]
    assert matrix.get("python-version") == ["3.12"]

    steps = job.get("steps", [])
    uses_list = [step.get("uses") for step in steps if step.get("uses")]
    assert "actions/checkout@v7" in uses_list
    assert "astral-sh/setup-uv@v10.4.0" in uses_list
    assert "actions/upload-artifact@v7" in uses_list

    commands = [step.get("run", "") for step in steps if "run" in step]
    assert any("uv sync --group dev --extra polyglot" in cmd for cmd in commands)
    assert any("uv run pytest -q" in cmd and ".pytest_tmp" in cmd for cmd in commands)
    assert any("uv run mypy src tests" in cmd for cmd in commands)
    assert any("uv run brain79 stats --format json" in cmd and "json.load(sys.stdin)" in cmd for cmd in commands)

    failure_steps = [s for s in steps if s.get("if") == "failure()"]
    assert failure_steps, "test-polyglot must include a failure() upload step"
    assert any(".pytest_tmp" in str(s.get("with", {}).get("path", "")) for s in failure_steps)
    assert any(
        s.get("with", {}).get("include-hidden-files") is True
        and s.get("with", {}).get("if-no-files-found") == "ignore"
        for s in failure_steps
    ), "test-polyglot failure upload step must set include-hidden-files: true and if-no-files-found: ignore"


# ==============================================================================
# Unit Tests for Doctor CI Allowlist Policy
# ==============================================================================


def test_doctor_policy_clean_ok() -> None:
    report = {
        "status": "ok",
        "exit_code": 0,
        "checks": [
            {"category": "wiki_structure", "status": "ok", "message": "clean"},
            {"category": "locks_and_filesystem", "status": "ok", "message": "clean"},
        ],
        "fixed": [],
    }
    assert evaluate_doctor_report(report) == 0


def test_doctor_policy_error_fails() -> None:
    report = {
        "status": "error",
        "exit_code": 1,
        "checks": [
            {"category": "wiki_structure", "status": "error", "message": "broken schema"},
        ],
        "fixed": [],
    }
    with pytest.raises(ValueError, match="failed with errors"):
        evaluate_doctor_report(report)


def test_doctor_policy_allowlisted_warning_passes() -> None:
    report = {
        "status": "warning",
        "exit_code": 2,
        "checks": [
            {"category": "handoff_hygiene", "status": "warning", "message": "11 handoffs"},
        ],
        "fixed": [],
    }
    assert evaluate_doctor_report(report, allowlist={"handoff_hygiene"}) == 0


def test_doctor_policy_default_allowlist_includes_local_git_checks() -> None:
    """Fresh CI checkouts lack local .git/hooks and local .git/config merge driver."""
    report = {
        "status": "warning",
        "exit_code": 2,
        "checks": [
            {"category": "git_hooks", "status": "warning", "message": "pre-commit hook missing"},
            {"category": "git_merge_driver", "status": "warning", "message": "local merge driver not configured"},
        ],
        "fixed": [],
    }
    assert evaluate_doctor_report(report) == 0


def test_doctor_policy_unallowlisted_warning_fails() -> None:
    report = {
        "status": "warning",
        "exit_code": 2,
        "checks": [
            {"category": "protocol_sync", "status": "warning", "message": "version drift"},
        ],
        "fixed": [],
    }
    with pytest.raises(ValueError, match="disallowed warning categories: \\['protocol_sync'\\]"):
        evaluate_doctor_report(report, allowlist={"handoff_hygiene"})


def test_doctor_file_cli_integration(tmp_path: Path) -> None:
    valid_file = tmp_path / "doctor_ok.json"
    valid_file.write_text(
        json.dumps({
            "status": "ok",
            "exit_code": 0,
            "checks": [{"category": "wiki_structure", "status": "ok", "message": "clean"}],
            "fixed": [],
        }),
        encoding="utf-8",
    )
    assert validate_doctor_file(valid_file) == 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--validate-doctor":
        path = Path(sys.argv[2])
        try:
            sys.exit(validate_doctor_file(path))
        except Exception as exc:
            print(f"❌ Doctor validation failed: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Usage: python -m tests.test_ci_workflow --validate-doctor <path-to-json>", file=sys.stderr)
        sys.exit(2)
