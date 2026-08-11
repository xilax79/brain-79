from pathlib import Path

import pytest

from brain79.config import set_project_root
from brain79.core.curate import analyze_wiki_state, prepare_curation_guide
from brain79.core.init_project import init_project


@pytest.fixture
def setup_wiki_root(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_analyze_wiki_state(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    state = analyze_wiki_state(wiki_root)
    assert state.has_index is True
    assert state.article_count > 0


def test_prepare_curation_guide_includes_state_and_violations(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    bad = wiki_root / "features" / "no_fm.md"
    bad.write_text("# No frontmatter\n", encoding="utf-8")

    guide = prepare_curation_guide(wiki_root, raw_content="Summary of session work")
    assert "# Brain-79 — State-Aware Ingest & Curation Guide" in guide
    assert "Articles in Wiki" in guide
    assert "no_fm.md" in guide or "Active Health Issues" in guide
    assert "Session Input Snippet" in guide


def test_prepare_curation_guide_500_lines_cap(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    huge_raw = "\n".join([f"Line {i}" for i in range(1000)])
    guide = prepare_curation_guide(wiki_root, raw_content=huge_raw)

    lines = guide.splitlines()
    assert len(lines) <= 500
