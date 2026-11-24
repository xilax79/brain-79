"""Tests for Phase 14 Stage 1: Git diff range resolution and core CI gate engine."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from brain79.core.ci_check import CiCheckReport, run_ci_check
from brain79.core.drift import WorkspaceIndex
from brain79.core.git_ops import (
    GitError,
    GitTimeoutError,
    NotAGitRepoError,
    git_diff_range_names,
    git_ls_files,
)
from brain79.core.init_project import init_project


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _setup_governed_repo(repo: Path) -> None:
    from brain79.config import project_context
    from brain79.core.drift import compute_applies_to_manifest
    from brain79.core.navigation import regenerate_index_navigation

    _init_git_repo(repo)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "auth.py").write_text("def login() -> bool:\n    return True\n", encoding="utf-8")
    init_project(repo, install_git_hooks_flag=False)

    w_root = repo / ".brain-79"
    with project_context(repo, w_root):
        digest, _, _ = compute_applies_to_manifest(["src/auth.py"], repo, w_root)

        adr_path = w_root / "decisions" / "adr-001-auth.md"
        adr_path.write_text(
            "---\n"
            "type: decision\n"
            "status: accepted\n"
            "date: 2026-11-24\n"
            "deciders: [xilax]\n"
            "summary: Require token validation for auth endpoints.\n"
            "last_updated: 2026-11-24\n"
            "---\n\n"
            "# ADR-001: Auth token validation\n\n"
            "## Status\n\nAccepted.\n\n"
            "## Context\n\nAuth endpoints require token verification.\n\n"
            "## Decision\n\nAll auth handlers must validate signed tokens.\n\n"
            "## Consequences\n\nUnauthorized requests are rejected.\n\n"
            "[← Back to Index](../INDEX.md)\n",
            encoding="utf-8",
        )

        feat_path = w_root / "features" / "auth.md"
        feat_path.write_text(
            "---\n"
            "type: feature\n"
            "status: shipped\n"
            "version: 0.14.0\n"
            "summary: Authentication module behavior and token checks.\n"
            "applies_to:\n"
            "  - src/auth.py\n"
            f"applies_to_digest: {digest}\n"
            "related:\n"
            "  - decisions/adr-001-auth.md\n"
            "last_updated: 2026-11-24\n"
            "---\n\n"
            "# Feature — Authentication\n\n"
            "## Overview\n\n"
            "Governs `src/auth.py` and links to [ADR-001](../decisions/adr-001-auth.md).\n\n"
            "[← Back to Index](../INDEX.md)\n",
            encoding="utf-8",
        )

        regenerate_index_navigation(w_root, rebuild=True)

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial governed repo")


# ---------------------------------------------------------------------------
# AC-1: Git diff range resolution, option-injection defense, git_ls_files
# ---------------------------------------------------------------------------


def test_git_diff_range_names_and_option_injection_guard(tmp_path: Path) -> None:
    """AC-1 / R-1.1: Diff range resolution, two-dot fallback, ref validation, and git_ls_files hardening."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (repo / ".brain-79" / "features").mkdir(parents=True)
    (repo / ".brain-79" / "features" / "app.md").write_text("# App\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")

    _git(repo, "checkout", "-b", "feat/test")
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    (repo / ".brain-79" / "features" / "app.md").write_text("# App v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feature change")

    changed = git_diff_range_names(repo, "main", "HEAD")
    assert changed == [".brain-79/features/app.md", "src/app.py"] or set(changed) == {
        "src/app.py",
        ".brain-79/features/app.md",
    }

    # Option and range injection guards
    for bad_ref in ("", "   ", "-o", " main", "main ", "main\x00", "main\n", "main..HEAD"):
        with pytest.raises(ValueError):
            git_diff_range_names(repo, bad_ref, "HEAD")
        with pytest.raises(ValueError):
            git_diff_range_names(repo, "main", bad_ref)

    # Non-git repo raises NotAGitRepoError immediately without fallback
    non_git = tmp_path / "non_git"
    non_git.mkdir()
    with pytest.raises(NotAGitRepoError):
        git_diff_range_names(non_git, "main", "HEAD")

    # GitTimeoutError propagates immediately without fallback
    with patch(
        "brain79.core.git_ops.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["git", "diff"], timeout=1.0),
    ):
        with pytest.raises(GitTimeoutError):
            git_diff_range_names(repo, "main", "HEAD", timeout=1.0)

    # Two-dot fallback when three-dot fails due to no merge base
    with patch("brain79.core.git_ops.run_git_bytes") as mock_run_bytes:
        from brain79.core.git_ops import GitBytesResult

        mock_run_bytes.side_effect = [
            GitBytesResult(returncode=128, stdout=b"", stderr=b"fatal: main...HEAD: no merge base\n"),
            GitBytesResult(returncode=0, stdout=b"src/app.py\x00src/app.py\x00", stderr=b""),
        ]
        fallback_res = git_diff_range_names(repo, "main", "HEAD")
        assert fallback_res == ["src/app.py"]
        assert mock_run_bytes.call_count == 2

    # Both three-dot and two-dot fail -> GitError
    with patch("brain79.core.git_ops.run_git_bytes") as mock_run_bytes:
        from brain79.core.git_ops import GitBytesResult

        mock_run_bytes.side_effect = [
            GitBytesResult(returncode=128, stdout=b"", stderr=b"fatal: no merge base\n"),
            GitBytesResult(returncode=128, stdout=b"", stderr=b"fatal: bad revision\n"),
        ]
        with pytest.raises(GitError):
            git_diff_range_names(repo, "main", "HEAD")

    # git_ls_files raises GitError on non-zero returncode and WorkspaceIndex.build falls back cleanly
    with patch("brain79.core.git_ops.run_git_bytes") as mock_run_bytes:
        from brain79.core.git_ops import GitBytesResult

        mock_run_bytes.return_value = GitBytesResult(
            returncode=128,
            stdout=b"",
            stderr=b"fatal: detected dubious ownership in repository",
        )
        with pytest.raises(GitError):
            git_ls_files(repo)

    with patch("brain79.core.drift.git_ls_files", side_effect=GitError("dubious ownership")):
        ws = WorkspaceIndex.build(repo, repo / ".brain-79")
        assert "src/app.py" in ws.all_paths


