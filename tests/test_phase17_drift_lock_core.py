"""Phase 17 Stage 1 tests: external drift.lock storage, locks, dual-read, exclusion, zero-mutation, and orient fast path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from brain79.cli.dispatch import dispatch_cmd
from brain79.core.ci_check import run_ci_check, run_lifecycle_hook
from brain79.core.drift import (
    CONFLICT_SENTINEL_DIGEST,
    DRIFT_LOCK_FILENAME,
    DRIFT_LOCK_VERSION,
    WorkspaceIndex,
    check_article_drift,
    compute_applies_to_manifest,
    compute_wiki_article_digest,
    detect_all_drift,
    load_drift_lock,
    parse_drift_lock_text,
    prune_drift_lock,
    save_drift_lock,
    serialize_drift_lock,
    update_drift_lock_entries,
    validate_drift_lock_data,
)
from brain79.core.frontmatter import ValidationError
from brain79.core.handoff_freshness import compute_handoff_freshness
from brain79.core.lint import collect_wiki_lint_results
from brain79.core.locks import (
    LOCK_HIERARCHY,
    cleanup_legacy_inline_locks,
    get_lock_path,
)
from brain79.core.navigation import regenerate_index_navigation
from brain79.core.orient import orient
from brain79.config import project_context
from brain79.core.context import get_context
from brain79.core.stats import compute_stats
from brain79.core.wiki import (
    list_articles,
    read_article,
    read_batch_articles,
    search_articles,
)


def _init_minimal_wiki(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal valid software wiki project under tmp_path."""
    p_root = tmp_path / "proj"
    w_root = p_root / ".brain-79"
    (w_root / "features").mkdir(parents=True)
    (w_root / "handoffs").mkdir(parents=True)
    (p_root / "src").mkdir(parents=True)

    (w_root / "INDEX.md").write_text(
        "---\ntype: navigation\nlast_updated: 2026-11-27\n---\n\n# Project index\n\n## Quick navigation\n",
        encoding="utf-8",
        newline="\n",
    )
    (w_root / "SCHEMA.md").write_text(
        "---\nprofile: software\nenforcement: strict\n---\n\n# Schema\n",
        encoding="utf-8",
        newline="\n",
    )
    return p_root, w_root


