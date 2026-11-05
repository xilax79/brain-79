"""Tests for Phase 6: Centralized .locks/ Isolation & Cross-Platform OS Portability.

Covers all 5 pillars deterministically on local environment without CI:
1. Centralized .locks/ directory isolation, deterministic lock naming, and zero inline locks.
2. Linux case-sensitivity simulation on macOS APFS (exact case validation for links & applies_to).
3. Linux ext4 inode iteration sorting determinism.
4. CRLF (\\r\\n) injection and strict LF (\\n) I/O boundaries.
5. Windows backslash path input normalization across all core APIs and registries.
6. NTFS PermissionError retry resilience and atomic replacement safety.
7. Pre-commit hook PATH and line ending hardening.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brain79.config import set_project_root
from brain79.core.context import get_context
from brain79.core.drift import find_matching_workspace_files
from brain79.core.frontmatter import parse_frontmatter
from brain79.core.handoff import purge_handoffs, write_handoff
from brain79.core.init_project import PRE_COMMIT_HOOK_SCRIPT, init_project
from brain79.core.lint import lint_wiki
from brain79.core.locks import (
    acquire_wiki_lock,
    atomic_replace_with_retry,
    cleanup_legacy_inline_locks,
    get_lock_path,
    has_exact_case_path,
)
from brain79.core.navigation import (
    load_registry,
    regenerate_index_navigation,
)
from brain79.core.orient import orient
from brain79.core.session_commit import commit_session
from brain79.core.wiki import (
    check_file_health,
    edit_article,
    list_articles,
    read_article,
    write_article,
)


@pytest.fixture
def wiki_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Create a populated workspace with a initialized .brain-79 wiki."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    set_project_root(workspace)
    wiki_root = workspace / ".brain-79"
    wiki_root.mkdir()

    # Create standard directory tree
    for d in ("architecture", "decisions", "features", "product", "changelog", "handoffs", "_raw/sessions"):
        (wiki_root / d).mkdir(parents=True, exist_ok=True)

    # Base INDEX.md and SCHEMA.md
    (wiki_root / "INDEX.md").write_text("# Knowledge Base Index\n\n## Quick navigation\n", encoding="utf-8")
    (wiki_root / "SCHEMA.md").write_text(
        "---\ntype: schema\nsummary: Declarative Schema\nversion: 1.0.0\nprofile: software\n"
        "status: active\nlast_updated: 2026-11-04\n---\n\n# Schema\n",
        encoding="utf-8",
    )

    # Initial article
    adr_content = (
        "---\n"
        "type: decision\n"
        "summary: Record test decision\n"
        "status: accepted\n"
        "deciders: Team\n"
        "date: 2026-11-04\n"
        "last_updated: 2026-11-04\n"
        "---\n\n"
        "# ADR-001: Test Decision\n\n"
        "## Status\nAccepted\n\n"
        "## Context\nTest context.\n\n"
        "## Decision\nTest decision.\n\n"
        "## Consequences\nTest consequences.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    (wiki_root / "decisions" / "adr-001.md").write_text(adr_content, encoding="utf-8")

    # Sync navigation
    regenerate_index_navigation(wiki_root)
    return workspace, wiki_root


# ==============================================================================
# PILLAR 1: Centralized .locks/ Isolation & Deterministic Naming
# ==============================================================================


def test_lock_path_mapping(wiki_env: tuple[Path, Path]) -> None:
    """Verify get_lock_path maps files into .brain-79/.locks/ with deterministic naming."""
    _, wiki_root = wiki_env
    locks_dir = wiki_root / ".locks"

    assert get_lock_path(wiki_root, ".navigation_registry.json") == locks_dir / "_registry.lock"
    assert get_lock_path(wiki_root, ".bootstrap_state.json") == locks_dir / "_bootstrap.lock"
    assert get_lock_path(wiki_root, "INDEX.md") == locks_dir / "INDEX.md.lock"
    assert get_lock_path(wiki_root, "SCHEMA.md") == locks_dir / "SCHEMA.md.lock"
    assert get_lock_path(wiki_root, "decisions/adr-001.md") == locks_dir / "decisions__adr-001.md.lock"
    assert get_lock_path(wiki_root, "product/nested/feature.md") == locks_dir / "product__nested__feature.md.lock"

    # Windows backslash input normalization in get_lock_path
    assert get_lock_path(wiki_root, "decisions\\adr-001.md") == locks_dir / "decisions__adr-001.md.lock"


def test_acquire_wiki_lock_creates_locks_dir(wiki_env: tuple[Path, Path]) -> None:
    """acquire_wiki_lock automatically ensures .locks/ directory exists and returns a FileLock."""
    _, wiki_root = wiki_env
    locks_dir = wiki_root / ".locks"
    if locks_dir.exists():
        for f in locks_dir.glob("*"):
            f.unlink()
        locks_dir.rmdir()

    assert not locks_dir.exists()
    lock = acquire_wiki_lock(wiki_root, "decisions/adr-001.md")
    with lock:
        assert locks_dir.exists()
        assert (locks_dir / "decisions__adr-001.md.lock").exists()


def test_zero_inline_locks_invariant_across_session_lifecycle(wiki_env: tuple[Path, Path]) -> None:
    """During article writing, editing, navigation, linting, and handoffs, NO *.lock files exist outside .locks/."""
    _, wiki_root = wiki_env

    # 1. Write article
    write_article(
        path="features/sample.md",
        content="---\ntype: feature\nsummary: Sample feature\nstatus: planned\nversion: 0.1.0\nlast_updated: 2026-11-04\n---\n\n"
        "# Sample\n\n## Overview\nOverview text.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
        wiki_root=wiki_root,
    )

    # 2. Edit article
    edit_article(
        path="features/sample.md",
        edits=[{"old_text": "Overview text.", "new_text": "Updated overview text."}],
        wiki_root=wiki_root,
    )

    # 3. Save handoff
    write_handoff(
        session_type="feature",
        previous_handoff_ref="none",
        summary="Test handoff session",
        boot_instruction="No pending tasks.",
        wiki_root=wiki_root,
    )

    # 4. Regenerate navigation & lint
    regenerate_index_navigation(wiki_root)
    lint_wiki()

    # Assert: zero *.lock files anywhere outside .locks/
    inline_locks = [
        p for p in wiki_root.rglob("*.lock")
        if ".locks" not in p.parts
    ]
    assert inline_locks == [], f"Found forbidden inline lock files outside .locks/: {inline_locks}"


def test_cleanup_legacy_inline_locks(wiki_env: tuple[Path, Path]) -> None:
    """cleanup_legacy_inline_locks removes leftover inline *.lock files from earlier versions."""
    _, wiki_root = wiki_env

    # Seed legacy inline locks
    legacy1 = wiki_root / "INDEX.md.lock"
    legacy2 = wiki_root / "decisions" / "adr-001.md.lock"
    legacy3 = wiki_root / ".navigation_registry.json.lock"
    legacy1.touch()
    legacy2.touch()
    legacy3.touch()

    # Active lock inside .locks/ should NOT be deleted
    canonical_lock = wiki_root / ".locks" / "decisions__adr-001.md.lock"
    canonical_lock.parent.mkdir(parents=True, exist_ok=True)
    canonical_lock.touch()

    removed = cleanup_legacy_inline_locks(wiki_root)
    assert removed >= 3
    assert not legacy1.exists()
    assert not legacy2.exists()
    assert not legacy3.exists()
    assert canonical_lock.exists()


def test_purge_handoffs_cleans_centralized_handoff_locks(wiki_env: tuple[Path, Path]) -> None:
    """purge_handoffs(apply=True) deletes handoff files AND their centralized locks in .locks/."""
    _, wiki_root = wiki_env

    # Create handoff
    handoff_path_str = write_handoff(
        session_type="bugfix",
        previous_handoff_ref="none",
        summary="Purge test handoff",
        boot_instruction="No pending tasks.",
        wiki_root=wiki_root,
    )
    handoff_filename = Path(handoff_path_str).name
    lock_filename = f"handoffs__{handoff_filename}.lock"
    lock_file = wiki_root / ".locks" / lock_filename
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.touch()

    assert lock_file.exists()
    purge_handoffs(wiki_root, apply=True)
    assert not lock_file.exists()


def test_locks_directory_excluded_from_listing_and_indexing(wiki_env: tuple[Path, Path]) -> None:
    """.locks/ directory is strictly excluded from list_articles, navigation registry, and linting."""
    _, wiki_root = wiki_env

    # Seed a stray markdown file in .locks/ just in case
    locks_dir = wiki_root / ".locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    (locks_dir / "stray.md").write_text("# Stray\n", encoding="utf-8")

    articles = list_articles()
    assert not any(".locks" in a for a in articles)

    report = lint_wiki(wiki_root)
    assert "stray.md" not in report
    for line in report.splitlines():
        assert ".locks" not in line


# ==============================================================================
# PILLAR 2: Linux Case-Sensitivity Simulation on macOS APFS
# ==============================================================================


def test_has_exact_case_path_simulation(tmp_path: Path) -> None:
    """has_exact_case_path checks disk case segment-by-segment, rejecting wrong case even on APFS."""
    test_dir = tmp_path / "SubDir"
    test_dir.mkdir()
    target_file = test_dir / "targetFile.txt"
    target_file.write_text("content", encoding="utf-8")

    # Exact case matches
    assert has_exact_case_path(tmp_path, "SubDir/targetFile.txt") is True

    # Case mismatches must fail even if target_file.exists() returns True on macOS
    assert has_exact_case_path(tmp_path, "subdir/targetFile.txt") is False
    assert has_exact_case_path(tmp_path, "SubDir/targetfile.txt") is False
    assert has_exact_case_path(tmp_path, "SUBDIR/TARGETFILE.TXT") is False
    assert has_exact_case_path(tmp_path, "nonexistent.txt") is False


def test_lint_wiki_flags_case_mismatched_links_on_apfs(wiki_env: tuple[Path, Path]) -> None:
    """lint_wiki flags links with case mismatches (Linux ext4 parity on macOS)."""
    _, wiki_root = wiki_env

    # File on disk is lowercase adr-001.md
    # Article links to uppercase ADR-001.md
    article_content = (
        "---\n"
        "type: feature\n"
        "summary: Feature with wrong-case link\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-04\n"
        "---\n\n"
        "# Feature Link Test\n\n"
        "## Overview\n"
        "Here is a link: [ADR 001](../decisions/ADR-001.md).\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    (wiki_root / "features" / "case-link.md").write_text(article_content, encoding="utf-8")

    report = lint_wiki(wiki_root)
    broken_link_lines = [line for line in report.splitlines() if "Broken Local Links" in line or "ADR-001.md" in line]
    assert any("ADR-001.md" in line for line in broken_link_lines), (
        f"Case-mismatched link must be flagged as broken, but got report: {report}"
    )


def test_write_article_inline_check_flags_case_mismatched_links(wiki_env: tuple[Path, Path]) -> None:
    """write_article inline check does NOT report 'lint OK' when linking to mismatched case."""
    _, wiki_root = wiki_env

    article_content = (
        "---\n"
        "type: feature\n"
        "summary: Feature linking with wrong case\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-04\n"
        "---\n\n"
        "# Case Test\n\n"
        "## Overview\n"
        "Link: [ADR 001](../decisions/ADR-001.md)\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    write_article(path="features/inline-case.md", content=article_content, wiki_root=wiki_root)
    warnings = check_file_health(wiki_root, "features/inline-case.md", article_content)
    assert any("ADR-001.md" in w for w in warnings)


def test_drift_rejects_case_mismatched_applies_to(wiki_env: tuple[Path, Path]) -> None:
    """find_matching_workspace_files rejects applies_to bindings with wrong case."""
    workspace, wiki_root = wiki_env
    src_file = workspace / "src" / "brain79" / "server.py"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text("# code", encoding="utf-8")

    # Exact case matches
    matches = find_matching_workspace_files(patterns=["src/brain79/server.py"], project_root=workspace)
    assert any("server.py" in str(p) for p in matches)

    # Mismatched case must not match on macOS/Linux
    bad_matches = find_matching_workspace_files(patterns=["src/brain79/SERVER.py"], project_root=workspace)
    assert bad_matches == []


# ==============================================================================
# PILLAR 3: Linux Inode Order Determinism (Sorted Directory Traversals)
# ==============================================================================


def test_directory_traversals_are_deterministically_sorted(wiki_env: tuple[Path, Path]) -> None:
    """Directory iterators in core modules return consistent results regardless of inode order."""
    _, wiki_root = wiki_env

    # Create several articles
    for i in ("c", "a", "b", "z", "m"):
        (wiki_root / "features" / f"{i}.md").write_text(
            f"---\ntype: feature\nsummary: Feature {i}\nstatus: planned\nversion: 0.1.0\nlast_updated: 2026-11-04\n---\n\n"
            f"# Feature {i}\n\n## Overview\nText.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            encoding="utf-8",
        )

    articles = list_articles(section="features")
    expected = sorted(articles)
    assert articles == expected, f"list_articles must be sorted, got {articles}"


# ==============================================================================
# PILLAR 4: CRLF (\r\n) Line-Ending Normalization Across I/O Boundaries
# ==============================================================================


def test_read_and_edit_article_normalizes_crlf(wiki_env: tuple[Path, Path]) -> None:
    """Files checked out with CRLF on Windows are read and edited without substring mismatch."""
    _, wiki_root = wiki_env
    target = wiki_root / "features" / "crlf-test.md"

    # Write explicit CRLF bytes to disk
    raw_crlf_content = (
        b"---\r\n"
        b"type: feature\r\n"
        b"summary: CRLF test article\r\n"
        b"status: planned\r\n"
        b"version: 0.1.0\r\n"
        b"last_updated: 2026-11-04\r\n"
        b"---\r\n\r\n"
        b"# CRLF Article\r\n\r\n"
        b"## Overview\r\n"
        b"Original line.\r\n\r\n"
        b"---\r\n\r\n"
        b"[<- Volver al Indice](../INDEX.md)\r\n"
    )
    target.write_bytes(raw_crlf_content)

    # 1. read_article converts CRLF to pure LF
    read_text = read_article(path="features/crlf-test.md", wiki_root=wiki_root)
    assert "\r\n" not in read_text

    # 2. edit_article with LF-only old_text matches cleanly and saves as pure LF
    edit_article(
        path="features/crlf-test.md",
        edits=[{"old_text": "Original line.", "new_text": "Replaced line."}],
        wiki_root=wiki_root,
    )

    saved_bytes = target.read_bytes()
    assert b"\r\n" not in saved_bytes, "Saved article must use pure LF line endings"
    assert b"Replaced line." in saved_bytes


def test_session_commit_edits_crlf_file_without_mismatch(wiki_env: tuple[Path, Path]) -> None:
    """commit_session pre-flight simulation and write cleanly edits CRLF files on disk."""
    _, wiki_root = wiki_env
    target = wiki_root / "features" / "commit-crlf.md"

    raw_crlf = (
        b"---\r\n"
        b"type: feature\r\n"
        b"summary: Preflight CRLF\r\n"
        b"status: planned\r\n"
        b"version: 0.1.0\r\n"
        b"last_updated: 2026-11-04\r\n"
        b"---\r\n\r\n"
        b"# Feature Title\r\n\r\n"
        b"## Overview\r\n"
        b"Block to replace.\r\n\r\n"
        b"---\r\n\r\n"
        b"[<- Volver al Indice](../INDEX.md)\r\n"
    )
    target.write_bytes(raw_crlf)

    # Commit with standard LF old_text
    receipt = commit_session(
        payload={
            "edits": [
                {
                    "path": "features/commit-crlf.md",
                    "edits": [{"old_text": "Block to replace.", "new_text": "Block replaced cleanly."}],
                }
            ]
        },
        wiki_root=wiki_root,
    )
    assert receipt.get("success") is True, f"Session commit failed on CRLF file: {receipt}"
    assert b"\r\n" not in target.read_bytes()


def test_parse_frontmatter_handles_crlf() -> None:
    """parse_frontmatter extracts frontmatter from CRLF text."""
    crlf_doc = "---\r\ntype: topic\r\nsummary: Test CRLF\r\n---\r\n\r\n# Body\r\n"
    meta, body = parse_frontmatter(crlf_doc)
    assert meta.get("type") == "topic"
    assert meta.get("summary") == "Test CRLF"
    assert "\r\n" not in body


def test_pre_commit_hook_written_with_pure_lf(tmp_path: Path) -> None:
    """init_project writes pre-commit hook with strict LF endings."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    git_dir = repo_dir / ".git"
    git_dir.mkdir()

    init_project(repo_dir)
    hook_file = git_dir / "hooks" / "pre-commit"
    assert hook_file.exists()
    assert b"\r\n" not in hook_file.read_bytes()