# ---------------------------------------------------------------------------
# AC-2: run_ci_check diff impact, 1-hop ADR surfacing, lint parity, drift
# ---------------------------------------------------------------------------


def test_run_ci_check_diff_impact_adrs_and_fresh_checkout_drift(tmp_path: Path) -> None:
    """AC-2 / R-1.2, R-1.3, R-1.4: Impacted articles, 1-hop ADRs, fresh checkout drift, and lint parity."""
    repo = tmp_path / "repo"
    _setup_governed_repo(repo)

    # Create feature branch modifying src/auth.py without updating features/auth.md
    _git(repo, "checkout", "-b", "feat/auth-update")
    (repo / "src" / "auth.py").write_text("def login() -> bool:\n    return False\n", encoding="utf-8")
    _git(repo, "add", "src/auth.py")
    _git(repo, "commit", "-m", "modify auth without updating wiki")

    # Simulate fresh CI checkout by deleting derived caches
    manifest = repo / ".brain-79" / ".drift_manifest.json"
    registry = repo / ".brain-79" / ".navigation_registry.json"
    if manifest.exists():
        manifest.unlink()
    if registry.exists():
        registry.unlink()

    report = run_ci_check(project_root=repo, base_ref="main", head_ref="HEAD")
    assert isinstance(report, CiCheckReport)
    assert "src/auth.py" in report.changed_files
    assert report.diff_range == "main...HEAD"

    impacted_paths = [item["path"] for item in report.impacted_articles]
    assert "features/auth.md" in impacted_paths
    auth_impact = next(item for item in report.impacted_articles if item["path"] == "features/auth.md")
    assert auth_impact["updated_in_diff"] is False
    assert "src/auth.py" in auth_impact["matched_files"]

    adr_paths = [item["path"] for item in report.relevant_adrs]
    assert "decisions/adr-001-auth.md" in adr_paths

    drifted_paths = [item["article_path"] for item in report.drifted_articles]
    assert "features/auth.md" in drifted_paths

    # Strictly read-only: derived caches must NOT be written
    assert not manifest.exists()
    assert not registry.exists()

    # Introduce a broken local link in features/auth.md -> CRITICAL lint error
    feat_path = repo / ".brain-79" / "features" / "auth.md"
    feat_path.write_text(
        feat_path.read_text(encoding="utf-8") + "\nSee [missing](missing-doc.md).\n",
        encoding="utf-8",
    )
    report_broken = run_ci_check(project_root=repo, base_ref="main", head_ref="HEAD")
    assert report_broken.lint_status == "CRITICAL"
    assert report_broken.lint_errors_count >= 1
    assert any(
        issue["severity"] == "error" and "missing-doc.md" in issue["message"]
        for issue in report_broken.issues
    )


