"""Tests for pluggable AST inspector subsystem (Phase 10 Stage 4: R-4.1, AC-10.10)."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

from brain79.core.ast_guards import (
    LanguageInspector,
    PythonInspector,
    SignatureDiff,
    extract_public_python_signatures,
    get_inspector_for_path,
    has_public_python_api_changes,
    register_inspector,
    unregister_extensions,
)
from brain79.core.drift import (
    extract_public_python_signatures as drift_extract,
    has_public_python_api_changes as drift_has_changes,
)
from brain79.core.git_ops import GitSessionCache


def test_python_inspector_protocol_and_registry() -> None:
    """AC-10.10: LanguageInspector protocol, SignatureDiff, and extension registry work cleanly."""
    inspector = get_inspector_for_path("src/mod.py")
    assert inspector is not None
    assert isinstance(inspector, PythonInspector)
    assert isinstance(inspector, LanguageInspector)

    diff = inspector.compare_sources(
        "def alpha(x: int) -> int:\n    return x\n",
        "def alpha(x: int, y: int) -> int:\n    return x + y\n",
        "src/mod.py",
    )
    assert isinstance(diff, SignatureDiff)
    assert diff.has_changes is True
    assert "alpha" in diff.description

    # Re-exports in drift.py remain intact
    assert drift_extract is extract_public_python_signatures
    assert callable(drift_has_changes)

    # Custom inspector registration works
    class _DummyInspector:
        extensions: tuple[str, ...] = (".dummy",)

        def extract_signatures(self, source_code: str) -> dict[str, object]:
            return {}

        def compare_sources(self, base_source: str, current_source: str, rel_path: str) -> SignatureDiff:
            return SignatureDiff(has_changes=False, description="")

    dummy = _DummyInspector()
    register_inspector(dummy)
    try:
        assert get_inspector_for_path("foo/bar.dummy") is dummy
    finally:
        unregister_extensions([".dummy"])


def test_verifying_10_python_files_reuses_cached_head_lookup(tmp_path: Path) -> None:
    """AC-10.10: Verifying 10 .py files with a shared GitSessionCache reuses cached HEAD lookup."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)

    for i in range(10):
        (repo / f"mod_{i}.py").write_text(f"def fn_{i}() -> int:\n    return {i}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)

    cache = GitSessionCache()
    head_calls = 0
    real_run_git = __import__("brain79.core.git_ops", fromlist=["run_git"]).run_git

    def _counting_run_git(args: list[str], cwd: Path, **kwargs: object) -> object:
        nonlocal head_calls
        if list(args) == ["rev-parse", "HEAD"]:
            head_calls += 1
        return real_run_git(args, cwd, **kwargs)

    with patch("brain79.core.git_ops.run_git", side_effect=_counting_run_git):
        for i in range(10):
            changed, _ = has_public_python_api_changes(
                repo,
                f"mod_{i}.py",
                "features/untracked_article.md",
                git_cache=cache,
            )
            assert changed is False

    assert head_calls == 1, f"Expected 1 cached HEAD lookup across 10 files, got {head_calls}"
