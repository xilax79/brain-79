"""Tests for Phase 11 Stage 5 R-5.1: Hot-path optimization, clone isolation, symlink containment, and GitSessionCache sharing."""

from pathlib import Path
from unittest.mock import patch

import pytest

from brain79.core.drift import WorkspaceIndex, _resolve_contained_path
from brain79.core.frontmatter import _clone_yaml_value, parse_frontmatter
from brain79.core.git_ops import GitSessionCache
from brain79.core.init_project import init_project
from brain79.core.orient import orient


def test_parse_cache_clone_isolation_for_nested_yaml_structures() -> None:
    """R-5.1: lightweight YAML cloner preserves 100% mutation isolation for nested dicts/lists."""
    raw = (
        "---\n"
        "type: architecture\n"
        "summary: test isolation\n"
        "stability: stable\n"
        "applies_to:\n"
        "  - src/a.py\n"
        "  - src/b.py\n"
        "last_updated: 2026-11-20\n"
        "---\n\n# Title\n"
    )
    meta1, body1 = parse_frontmatter(raw)
    meta1["applies_to"].append("src/mutated.py")
    meta1["injected"] = {"nested": [1, 2, 3]}

    meta2, body2 = parse_frontmatter(raw)
    assert meta2["applies_to"] == ["src/a.py", "src/b.py"]
    assert "injected" not in meta2
    assert body1 == body2

    # Direct nested dict/list check
    nested: dict[str, object] = {"a": [1, {"b": "x"}], "c": True, "d": None}
    cloned = _clone_yaml_value(nested)
    assert isinstance(cloned, dict)
    cloned["a"][1]["b"] = "changed"
    assert nested["a"] == [1, {"b": "x"}]


def test_workspace_index_memoized_resolve_contained_path_and_symlink_rejection(tmp_path: Path) -> None:
    """R-5.1: WorkspaceIndex.resolve_contained_path memoizes valid paths and rejects escaping symlinks/traversals."""
    proj = tmp_path / "repo"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    src_file = proj / "app.py"
    src_file.write_text("x = 1\n", encoding="utf-8")

    outside = tmp_path / "secret.txt"
    outside.write_text("top-secret\n", encoding="utf-8")
    escape_link = proj / "escape.txt"
    escape_link.symlink_to(outside)

    ws = WorkspaceIndex.build(proj, wiki)
    resolved_first = ws.resolve_contained_path("app.py")
    resolved_second = ws.resolve_contained_path("app.py")
    assert resolved_first == src_file.resolve()
    assert resolved_first == resolved_second
    assert "app.py" in ws._contained_path_cache

    with pytest.raises(ValueError, match="resolves outside project root"):
        ws.resolve_contained_path("escape.txt")
    # Cached rejection still raises ValueError
    with pytest.raises(ValueError, match="resolves outside project root"):
        ws.resolve_contained_path("escape.txt")

    with pytest.raises(ValueError, match="resolves outside project root"):
        _resolve_contained_path(proj, "../secret.txt", resolved_root=proj.resolve())


def test_orient_shares_single_git_session_cache(tmp_path: Path) -> None:
    """R-5.1: orient() creates and shares a single GitSessionCache across sub-calls."""
    init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
    w_root = tmp_path / ".brain-79"

    seen_caches: list[object] = []
    from brain79.core.drift import detect_all_drift as real_detect_all_drift

    def spy_detect_all_drift(*args: object, **kwargs: object) -> list[dict[str, object]]:
        seen_caches.append(kwargs.get("git_cache"))
        return real_detect_all_drift(*args, **kwargs)  # type: ignore[arg-type]

    with patch("brain79.core.drift.detect_all_drift", side_effect=spy_detect_all_drift):
        out = orient(task="check cache sharing", wiki_root=w_root)

    assert "Brain-79" in out
    assert len(seen_caches) == 1
    assert isinstance(seen_caches[0], GitSessionCache)