# ---------------------------------------------------------------------------
# AC-3: Dual-tier enforcement matrix
# ---------------------------------------------------------------------------


def test_ci_check_enforcement_tier_matrix(tmp_path: Path) -> None:
    """AC-3 / R-1.5: Strict, balanced, advisory, schema, and fail_on_warnings enforcement matrix."""
    repo = tmp_path / "repo"
    _setup_governed_repo(repo)

    # Set SCHEMA.md enforcement to balanced
    schema_path = repo / ".brain-79" / "SCHEMA.md"
    schema_text = schema_path.read_text(encoding="utf-8").replace("enforcement: strict", "enforcement: balanced")
    schema_path.write_text(schema_text, encoding="utf-8")
    _git(repo, "add", ".brain-79/SCHEMA.md")
    _git(repo, "commit", "-m", "set balanced enforcement")

    # Introduce drift on src/auth.py (0 CRITICAL lint errors)
    (repo / "src" / "auth.py").write_text("def login() -> bool:\n    return False\n", encoding="utf-8")

    # Default enforcement="strict" fails on drift
    r_strict = run_ci_check(project_root=repo)
    assert r_strict.enforcement == "strict"
    assert r_strict.status == "failed"
    assert r_strict.exit_code == 1

    # enforcement="schema" honors balanced -> warning, exit 0
    r_schema = run_ci_check(project_root=repo, enforcement="schema")
    assert r_schema.enforcement == "balanced"
    assert r_schema.status == "warning"
    assert r_schema.exit_code == 0

    # enforcement="schema", fail_on_warnings=True -> failed, exit 1
    r_fail_warn = run_ci_check(project_root=repo, enforcement="schema", fail_on_warnings=True)
    assert r_fail_warn.status == "failed"
    assert r_fail_warn.exit_code == 1

    # Introduce CRITICAL lint error (broken link) -> fails even under advisory
    feat_path = repo / ".brain-79" / "features" / "auth.md"
    feat_path.write_text(
        feat_path.read_text(encoding="utf-8") + "\nSee [broken](nonexistent.md).\n",
        encoding="utf-8",
    )
    r_advisory_crit = run_ci_check(project_root=repo, enforcement="advisory")
    assert r_advisory_crit.lint_status == "CRITICAL"
    assert r_advisory_crit.status == "failed"
    assert r_advisory_crit.exit_code == 1

    # Missing .brain-79/ -> failed, exit 1
    missing_repo = tmp_path / "empty_dir"
    missing_repo.mkdir()
    r_missing = run_ci_check(project_root=missing_repo)
    assert r_missing.status == "failed"
    assert r_missing.exit_code == 1


# ---------------------------------------------------------------------------
# AC-4: Markdown report marker, JSON serialization, summary_file & step summary
# ---------------------------------------------------------------------------


def test_ci_check_formats_and_step_summary_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4 / R-1.6, R-1.7: Markdown marker, canonical to_dict keys, summary_file, and GITHUB_STEP_SUMMARY."""
    repo = tmp_path / "repo"
    _setup_governed_repo(repo)

    step_summary = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))

    summary_file = tmp_path / "out" / "summary.md"
    summary_file.parent.mkdir(parents=True)

    report = run_ci_check(
        project_root=repo,
        summary_file=summary_file,
        write_step_summary=True,
    )
    payload = report.to_dict()
    expected_keys = {
        "status",
        "exit_code",
        "enforcement",
        "diff_range",
        "changed_files",
        "drifted_articles",
        "impacted_articles",
        "relevant_adrs",
        "lint_status",
        "lint_errors_count",
        "lint_warnings_count",
        "issues",
        "markdown_summary",
    }
    assert expected_keys.issubset(payload.keys())
    assert "<!-- brain79:ci-check -->" in report.markdown_summary
    assert "# Brain-79 CI governance report" in report.markdown_summary

    step_bytes = step_summary.read_bytes()
    assert b"\r\n" not in step_bytes
    step_text = step_bytes.decode("utf-8")
    assert "<!-- brain79:ci-check -->" in step_text
    assert "# Brain-79 CI governance report" in step_text

    sum_bytes = summary_file.read_bytes()
    assert b"\r\n" not in sum_bytes
    assert "<!-- brain79:ci-check -->" in sum_bytes.decode("utf-8")

    # Missing parent directory for summary_file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        run_ci_check(
            project_root=repo,
            summary_file=tmp_path / "nonexistent_dir" / "summary.md",
        )
