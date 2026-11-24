"""Tests for Phase 14: Git diff range resolution, ci-check PR gate, passive lifecycle hooks, and composite GitHub Action."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from brain79.core.ci_check import (
    MAX_INPUT_BYTES,
    CiCheckReport,
    run_ci_check,
    run_lifecycle_hook,
)
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

    # Orphan article produces lint_status == "WARNING", lint_warnings_count >= 1, and appears in markdown_summary
    orphan_repo = tmp_path / "orphan_repo"
    _setup_governed_repo(orphan_repo)
    orphan_path = orphan_repo / ".brain-79" / "topics" / "unlinked-note.md"
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_text(
        "---\n"
        "type: topic\n"
        "summary: unlinked orphan topic\n"
        "status: active\n"
        "last_updated: 2026-11-24\n"
        "---\n\n"
        "# Unlinked orphan topic\n\n"
        "Content.\n\n"
        "---\n\n"
        "[← Back to Index](../INDEX.md)\n",
        encoding="utf-8",
    )
    with patch("brain79.core.lint_organizational.lint_organizational", return_value=[]):
        report_orphan = run_ci_check(project_root=orphan_repo, base_ref="main", head_ref="HEAD")
    assert report_orphan.lint_status == "WARNING"
    assert report_orphan.lint_warnings_count >= 1
    assert any(issue["rule"] == "orphan_article" and issue["severity"] == "warning" for issue in report_orphan.issues)
    assert "unlinked-note.md" in report_orphan.markdown_summary


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


# ---------------------------------------------------------------------------
# AC-5: Lifecycle hook session-start across agy, claude, cursor, auto
# ---------------------------------------------------------------------------


def test_lifecycle_hook_session_start_all_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5 / R-2.1, R-2.2, R-2.3: Session-start payload shapes, auto inference, stdin cap, and ASCII JSON."""
    import io
    import json
    import sys

    repo = tmp_path / "repo"
    _setup_governed_repo(repo)
    agy_subdir = repo / ".agents" / "plugins" / "brain79"
    agy_subdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(agy_subdir)

    # 1. Antigravity with auto client inference and cwd in payload
    agy_payload = json.dumps(
        {
            "hookEventName": "SessionStart",
            "cwd": str(repo),
            "lastUserInput": "update auth",
        }
    )
    res_agy = run_lifecycle_hook("session-start", client="auto", stdin_payload=agy_payload)
    assert "injectSteps" in res_agy
    msg_agy = res_agy["injectSteps"][0]["systemMessage"]["systemMessage"]
    assert "Brain-79 — Session Cold Start Orientation" in msg_agy
    assert json.loads(json.dumps(res_agy, ensure_ascii=True)) == res_agy

    # 2. Claude Code (explicit and auto fallback)
    claude_payload = json.dumps({"cwd": str(repo), "prompt": "check auth " * 500})
    res_claude = run_lifecycle_hook("session-start", client="auto", stdin_payload=claude_payload)
    assert res_claude["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Brain-79 — Session Cold Start Orientation" in res_claude["hookSpecificOutput"]["additionalContext"]
    assert json.loads(json.dumps(res_claude, ensure_ascii=True)) == res_claude

    # 3. Cursor (auto inference via hook_event_name == "sessionStart" and workspace_roots)
    cursor_payload = json.dumps(
        {
            "hook_event_name": "sessionStart",
            "workspace_roots": [str(repo)],
        }
    )
    res_cursor = run_lifecycle_hook("session-start", client="auto", stdin_payload=cursor_payload)
    assert "additional_context" in res_cursor
    assert "Brain-79 — Session Cold Start Orientation" in res_cursor["additional_context"]
    assert json.loads(json.dumps(res_cursor, ensure_ascii=True)) == res_cursor

    # 4. Bounded sys.stdin reading (oversized > 1 MB fails open to {}, binary UTF-8 succeeds, multi-byte > 1 MB fails open)
    oversized = '{"cwd": "' + ("a" * (MAX_INPUT_BYTES + 100)) + '"}'
    fake_stdin = io.StringIO(oversized)
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    assert run_lifecycle_hook("session-start", client="claude") == {}

    utf8_payload = json.dumps({"cwd": str(repo), "prompt": "café naïve résumé 日本語"}, ensure_ascii=False).encode("utf-8")
    bin_stdin = io.TextIOWrapper(io.BytesIO(utf8_payload), encoding="cp1252")
    monkeypatch.setattr(sys, "stdin", bin_stdin)
    res_utf8 = run_lifecycle_hook("session-start", client="claude")
    assert "hookSpecificOutput" in res_utf8

    # Multi-byte UTF-8: 400_000 'é' chars = 400_000 chars (< MAX_INPUT_BYTES) but ~800 KB+, use 600_000 'é' = 1.2 MB
    multibyte_over = ('{"cwd": "' + ("é" * 600_000) + '"}').encode("utf-8")
    assert len(multibyte_over) > MAX_INPUT_BYTES
    bin_over = io.TextIOWrapper(io.BytesIO(multibyte_over), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", bin_over)
    assert run_lifecycle_hook("session-start", client="claude") == {}

    # 5. Non-object JSON and malformed JSON fail open to {}
    assert run_lifecycle_hook("session-start", client="claude", stdin_payload="[]") == {}
    assert run_lifecycle_hook("session-start", client="claude", stdin_payload="{bad") == {}

    # 6. Missing .brain-79/ fails open to {}
    empty_dir = tmp_path / "no_wiki"
    empty_dir.mkdir()
    assert run_lifecycle_hook("session-start", client="claude", project_root=empty_dir) == {}


# ---------------------------------------------------------------------------
# AC-6: Lifecycle hook stop drift interception and loop-prevention guards
# ---------------------------------------------------------------------------


def test_lifecycle_hook_stop_drift_and_loop_guards(tmp_path: Path) -> None:
    """AC-6 / R-2.2, R-2.4: Stop drift reporting, loop/termination guards, advisory, and .git boundary."""
    import json

    repo = tmp_path / "repo"
    _setup_governed_repo(repo)

    # Clean repo -> {}
    assert run_lifecycle_hook("stop", client="claude", project_root=repo, stdin_payload="{}") == {}

    # Introduce drift on src/auth.py leaving features/auth.md drifted
    (repo / "src" / "auth.py").write_text("def login() -> bool:\n    return False\n", encoding="utf-8")

    # 1. Clean initial stop payloads for agy, claude, cursor
    res_agy = run_lifecycle_hook(
        "stop",
        client="auto",
        stdin_payload=json.dumps({"hookEventName": "Stop", "cwd": str(repo), "terminationReason": "NO_TOOL_CALL"}),
    )
    assert res_agy["decision"] == "continue"
    assert "features/auth.md" in res_agy["reason"]
    assert "brain79_session_commit" in res_agy["reason"]

    res_claude = run_lifecycle_hook(
        "stop",
        client="claude",
        stdin_payload=json.dumps({"cwd": str(repo), "stop_hook_active": False}),
    )
    assert res_claude["decision"] == "block"
    assert "features/auth.md" in res_claude["reason"]

    res_cursor = run_lifecycle_hook(
        "stop",
        client="auto",
        stdin_payload=json.dumps({"workspace_roots": [str(repo)], "status": "completed", "loop_count": 0}),
    )
    assert "followup_message" in res_cursor
    assert "features/auth.md" in res_cursor["followup_message"]

    # 2. Loop-immunity and non-normal termination guards -> {}
    assert run_lifecycle_hook("stop", client="agy", project_root=repo, stdin_payload=json.dumps({"continuationActive": True})) == {}
    assert run_lifecycle_hook("stop", client="agy", project_root=repo, stdin_payload=json.dumps({"terminationReason": "USER_CANCELED"})) == {}
    assert run_lifecycle_hook("stop", client="claude", project_root=repo, stdin_payload=json.dumps({"stop_hook_active": True})) == {}
    assert run_lifecycle_hook("stop", client="cursor", project_root=repo, stdin_payload=json.dumps({"loop_count": 1})) == {}
    assert run_lifecycle_hook("stop", client="cursor", project_root=repo, stdin_payload=json.dumps({"loop_count": "not_a_number"})) == {}
    assert run_lifecycle_hook("stop", client="cursor", project_root=repo, stdin_payload=json.dumps({"status": "aborted", "loop_count": 0})) == {}

    # 3. Malformed stdin -> {}
    assert run_lifecycle_hook("stop", client="claude", project_root=repo, stdin_payload="{bad") == {}

    # 4. .git boundary walk: child .git repo inside parent with .brain-79/ must NOT inherit parent's .brain-79/
    child_repo = repo / "packages" / "child_service"
    _init_git_repo(child_repo)
    assert run_lifecycle_hook("stop", client="claude", stdin_payload=json.dumps({"cwd": str(child_repo)})) == {}

    # 5. Advisory enforcement -> {}
    schema_path = repo / ".brain-79" / "SCHEMA.md"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8").replace("enforcement: strict", "enforcement: advisory"),
        encoding="utf-8",
    )
    assert run_lifecycle_hook("stop", client="claude", project_root=repo, stdin_payload="{}") == {}


def test_lifecycle_hook_adapters_sync_and_doctor(tmp_path: Path) -> None:
    """AC-7 / R-3.1..R-3.5: Opt-in lifecycle hook adapters, non-destructive merging, and doctor diagnostics."""
    import json

    from brain79.cli.dispatch import dispatch_cmd
    from brain79.core.doctor import run_doctor
    from brain79.core.harnesses import (
        AntigravityHooksAdapter,
        ClaudeHooksAdapter,
        CursorHooksAdapter,
        diagnose_all_harnesses,
        get_harness_adapters,
        get_lifecycle_hook_adapters,
        resolve_harness_selection,
    )
    from brain79.core.init_project import init_project, update_project

    # 1. Registry invariants (R-3.3)
    assert len(get_harness_adapters()) == 7
    hook_adapters = get_lifecycle_hook_adapters()
    assert [a.name for a in hook_adapters] == ["claude_hooks", "agy_hooks", "cursor_hooks"]
    assert [a.name for a in resolve_harness_selection(None)] == [a.name for a in get_harness_adapters()]
    assert [a.name for a in resolve_harness_selection("all")] == [a.name for a in get_harness_adapters()]
    assert [a.name for a in resolve_harness_selection("hooks")] == ["claude_hooks", "agy_hooks", "cursor_hooks"]
    all_plus_hooks = [a.name for a in resolve_harness_selection("all,hooks")]
    assert len(all_plus_hooks) == 10
    assert "claude_hooks" in all_plus_hooks and "agents_md" in all_plus_hooks

    # 2. Pre-existing unrelated Claude and Cursor configs (AC-7 Given)
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude").mkdir(parents=True, exist_ok=True)
    claude_settings = repo / ".claude" / "settings.json"
    claude_settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}, indent=2) + "\n", encoding="utf-8")
    (repo / ".cursor").mkdir(parents=True, exist_ok=True)
    cursor_hooks = repo / ".cursor" / "hooks.json"
    cursor_hooks.write_text(
        json.dumps({"version": 1, "hooks": {"stop": [{"command": "echo custom"}]}}, indent=2) + "\n",
        encoding="utf-8",
    )

    # Default init_project and update_project MUST NOT inject hooks (R-3.4)
    init_project(repo, auto_git_init=False)
    up_default = update_project(repo)
    assert up_default["lifecycle_hooks"] == []
    assert ClaudeHooksAdapter().detect(repo) is False
    assert AntigravityHooksAdapter().detect(repo) is False
    assert CursorHooksAdapter().detect(repo) is False
    assert not (repo / ".agents" / "plugins" / "brain79" / "hooks.json").exists()
    assert json.loads(claude_settings.read_text(encoding="utf-8")) == {"permissions": {"allow": ["Bash"]}}
    assert json.loads(cursor_hooks.read_text(encoding="utf-8")) == {
        "version": 1,
        "hooks": {"stop": [{"command": "echo custom"}]},
    }

    # Doctor preserves 9 canonical checks when hooks are not installed
    doc_clean = run_doctor(repo)
    assert doc_clean.exit_code == 0
    assert len(doc_clean.checks) == 9
    assert "claude_hooks" not in diagnose_all_harnesses(repo)

    # 3. Opt-in installation via update_project(install_lifecycle_hooks=True)
    up_hooks = update_project(repo, install_lifecycle_hooks=True)
    assert set(up_hooks["lifecycle_hooks"]) == {
        ".claude/settings.json",
        ".agents/plugins/brain79/hooks.json",
        ".cursor/hooks.json",
    }
    assert ClaudeHooksAdapter().detect(repo) is True
    assert AntigravityHooksAdapter().detect(repo) is True
    assert CursorHooksAdapter().detect(repo) is True

    # Verify exact host schemas & non-destructive preservation (R-3.1)
    c_data = json.loads(claude_settings.read_text(encoding="utf-8"))
    assert c_data["permissions"] == {"allow": ["Bash"]}
    assert c_data["hooks"]["SessionStart"] == [
        {"matcher": "", "hooks": [{"type": "command", "command": "brain79 ci-check --lifecycle-hook session-start --client claude", "timeout": 15}]}
    ]
    assert c_data["hooks"]["Stop"] == [
        {"matcher": "", "hooks": [{"type": "command", "command": "brain79 ci-check --lifecycle-hook stop --client claude", "timeout": 15}]}
    ]

    agy_hooks_file = repo / ".agents" / "plugins" / "brain79" / "hooks.json"
    a_data = json.loads(agy_hooks_file.read_text(encoding="utf-8"))
    assert a_data["brain79-lifecycle"]["enabled"] is True
    assert a_data["brain79-lifecycle"]["SessionStart"] == [
        {"type": "command", "command": "brain79 ci-check --lifecycle-hook session-start --client agy", "timeout": 15}
    ]
    assert a_data["brain79-lifecycle"]["Stop"] == [
        {"type": "command", "command": "brain79 ci-check --lifecycle-hook stop --client agy", "timeout": 15}
    ]

    cur_data = json.loads(cursor_hooks.read_text(encoding="utf-8"))
    assert cur_data["version"] == 1
    assert cur_data["hooks"]["sessionStart"] == [
        {"command": "brain79 ci-check --lifecycle-hook session-start --client cursor", "timeout": 15}
    ]
    assert cur_data["hooks"]["stop"] == [
        {"command": "echo custom"},
        {"command": "brain79 ci-check --lifecycle-hook stop --client cursor", "timeout": 15},
    ]

    # Idempotence: second update_project (even without install_lifecycle_hooks=True) detects installed hooks and makes 0 changes
    up_idem = update_project(repo)
    assert up_idem["lifecycle_hooks"] == []

    # Preserve Antigravity enabled: false without error or warning
    a_data["brain79-lifecycle"]["enabled"] = False
    agy_hooks_file.write_text(json.dumps(a_data, indent=2) + "\n", encoding="utf-8")
    assert update_project(repo)["lifecycle_hooks"] == []
    assert json.loads(agy_hooks_file.read_text(encoding="utf-8"))["brain79-lifecycle"]["enabled"] is False
    doc_healthy = run_doctor(repo)
    assert doc_healthy.exit_code == 0
    assert len(doc_healthy.checks) == 9

    # 4. dry_run=True on corrupt JSON makes zero disk mutations, and repeated corruption overwrites .bak (R-3.2)
    agy_hooks_file.write_text("{corrupt", encoding="utf-8")
    assert AntigravityHooksAdapter().detect(repo) is True
    up_dry = update_project(repo, dry_run=True)
    assert ".agents/plugins/brain79/hooks.json" in up_dry["lifecycle_hooks"]
    assert agy_hooks_file.read_text(encoding="utf-8") == "{corrupt"
    assert not agy_hooks_file.with_name("hooks.json.bak").exists()

    # Corrupt Claude command (warning) + corrupt Agy JSON (error) -> Doctor checks & --fix (R-3.5)
    c_data["hooks"]["Stop"][0]["hooks"][0]["command"] = "/usr/local/bin/brain79 ci-check --lifecycle-hook stop --client claude"
    claude_settings.write_text(json.dumps(c_data, indent=2) + "\n", encoding="utf-8")

    doc_bad = run_doctor(repo)
    assert doc_bad.exit_code == 1
    by_cat = {c.category: c for c in doc_bad.checks}
    assert by_cat["harness:claude_hooks"].status == "warning"
    assert by_cat["harness:agy_hooks"].status == "error"

    # Dirty working-tree guard includes .claude/settings.json / .cursor/hooks.json
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "chore: commit hooks")
    cur_data["hooks"]["stop"].append({"command": "echo dirty"})
    cursor_hooks.write_text(json.dumps(cur_data, indent=2) + "\n", encoding="utf-8")
    doc_dirty = run_doctor(repo, fix=True, force=False)
    assert doc_dirty.exit_code == 1
    assert doc_dirty.checks[0].category == "dirty_working_tree"

    # Force fix repairs both and creates .bak
    doc_fixed = run_doctor(repo, fix=True, force=True)
    assert doc_fixed.exit_code == 0
    assert len(doc_fixed.checks) == 9
    assert agy_hooks_file.with_name("hooks.json.bak").is_file()
    assert any("lifecycle hooks" in item.lower() for item in doc_fixed.fixed)

    # Repeated corruption overwrites .bak cleanly without FileExistsError
    agy_hooks_file.write_text("{corrupt2", encoding="utf-8")
    update_project(repo)
    assert agy_hooks_file.with_name("hooks.json.bak").read_text(encoding="utf-8") == "{corrupt2"

    # 5. Directory collision guard (R-3.2)
    collision_repo = tmp_path / "collision_repo"
    collision_repo.mkdir()
    (collision_repo / ".claude" / "settings.json").mkdir(parents=True)
    assert ClaudeHooksAdapter().sync(collision_repo) == []

    # 6. CLI flags & init_project(harnesses=["all", "hooks"]) + init --upgrade --install-lifecycle-hooks (R-3.3, R-3.4)
    cli_repo = tmp_path / "cli_repo"
    _init_git_repo(cli_repo)
    assert dispatch_cmd("init", ["--project-root", str(cli_repo), "--harnesses", "all,hooks"]) == 0
    assert ClaudeHooksAdapter().detect(cli_repo) is True
    assert AntigravityHooksAdapter().detect(cli_repo) is True
    assert CursorHooksAdapter().detect(cli_repo) is True

    cli_repo2 = tmp_path / "cli_repo2"
    _init_git_repo(cli_repo2)
    assert dispatch_cmd("init", ["--project-root", str(cli_repo2)]) == 0
    assert ClaudeHooksAdapter().detect(cli_repo2) is False
    assert dispatch_cmd("update-project", ["--project-root", str(cli_repo2), "--install-lifecycle-hooks"]) == 0
    assert ClaudeHooksAdapter().detect(cli_repo2) is True
    assert AntigravityHooksAdapter().detect(cli_repo2) is True
    assert CursorHooksAdapter().detect(cli_repo2) is True

    # 7. Cursor version: 2 / version: True repair and Claude flat-entry detection & repair
    cursor_repo_file = cli_repo2 / ".cursor" / "hooks.json"
    for bad_ver in (2, True):
        bad_cursor = json.loads(cursor_repo_file.read_text(encoding="utf-8"))
        bad_cursor["version"] = bad_ver
        cursor_repo_file.write_text(json.dumps(bad_cursor, indent=2) + "\n", encoding="utf-8")
        assert CursorHooksAdapter().diagnose(cli_repo2)
        assert CursorHooksAdapter().sync(cli_repo2) == [".cursor/hooks.json"]
        assert CursorHooksAdapter().diagnose(cli_repo2) == []

    claude_repo_file = cli_repo2 / ".claude" / "settings.json"
    flat_claude = {
        "hooks": {
            "SessionStart": [
                {"type": "command", "command": "brain79 ci-check --lifecycle-hook session-start --client claude", "timeout": 15}
            ],
            "Stop": [
                {"type": "command", "command": "brain79 ci-check --lifecycle-hook stop --client claude", "timeout": 15}
            ],
        }
    }
    claude_repo_file.write_text(json.dumps(flat_claude, indent=2) + "\n", encoding="utf-8")
    claude_issues = ClaudeHooksAdapter().diagnose(cli_repo2)
    assert any("flat" in msg.lower() for msg in claude_issues)
    assert ClaudeHooksAdapter().sync(cli_repo2) == [".claude/settings.json"]
    assert ClaudeHooksAdapter().diagnose(cli_repo2) == []


