"""Stage 1 tests for SPEC-016: LedgerPulse fixture, contracts, and dual-arm isolation (AC-1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.anti_rot import (
    ANTI_ROT_ROOT,
    CONTROL_AGENTS_PATH,
    CONTRACTS_DIR,
    FIXTURE_DIR,
    discover_canonical_sources,
    resolve_git_bin,
)
from benchmarks.anti_rot.contracts import (
    SESSION_CONTRACTS,
    ContractResult,
    run_session_contract,
)
from benchmarks.anti_rot.workspace import (
    DualArmWorkspace,
    FixtureError,
    IsolationError,
    PreflightReport,
    initialize_arms,
    run_preflight_checks,
)
from brain79.core.ast_guards import (
    discover_polyglot_inspectors,
    get_inspector_for_path,
)


def _git_head_sha(repo: Path) -> str:
    git_bin = resolve_git_bin()
    proc = subprocess.run(
        [git_bin, "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _git_first_commit_sha(repo: Path) -> str:
    git_bin = resolve_git_bin()
    proc = subprocess.run(
        [git_bin, "rev-list", "--max-parents=0", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip().splitlines()[0]


def test_package_exports_and_fixture_source_count() -> None:
    """Fixture must exist with 12-15 canonical non-test source files under src/."""
    assert ANTI_ROT_ROOT.is_dir()
    assert FIXTURE_DIR.is_dir()
    assert CONTROL_AGENTS_PATH.is_file()
    assert CONTRACTS_DIR.is_dir()

    sources = discover_canonical_sources(FIXTURE_DIR)
    assert 12 <= len(sources) <= 15, f"Expected 12-15 canonical sources, got {len(sources)}: {sources}"
    assert any(s.startswith("src/ledgerpulse/") and s.endswith(".py") for s in sources)
    assert any(s.startswith("src/reporter/") and s.endswith(".mjs") for s in sources)


def test_fixture_unit_tests_pass_python_and_node() -> None:
    """Both pytest and node --test suites inside LedgerPulse fixture must pass offline."""
    py_proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_ledgerpulse.py"],
        cwd=FIXTURE_DIR,
        capture_output=True,
        text=True,
    )
    assert py_proc.returncode == 0, f"Fixture pytest failed:\n{py_proc.stdout}\n{py_proc.stderr}"

    js_proc = subprocess.run(
        ["node", "--test", "tests/reporter.test.mjs"],
        cwd=FIXTURE_DIR,
        capture_output=True,
        text=True,
    )
    assert js_proc.returncode == 0, f"Fixture node --test failed:\n{js_proc.stdout}\n{js_proc.stderr}"


def test_fixture_sources_supported_by_ast_guard_c() -> None:
    """All canonical .py and .mjs fixture files must be inspectable by Guard C."""
    discover_polyglot_inspectors(reset=True)
    sources = discover_canonical_sources(FIXTURE_DIR)
    for rel in sources:
        inspector = get_inspector_for_path(rel)
        assert inspector is not None, f"No Guard C AST inspector for fixture file: {rel}"
        text = (FIXTURE_DIR / rel).read_text(encoding="utf-8")
        sigs = inspector.extract_signatures(text)
        assert isinstance(sigs, dict)


def test_control_agents_md_parity_and_zero_brain79_leakage() -> None:
    """Control baseline must be realistic, cover Type A/B, and never mention brain79."""
    content = CONTROL_AGENTS_PATH.read_text(encoding="utf-8")
    lower = content.lower()
    assert "brain79" not in lower
    assert ".brain-79" not in lower
    assert "mcp" not in lower
    assert "docs/" in content
    assert "docs/research/" in content
    assert "read-only" in lower or "type a" in lower
    assert "research" in lower


def test_contracts_cover_s2_through_s12_with_pass_and_fail_cases(tmp_path: Path) -> None:
    """Contracts S2-S12 must validate symbols/constants/triage and fail when violated."""
    expected_ids = [f"S{i}" for i in range(2, 13)]
    assert sorted(SESSION_CONTRACTS.keys(), key=lambda s: int(s[1:])) == expected_ids

    # Baseline fixture should fail S2 (feature not yet implemented)
    s2_fail = run_session_contract("S2", FIXTURE_DIR)
    assert isinstance(s2_fail, ContractResult)
    assert not s2_fail.passed
    assert s2_fail.errors

    # Copy fixture to tmp_path and simulate S2 passing
    import shutil

    ws = tmp_path / "ws"
    shutil.copytree(FIXTURE_DIR, ws)
    pricing_file = ws / "src" / "ledgerpulse" / "pricing.py"
    pricing_file.write_text(
        pricing_file.read_text(encoding="utf-8")
        + "\nTIERED_BULK_THRESHOLD = 10\n"
        + "TIERED_BULK_DISCOUNT_BPS = 500\n\n"
        + "def calculate_bulk_discount(items: list[LineItem]) -> int:\n"
        + "    return 0\n",
        encoding="utf-8",
    )
    s2_pass = run_session_contract("S2", ws)
    assert s2_pass.passed, f"Expected S2 to pass, got errors: {s2_pass.errors}"

    # S4 vs S7 constant enforcement: wrong constant value must fail
    tax_file = ws / "src" / "ledgerpulse" / "tax.py"
    orig_tax = tax_file.read_text(encoding="utf-8")
    tax_file.write_text(
        orig_tax
        + "\nLATE_FEE_BPS = 999\nLATE_FEE_GRACE_DAYS = 15\n\n"
        + "def calculate_late_fee(amount_cents: int, days_overdue: int) -> int:\n    return 0\n",
        encoding="utf-8",
    )
    s4_wrong = run_session_contract("S4", ws)
    assert not s4_wrong.passed
    assert any("LATE_FEE_BPS" in err for err in s4_wrong.errors)

    tax_file.write_text(
        orig_tax
        + "\nLATE_FEE_BPS = 250\nLATE_FEE_GRACE_DAYS = 15\n\n"
        + "def calculate_late_fee(amount_cents: int, days_overdue: int) -> int:\n    return 0\n",
        encoding="utf-8",
    )
    s4_pass = run_session_contract("S4", ws)
    assert s4_pass.passed, f"Expected S4 to pass, got errors: {s4_pass.errors}"

    # S9 Type A triage: permanent doc or src mutation fails; ephemeral handoffs/_raw ignored
    s9_fail = run_session_contract("S9", ws, changed_paths=[".brain-79/INDEX.md"])
    assert not s9_fail.passed
    s9_ephemeral = run_session_contract("S9", ws, changed_paths=[".brain-79/handoffs/2026-11-26.md"])
    assert s9_ephemeral.passed
    s9_pass = run_session_contract("S9", ws, changed_paths=[])
    assert s9_pass.passed

    # S10 Type B triage: src mutation fails; pre-existing research with empty changed_paths fails; new research passes
    s10_fail = run_session_contract("S10", ws, changed_paths=["src/ledgerpulse/tax.py"])
    assert not s10_fail.passed
    research_doc = ws / "docs" / "research" / "fee-analysis.md"
    research_doc.parent.mkdir(parents=True, exist_ok=True)
    research_doc.write_text("# Fee analysis\n\nDetailed findings.\n", encoding="utf-8")
    s10_noop = run_session_contract("S10", ws, changed_paths=[])
    assert not s10_noop.passed
    s10_pass = run_session_contract("S10", ws, changed_paths=["docs/research/fee-analysis.md"])
    assert s10_pass.passed


def test_initialize_arms_creates_identical_commit0_and_strict_isolation(tmp_path: Path) -> None:
    """Arm A and Arm B must share commit 0 SHA, with strict brain79 in A and zero in B."""
    arms = initialize_arms(base_dir=tmp_path)
    assert isinstance(arms, DualArmWorkspace)
    assert arms.arm_a.is_dir()
    assert arms.arm_b.is_dir()

    # Identical commit 0 SHA
    c0_a = _git_first_commit_sha(arms.arm_a)
    c0_b = _git_first_commit_sha(arms.arm_b)
    assert c0_a == c0_b == arms.commit_zero_sha

    # Arm A has .brain-79/ with enforcement: strict and native agy plugin + hooks, no git hooks
    schema_text = (arms.arm_a / ".brain-79" / "SCHEMA.md").read_text(encoding="utf-8")
    assert "enforcement: strict" in schema_text
    assert (arms.arm_a / ".agents" / "plugins" / "brain79" / "mcp_config.json").is_file()
    assert (arms.arm_a / ".agents" / "plugins" / "brain79" / "hooks.json").is_file()
    assert not (arms.arm_a / ".git" / "hooks" / "pre-commit").exists()

    # Arm B has AGENTS.md from control_agents.md and zero .brain-79/ or hooks
    assert (arms.arm_b / "AGENTS.md").read_text(encoding="utf-8") == CONTROL_AGENTS_PATH.read_text(encoding="utf-8")
    assert not (arms.arm_b / ".brain-79").exists()
    assert not (arms.arm_b / ".agents").exists()

    # Missing fixture raises FixtureError
    with pytest.raises(FixtureError):
        initialize_arms(base_dir=tmp_path / "bad", fixture_dir=tmp_path / "nonexistent")


def test_preflight_checks_fail_closed_on_leakage_and_missing_hooks(tmp_path: Path) -> None:
    """Preflight probe must pass on clean probes and fail-closed on leakage or bad output."""
    arms = initialize_arms(base_dir=tmp_path)

    seen_cmds: list[list[str]] = []

    def clean_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        seen_cmds.append(cmd)
        if cwd == arms.arm_a:
            events = [
                {"type": "hook", "hookEventName": "SessionStart", "status": "ok"},
                {"type": "init", "tools": ["read_file", "brain79_orient", "brain79_session_commit"]},
                {"type": "result", "status": "success"},
            ]
        else:
            events = [
                {"type": "init", "tools": ["read_file", "write_file", "run_command"]},
                {"type": "result", "status": "success"},
            ]
        stdout = "\n".join(json.dumps(e) for e in events) + "\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    report = run_preflight_checks(arms, agy_runner=clean_runner)
    assert isinstance(report, PreflightReport)
    assert report.passed
    assert report.arm_b_brain79_tools == []
    assert report.arm_a_hooks_verified
    assert len(seen_cmds) == 2
    for cmd in seen_cmds:
        assert "--model" in cmd and "gemini-4-hydrogen-low" in cmd
        assert "--effort" in cmd and "low" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "--print-timeout" in cmd and "60s" in cmd

    # Leakage in Arm B (including namespaced MCP tool names) fails closed
    def leaky_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if cwd == arms.arm_b:
            events = [{"type": "init", "tools": ["read_file", "mcp__brain79__brain79_orient"]}]
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(events[0]) + "\n", stderr="")
        return clean_runner(cmd, cwd)

    with pytest.raises(IsolationError, match="brain79"):
        run_preflight_checks(arms, agy_runner=leaky_runner)

    # Missing brain79 MCP tools in Arm A fails closed
    def no_mcp_in_a_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if cwd == arms.arm_a:
            events = [
                {"type": "hook", "hookEventName": "SessionStart", "status": "ok"},
                {"type": "init", "tools": ["read_file", "write_file"]},
            ]
            return subprocess.CompletedProcess(
                cmd, 0, stdout="\n".join(json.dumps(e) for e in events) + "\n", stderr=""
            )
        return clean_runner(cmd, cwd)

    with pytest.raises(IsolationError, match="brain79 MCP tools"):
        run_preflight_checks(arms, agy_runner=no_mcp_in_a_runner)

    # Unparseable/missing tool inventory in Arm B fails closed
    def empty_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout="not-json\n", stderr="")

    with pytest.raises(IsolationError):
        run_preflight_checks(arms, agy_runner=empty_runner)

    # Missing hook evidence in Arm A probe fails closed
    def no_hook_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if cwd == arms.arm_a:
            events = [{"type": "init", "tools": ["read_file", "brain79_orient"]}]
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(events[0]) + "\n", stderr="")
        return clean_runner(cmd, cwd)

    with pytest.raises(IsolationError, match="hook"):
        run_preflight_checks(arms, agy_runner=no_hook_runner)


def test_preflight_checks_real_agy_wire_format(tmp_path: Path) -> None:
    """Preflight must handle real agy nested init.tools, step_update(system_message), and result.structured_output."""
    arms = initialize_arms(base_dir=tmp_path)

    def real_agy_runner(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert "--json-schema" in cmd
        if cwd == arms.arm_a:
            events = [
                {
                    "event": "init",
                    "conversation_id": "conv-a",
                    "init": {
                        "model": "gemini-4-hydrogen-low",
                        "cwd": str(cwd),
                        "tools": ["call_mcp_tool", "read_file", "write_file"],
                        "permission_mode": "always-proceed",
                    },
                },
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "conv-a",
                        "step_index": 1,
                        "state": "DONE",
                        "step_type": "system_message",
                        "duration_seconds": 0.003,
                    },
                },
                {
                    "event": "result",
                    "result": {
                        "status": "SUCCESS",
                        "response": '{"mcp_servers":["brain79","brain79_brain79"]}\n',
                        "structured_output": {"mcp_servers": ["brain79", "brain79_brain79"]},
                    },
                },
            ]
        else:
            events = [
                {
                    "event": "init",
                    "conversation_id": "conv-b",
                    "init": {
                        "model": "gemini-4-hydrogen-low",
                        "cwd": str(cwd),
                        "tools": ["call_mcp_tool", "read_file", "write_file"],
                        "permission_mode": "always-proceed",
                    },
                },
                {
                    "event": "result",
                    "result": {
                        "status": "SUCCESS",
                        "response": '{"mcp_servers":[]}\n',
                        "structured_output": {"mcp_servers": []},
                    },
                },
            ]
        stdout = "\n".join(json.dumps(e) for e in events) + "\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    report = run_preflight_checks(arms, agy_runner=real_agy_runner)
    assert report.passed
    assert report.arm_a_hooks_verified
    assert report.arm_a_mcp_servers == ["brain79", "brain79_brain79"]
    assert report.arm_b_mcp_servers == []
    assert "call_mcp_tool" in report.arm_b_tools

    # Failing Arm B when structured_output.mcp_servers leaks ["brain79"]
    def leaky_mcp_b(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if cwd == arms.arm_b:
            events = [
                {"event": "init", "init": {"tools": ["call_mcp_tool", "read_file"]}},
                {"event": "result", "result": {"structured_output": {"mcp_servers": ["brain79"]}}},
            ]
            return subprocess.CompletedProcess(
                cmd, 0, stdout="\n".join(json.dumps(e) for e in events) + "\n", stderr=""
            )
        return real_agy_runner(cmd, cwd)

    with pytest.raises(IsolationError, match="brain79"):
        run_preflight_checks(arms, agy_runner=leaky_mcp_b)

    # Failing Arm A when system_message hook step is missing
    def missing_hook_a(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if cwd == arms.arm_a:
            events = [
                {"event": "init", "init": {"tools": ["call_mcp_tool", "read_file"]}},
                {"event": "result", "result": {"structured_output": {"mcp_servers": ["brain79"]}}},
            ]
            return subprocess.CompletedProcess(
                cmd, 0, stdout="\n".join(json.dumps(e) for e in events) + "\n", stderr=""
            )
        return real_agy_runner(cmd, cwd)

    with pytest.raises(IsolationError, match="hook"):
        run_preflight_checks(arms, agy_runner=missing_hook_a)

    # Failing Arm A when mcp_servers lacks brain79
    def missing_mcp_a(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if cwd == arms.arm_a:
            events = [
                {"event": "init", "init": {"tools": ["call_mcp_tool", "read_file"]}},
                {"event": "step_update", "step_update": {"step_type": "system_message"}},
                {"event": "result", "result": {"structured_output": {"mcp_servers": []}}},
            ]
            return subprocess.CompletedProcess(
                cmd, 0, stdout="\n".join(json.dumps(e) for e in events) + "\n", stderr=""
            )
        return real_agy_runner(cmd, cwd)

    with pytest.raises(IsolationError, match="brain79 MCP tools"):
        run_preflight_checks(arms, agy_runner=missing_mcp_a)