# ==============================================================================
# PILLAR 5: Windows Backslash Path Normalization Across All Entry Points
# ==============================================================================


def test_windows_backslash_inputs_across_apis(wiki_env: tuple[Path, Path]) -> None:
    """APIs accepting relative paths accept Windows backslashes and normalize them."""
    workspace, wiki_root = wiki_env

    # 1. write_article with backslash creates proper nested directory
    write_article(
        path="features\\win-sub\\win-feat.md",
        content="---\ntype: feature\nsummary: Windows feature\nstatus: planned\nversion: 0.1.0\nlast_updated: 2026-11-04\n---\n\n"
        "# Win Feat\n\n## Overview\nWindows path.\n\n---\n\n[← Volver al Índice](../../INDEX.md)\n",
        wiki_root=wiki_root,
    )
    assert (wiki_root / "features" / "win-sub" / "win-feat.md").exists()

    # 2. read_article with backslash
    content = read_article(path="features\\win-sub\\win-feat.md", wiki_root=wiki_root)
    assert "# Win Feat" in content

    # 3. edit_article with backslash
    edit_article(
        path="features\\win-sub\\win-feat.md",
        edits=[{"old_text": "Windows path.", "new_text": "Updated windows path."}],
        wiki_root=wiki_root,
    )
    assert "Updated windows path." in read_article(path="features/win-sub/win-feat.md", wiki_root=wiki_root)

    # 4. .navigation_registry.json must contain POSIX forward slashes ONLY
    registry = load_registry(wiki_root)
    articles = registry.get("articles", [])
    assert len(articles) > 0
    for article in articles:
        p = article.get("path", "")
        assert "\\" not in p, f"Registry article path contains Windows backslash: {p}"

    # 5. orient and context accept backslashes in paths argument
    orient_out = orient(wiki_root=wiki_root, paths=["src\\brain79\\server.py"])
    assert "Active Schema Summary" in orient_out

    context_out = get_context(task="test task", paths=["src\\brain79\\server.py"], wiki_root=wiki_root)
    assert isinstance(context_out, str)
    assert "Context Retrieval Report" in context_out


