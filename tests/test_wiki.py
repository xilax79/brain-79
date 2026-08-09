import re

from pathlib import Path
import subprocess

import filelock
import pytest

from brain79.config import set_project_root
from brain79.core import wiki as wiki_ops
from brain79.core.init_project import init_project


@pytest.fixture(autouse=True)
def setup_wiki_root(tmp_path: Path) -> Path:
    """Set project root to a temporary directory with initialized wiki for each test."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


# --- 1. Pruebas de Seguridad en _safe_resolve ---


def test_safe_resolve_valid() -> None:
    resolved = wiki_ops._safe_resolve("architecture/overview.md")
    assert resolved.name == "overview.md"
    assert "architecture" in resolved.parts


def test_resolve_wiki_path_public_alias() -> None:
    resolved = wiki_ops.resolve_wiki_path("architecture/overview.md")
    assert resolved.name == "overview.md"


def test_safe_resolve_path_traversal() -> None:
    with pytest.raises(ValueError, match="resolves outside the wiki directory"):
        wiki_ops._safe_resolve("../outside.md")


def test_safe_resolve_absolute_path_traversal() -> None:
    with pytest.raises(ValueError, match="resolves outside the wiki directory"):
        wiki_ops._safe_resolve("/etc/passwd")


def test_safe_resolve_sibling_prefix_attack(tmp_path: Path) -> None:
    # Setup project_dir and sibling_dir (e.g. /tmp/brain and /tmp/brain-sibling)
    project_dir = tmp_path / "brain"
    project_dir.mkdir()
    sibling_dir = tmp_path / "brain-sibling"
    sibling_dir.mkdir()

    set_project_root(project_dir)
    init_project(project_dir)

    with pytest.raises(ValueError, match="resolves outside the wiki directory"):
        wiki_ops._safe_resolve("../brain-sibling/secret.md")


# --- 2. Pruebas de IO y Concurrencia ---


def test_write_and_read_roundtrip() -> None:
    msg = wiki_ops.write_article("decisions/test.md", "# Test Decision")
    assert msg == "Written: decisions/test.md"

    content = wiki_ops.read_article("decisions/test.md")
    assert content == "# Test Decision"


def test_write_article_creates_parents() -> None:
    path = "deep/nested/sub/dir/doc.md"
    wiki_ops.write_article(path, "Nested content")
    assert wiki_ops.read_article(path) == "Nested content"


def test_read_article_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="Article not found"):
        wiki_ops.read_article("nonexistent.md")


def test_read_article_not_a_file(setup_wiki_root: Path) -> None:
    dir_path = setup_wiki_root / ".brain-79" / "folder.md"
    dir_path.mkdir(parents=True)
    with pytest.raises(ValueError, match="Path is not a file"):
        wiki_ops.read_article("folder.md")


def test_write_article_requires_md_suffix() -> None:
    with pytest.raises(ValueError, match="write_article requires .md paths"):
        wiki_ops.write_article("invalid_file.txt", "content")


def test_write_article_uses_atomic_replace(setup_wiki_root: Path) -> None:
    wiki_ops.write_article("atomic.md", "Content 1")
    target = setup_wiki_root / ".brain-79" / "atomic.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Content 1"

    # Test error during atomic write cleans up .tmp file
    class DummyError(Exception):
        pass

    def mock_replace(self: Path, target: Path) -> None:
        raise DummyError("Simulated write failure")

    with pytest.raises(DummyError):
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Path, "replace", mock_replace)
            wiki_ops.write_article("atomic.md", "Content 2")

    # Target remains untouched and .tmp was removed
    assert target.read_text(encoding="utf-8") == "Content 1"
    assert not (setup_wiki_root / ".brain-79" / "atomic.md.tmp").exists()


def test_write_article_lock_timeout(setup_wiki_root: Path) -> None:
    target = setup_wiki_root / ".brain-79" / "locked.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(".md.lock")

    lock = filelock.FileLock(str(lock_path))
    lock.acquire()
    try:
        with pytest.raises(OSError, match="está bloqueado por otro proceso"):
            wiki_ops.write_article("locked.md", "content", timeout=0.1)
    finally:
        lock.release()


def test_write_article_lock_released_after_write(setup_wiki_root: Path) -> None:
    wiki_ops.write_article("lock_release.md", "Initial content")

    # Immediate second write must succeed without timing out
    wiki_ops.write_article("lock_release.md", "Updated content", timeout=0.5)
    assert wiki_ops.read_article("lock_release.md") == "Updated content"

    # Confirm third-party lock acquisition succeeds immediately after write_article returns
    target = setup_wiki_root / ".brain-79" / "lock_release.md"
    lock_path = target.with_suffix(".md.lock")
    lock = filelock.FileLock(str(lock_path))
    with lock.acquire(timeout=0.1):
        pass


# --- 3. Pruebas de Exploración ---


def test_list_articles_empty(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    # Remove files created by init_project except _raw
    for p in wiki_root.rglob("*.md"):
        if "_raw" not in p.parts:
            p.unlink()

    assert wiki_ops.list_articles() == []


def test_list_articles_non_existent_wiki_root(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    for p in list(wiki_root.rglob("*")):
        if p.is_file():
            p.unlink()
    for p in sorted(list(wiki_root.rglob("*")), reverse=True):
        if p.is_dir():
            p.rmdir()
    wiki_root.rmdir()

    assert wiki_ops.list_articles() == []


def test_list_articles_non_existent_section() -> None:
    assert wiki_ops.list_articles("nonexistent_section") == []


def test_list_articles_excludes_raw() -> None:
    wiki_ops.write_article("article1.md", "Article 1")
    wiki_ops.write_article("_raw/sessions/session1.md", "Raw session")

    articles = wiki_ops.list_articles()
    assert "article1.md" in articles
    assert not any("_raw" in a for a in articles)


def test_list_articles_with_section() -> None:
    wiki_ops.write_article("arch/overview.md", "Overview")
    wiki_ops.write_article("decisions/adr1.md", "ADR 1")

    arch_articles = wiki_ops.list_articles("arch")
    assert arch_articles == ["arch/overview.md"]


def test_list_articles_excludes_raw_when_section_is_raw() -> None:
    wiki_ops.write_article("_raw/sessions/session1.md", "Raw session")
    assert wiki_ops.list_articles("_raw") == []
    assert wiki_ops.list_articles("_raw/sessions") == []


def test_get_index_fallback(setup_wiki_root: Path) -> None:
    index_file = setup_wiki_root / ".brain-79" / "INDEX.md"
    if index_file.exists():
        index_file.unlink()

    fallback = wiki_ops.get_index()
    assert "INDEX.md not found" in fallback

    wiki_ops.write_article("INDEX.md", "# My Wiki Index")
    assert wiki_ops.get_index() == "# My Wiki Index"


# --- 4. Pruebas de Búsqueda y RAW ---


def test_search_articles_case_insensitive() -> None:
    wiki_ops.write_article("doc.md", "This has UNIQUE_KEYWORD in it.")
    results = wiki_ops.search_articles("unique_keyword")
    assert len(results) == 1
    assert results[0]["path"] == "doc.md"
    assert "UNIQUE_KEYWORD" in results[0]["excerpt"]


def test_search_articles_excludes_raw() -> None:
    wiki_ops.write_article("_raw/sessions/session.md", "SECRET_KEYWORD")
    wiki_ops.write_article("valid.md", "SECRET_KEYWORD here")

    results = wiki_ops.search_articles("SECRET_KEYWORD")
    paths = [r["path"] for r in results]
    assert "valid.md" in paths
    assert not any("_raw" in p for p in paths)


def test_search_articles_excerpt() -> None:
    content = "Line 1\nLine 2 with target term\nLine 3"
    wiki_ops.write_article("excerpt_test.md", content)

    results = wiki_ops.search_articles("target term")
    assert len(results) == 1
    assert results[0]["excerpt"] == "Line 2 with target term"


def test_save_raw_session() -> None:
    saved_path = wiki_ops.save_raw_session(
        session_summary="Session details",
        instructions="Focus on arch",
    )
    assert saved_path.startswith("_raw/sessions/session-")

    content = wiki_ops.read_article(saved_path)
    assert "Session details" in content
    assert "Focus on arch" in content


def test_search_articles_empty_query_returns_empty() -> None:
    wiki_ops.write_article("doc.md", "Some content")
    assert wiki_ops.search_articles("") == []
    assert wiki_ops.search_articles("   ") == []
    assert wiki_ops.search_articles("\t\n") == []


def test_search_articles_non_existent_wiki_root(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    for p in list(wiki_root.rglob("*")):
        if p.is_file():
            p.unlink()
    for p in sorted(list(wiki_root.rglob("*")), reverse=True):
        if p.is_dir():
            p.rmdir()
    wiki_root.rmdir()

    assert wiki_ops.search_articles("query") == []


def test_save_raw_session_timestamp_milliseconds() -> None:
    saved_path = wiki_ops.save_raw_session("Test ms timestamp")
    # File format: _raw/sessions/session-YYYY-MM-DD-HHMMSS-mmm.md
    filename = Path(saved_path).name
    pattern = r"^session-\d{4}-\d{2}-\d{2}-\d{6}-\d{3}\.md$"
    assert re.match(pattern, filename) is not None


def test_search_articles_uses_ripgrep_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki_ops.write_article("rg_test.md", "Ripgrep query string match.")

    monkeypatch.setattr(wiki_ops, "_RG_PATH", shutil_rg := wiki_ops.shutil.which("rg"))
    if shutil_rg:
        results = wiki_ops.search_articles("Ripgrep query")
        assert len(results) == 1
        assert results[0]["path"] == "rg_test.md"


def test_search_articles_ripgrep_command_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_cmd: list[str] = []

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_cmd.extend(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(wiki_ops, "_RG_PATH", "/usr/bin/rg")
    monkeypatch.setattr(subprocess, "run", mock_run)

    wiki_ops.search_articles("test_query")

    assert "-F" in captured_cmd
    assert "--null" in captured_cmd
    assert "--no-follow" in captured_cmd
    assert "-i" in captured_cmd
    assert "-g" in captured_cmd
    assert "*.md" in captured_cmd
    assert "!_raw/**" in captured_cmd
    assert "test_query" in captured_cmd


def test_search_articles_ripgrep_malformed_and_edge_cases(
    setup_wiki_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    file_path = wiki_root / "sample.md"
    file_path.write_text("Hello world", encoding="utf-8")

    # Mock subprocess output with empty lines, lines without \0, invalid relative path, line without colon
    stdout_lines = [
        "",
        "invalid_line_no_null",
        "/tmp/outside/file.md\0 1:Hello world",
        f"{file_path}\0 1 Hello world",  # no colon in rest
        f"{file_path}\0 1:Hello world",
        f"{file_path}\0 2:Hello world duplicate",
    ]
    stdout_data = "\n".join(stdout_lines)

    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["rg"], returncode=0, stdout=stdout_data, stderr=""
        )

    monkeypatch.setattr(wiki_ops, "_RG_PATH", "/fake/bin/rg")
    monkeypatch.setattr(subprocess, "run", mock_run)

    results = wiki_ops.search_articles("Hello")
    assert len(results) == 1
    assert results[0]["path"] == "sample.md"


def test_search_articles_ripgrep_returncode_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki_ops.write_article("fallback.md", "Fallback content")

    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["rg"], returncode=2, stdout="", stderr="error"
        )

    monkeypatch.setattr(wiki_ops, "_RG_PATH", "/fake/bin/rg")
    monkeypatch.setattr(subprocess, "run", mock_run)

    results = wiki_ops.search_articles("Fallback")
    assert len(results) == 1
    assert results[0]["path"] == "fallback.md"


def test_search_articles_falls_back_to_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wiki_ops.write_article("py_test.md", "Python fallback match.")

    # Case 1: _RG_PATH is None
    monkeypatch.setattr(wiki_ops, "_RG_PATH", None)
    results1 = wiki_ops.search_articles("fallback match")
    assert len(results1) == 1
    assert results1[0]["path"] == "py_test.md"

    # Case 2: _RG_PATH fails with exception
    monkeypatch.setattr(wiki_ops, "_RG_PATH", "/nonexistent/path/to/rg")

    def mock_run(*args: object, **kwargs: object) -> None:
        raise OSError("ripgrep not executable")

    monkeypatch.setattr(subprocess, "run", mock_run)
    results2 = wiki_ops.search_articles("fallback match")
    assert len(results2) == 1
    assert results2[0]["path"] == "py_test.md"


def test_search_articles_python_unreadable_file(
    setup_wiki_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wiki_ops, "_RG_PATH", None)
    wiki_ops.write_article("readable.md", "Search term")
    wiki_ops.write_article("unreadable.md", "Search term")
    wiki_ops.write_article("_raw/sessions/session.md", "Search term")

    orig_read_text = Path.read_text

    def mock_read_text(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        if self.name == "unreadable.md":
            raise OSError("Permission denied")
        return orig_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(wiki_ops.Path, "read_text", mock_read_text)

    results = wiki_ops.search_articles("Search term")
    assert len(results) == 1
    assert results[0]["path"] == "readable.md"
