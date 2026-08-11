import json
from pathlib import Path

import pytest

from brain79.cli.dispatch import run_cli
from brain79.config import set_project_root
from brain79.core.init_project import init_project
from brain79.core.lint import lint_wiki
from brain79.core.lint_organizational import (
    check_article_atomicity,
    check_decision_leakage,
    check_force_skipped_articles,
    check_frontmatter_consistency,
    check_index_size,
    check_legacy_articles,
    check_navigation_freshness,
    check_prohibited_content,
    check_type_location_mismatch,
)
from brain79.core.navigation import register_article


@pytest.fixture
def setup_wiki_root(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_check_index_size(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    index_path = wiki_root / "INDEX.md"
    lines = ["# Index\n", "## Project\n"] + [f"- Line {i}\n" for i in range(160)]
    index_path.write_text("".join(lines), encoding="utf-8")

    issues = check_index_size(wiki_root)
    assert len(issues) == 1
    assert issues[0].rule == "index_size_limit"
    assert issues[0].severity == "error"


def test_check_frontmatter_consistency(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    no_fm = wiki_root / "features" / "no_fm.md"
    no_fm.write_text("# No Frontmatter\n\nBody text\n", encoding="utf-8")

    issues = check_frontmatter_consistency(wiki_root)
    assert any(i.rule == "frontmatter_missing" and i.path == "features/no_fm.md" for i in issues)


def test_check_type_location_mismatch(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    bad_type = wiki_root / "features" / "bad_type.md"
    bad_type.write_text(
        "---\ntype: product\nlast_updated: 2026-08-11\n---\n\n# Bad Location\n",
        encoding="utf-8",
    )

    issues = check_type_location_mismatch(wiki_root)
    assert any(i.rule == "type_location_mismatch" for i in issues)


def test_check_decision_leakage(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    feature_file = wiki_root / "features" / "leak.md"
    feature_file.write_text(
        "---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n"
        "# Feature\n\n- Decision: use SQLite for offline storage.\n\n"
        "```yaml\n- Decision: example in code fence\n```\n",
        encoding="utf-8",
    )

    issues = check_decision_leakage(wiki_root)
    assert len(issues) == 1
    assert issues[0].rule == "decision_leakage"
    assert issues[0].line == 8


def test_check_article_atomicity(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    large_file = wiki_root / "features" / "large.md"
    headers = [f"## Section {i}\nContent {i}\n" for i in range(10)]
    large_file.write_text(
        "---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Large\n\n" + "".join(headers),
        encoding="utf-8",
    )

    issues = check_article_atomicity(wiki_root)
    assert any(i.rule == "article_not_atomic" for i in issues)


def test_check_prohibited_content(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    index_path = wiki_root / "INDEX.md"
    index_path.write_text(
        "# Index\n\n## Invalid Section Header\nText\n\n## Project\n- Decision: use Yjs\n",
        encoding="utf-8",
    )

    issues = check_prohibited_content(wiki_root)
    assert any(i.rule == "index_prohibited_header" for i in issues)
    assert any(i.rule == "index_prohibited_content" for i in issues)


def test_check_navigation_freshness(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    register_article(wiki_root, "features/login.md", "Login", "User login", "features")

    issues = check_navigation_freshness(wiki_root)
    assert len(issues) == 1
    assert issues[0].rule == "navigation_desync"


def test_check_legacy_articles(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    legacy_file = wiki_root / "features" / "old.md"
    legacy_file.write_text(
        "---\ntype: feature\nstatus: legacy\nlast_updated: 2026-08-11\n---\n\n# Old Feature\n",
        encoding="utf-8",
    )

    issues = check_legacy_articles(wiki_root)
    assert len(issues) == 1
    assert issues[0].rule == "legacy_needs_review"
    assert issues[0].severity == "info"


def test_check_force_skipped_articles(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    skip_file = wiki_root / "features" / "skipped.md"
    skip_file.write_text(
        "---\ntype: feature\nvalidation: force_skip\nlast_updated: 2026-08-11\n---\n\n# Skipped\n",
        encoding="utf-8",
    )

    issues = check_force_skipped_articles(wiki_root)
    assert len(issues) == 1
    assert issues[0].rule == "force_skipped_article"
    assert issues[0].severity == "warning"


def test_lint_wiki_includes_organizational_health(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    no_fm = wiki_root / "features" / "no_fm.md"
    no_fm.write_text("# No Frontmatter\n", encoding="utf-8")

    report = lint_wiki()
    assert "## Organizational Health" in report
    assert "frontmatter_missing" in report or "lacks frontmatter" in report


def test_cli_lint_flags(setup_wiki_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code_suggest = run_cli("lint", ["--suggest-extract"])
    assert code_suggest == 0
    captured = capsys.readouterr()
    assert "Suggested Extractions from INDEX.md" in captured.out

    code_json = run_cli("lint", ["--format", "json"])
    assert code_json == 0
    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)
    assert "issues" in data
    assert "report" in data


def test_cli_lint_strict_exit_codes(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"

    # Fresh initialized template is now 100% compliant -> expect exit 0
    code_fresh = run_cli("lint", ["--strict"])
    assert code_fresh == 0

    # Wiki with missing frontmatter error -> expect exit 1
    bad = wiki_root / "features" / "no_fm.md"
    bad.write_text("# No frontmatter\n", encoding="utf-8")
    code_bad = run_cli("lint", ["--strict"])
    assert code_bad == 1


def test_atomicity_check_excludes_decisions(tmp_path: Path) -> None:
    """BUG-5: decisions/ articles with many H2 should NOT be flagged as non-atomic."""
    project = tmp_path / "project"
    project.mkdir()
    set_project_root(project)
    init_project(project)

    dec_dir = project / ".brain-79" / "decisions"
    dec_dir.mkdir(exist_ok=True)
    adr_content = """---
type: decision
status: legacy
last_updated: 2026-08-11
---

# Decision 1

## Status

## Context

## Decision

## Consequences

## Alternatives Considered

## References

## Related Decisions

## Examples

## Implementation Notes

## Open Questions
"""
    (dec_dir / "adr-001.md").write_text(adr_content, encoding="utf-8")

    issues = check_article_atomicity(project / ".brain-79")
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 0


def test_atomicity_check_still_flags_features(tmp_path: Path) -> None:
    """BUG-5: features/ articles with many H2 should still be flagged."""
    project = tmp_path / "project"
    project.mkdir()
    set_project_root(project)
    init_project(project)

    feat_dir = project / ".brain-79" / "features"
    feat_dir.mkdir(exist_ok=True)
    feat_content = """---
type: feature
status: planned
version: 0.1.0
last_updated: 2026-08-11
---

# Feature

""" + "\n\n".join(f"## Section {i}\n" for i in range(10))

    (feat_dir / "f.md").write_text(feat_content, encoding="utf-8")

    issues = check_article_atomicity(project / ".brain-79")
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 1
    assert "features/f.md" in atomicity_issues[0].path
