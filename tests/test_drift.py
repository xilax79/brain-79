"""Tests for drift AST guard error handling (Phase 10 Stage 2: R-2.2, AC-10.6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brain79.core.drift import has_public_python_api_changes
from brain79.core.frontmatter import ValidationError
from brain79.core.git_ops import GitTimeoutError, NotAGitRepoError


def test_has_public_python_api_changes_fails_closed_on_git_timeout(tmp_path: Path) -> None:
    """AC-10.6: Simulated GitTimeoutError during AST Guard C raises ValidationError instead of fail-open."""
    p_root = tmp_path / "repo"
    p_root.mkdir()
    target = p_root / "mod.py"
    target.write_text("def foo() -> int:\n    return 1\n", encoding="utf-8")

    with patch(
        "brain79.core.ast_guards.python_inspector.git_last_commit_for_path",
        side_effect=GitTimeoutError("git log timed out"),
    ):
        with pytest.raises(ValidationError) as exc_info:
            has_public_python_api_changes(p_root, "mod.py", "features/mod.md")
        assert exc_info.value.rule == "ast_verification_failed"


def test_has_public_python_api_changes_fails_closed_on_unreadable_target(tmp_path: Path) -> None:
    """AC-10.6: Unreadable target (invalid UTF-8) during AST Guard C raises ValidationError instead of fail-open."""
    p_root = tmp_path / "repo"
    p_root.mkdir()
    target = p_root / "bad.py"
    target.write_bytes(b"\xff\xfe\x00\x00invalid utf-8")

    with pytest.raises(ValidationError) as exc_info:
        has_public_python_api_changes(p_root, "bad.py", "features/bad.md")
    assert exc_info.value.rule == "ast_verification_failed"


def test_has_public_python_api_changes_allows_non_git_workspace(tmp_path: Path) -> None:
    """R-2.2: Expected NotAGitRepoError in non-git workspace returns (False, '') cleanly."""
    p_root = tmp_path / "plain"
    p_root.mkdir()
    target = p_root / "mod.py"
    target.write_text("def foo() -> int:\n    return 1\n", encoding="utf-8")

    with patch(
        "brain79.core.ast_guards.python_inspector.git_last_commit_for_path",
        side_effect=NotAGitRepoError("not a git repo"),
    ):
        changed, desc = has_public_python_api_changes(p_root, "mod.py", "features/mod.md")
        assert changed is False
        assert desc == ""


def test_has_public_python_api_changes_rejects_escaping_symlink(tmp_path: Path) -> None:
    """AC-10.8: Escaping symlink in workspace is rejected with path_outside_project_root."""
    outside = tmp_path / "outside.py"
    outside.write_text("def leak() -> None:\n    pass\n", encoding="utf-8")

    p_root = tmp_path / "repo"
    p_root.mkdir()
    (p_root / "link.py").symlink_to(outside)

    with pytest.raises(ValidationError) as exc_info:
        has_public_python_api_changes(p_root, "link.py", "features/link.md")
    assert exc_info.value.rule == "path_outside_project_root"
