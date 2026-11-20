"""Tests for centralized Git abstraction layer (Phase 10 Stage 2: R-2.1, AC-10.5)."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from brain79.core.git_ops import (
    GitSessionCache,
    GitTimeoutError,
    NotAGitRepoError,
    git_current_branch,
    git_diff_names,
    git_dirty_paths,
    git_last_commit_for_path,
    git_rev_parse_head,
    git_show_blob,
    run_git,
)


def test_no_direct_git_subprocess_calls_outside_git_ops() -> None:
    """AC-10.5: Zero direct subprocess.run(['git', ...]) calls remain outside src/brain79/core/git_ops.py."""
    src_root = Path("src/brain79")
    git_ops_path = (src_root / "core" / "git_ops.py").resolve()
    violations: list[str] = []

    for py_file in sorted(src_root.rglob("*.py")):
        if py_file.resolve() == git_ops_path:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_subproc_run = (
                isinstance(func, ast.Attribute)
                and func.attr == "run"
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            )
            if not is_subproc_run or not node.args:
                continue
            first_arg = node.args[0]
            if isinstance(first_arg, (ast.List, ast.Tuple)) and first_arg.elts:
                first_elt = first_arg.elts[0]
                if isinstance(first_elt, ast.Constant) and first_elt.value == "git":
                    violations.append(f"{py_file.as_posix()}:{node.lineno}")

    assert violations == [], (
        f"Direct subprocess.run(['git', ...]) calls found outside git_ops.py: {violations}"
    )


def _init_temp_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    (repo / "hello.py").write_text("def greet() -> str:\n    return 'hi'\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)


def test_git_ops_typed_helpers_and_session_cache(tmp_path: Path) -> None:
    """R-2.1: Typed helpers return structured results and GitSessionCache avoids redundant calls."""
    repo = tmp_path / "repo"
    _init_temp_git_repo(repo)

    cache = GitSessionCache()
    head1 = git_rev_parse_head(repo, cache=cache)
    assert len(head1) == 40

    # Second call with cache should not invoke subprocess.run
    with patch("brain79.core.git_ops.subprocess.run") as mock_run:
        head2 = git_rev_parse_head(repo, cache=cache)
        assert head2 == head1
        mock_run.assert_not_called()

    branch = git_current_branch(repo)
    assert branch in ("main", "master") or len(branch) > 0

    last_sha = git_last_commit_for_path(repo, "hello.py", cache=cache)
    assert last_sha == head1

    blob = git_show_blob(repo, head1, "hello.py", cache=cache)
    assert blob is not None and "def greet" in blob

    # Modify hello.py and verify dirty_paths and diff_names
    (repo / "hello.py").write_text("def greet() -> str:\n    return 'hello'\n", encoding="utf-8")
    dirty = git_dirty_paths(repo)
    assert "hello.py" in dirty

    diff_files = git_diff_names(repo)
    assert "hello.py" in diff_files


def test_git_ops_raises_not_a_git_repo_and_timeout(tmp_path: Path) -> None:
    """R-2.1: Non-git directories raise NotAGitRepoError and timeouts raise GitTimeoutError."""
    non_git = tmp_path / "plain_dir"
    non_git.mkdir()

    with pytest.raises(NotAGitRepoError):
        git_rev_parse_head(non_git)

    with pytest.raises(NotAGitRepoError):
        git_dirty_paths(non_git)

    with patch(
        "brain79.core.git_ops.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["git", "status"], timeout=1.0),
    ):
        with pytest.raises(GitTimeoutError):
            run_git(["status"], cwd=non_git, timeout=1.0)


def test_git_ops_defensive_option_validation_and_no_shell_true(tmp_path: Path) -> None:
    """R-3.2: git_ops rejects leading '-' in remote/branch args and never uses shell=True."""
    from brain79.core.git_ops import git_fetch, git_pull_ff_only, git_remote_get_url

    with pytest.raises(ValueError, match="must not start with '-'"):
        git_fetch(tmp_path, remote="--upload-pack=evil")

    with pytest.raises(ValueError, match="must not start with '-'"):
        git_pull_ff_only(tmp_path, remote="origin", branch="--upload-pack=evil")

    with pytest.raises(ValueError, match="must not start with '-'"):
        git_remote_get_url(tmp_path, remote="-v")

    # Static AST check: git_ops.py never passes shell=True
    git_ops_src = Path("src/brain79/core/git_ops.py").read_text(encoding="utf-8")
    tree = ast.parse(git_ops_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    pytest.fail("git_ops.py must never use shell=True")
