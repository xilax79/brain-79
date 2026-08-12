import concurrent.futures
from pathlib import Path

import pytest

from brain79.cli.dispatch import run_cli
from brain79.config import set_project_root
from brain79.core.init_project import init_project
from brain79.core.navigation import (
    extract_title_and_summary,
    generate_quick_navigation,
    load_registry,
    regenerate_index_navigation,
    register_article,
    unregister_article,
)
from brain79.core.wiki import write_article
from brain79.server import brain79_navigate


@pytest.fixture
def setup_wiki_root(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_load_save_registry(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    reg = load_registry(wiki_root)
    assert reg == {"articles": []}

    register_article(
        wiki_root,
        "features/auth.md",
        "Authentication Feature",
        "Auth system details",
        "features",
    )
    reg2 = load_registry(wiki_root)
    assert len(reg2["articles"]) == 1
    assert reg2["articles"][0]["path"] == "features/auth.md"
    assert reg2["articles"][0]["title"] == "Authentication Feature"


def test_register_and_unregister_article(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(wiki_root, "features/f1.md", "F1", "F1 summary", "features")
    register_article(wiki_root, "features/f2.md", "F2", "F2 summary", "features")

    reg = load_registry(wiki_root)
    assert len(reg["articles"]) == 2

    # Update f1
    register_article(wiki_root, "features/f1.md", "F1 Updated", "New summary", "features")
    reg_updated = load_registry(wiki_root)
    assert len(reg_updated["articles"]) == 2
    f1_entry = next(a for a in reg_updated["articles"] if a["path"] == "features/f1.md")
    assert f1_entry["title"] == "F1 Updated"

    # Unregister f2
    unregister_article(wiki_root, "features/f2.md")
    reg_after_del = load_registry(wiki_root)
    assert len(reg_after_del["articles"]) == 1
    assert reg_after_del["articles"][0]["path"] == "features/f1.md"


def test_extract_title_and_summary() -> None:
    content = (
        "---\n"
        "type: feature\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-08-11\n"
        "---\n\n"
        "# My Great Feature\n\n"
        "This is the summary of the feature.\n\n"
        "## Details\n"
        "More text"
    )
    title, summary = extract_title_and_summary(content)
    assert title == "My Great Feature"
    assert summary == "This is the summary of the feature."


def test_generate_quick_navigation(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(wiki_root, "product/overview.md", "Overview", "Product overview", "product")
    register_article(wiki_root, "features/login.md", "Login Feature", "User login", "features")

    nav_md = generate_quick_navigation(wiki_root)
    assert "## Quick navigation" in nav_md
    assert "### Features" in nav_md
    assert "### Product" in nav_md
    assert "- [Login Feature](features/login.md) — User login" in nav_md
    assert "- [Overview](product/overview.md) — Product overview" in nav_md


def test_write_article_auto_registers(setup_wiki_root: Path) -> None:
    content = (
        "---\n"
        "type: feature\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-08-11\n"
        "---\n\n"
        "# Auto Registered\n\n"
        "Summary text.\n"
    )
    write_article("features/auto.md", content)

    wiki_root = setup_wiki_root / ".brain-79"
    reg = load_registry(wiki_root)
    assert any(a["path"] == "features/auto.md" for a in reg["articles"])


def test_regenerate_index_navigation(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(wiki_root, "features/search.md", "Search Feature", "Search wiki", "features")

    msg = regenerate_index_navigation(wiki_root)
    assert msg == "INDEX.md Quick navigation regenerated."

    index_content = (wiki_root / "INDEX.md").read_text(encoding="utf-8")
    assert "## Quick navigation" in index_content
    assert "- [Search Feature](features/search.md) — Search wiki" in index_content


def test_cli_navigate(setup_wiki_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("navigate", ["--regenerate"])
    assert code == 0
    captured = capsys.readouterr()
    assert "INDEX.md Quick navigation regenerated." in captured.out


def test_mcp_navigate(setup_wiki_root: Path) -> None:
    res = brain79_navigate(regenerate=True)
    assert res == "INDEX.md Quick navigation regenerated."


def test_concurrent_registry_writes(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"

    def _worker(i: int) -> None:
        register_article(
            wiki_root,
            f"features/f{i}.md",
            f"Feature {i}",
            f"Summary {i}",
            "features",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_worker, i) for i in range(10)]
        concurrent.futures.wait(futures)

    reg = load_registry(wiki_root)
    assert len(reg["articles"]) == 10


def test_see_all_link_uses_anchor(setup_wiki_root: Path) -> None:
    """BUG-2: All articles should be listed (no truncation + broken anchor)."""
    wiki_root = setup_wiki_root / ".brain-79"
    for i in range(52):
        register_article(
            wiki_root,
            f"features/f{i:02d}.md",
            f"Feature {i:02d}",
            f"Summary {i:02d}",
            "features",
        )

    nav = generate_quick_navigation(wiki_root)
    assert nav.count("- [Feature") == 52
    assert "See all" not in nav
    assert "[→](#" not in nav


def test_regenerate_index_navigation_deduplicates(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    index_path = wiki_root / "INDEX.md"
    index_path.write_text(
        "# Index\n\n## Quick navigation\nOld section 1\n\n## Quick navigation\nOld section 2\n",
        encoding="utf-8",
    )
    register_article(wiki_root, "features/f1.md", "F1", "Sum", "features")

    regenerate_index_navigation(wiki_root)
    content = index_path.read_text(encoding="utf-8")
    assert content.count("## Quick navigation") == 1
    assert "- [F1](features/f1.md) — Sum" in content


def test_escape_markdown_in_titles(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(
        wiki_root,
        "features/x.md",
        "Title with [brackets] and **bold**",
        "summary",
        "features",
    )
    nav = generate_quick_navigation(wiki_root)
    assert "- [Title with \\[brackets\\] and \\*\\*bold\\*\\*](features/x.md) — summary" in nav

    register_article(
        wiki_root,
        "features/y.md",
        "Title with _underscore_",
        "summary 2",
        "features",
    )
    nav2 = generate_quick_navigation(wiki_root)
    assert "\\_underscore\\_" in nav2


def test_escape_markdown_full_chars(setup_wiki_root: Path) -> None:
    """BUG-3/12: GFM inline chars escaped (except backticks, which are valid inline code)."""
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(
        wiki_root,
        "features/x.md",
        "Title with _italic_, **bold**, `code`, ~~strike~~",
        "Summary with <tag> and > arrow",
        "features",
    )
    nav = generate_quick_navigation(wiki_root)

    assert "\\_italic\\_" in nav
    assert "\\*\\*bold\\*\\*" in nav
    assert "\\`code\\`" not in nav
    assert "`code`" in nav
    assert "\\~\\~strike\\~\\~" in nav
    assert "\\<tag\\>" in nav
    assert "\\> arrow" in nav


def test_root_section_header(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(wiki_root, "loose.md", "Loose Article", "Summary", "root")
    nav = generate_quick_navigation(wiki_root)
    assert "### General" in nav
    assert "### Root" not in nav


def test_register_path_traversal_validation(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    with pytest.raises(ValueError, match="Invalid path for navigation registry"):
        register_article(wiki_root, "../outside.md", "Outside", "Summary", "features")
    with pytest.raises(ValueError, match="Invalid path for navigation registry"):
        register_article(wiki_root, "/etc/passwd", "Passwd", "Summary", "features")


def test_register_rejects_empty_path(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    for bad in ["", "   ", "\t\n"]:
        with pytest.raises(ValueError, match="Invalid path"):
            register_article(wiki_root, bad, "X", "sum", "features")


def test_escape_markdown_in_summaries(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(
        wiki_root,
        "features/x.md",
        "Title",
        "Summary with [brackets] and **bold**",
        "features",
    )
    nav = generate_quick_navigation(wiki_root)
    assert "\\[brackets\\]" in nav
    assert "\\*\\*bold\\*\\*" in nav