# ==============================================================================
# PILLAR 6: NTFS Atomic Replace Retry Resilience
# ==============================================================================


def test_atomic_replace_with_retry_succeeds_on_transient_permission_error(tmp_path: Path) -> None:
    """atomic_replace_with_retry retries upon transient PermissionError (Windows antivirus simulation)."""
    src = tmp_path / "src.tmp"
    dst = tmp_path / "dst.txt"
    src.write_text("new content", encoding="utf-8")
    dst.write_text("old content", encoding="utf-8")

    attempts = 0
    real_replace = Path.replace

    def flaky_replace(self: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("[WinError 5] Access is denied")
        return real_replace(self, target)

    with patch.object(Path, "replace", side_effect=flaky_replace, autospec=True):
        atomic_replace_with_retry(src, dst, retries=3, delay=0.005)

    assert attempts == 3
    assert dst.read_text(encoding="utf-8") == "new content"
    assert not src.exists()


def test_atomic_replace_cleans_up_tmp_file_on_exhausted_retries(tmp_path: Path) -> None:
    """atomic_replace_with_retry cleans up the tmp file if retries are exhausted."""
    src = tmp_path / "src.tmp"
    dst = tmp_path / "dst.txt"
    src.write_text("new content", encoding="utf-8")

    with patch.object(Path, "replace", side_effect=PermissionError("Locked forever")):
        with pytest.raises(PermissionError):
            atomic_replace_with_retry(src, dst, retries=2, delay=0.005)

    assert not src.exists(), "Temporary file must be deleted on failure to avoid leaking clutter"


# ==============================================================================
# PILLAR 7: Pre-Commit Hook PATH Hardening
# ==============================================================================


def test_pre_commit_hook_includes_fallback_paths() -> None:
    """PRE_COMMIT_HOOK_SCRIPT expands PATH to locate brain79 in user environments."""
    assert "$HOME/.local/bin" in PRE_COMMIT_HOOK_SCRIPT or "$USERPROFILE" in PRE_COMMIT_HOOK_SCRIPT
    assert "set -e" in PRE_COMMIT_HOOK_SCRIPT


def test_regenerate_index_navigation_crlf_does_not_duplicate_sections(wiki_env: tuple[Path, Path]) -> None:
    """regenerate_index_navigation cleanly updates INDEX.md checked out with CRLF, without duplicate headers."""
    _, wiki_root = wiki_env
    index_path = wiki_root / "INDEX.md"

    # Write explicit CRLF bytes with Quick navigation
    crlf_index = (
        b"---\r\n"
        b"type: navigation\r\n"
        b"last_updated: 2026-11-04\r\n"
        b"---\r\n\r\n"
        b"# Project Index\r\n\r\n"
        b"## Quick navigation\r\n"
        b"### Decisions\r\n"
        b"- [ADR-001](decisions/adr-001.md)\r\n"
    )
    index_path.write_bytes(crlf_index)

    # Regenerate twice
    regenerate_index_navigation(wiki_root)
    regenerate_index_navigation(wiki_root)

    updated_content = index_path.read_text(encoding="utf-8")
    assert b"\r\n" not in index_path.read_bytes(), "Must be written with pure LF"
    assert updated_content.count("## Quick navigation") == 1, "Quick navigation must not be duplicated"


# ==============================================================================
# STATIC ENFORCEMENT: Zero str(...relative_to(...)) Calls in src/brain79/core/
# ==============================================================================


def test_static_analysis_zero_relative_to_string_casts() -> None:
    """Static AST check: ensure zero str(...relative_to(...)) calls exist in src/brain79/core/."""
    import ast

    core_dir = Path(__file__).resolve().parent.parent / "src" / "brain79" / "core"
    assert core_dir.is_dir()

    violations: list[str] = []
    for py_file in sorted(core_dir.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check for str(x.relative_to(...))
                if isinstance(node.func, ast.Name) and node.func.id == "str" and node.args:
                    arg = node.args[0]
                    if (
                        isinstance(arg, ast.Call)
                        and isinstance(arg.func, ast.Attribute)
                        and arg.func.attr == "relative_to"
                    ):
                        violations.append(f"{py_file.name}:{node.lineno}: str(...relative_to(...))")
    assert violations == [], f"Found forbidden str(...relative_to(...)) calls: {violations}"