# ---------------------------------------------------------------------------
# Stage 4: CLI dispatcher (`brain79 ci-check`), action.yml, and ci.yml
# ---------------------------------------------------------------------------


def test_cli_ci_check_git_errors_enforcement_and_formats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-1, AC-3, AC-4, AC-5 / R-4.1, R-4.2: CLI dispatcher ci-check behavior and exit codes."""
    import json

    from brain79.__main__ import ROOT_HELP
    from brain79.cli.dispatch import WHITELIST, dispatch_cmd, run_cli

    assert "ci-check" in WHITELIST
    assert len(WHITELIST) == 25
    assert "ci-check" in ROOT_HELP

    # Help output
    assert run_cli("ci-check", ["--help"]) == 0
    help_out = capsys.readouterr().out
    assert "brain79 ci-check" in help_out
    assert "--lifecycle-hook" in help_out
    assert "--write-step-summary" in help_out

    repo = tmp_path / "repo"
    _setup_governed_repo(repo)
    monkeypatch.chdir(repo)

    # AC-1: option-injection --base=-o -> exit 2, stderr
    code_opt = dispatch_cmd("ci-check", ["--base=-o"])
    assert code_opt == 2
    assert capsys.readouterr().err.strip()

    # AC-1: unresolvable --base nonexistent_branch_ref -> exit 2, stderr
    code_bad_ref = dispatch_cmd("ci-check", ["--base", "nonexistent_branch_ref"])
    assert code_bad_ref == 2
    assert capsys.readouterr().err.strip()

    # AC-1: GitTimeoutError -> exit 3, stderr
    with patch("brain79.core.ci_check.run_ci_check", side_effect=GitTimeoutError("git diff timed out")):
        code_timeout = dispatch_cmd("ci-check", ["--base", "main"])
    assert code_timeout == 3
    assert "timed out" in capsys.readouterr().err.lower()

    # AC-3: CLI enforcement tiers on drifted repo with SCHEMA.md enforcement: balanced
    schema_path = repo / ".brain-79" / "SCHEMA.md"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8").replace("enforcement: strict", "enforcement: balanced"),
        encoding="utf-8",
    )
    _git(repo, "add", ".brain-79/SCHEMA.md")
    _git(repo, "commit", "-m", "set balanced enforcement")
    (repo / "src" / "auth.py").write_text("def login() -> bool:\n    return False\n", encoding="utf-8")

    assert dispatch_cmd("ci-check", ["--project-root", str(repo)]) == 1
    capsys.readouterr()

    assert dispatch_cmd("ci-check", ["--project-root", str(repo), "--enforcement", "schema"]) == 0
    capsys.readouterr()

    assert (
        dispatch_cmd(
            "ci-check",
            ["--project-root", str(repo), "--enforcement", "schema", "--fail-on-warnings"],
        )
        == 1
    )
    capsys.readouterr()

    # AC-4: --write-step-summary --format json and invalid --summary-file -> exit 2
    step_summary = tmp_path / "cli_step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))
    code_json = dispatch_cmd(
        "ci-check",
        ["--project-root", str(repo), "--enforcement", "advisory", "--write-step-summary", "--format", "json"],
    )
    assert code_json == 0
    json_out = capsys.readouterr().out
    parsed = json.loads(json_out)
    assert parsed["status"] == "warning"
    assert "<!-- brain79:ci-check -->" in step_summary.read_text(encoding="utf-8")

    code_bad_sum = dispatch_cmd(
        "ci-check",
        ["--project-root", str(repo), "--summary-file", str(tmp_path / "missing_dir" / "out.md")],
    )
    assert code_bad_sum == 2
    assert capsys.readouterr().err.strip()

    # AC-5: CLI --lifecycle-hook session-start emits ASCII-escaped JSON and exits 0
    import io
    import sys

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"hookEventName": "SessionStart", "cwd": str(repo), "lastUserInput": "auth"})),
    )
    code_hook = dispatch_cmd("ci-check", ["--lifecycle-hook", "session-start", "--client", "auto"])
    assert code_hook == 0
    hook_out = capsys.readouterr().out
    assert hook_out.isascii()
    hook_json = json.loads(hook_out)
    assert "injectSteps" in hook_json

    # Explicit global set_project_root(repo) overrides payload["cwd"]
    from brain79.config import set_project_root

    other_dir = tmp_path / "other_empty_dir"
    other_dir.mkdir()
    set_project_root(repo)
    try:
        monkeypatch.setattr(
            sys,
            "stdin",
            io.StringIO(json.dumps({"hookEventName": "SessionStart", "cwd": str(other_dir), "lastUserInput": "auth"})),
        )
        assert dispatch_cmd("ci-check", ["--lifecycle-hook", "session-start", "--client", "auto"]) == 0
        global_hook_out = json.loads(capsys.readouterr().out)
        assert "injectSteps" in global_hook_out
    finally:
        set_project_root(None)


def test_github_action_manifest_and_ci_workflow() -> None:
    """AC-8 / R-4.3, R-4.4, R-4.5: Composite action.yml and ci.yml governance & security checks."""
    import re
    import yaml

    root = Path(__file__).resolve().parent.parent
    action_path = root / "action.yml"
    ci_path = root / ".github" / "workflows" / "ci.yml"

    assert action_path.is_file(), "action.yml must exist at repository root"
    assert ci_path.is_file(), ".github/workflows/ci.yml must exist"

    action_data = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    assert isinstance(action_data, dict)
    assert action_data.get("name") == "Brain-79 CI governance and PR gate"

    # Inputs & outputs
    inputs = action_data.get("inputs", {})
    expected_inputs = {
        "python-version",
        "base-ref",
        "head-ref",
        "enforcement",
        "fail-on-warnings",
        "project-root",
        "comment-on-pr",
        "github-token",
    }
    assert expected_inputs.issubset(inputs.keys())
    assert inputs["python-version"]["default"] == "3.12"
    assert inputs["head-ref"]["default"] == "HEAD"
    assert inputs["enforcement"]["default"] == "strict"

    outputs = action_data.get("outputs", {})
    assert {"status", "exit-code", "drifted-count", "report-json-path"}.issubset(outputs.keys())

    runs = action_data.get("runs", {})
    assert runs.get("using") == "composite"
    steps = runs.get("steps", [])
    assert steps

    pinned_pattern = re.compile(r"^[^@]+@v\d+(\.\d+)*$")
    all_run_scripts: list[str] = []
    for step in steps:
        if "uses" in step:
            assert pinned_pattern.match(step["uses"]), f"Unpinned action: {step['uses']}"
        if "run" in step:
            assert step.get("shell") == "bash", f"Every run step in action.yml must declare shell: bash: {step}"
            script = step["run"]
            all_run_scripts.append(script)
            # Zero ${{ inputs.* }} or ${{ github.* }} inside run: bodies (script injection defense)
            assert "${{ inputs." not in script, "Do not interpolate ${{ inputs.* }} directly in run:"
            assert "${{ github." not in script, "Do not interpolate ${{ github.* }} directly in run:"

    combined_scripts = "\n".join(all_run_scripts)
    assert "$GITHUB_ACTION_PATH" in combined_scripts
    assert "uv run --no-project --with \"$GITHUB_ACTION_PATH\" brain79" in combined_scripts
    assert "uv run --no-project python -" in combined_scripts
    assert "set +e" in combined_scripts
    assert "<!-- brain79:ci-check -->" in combined_scripts
    assert "gh api" in combined_scripts
    assert "--input -" in combined_scripts

    # ci.yml ordering: Run brain79 ci-check BEFORE Run brain79 doctor
    ci_data = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    ci_steps = ci_data["jobs"]["test"]["steps"]
    step_names = [s.get("name", "") for s in ci_steps]
    assert "Run brain79 ci-check" in step_names
    assert "Run brain79 doctor" in step_names
    assert step_names.index("Run brain79 ci-check") < step_names.index("Run brain79 doctor")
    ci_check_step = ci_steps[step_names.index("Run brain79 ci-check")]
    assert "uv run brain79 ci-check --write-step-summary" in ci_check_step.get("run", "")