def _write_feature_article(
    w_root: Path,
    rel_path: str,
    applies_to: list[str] | None,
    *,
    status: str = "active",
    last_updated: str = "2026-11-27",
    extra_fm: str = "",
) -> Path:
    art_path = w_root / rel_path
    art_path.parent.mkdir(parents=True, exist_ok=True)
    applies_block = ""
    if applies_to is not None:
        applies_lines = "\n".join(f"  - {p}" for p in applies_to)
        applies_block = f"applies_to:\n{applies_lines}\n"
    art_path.write_text(
        (
            "---\n"
            "type: feature\n"
            f"status: {status}\n"
            f"summary: Test article {rel_path}.\n"
            f"last_updated: {last_updated}\n"
            f"{applies_block}"
            f"{extra_fm}"
            "---\n\n"
            f"# {rel_path}\n\n"
            "## Overview\n\nTest content.\n\n"
            "[← Back to Index](../INDEX.md)\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    return art_path


# ---------------------------------------------------------------------------
# AC-1: Deterministic schema, strict validation, locks, pruning, fail-closed
# ---------------------------------------------------------------------------


def test_drift_lock_deterministic_serialization_and_empty_invariant(tmp_path: Path) -> None:
    """R-1.1: Deterministic LF JSON serialization and empty-nonexistent invariant."""
    _, w_root = _init_minimal_wiki(tmp_path)
    lock_file = w_root / DRIFT_LOCK_FILENAME

    # Empty articles must NOT create drift.lock when absent
    wrote = save_drift_lock(w_root, {"version": DRIFT_LOCK_VERSION, "articles": {}})
    assert wrote is False
    assert not lock_file.exists()

    # Non-empty articles creates deterministic LF JSON
    data = {
        "version": DRIFT_LOCK_VERSION,
        "articles": {
            "features/b.md": {
                "digest": "sha256:0123456789abcdef",
                "count": 1,
                "targets": {"src/b.py": "sha256:fedcba9876543210"},
            },
            "features/a.md": {
                "digest": "sha256:abcdef0123456789",
                "count": 0,
                "targets": {},
            },
        },
    }
    assert save_drift_lock(w_root, data) is True
    assert lock_file.is_file()

    raw_bytes = lock_file.read_bytes()
    assert b"\r\n" not in raw_bytes
    text = raw_bytes.decode("utf-8")
    assert text == serialize_drift_lock(data)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")

    # Once drift.lock exists, saving empty articles updates it rather than failing
    assert save_drift_lock(w_root, {"version": DRIFT_LOCK_VERSION, "articles": {}}) is True
    loaded = load_drift_lock(w_root)
    assert loaded == {"version": DRIFT_LOCK_VERSION, "articles": {}}


@pytest.mark.parametrize(
    "raw_json",
    [
        "",
        "   \n",
        "{not valid json",
        '{"version": "2.0", "version": "2.0", "articles": {}}',
        '{"version": "2.0", "articles": {"features/a.md": {"digest": "sha256:0123456789abcdef", "count": NaN, "targets": {}}}}',
        '{"version": "1.0", "articles": {}}',
        '{"version": "2.0", "articles": {}, "extra": 1}',
        '{"version": "2.0", "articles": {"/abs.md": {"digest": "sha256:0123456789abcdef", "count": 0, "targets": {}}}}',
        '{"version": "2.0", "articles": {".brain-79/features/a.md": {"digest": "sha256:0123456789abcdef", "count": 0, "targets": {}}}}',
        '{"version": "2.0", "articles": {"../escape.md": {"digest": "sha256:0123456789abcdef", "count": 0, "targets": {}}}}',
        '{"version": "2.0", "articles": {"features\\\\a.md": {"digest": "sha256:0123456789abcdef", "count": 0, "targets": {}}}}',
        '{"version": "2.0", "articles": {"features/a.md": {"digest": "bad", "count": 0, "targets": {}}}}',
        '{"version": "2.0", "articles": {"features/a.md": {"digest": "sha256:0123456789abcdef", "count": true, "targets": {}}}}',
        '{"version": "2.0", "articles": {"features/a.md": {"digest": "sha256:0123456789abcdef", "count": -1, "targets": {}}}}',
        '{"version": "2.0", "articles": {"features/a.md": {"digest": "sha256:0123456789abcdef", "count": 0, "targets": {}, "unknown": 1}}}',
        '{"version": "2.0", "articles": {"features/a.md": {"digest": "sha256:0123456789abcdef", "count": 0, "targets": {}, "conflict": false}}}',
        '{"version": "2.0", "articles": {"features/a.md": {"digest": "sha256:0123456789abcdef", "count": 1, "targets": {"../bad.py": "sha256:0123456789abcdef"}}}}',
    ],
)
def test_drift_lock_rejects_corrupt_payloads(tmp_path: Path, raw_json: str) -> None:
    """R-1.1 & R-1.4: Strict schema validation rejects all corrupt drift.lock payloads."""
    _, w_root = _init_minimal_wiki(tmp_path)
    (w_root / DRIFT_LOCK_FILENAME).write_text(raw_json, encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        load_drift_lock(w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"


def test_drift_lock_rejects_invalid_utf8(tmp_path: Path) -> None:
    """R-1.4: Invalid UTF-8 bytes in drift.lock raise ValidationError(rule='corrupt_drift_lock')."""
    _, w_root = _init_minimal_wiki(tmp_path)
    (w_root / DRIFT_LOCK_FILENAME).write_bytes(b"\xff\xfe\x00\x00")

    with pytest.raises(ValidationError) as exc_info:
        load_drift_lock(w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"


def test_lock_mapping_and_cleanup_preserves_drift_lock(tmp_path: Path) -> None:
    """R-1.2: get_lock_path maps drift.lock to _drift_lock.lock and cleanup_legacy_inline_locks preserves drift.lock."""
    _, w_root = _init_minimal_wiki(tmp_path)

    assert "_drift_lock.lock" in LOCK_HIERARCHY
    assert LOCK_HIERARCHY.index("_registry.lock") < LOCK_HIERARCHY.index("_drift_lock.lock")
    assert LOCK_HIERARCHY.index("_drift_lock.lock") < LOCK_HIERARCHY.index("_drift_manifest.lock")
    assert get_lock_path(w_root, "drift.lock") == w_root / ".locks" / "_drift_lock.lock"
    assert get_lock_path(w_root, ".drift_manifest.json") == w_root / ".locks" / "_drift_manifest.lock"

    # Create tracked drift.lock and stray legacy inline locks
    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/a.md": {
                    "digest": "sha256:0123456789abcdef",
                    "count": 0,
                    "targets": {},
                }
            },
        },
    )
    stray_index_lock = w_root / "INDEX.md.lock"
    stray_feature_lock = w_root / "features" / "a.md.lock"
    stray_index_lock.write_text("", encoding="utf-8")
    stray_feature_lock.write_text("", encoding="utf-8")

    removed = cleanup_legacy_inline_locks(w_root)
    assert removed == 2
    assert (w_root / DRIFT_LOCK_FILENAME).is_file()
    assert not stray_index_lock.exists()
    assert not stray_feature_lock.exists()


def test_navigation_prunes_deleted_inactive_and_unanchored_entries(tmp_path: Path) -> None:
    """R-1.3: regenerate_index_navigation prunes deleted, inactive, and unanchored articles from drift.lock."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    (p_root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")

    _write_feature_article(w_root, "features/active.md", ["src/a.py"], status="active")
    _write_feature_article(w_root, "features/inactive.md", ["src/a.py"], status="archived")
    _write_feature_article(w_root, "features/unanchored.md", None, status="active")

    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/active.md": {
                    "digest": "sha256:0123456789abcdef",
                    "count": 1,
                    "targets": {"src/a.py": "sha256:0123456789abcdef"},
                },
                "features/inactive.md": {
                    "digest": "sha256:0123456789abcdef",
                    "count": 1,
                    "targets": {"src/a.py": "sha256:0123456789abcdef"},
                },
                "features/unanchored.md": {
                    "digest": "sha256:0123456789abcdef",
                    "count": 1,
                    "targets": {"src/a.py": "sha256:0123456789abcdef"},
                },
                "features/deleted.md": {
                    "digest": "sha256:0123456789abcdef",
                    "count": 1,
                    "targets": {"src/a.py": "sha256:0123456789abcdef"},
                },
            },
        },
    )

    regenerate_index_navigation(w_root, rebuild=True)
    loaded = load_drift_lock(w_root)
    assert loaded is not None
    assert list(loaded["articles"].keys()) == ["features/active.md"]


def test_corrupt_drift_lock_fails_closed_everywhere_except_lifecycle_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-1.4: Corrupt drift.lock fails closed across all read/nav paths (Exit 1 in ci-check), while lifecycle hook stays fail-open."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    # Zero active governed articles — still MUST fail closed unconditionally!
    (w_root / DRIFT_LOCK_FILENAME).write_text('{"version": "2.0", "articles": {"bad": {}}}', encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        detect_all_drift(wiki_root=w_root, project_root=p_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        orient(wiki_root=w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        compute_stats(wiki_root=w_root, project_root=p_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        collect_wiki_lint_results(wiki_root=w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        regenerate_index_navigation(w_root, rebuild=True)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        run_ci_check(project_root=p_root, wiki_root=w_root, enforcement="strict")
    assert exc_info.value.rule == "corrupt_drift_lock"

    # CLI dispatch for ci-check must exit 1 (not 2)
    monkeypatch.setenv("BRAIN79_PROJECT_ROOT", str(p_root))
    rc = dispatch_cmd("ci-check", ["--project-root", str(p_root), "--enforcement", "strict"])
    assert rc == 1

    # Lifecycle hook must remain fail-open (ADR-021): returns {} and Exit 0
    hook_res = run_lifecycle_hook(
        "session-start",
        client="agy",
        stdin_payload=json.dumps({"hookEventName": "session-start", "workspacePaths": [str(p_root)]}),
        project_root=p_root,
    )
    assert hook_res == {}
    hook_rc = dispatch_cmd(
        "ci-check",
        ["--project-root", str(p_root), "--lifecycle-hook", "session-start", "--client", "agy"],
    )
    assert hook_rc == 0


# ---------------------------------------------------------------------------
# AC-4: Exact per-file attribution, conflict, dual-read, exclusion, zero-mutation
# ---------------------------------------------------------------------------


def test_fresh_clone_exact_per_file_attribution_without_manifest(tmp_path: Path) -> None:
    """R-3.1: Fresh clone with drift.lock and no .drift_manifest.json reports exact modified/deleted/added attribution."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    (p_root / "src" / "keep.py").write_text("keep = 1\n", encoding="utf-8")
    (p_root / "src" / "mod.py").write_text("mod = 1\n", encoding="utf-8")
    (p_root / "src" / "del.py").write_text("gone = 1\n", encoding="utf-8")

    _write_feature_article(w_root, "features/core.md", ["src/*.py"])
    digest, count, targets = compute_applies_to_manifest(["src/*.py"], p_root, w_root)
    assert digest is not None and count == 3

    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/core.md": {
                    "digest": digest,
                    "count": count,
                    "targets": targets,
                }
            },
        },
    )
    assert not (w_root / ".drift_manifest.json").exists()

    # Mutate workspace: modify mod.py, delete del.py, add add.py
    (p_root / "src" / "mod.py").write_text("mod = 2\n", encoding="utf-8")
    (p_root / "src" / "del.py").unlink()
    (p_root / "src" / "add.py").write_text("added = 1\n", encoding="utf-8")

    drifts = detect_all_drift(wiki_root=w_root, project_root=p_root)
    by_target = {d["workspace_file"]: d["drift_kind"] for d in drifts}
    assert by_target == {
        "src/mod.py": "modified",
        "src/del.py": "deleted",
        "src/add.py": "added",
    }
    assert not (w_root / ".drift_manifest.json").exists()


