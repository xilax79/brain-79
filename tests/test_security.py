"""Security hardening tests (Phase 10 Stage 3: R-3.1, AC-10.8)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brain79.core.drift import compute_applies_to_manifest, has_public_python_api_changes
from brain79.core.frontmatter import ValidationError


def test_symlink_outside_project_root_rejected_by_ast_verification(tmp_path: Path) -> None:
    """AC-10.8: Symlink pointing outside project_root is rejected before reading by AST verification."""
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.py"
    secret_file.write_text("SECRET = 'top-secret'\n", encoding="utf-8")

    project_root = tmp_path / "project"
    project_root.mkdir()
    symlink_path = project_root / "evil_link.py"
    symlink_path.symlink_to(secret_file)

    with pytest.raises(ValidationError) as exc_info:
        has_public_python_api_changes(project_root, "evil_link.py", "features/evil.md")
    assert exc_info.value.rule == "path_outside_project_root"


def test_path_traversal_outside_project_root_rejected_by_ast_verification(tmp_path: Path) -> None:
    """AC-10.8: Relative '../' path traversal is rejected before reading by AST verification."""
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("X = 1\n", encoding="utf-8")

    project_root = tmp_path / "project"
    project_root.mkdir()

    with pytest.raises(ValidationError) as exc_info:
        has_public_python_api_changes(project_root, "../outside.py", "features/evil.md")
    assert exc_info.value.rule == "path_outside_project_root"


def test_symlink_outside_project_root_never_read_by_applies_to_manifest(tmp_path: Path) -> None:
    """R-3.1: compute_applies_to_manifest skips symlinks escaping project_root without reading them."""
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.py"
    secret_file.write_text("SECRET = 'do-not-read'\n", encoding="utf-8")

    project_root = tmp_path / "project"
    wiki_root = project_root / ".brain-79"
    wiki_root.mkdir(parents=True)
    symlink_path = project_root / "evil_link.py"
    symlink_path.symlink_to(secret_file)

    with patch("brain79.core.drift.compute_file_content_digest") as mock_digest:
        master, count, targets = compute_applies_to_manifest(
            ["evil_link.py"],
            project_root=project_root,
            wiki_root=wiki_root,
        )
        mock_digest.assert_not_called()
        assert master is None
        assert count == 0
        assert targets == {}
