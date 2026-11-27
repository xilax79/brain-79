"""Phase 17 Stage 2 tests: hash-free writes, zero-diff verified_articles, conflict blocking, Guard C baseline resolver, and Pass 2d ripple parity."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from brain79.core.ast_guards.orchestrator import has_public_api_changes
from brain79.core.ast_guards.python_inspector import has_public_python_api_changes
from brain79.core.drift import (
    CONFLICT_SENTINEL_DIGEST,
    DRIFT_LOCK_FILENAME,
    DRIFT_LOCK_VERSION,
    compute_applies_to_manifest,
    load_drift_lock,
    save_drift_lock,
)
from brain79.core.frontmatter import ValidationError
from brain79.core.git_ops import GitSessionCache
from brain79.core.session_commit import commit_session
from brain79.core.wiki import edit_article, write_article, write_many_articles


def _init_project(tmp_path: Path, *, enforcement: str = "strict") -> tuple[Path, Path]:
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
        f"---\nprofile: software\nenforcement: {enforcement}\n---\n\n# Schema\n",
        encoding="utf-8",
        newline="\n",
    )
    return p_root, w_root


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def _init_git_repo(p_root: Path) -> None:
    _git(p_root, "init")
    _git(p_root, "config", "user.email", "test@example.com")
    _git(p_root, "config", "user.name", "Test User")


def _feature_md(
    title: str,
    applies_to: list[str] | None,
    *,
    status: str = "shipped",
    extra_fm: str = "",
    body_extra: str = "",
) -> str:
    applies_block = ""
    if applies_to is not None:
        lines = "\n".join(f"  - {p}" for p in applies_to)
        applies_block = f"applies_to:\n{lines}\n"
    return (
        "---\n"
        "type: feature\n"
        "summary: feature summary for testing\n"
        f"status: {status}\n"
        "last_updated: 2026-11-27\n"
        f"{applies_block}"
        f"{extra_fm}"
        "---\n\n"
        f"# Feature — {title}\n\n"
        "## Overview\n\n"
        f"Describes {title}.{body_extra}\n\n"
        "[← Back to Index](../INDEX.md)\n"
    )


# ---------------------------------------------------------------------------
# AC-1 write/session-commit corrupt & pruning cases
# ---------------------------------------------------------------------------


def test_corrupt_drift_lock_blocks_all_write_and_session_commit_paths(tmp_path: Path) -> None:
    """R-1.4: write_article (incl. force_validation_skip, is_special, no applies_to), write_many_articles, and commit_session fail closed on corrupt drift.lock."""
    p_root, w_root = _init_project(tmp_path)
    (p_root / "src" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")

    corrupt_payload = '{"version": "2.0", "articles": {"features/a.md": {"digest": "sha256:0000000000000000", "count": 0, "targets": {}, "conflict": false}}}'
    lock_file = w_root / DRIFT_LOCK_FILENAME
    lock_file.write_text(corrupt_payload, encoding="utf-8", newline="\n")

    art_content = _feature_md("Alpha", ["src/a.py"])
    topic_content = (
        "---\ntype: topic\nsummary: topic summary\nstatus: active\nlast_updated: 2026-11-27\n---\n\n"
        "# Topic — Notes\n\n## Overview\n\nDetails.\n\n[← Back to Index](../INDEX.md)\n"
    )

    with pytest.raises(ValidationError) as exc_info:
        write_article("features/alpha.md", art_content, wiki_root=w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        write_article("features/alpha.md", art_content, force_validation_skip=True, wiki_root=w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        write_article("_raw/note.md", "# Raw\n", wiki_root=w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        write_article("topics/notes.md", topic_content, wiki_root=w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        write_many_articles([{"path": "topics/notes.md", "content": topic_content}], wiki_root=w_root)
    assert exc_info.value.rule == "corrupt_drift_lock"

    with pytest.raises(ValidationError) as exc_info:
        commit_session(
            session_summary="Handoff-only session",
            allow_partial_ripple=True,
            wiki_root=w_root,
        )
    assert exc_info.value.rule == "corrupt_drift_lock"

    # Corrupt file must never be silently overwritten
    assert lock_file.read_text(encoding="utf-8") == corrupt_payload


def test_write_article_and_commit_session_prune_inactive_and_unanchored_articles(tmp_path: Path) -> None:
    """R-1.3: transitioning to inactive/pre-impl or removing applies_to (including force_validation_skip=True) prunes drift.lock."""
    p_root, w_root = _init_project(tmp_path)
    (p_root / "src" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
    (p_root / "src" / "b.py").write_text("def b() -> int:\n    return 2\n", encoding="utf-8", newline="\n")

    write_article("features/a.md", _feature_md("A", ["src/a.py"]), wiki_root=w_root)
    write_article("features/b.md", _feature_md("B", ["src/b.py"]), wiki_root=w_root)

    locked = load_drift_lock(w_root)
    assert locked is not None
    assert set(locked["articles"].keys()) == {"features/a.md", "features/b.md"}

    # Transition features/a.md to archived with force_validation_skip=True -> pruned from drift.lock
    write_article(
        "features/a.md",
        _feature_md("A", ["src/a.py"], status="archived", extra_fm="applies_to_digest: \"sha256:1111111111111111\"\napplies_to_count: 1\n"),
        force_validation_skip=True,
        wiki_root=w_root,
    )
    locked = load_drift_lock(w_root)
    assert locked is not None
    assert "features/a.md" not in locked["articles"]
    assert "features/b.md" in locked["articles"]
    assert "applies_to_digest" not in (w_root / "features/a.md").read_text(encoding="utf-8")

    # Remove applies_to from features/b.md in commit_session (balanced mode to allow unanchored) -> pruned
    (w_root / "SCHEMA.md").write_text(
        "---\nprofile: software\nenforcement: balanced\n---\n\n# Schema\n",
        encoding="utf-8",
        newline="\n",
    )
    commit_session(
        writes=[{"path": "features/b.md", "content": _feature_md("B", None)}],
        session_summary="Removed applies_to from B",
        wiki_root=w_root,
    )
    locked = load_drift_lock(w_root)
    assert locked is not None
    assert "features/b.md" not in locked["articles"]


# ---------------------------------------------------------------------------
# AC-2: Hash-free writes, concurrency, verified_articles, conflict, rollback
# ---------------------------------------------------------------------------


def test_write_article_hash_free_stripping_and_force_skip_malformed_yaml(tmp_path: Path) -> None:
    """R-2.1 / AC-2(a): strips legacy digest keys without writing .drift_manifest.json; force_validation_skip handles valid & malformed YAML."""
    p_root, w_root = _init_project(tmp_path)
    (p_root / "src" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")

    legacy_md = _feature_md(
        "Alpha",
        ["src/a.py"],
        extra_fm='applies_to_digest: "sha256:aaaaaaaaaaaaaaaa"\napplies_to_count: 1\n',
    )
    write_article("features/alpha.md", legacy_md, wiki_root=w_root)

    disk_text = (w_root / "features/alpha.md").read_text(encoding="utf-8")
    assert "applies_to_digest" not in disk_text
    assert "applies_to_count" not in disk_text
    assert not (w_root / ".drift_manifest.json").exists()

    locked = load_drift_lock(w_root)
    assert locked is not None
    assert "features/alpha.md" in locked["articles"]
    assert locked["articles"]["features/alpha.md"]["count"] == 1
    assert "src/a.py" in locked["articles"]["features/alpha.md"]["targets"]

    # edit_article inherits hash-free stripping and drift.lock update
    (p_root / "src" / "a.py").write_text("def a() -> int:\n    return 2\n", encoding="utf-8", newline="\n")
    edit_article(
        "features/alpha.md",
        [{"old_text": "Describes Alpha.", "new_text": "Describes Alpha v2."}],
        wiki_root=w_root,
    )
    disk_after_edit = (w_root / "features/alpha.md").read_text(encoding="utf-8")
    assert "applies_to_digest" not in disk_after_edit
    assert not (w_root / ".drift_manifest.json").exists()

    # force_validation_skip=True with valid YAML strips legacy keys
    write_article(
        "features/beta.md",
        _feature_md("Beta", None, extra_fm='applies_to_digest: "sha256:bbbbbbbbbbbbbbbb"\napplies_to_count: 1\n'),
        force_validation_skip=True,
        wiki_root=w_root,
    )
    beta_text = (w_root / "features/beta.md").read_text(encoding="utf-8")
    assert "applies_to_digest" not in beta_text
    assert "applies_to_count" not in beta_text
    assert "force_validation_skipped: true" in beta_text

    # force_validation_skip=True with intentionally malformed YAML must not crash
    malformed = "---\ntitle: [unclosed\napplies_to_digest: \"sha256:cccccccccccccccc\"\n---\n\n# Broken\n"
    write_article("features/malformed.md", malformed, force_validation_skip=True, wiki_root=w_root)
    assert (w_root / "features/malformed.md").exists()


def test_concurrent_write_article_preserves_all_drift_lock_entries(tmp_path: Path) -> None:
    """R-2.1 / AC-2(a): concurrent write_article calls on distinct articles do not clobber drift.lock."""
    p_root, w_root = _init_project(tmp_path)
    for i in range(6):
        (p_root / "src" / f"mod_{i}.py").write_text(f"def fn_{i}() -> int:\n    return {i}\n", encoding="utf-8", newline="\n")

    def _write_one(idx: int) -> None:
        write_article(
            f"features/mod_{idx}.md",
            _feature_md(f"Mod {idx}", [f"src/mod_{idx}.py"]),
            wiki_root=w_root,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_write_one, range(6)))

    locked = load_drift_lock(w_root)
    assert locked is not None
    assert set(locked["articles"].keys()) == {f"features/mod_{i}.md" for i in range(6)}


def test_write_article_and_write_many_rollback_on_drift_lock_failure(tmp_path: Path) -> None:
    """R-2.1 / AC-2(b): write_article and write_many_articles restore/unlink .md and drift.lock on failure."""
    p_root, w_root = _init_project(tmp_path)
    (p_root / "src" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
    (p_root / "src" / "b.py").write_text("def b() -> int:\n    return 2\n", encoding="utf-8", newline="\n")

    write_article("features/a.md", _feature_md("A", ["src/a.py"]), wiki_root=w_root)
    orig_lock_bytes = (w_root / DRIFT_LOCK_FILENAME).read_bytes()
    orig_a_bytes = (w_root / "features/a.md").read_bytes()

    # Standalone write_article failure during drift.lock update restores/unlinks .md
    with patch("brain79.core.drift.update_drift_lock_entries", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            write_article("features/b.md", _feature_md("B", ["src/b.py"]), wiki_root=w_root)
    assert not (w_root / "features/b.md").exists()
    assert (w_root / DRIFT_LOCK_FILENAME).read_bytes() == orig_lock_bytes

    # write_many_articles mid-batch failure restores drift.lock and .md files
    call_count = 0
    real_write = write_article

    def _fail_on_second(path: str, content: str, **kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("simulated mid-batch failure")
        return real_write(path, content, **kwargs)  # type: ignore[arg-type]

    with patch("brain79.core.wiki.write_article", side_effect=_fail_on_second):
        with pytest.raises(OSError, match="simulated mid-batch failure"):
            write_many_articles(
                [
                    {"path": "features/a.md", "content": _feature_md("A", ["src/a.py"], body_extra=" Updated.")},
                    {"path": "features/b.md", "content": _feature_md("B", ["src/b.py"])},
                ],
                wiki_root=w_root,
            )

    assert (w_root / "features/a.md").read_bytes() == orig_a_bytes
    assert not (w_root / "features/b.md").exists()
    assert (w_root / DRIFT_LOCK_FILENAME).read_bytes() == orig_lock_bytes


def test_verified_articles_zero_diff_on_md_and_precedence_over_edits(tmp_path: Path) -> None:
    """R-2.2 / AC-2(c),(e): verified_articles leaves .md git diff empty (even with legacy frontmatter); writes/edits takes precedence."""
    p_root, w_root = _init_project(tmp_path)
    _init_git_repo(p_root)

    src_a = p_root / "src" / "a.py"
    src_b = p_root / "src" / "b.py"
    src_a.write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
    src_b.write_text("def b() -> int:\n    return 2\n", encoding="utf-8", newline="\n")

    # Seed features/a.md with legacy frontmatter digest and features/b.md hash-free
    dig_a, cnt_a, _ = compute_applies_to_manifest(["src/a.py"], p_root, w_root)
    (w_root / "features/a.md").write_text(
        _feature_md("A", ["src/a.py"], extra_fm=f'applies_to_digest: "{dig_a}"\napplies_to_count: {cnt_a}\n'),
        encoding="utf-8",
        newline="\n",
    )
    write_article("features/b.md", _feature_md("B", ["src/b.py"]), wiki_root=w_root)

    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "initial")

    # Internal non-API refactor in both files
    src_a.write_text("def a() -> int:\n    x = 1\n    return x\n", encoding="utf-8", newline="\n")
    src_b.write_text("def b() -> int:\n    y = 2\n    return y\n", encoding="utf-8", newline="\n")

    # Verify a.md via verified_articles; edit AND verify b.md (edits must win)
    res = commit_session(
        edits=[
            {
                "path": "features/b.md",
                "edits": [{"old_text": "Describes B.", "new_text": "Describes B (edited)."}],
            }
        ],
        verified_articles=[
            {"path": "features/a.md", "reason": "Internal refactor only, public signature unchanged."},
            {"path": "features/b.md", "reason": "Also passed in verified_articles, edits must take precedence."},
        ],
        session_summary="Refactor a and b",
        wiki_root=w_root,
    )
    assert res["success"] is True

    # git diff on features/a.md MUST be empty (zero-diff even with legacy frontmatter digest)
    assert _git(p_root, "diff", "--", ".brain-79/features/a.md") == ""
    assert "applies_to_digest" in (w_root / "features/a.md").read_text(encoding="utf-8")

    # features/b.md was edited (hash-free)
    b_disk = (w_root / "features/b.md").read_text(encoding="utf-8")
    assert "Describes B (edited)." in b_disk
    assert "applies_to_digest" not in b_disk

    locked = load_drift_lock(w_root)
    assert locked is not None
    assert "features/a.md" in locked["articles"]
    assert "features/b.md" in locked["articles"]


def test_verified_articles_conflict_blocking_across_enforcement_tiers(tmp_path: Path) -> None:
    """R-2.2 / AC-2(d): conflict sentinel blocks verified_articles under strict/balanced and warns under advisory."""
    for tier, should_raise in [("strict", True), ("balanced", True), ("advisory", False)]:
        sub = tmp_path / tier
        p_root, w_root = _init_project(sub, enforcement=tier)
        (p_root / "src" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
        (w_root / "features/a.md").write_text(_feature_md("A", ["src/a.py"]), encoding="utf-8", newline="\n")

        save_drift_lock(
            w_root,
            {
                "version": DRIFT_LOCK_VERSION,
                "articles": {
                    "features/a.md": {
                        "conflict": True,
                        "count": 0,
                        "digest": CONFLICT_SENTINEL_DIGEST,
                        "targets": {},
                    }
                },
            },
        )

        if should_raise:
            with pytest.raises(ValidationError) as exc_info:
                commit_session(
                    verified_articles=[
                        {"path": "features/a.md", "reason": "Attempting to clear conflict without editing article."}
                    ],
                    session_summary="Attempt verify on conflict",
                    wiki_root=w_root,
                )
            assert exc_info.value.rule == "verified_article_conflict_forbidden"
        else:
            res = commit_session(
                verified_articles=[
                    {"path": "features/a.md", "reason": "Attempting to clear conflict under advisory mode."}
                ],
                session_summary="Advisory verify on conflict",
                wiki_root=w_root,
            )
            assert res["success"] is True
            assert any("verified_article_conflict_forbidden" in w for w in res["warnings"])


def test_commit_session_pass3_rollback_restores_or_unlinks_drift_lock(tmp_path: Path) -> None:
    """R-2.3 / AC-2(f): Pass 3 failure atomically restores pre-existing drift.lock or unlinks newly created drift.lock."""
    # Case 1: drift.lock did not exist pre-transaction -> unlinked on Pass 3 failure
    p1, w1 = _init_project(tmp_path / "c1")
    (p1 / "src" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")

    with patch("brain79.core.session_commit.write_article", side_effect=OSError("disk error in pass 3")):
        with pytest.raises(OSError, match="disk error in pass 3"):
            commit_session(
                writes=[{"path": "features/a.md", "content": _feature_md("A", ["src/a.py"])}],
                session_summary="Should roll back",
                wiki_root=w1,
            )
    assert not (w1 / DRIFT_LOCK_FILENAME).exists()
    assert not (w1 / "features/a.md").exists()

    # Case 2: drift.lock existed pre-transaction -> restored byte-for-byte on Pass 3 failure
    p2, w2 = _init_project(tmp_path / "c2")
    (p2 / "src" / "a.py").write_text("def a() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
    (p2 / "src" / "b.py").write_text("def b() -> int:\n    return 2\n", encoding="utf-8", newline="\n")
    write_article("features/a.md", _feature_md("A", ["src/a.py"]), wiki_root=w2)
    orig_lock_bytes = (w2 / DRIFT_LOCK_FILENAME).read_bytes()

    with patch("brain79.core.session_commit.write_article", side_effect=OSError("disk error in pass 3")):
        with pytest.raises(OSError, match="disk error in pass 3"):
            commit_session(
                writes=[{"path": "features/b.md", "content": _feature_md("B", ["src/b.py"])}],
                session_summary="Should restore drift.lock",
                wiki_root=w2,
            )
    assert (w2 / DRIFT_LOCK_FILENAME).read_bytes() == orig_lock_bytes
    assert not (w2 / "features/b.md").exists()


# ---------------------------------------------------------------------------
# AC-3: Guard C baseline resolver & Pass 2d Hard Session Ripple Gate parity
# ---------------------------------------------------------------------------


def _assert_both_guard_c_agree(
    p_root: Path,
    w_root: Path,
    rel_src: str,
    rel_art: str,
    expected_changed: bool,
) -> None:
    cache1 = GitSessionCache()
    cache2 = GitSessionCache()
    c_orch, desc_orch = has_public_api_changes(p_root, rel_src, rel_art, wiki_root=w_root, git_cache=cache1)
    c_py, desc_py = has_public_python_api_changes(p_root, rel_src, rel_art, wiki_root=w_root, git_cache=cache2)
    assert c_orch is expected_changed, f"orchestrator mismatch: {(c_orch, desc_orch)}"
    assert c_py is expected_changed, f"python_inspector mismatch: {(c_py, desc_py)}"
    assert c_orch == c_py


def test_guard_c_skips_pure_migration_commit_and_catches_prior_api_break(tmp_path: Path) -> None:
    """R-2.4 / AC-3(a),(e): skips pure migrate --apply commit and still blocks pre-existing breaking API change."""
    p_root, w_root = _init_project(tmp_path)
    _init_git_repo(p_root)

    src = p_root / "src" / "billing.py"
    src.write_text("def charge(amount: int) -> int:\n    return amount\n", encoding="utf-8", newline="\n")
    dig_1, cnt_1, _ = compute_applies_to_manifest(["src/billing.py"], p_root, w_root)
    art = w_root / "features/billing.md"
    art.write_text(
        _feature_md("Billing", ["src/billing.py"], extra_fm=f'applies_to_digest: "{dig_1}"\napplies_to_count: {cnt_1}\n'),
        encoding="utf-8",
        newline="\n",
    )
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "initial documented billing")

    # Commit 2: breaking public API change committed without updating billing.md
    src.write_text("def charge(amount: int, currency: str) -> int:\n    return amount\n", encoding="utf-8", newline="\n")
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "breaking api change before migration")

    # Commit 3: pure migration commit (strips frontmatter digest and copies stale dig_1 into drift.lock)
    art.write_text(_feature_md("Billing", ["src/billing.py"]), encoding="utf-8", newline="\n")
    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/billing.md": {"digest": dig_1, "count": cnt_1, "targets": {}}
            },
        },
    )
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "pure migration commit")

    _assert_both_guard_c_agree(p_root, w_root, "src/billing.py", "features/billing.md", True)


def test_guard_c_anchors_at_balanced_drift_lock_verification_and_distinguishes_volatile_md(tmp_path: Path) -> None:
    """R-2.4 / AC-3(b),(d),(e): anchors at balanced drift.lock verification; ignores volatile-only .md edits."""
    p_root, w_root = _init_project(tmp_path)
    _init_git_repo(p_root)

    src = p_root / "src" / "billing.py"
    src.write_text("def charge(amount: int) -> int:\n    return amount\n", encoding="utf-8", newline="\n")
    write_article("features/billing.md", _feature_md("Billing", ["src/billing.py"]), wiki_root=w_root)
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "initial")

    # Commit 2: public API change verified under balanced (updates drift.lock only)
    src.write_text("def charge(amount: int, currency: str) -> int:\n    return amount\n", encoding="utf-8", newline="\n")
    dig_2, cnt_2, tgts_2 = compute_applies_to_manifest(["src/billing.py"], p_root, w_root)
    save_drift_lock(
        w_root,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/billing.md": {"digest": dig_2, "count": cnt_2, "targets": tgts_2}
            },
        },
    )
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "balanced verified_articles drift.lock update")

    # Commit 3: volatile-only .md edit (last_updated bump only) -> must NOT shift baseline
    # Working tree: internal non-API refactor -> must be allowed (False) because baseline is Commit 2
    (w_root / "features/billing.md").write_text(
        _feature_md("Billing", ["src/billing.py"]).replace("2026-11-27", "2026-11-28"),
        encoding="utf-8",
        newline="\n",
    )
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "volatile only md edit")

    src.write_text("def charge(amount: int, currency: str) -> int:\n    total = amount\n    return total\n", encoding="utf-8", newline="\n")
    _assert_both_guard_c_agree(p_root, w_root, "src/billing.py", "features/billing.md", False)

    # Substantive .md edit after another API change anchors at the substantive .md commit
    src.write_text("def charge(amount: int, currency: str, tax: int) -> int:\n    return amount + tax\n", encoding="utf-8", newline="\n")
    (w_root / "features/billing.md").write_text(
        _feature_md("Billing", ["src/billing.py"], body_extra=" Includes tax."),
        encoding="utf-8",
        newline="\n",
    )
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "substantive md update")
    _assert_both_guard_c_agree(p_root, w_root, "src/billing.py", "features/billing.md", False)


def test_guard_c_pass2_article_only_fallback_over_50_drift_lock_commits(tmp_path: Path) -> None:
    """R-2.4 / AC-3(c): >50 unrelated drift.lock commits trigger Pass 2 article-only walk without losing pre-existing API break."""
    p_root, w_root = _init_project(tmp_path)
    _init_git_repo(p_root)

    src = p_root / "src" / "billing.py"
    src.write_text("def charge(amount: int) -> int:\n    return amount\n", encoding="utf-8", newline="\n")
    (p_root / "src" / "other.py").write_text("def other() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
    write_article("features/billing.md", _feature_md("Billing", ["src/billing.py"]), wiki_root=w_root)
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "initial billing")

    # Commit 2: unverified breaking API change on billing.py
    src.write_text("def charge(amount: int, fee: int) -> int:\n    return amount + fee\n", encoding="utf-8", newline="\n")
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "unverified breaking billing change")

    # 52 unrelated commits touching drift.lock for features/other.md
    lock_data = load_drift_lock(w_root)
    assert lock_data is not None
    for i in range(52):
        lock_data["articles"]["features/other.md"] = {
            "digest": f"sha256:{i:016x}",
            "count": 1,
            "targets": {"src/other.py": f"sha256:{i:016x}"},
        }
        save_drift_lock(w_root, lock_data)
        _git(p_root, "add", ".")
        _git(p_root, "commit", "-m", f"unrelated drift.lock update {i}")

    _assert_both_guard_c_agree(p_root, w_root, "src/billing.py", "features/billing.md", True)


def test_pass2d_hard_session_ripple_gate_without_frontmatter_digests(tmp_path: Path) -> None:
    """R-2.5 / AC-3(f): Pass 2d flags dirty working-tree code and conflict articles even with zero frontmatter digests."""
    # Case 1: dirty working-tree code edit tracked in drift.lock (hash-free .md)
    p1, w1 = _init_project(tmp_path / "dirty")
    _init_git_repo(p1)
    src = p1 / "src" / "billing.py"
    src.write_text("def charge() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
    write_article("features/billing.md", _feature_md("Billing", ["src/billing.py"]), wiki_root=w1)
    _git(p1, "add", ".")
    _git(p1, "commit", "-m", "initial")

    # Modify tracked source file in working tree (dirty) and commit an unrelated topic
    src.write_text("def charge() -> int:\n    return 2\n", encoding="utf-8", newline="\n")
    topic = (
        "---\ntype: topic\nsummary: unrelated topic\nstatus: active\nlast_updated: 2026-11-27\n---\n\n"
        "# Topic — Misc\n\n## Overview\n\nText.\n\n[← Back to Index](../INDEX.md)\n"
    )
    with pytest.raises(ValidationError) as exc_info:
        commit_session(
            writes=[{"path": "topics/misc.md", "content": topic}],
            session_summary="Unrelated topic while billing.py is dirty",
            wiki_root=w1,
        )
    assert exc_info.value.rule == "unresolved_session_ripple"

    # Case 2: conflict sentinel article governing dirty working-tree code or touched intra-wiki article
    p2, w2 = _init_project(tmp_path / "conflict")
    _init_git_repo(p2)
    src2 = p2 / "src" / "billing.py"
    src2.write_text("def charge() -> int:\n    return 1\n", encoding="utf-8", newline="\n")
    (w2 / "features/billing.md").write_text(_feature_md("Billing", ["src/billing.py"]), encoding="utf-8", newline="\n")
    save_drift_lock(
        w2,
        {
            "version": DRIFT_LOCK_VERSION,
            "articles": {
                "features/billing.md": {
                    "conflict": True,
                    "count": 0,
                    "digest": CONFLICT_SENTINEL_DIGEST,
                    "targets": {},
                }
            },
        },
    )
    _git(p2, "add", ".")
    _git(p2, "commit", "-m", "initial with conflict sentinel")
    src2.write_text("def charge() -> int:\n    return 2\n", encoding="utf-8", newline="\n")

    with pytest.raises(ValidationError) as exc_info2:
        commit_session(
            writes=[{"path": "topics/misc.md", "content": topic}],
            session_summary="Unrelated topic while conflict article governs dirty code",
            wiki_root=w2,
        )
    assert exc_info2.value.rule == "unresolved_session_ripple"