def test_conflict_sentinel_and_transitive_propagation(tmp_path: Path) -> None:
    """R-3.1: conflict: true emits drift_kind='conflict' and propagates transitively to parent umbrella."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    (p_root / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")

    _write_feature_article(w_root, "features/child.md", ["src/a.py"], last_updated="2026-11-27")
    _write_feature_article(w_root, "features/parent.md", [".brain-79/features/child.md"], last_updated="2026-11-27")

    p_digest, p_count, p_targets = compute_applies_to_manifest(
        [".brain-79/features/child.md"], p_root, w_root, exclude_self_path="features/parent.md"
    )
    assert p_digest is not None

    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/child.md": {
                    "digest": CONFLICT_SENTINEL_DIGEST,
                    "count": 0,
                    "targets": {},
                    "conflict": True,
                },
                "features/parent.md": {
                    "digest": p_digest,
                    "count": p_count,
                    "targets": p_targets,
                },
            },
        },
    )

    child_drifts = check_article_drift("features/child.md", wiki_root=w_root, project_root=p_root)
    assert len(child_drifts) == 1
    assert child_drifts[0]["drift_kind"] == "conflict"

    parent_drifts = check_article_drift("features/parent.md", wiki_root=w_root, project_root=p_root)
    assert len(parent_drifts) == 1
    assert parent_drifts[0]["drift_kind"] == "transitive"
    assert parent_drifts[0]["child_article"] == "features/child.md"


def test_tampered_master_digest_zero_masking_fallback(tmp_path: Path) -> None:
    """R-3.1: If targets match disk but stored master digest mismatches, emit fallback modified drift."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    (p_root / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
    _write_feature_article(w_root, "features/a.md", ["src/a.py"])
    _, count, targets = compute_applies_to_manifest(["src/a.py"], p_root, w_root)

    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/a.md": {
                    "digest": "sha256:000000000000dead",
                    "count": count,
                    "targets": targets,
                }
            },
        },
    )

    drifts = check_article_drift("features/a.md", wiki_root=w_root, project_root=p_root)
    assert len(drifts) == 1
    assert drifts[0]["drift_kind"] == "modified"
    assert drifts[0]["fallback_targets"] == ["src/a.py"]


