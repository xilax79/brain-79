"""Tests for Phase 9 Deliverable 9.3: Five-Archetype Multi-Repo Battle Gauntlet."""

import json
from pathlib import Path
import subprocess
import sys
import pytest

from scripts.run_battle_gauntlet import (
    build_archetype_1,
    build_archetype_2,
    build_archetype_3,
    build_archetype_4,
    build_archetype_5,
    get_perf_factor,
    run_archetype_1_lifecycle,
    run_archetype_2_lifecycle,
    run_archetype_3_lifecycle,
    run_archetype_4_lifecycle,
    run_archetype_5_lifecycle,
)


@pytest.mark.gauntlet
def test_archetype_1_dirty_polyglot_monorepo(tmp_path: Path) -> None:
    perf_factor = get_perf_factor()
    build_archetype_1(tmp_path)
    steps = run_archetype_1_lifecycle(tmp_path, perf_factor=perf_factor)
    assert len(steps) == 10
    assert all(s["status"] == "ok" for s in steps)


@pytest.mark.gauntlet
def test_archetype_2_chaotic_legacy_wiki(tmp_path: Path) -> None:
    perf_factor = get_perf_factor()
    build_archetype_2(tmp_path)
    steps = run_archetype_2_lifecycle(tmp_path, perf_factor=perf_factor)
    assert len(steps) == 10
    assert all(s["status"] == "ok" for s in steps)


@pytest.mark.gauntlet
def test_archetype_3_gitless_research(tmp_path: Path) -> None:
    perf_factor = get_perf_factor()
    build_archetype_3(tmp_path)
    steps = run_archetype_3_lifecycle(tmp_path, perf_factor=perf_factor)
    assert len(steps) == 10
    assert all(s["status"] == "ok" for s in steps)


@pytest.mark.gauntlet
def test_archetype_4_git_branch_warfare_and_guard_c(tmp_path: Path) -> None:
    perf_factor = get_perf_factor()
    build_archetype_4(tmp_path)
    steps = run_archetype_4_lifecycle(tmp_path, perf_factor=perf_factor)
    assert len(steps) == 10
    assert all(s["status"] == "ok" for s in steps)


@pytest.mark.gauntlet
@pytest.mark.perf
def test_archetype_5_scale_benchmark(tmp_path: Path) -> None:
    perf_factor = get_perf_factor()
    build_archetype_5(tmp_path)
    steps = run_archetype_5_lifecycle(tmp_path, perf_factor=perf_factor)
    assert len(steps) == 10
    assert all(s["status"] == "ok" for s in steps)


@pytest.mark.gauntlet
def test_gauntlet_cli_runner_and_json_report(tmp_path: Path) -> None:
    report_file = tmp_path / "gauntlet_report.json"
    cmd = [
        sys.executable,
        "scripts/run_battle_gauntlet.py",
        "--archetype",
        "1",
        "--json",
        str(report_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Gauntlet CLI failed: {res.stderr}\n{res.stdout}"
    assert report_file.is_file(), "Report file was not created"

    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["status"] == "passed"
    assert "steps" in data
    assert len(data["steps"]) == 10
    for s in data["steps"]:
        assert s["archetype"] == 1
        assert "step" in s
        assert "name" in s
        assert s["status"] == "ok"
        assert "duration_ms" in s
        assert s["error"] is None


@pytest.mark.gauntlet
def test_gauntlet_cli_runner_invalid_archetype() -> None:
    cmd = [
        sys.executable,
        "scripts/run_battle_gauntlet.py",
        "--archetype",
        "99",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 2
