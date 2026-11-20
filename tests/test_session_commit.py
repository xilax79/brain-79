"""Unit and transactional integrity tests for session_commit (Phase 10 Stage 1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brain79.config import set_project_root
from brain79.core.init_project import init_project
import brain79.core.session_commit as sc_mod
from brain79.core.session_commit import commit_session
from brain79.core.wiki import write_article


@pytest.fixture
def wiki_env(tmp_path: Path) -> tuple[Path, Path]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir, install_git_hooks_flag=False)
    wiki_root = project_dir / ".brain-79"
    return project_dir, wiki_root


def _valid_topic(title: str, summary: str, body: str = "Topic body.") -> str:
    return (
        "---\n"
        "type: topic\n"
        f"summary: {summary}\n"
        "last_updated: 2026-11-20\n"
        "---\n\n"
        f"# {title}\n\n"
        "## Overview\n"
        f"{body}\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )


def test_commit_session_rollback_restores_all_pass3_artifacts_and_preserves_unrelated_tmp(
    wiki_env: tuple[Path, Path],
) -> None:
    """AC-10.3: BaseException in Pass 3 rolls back all Pass 3 artifacts and preserves unrelated .tmp files."""
    _, wiki_root = wiki_env

    # Seed an existing article so registry, INDEX.md, and manifest have pre-commit state
    write_article(
        "topics/existing.md",
        _valid_topic("Existing Topic", "Initial existing topic summary", "Original body."),
        wiki_root=wiki_root,
    )
    manifest_file = wiki_root / ".drift_manifest.json"
    manifest_file.write_text('{"articles": {}}\n', encoding="utf-8")

    registry_file = wiki_root / ".navigation_registry.json"
    index_file = wiki_root / "INDEX.md"
    existing_file = wiki_root / "topics/existing.md"

    pre_existing = existing_file.read_text(encoding="utf-8")
    pre_manifest = manifest_file.read_text(encoding="utf-8")
    pre_registry = registry_file.read_text(encoding="utf-8")
    pre_index = index_file.read_text(encoding="utf-8")

    # Create an unrelated .tmp file simulating another concurrent worker
    unrelated_tmp = wiki_root / "topics" / "other_worker.tmp.999999"
    unrelated_tmp.write_text("do not delete me", encoding="utf-8")

    raw_sessions_dir = wiki_root / "_raw" / "sessions"
    pre_raw_files = set(raw_sessions_dir.glob("*")) if raw_sessions_dir.exists() else set()

    # Inject BaseException (KeyboardInterrupt) during Pass 3 after writes/raw session have occurred,
    # leaving a transaction-owned .tmp file behind to verify scoped cleanup.
    tx_owned_tmp = wiki_root / "topics" / "tx_owned.tmp.abc123"

    def _fail_with_tx_tmp(_w_root: Path) -> str:
        from brain79.core.locks import register_tx_temp_file

        tx_owned_tmp.write_text("partial tx temp", encoding="utf-8")
        register_tx_temp_file(tx_owned_tmp)
        raise KeyboardInterrupt("simulated interrupt in Pass 3")

    with patch.object(
        sc_mod,
        "regenerate_index_navigation",
        side_effect=_fail_with_tx_tmp,
    ):
        with pytest.raises(KeyboardInterrupt, match="simulated interrupt in Pass 3"):
            commit_session(
                session_summary="Session summary that must be rolled back",
                writes=[
                    {
                        "path": "topics/new_article.md",
                        "content": _valid_topic("New Article", "New article summary"),
                    }
                ],
                edits=[
                    {
                        "path": "topics/existing.md",
                        "edits": [{"old_text": "Original body.", "new_text": "Mutated body."}],
                    }
                ],
                wiki_root=wiki_root,
            )

    # All Pass 3 artifacts must be restored to pre-commit state
    assert existing_file.read_text(encoding="utf-8") == pre_existing
    assert not (wiki_root / "topics/new_article.md").exists()
    assert manifest_file.read_text(encoding="utf-8") == pre_manifest
    assert registry_file.read_text(encoding="utf-8") == pre_registry
    assert index_file.read_text(encoding="utf-8") == pre_index

    # Any _raw/sessions/ file created in Pass 3 must be cleaned up
    post_raw_files = set(raw_sessions_dir.glob("*")) if raw_sessions_dir.exists() else set()
    assert post_raw_files == pre_raw_files

    # Transaction-owned .tmp file must be unlinked on rollback
    assert not tx_owned_tmp.exists()

    # Unrelated worker temp file must remain untouched
    assert unrelated_tmp.exists()
    assert unrelated_tmp.read_text(encoding="utf-8") == "do not delete me"


def test_commit_session_surfaces_navigation_regeneration_failure(
    wiki_env: tuple[Path, Path],
) -> None:
    """AC-10.4: Failure in regenerate_index_navigation during Pass 3 never returns health_status='ok'."""
    _, wiki_root = wiki_env

    with patch.object(
        sc_mod,
        "regenerate_index_navigation",
        side_effect=RuntimeError("simulated index write failure"),
    ):
        result = commit_session(
            writes=[
                {
                    "path": "topics/nav_fail.md",
                    "content": _valid_topic("Nav Fail Topic", "Topic to test nav failure"),
                }
            ],
            wiki_root=wiki_root,
        )

    assert result["success"] is True
    assert result["health_status"] == "degraded"
    assert any("regenerate_index_navigation" in w or "INDEX.md" in w for w in result["warnings"])


def test_commit_session_pass2d_fails_closed_on_git_timeout(
    wiki_env: tuple[Path, Path],
) -> None:
    """AC-10.6: Simulated GitTimeoutError in Pass 2d raises ValidationError instead of fail-open."""
    from brain79.core.frontmatter import ValidationError
    from brain79.core.git_ops import GitTimeoutError

    _, wiki_root = wiki_env

    with patch.object(
        sc_mod,
        "git_dirty_paths",
        side_effect=GitTimeoutError("git status timed out"),
    ):
        with pytest.raises(ValidationError) as exc_info:
            commit_session(
                writes=[
                    {
                        "path": "topics/timeout_test.md",
                        "content": _valid_topic("Timeout Test", "Verify Pass 2d fails closed"),
                    }
                ],
                wiki_root=wiki_root,
            )
        assert exc_info.value.rule == "git_status_verification_failed"