def test_legacy_frontmatter_dual_read_fallback(tmp_path: Path) -> None:
    """R-3.1: Articles without drift.lock entry fall back to legacy frontmatter applies_to_digest."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    (p_root / "src" / "legacy.py").write_text("v = 1\n", encoding="utf-8")
    _write_feature_article(
        w_root,
        "features/legacy.md",
        ["src/legacy.py"],
        extra_fm='applies_to_digest: "sha256:1111111111111111"\napplies_to_count: 1\n',
    )

    drifts = detect_all_drift(wiki_root=w_root, project_root=p_root)
    assert len(drifts) == 1
    assert drifts[0]["article_path"] == "features/legacy.md"
    assert drifts[0]["drift_kind"] == "modified"
    # Read-only dual-read must not persist .drift_manifest.json or drift.lock
    assert not (w_root / ".drift_manifest.json").exists()
    assert not (w_root / DRIFT_LOCK_FILENAME).exists()


def test_drift_lock_excluded_from_workspace_ci_and_handoff_freshness(tmp_path: Path) -> None:
    """R-3.3: drift.lock is excluded from WorkspaceIndex.all_paths, ci-check impacted_articles, and handoff staleness."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    _write_feature_article(w_root, "features/meta.md", [".brain-79/**"])

    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/meta.md": {
                    "digest": "sha256:0123456789abcdef",
                    "count": 0,
                    "targets": {},
                }
            },
        },
    )

    ws = WorkspaceIndex.build(p_root, w_root)
    assert ".brain-79/drift.lock" not in ws.all_paths

    handoff_file = w_root / "handoffs" / "2026-11-27-01.md"
    handoff_file.write_text(
        "---\n"
        "type: handoff\n"
        "date: 2026-11-27\n"
        "created_at: 2026-11-27T12:00:00Z\n"
        "branch: main\n"
        "wiki_digest: sha256:0000000000000000\n"
        "---\n\n# Handoff\n",
        encoding="utf-8",
        newline="\n",
    )
    freshness = compute_handoff_freshness(handoff_file, wiki_root=w_root, workspace_index=ws)
    assert "drift.lock" not in freshness.changed_wiki_articles


def test_read_only_commands_perform_zero_disk_mutations(tmp_path: Path) -> None:
    """R-3.3: orient, stats, ci-check, lint, read, read-batch, context, list, search create zero files under .brain-79/ or .locks/."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    (p_root / "src" / "app.py").write_text("def hello() -> str:\n    return 'hi'\n", encoding="utf-8")
    _write_feature_article(w_root, "features/app.md", ["src/app.py"])

    digest, count, targets = compute_applies_to_manifest(["src/app.py"], p_root, w_root)
    assert digest is not None
    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/app.md": {"digest": digest, "count": count, "targets": targets}
            },
        },
    )

    # Remove .locks/ to verify read-only commands never recreate it or .drift_manifest.json
    locks_dir = w_root / ".locks"
    if locks_dir.exists():
        for f in locks_dir.iterdir():
            f.unlink()
        locks_dir.rmdir()

    def _snapshot() -> set[str]:
        return {p.relative_to(w_root).as_posix() for p in w_root.rglob("*")}

    before = _snapshot()

    with project_context(p_root, w_root):
        orient(task="hello", wiki_root=w_root)
        compute_stats(wiki_root=w_root, project_root=p_root)
        run_ci_check(project_root=p_root, wiki_root=w_root, enforcement="strict")
        collect_wiki_lint_results(wiki_root=w_root)
        read_article("features/app.md", wiki_root=w_root)
        read_batch_articles(["features/app.md"], wiki_root=w_root)
        get_context("app")
        list_articles(wiki_root=w_root)
        search_articles("hello")

    after = _snapshot()
    assert after == before
    assert not (w_root / ".drift_manifest.json").exists()
    assert not (w_root / ".locks").exists()


# ---------------------------------------------------------------------------
# AC-8 (c): orient() zero-rebuild fast path
# ---------------------------------------------------------------------------


def test_orient_skips_rebuild_drift_manifest_when_tracked_in_drift_lock(tmp_path: Path) -> None:
    """R-6.3: orient() MUST NOT invoke rebuild_drift_manifest() when all active governed articles are in drift.lock."""
    p_root, w_root = _init_minimal_wiki(tmp_path)
    (p_root / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _write_feature_article(w_root, "features/mod.md", ["src/mod.py"])

    digest, count, targets = compute_applies_to_manifest(["src/mod.py"], p_root, w_root)
    assert digest is not None
    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/mod.md": {"digest": digest, "count": count, "targets": targets}
            },
        },
    )

    with patch("brain79.core.drift.rebuild_drift_manifest") as mock_rebuild:
        out = orient(task="mod", wiki_root=w_root)
        assert "features/mod.md" in out or "Active handoff state" in out
        mock_rebuild.assert_not_called()
