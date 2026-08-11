from pathlib import Path

import pytest

from brain79.cli.dispatch import run_cli
from brain79.config import set_project_root
from brain79.core.frontmatter import parse_frontmatter
from brain79.core.init_project import init_project
from brain79.core.lint import lint_wiki
from brain79.core.wiki import write_article
from brain79.server import brain79_migrate
from brain79.core.migration import migrate_wiki, suggest_relocations


@pytest.fixture
def setup_wiki_root(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_migrate_wiki_dry_run(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    feature_file = wiki_root / "features" / "legacy.md"
    feature_file.write_text("# Legacy Feature\n\nLegacy content.\n", encoding="utf-8")

    report = migrate_wiki(wiki_root, dry_run=True)
    assert "# Migration Report (DRY RUN)" in report
    assert "features/legacy.md" in report

    # File should not have frontmatter written in dry run
    content = feature_file.read_text(encoding="utf-8")
    assert not content.startswith("---\n")


def test_migrate_wiki_applied_legacy_defaults(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    feature_file = wiki_root / "features" / "legacy.md"
    feature_file.write_text("# Legacy Feature\n\nLegacy content.\n", encoding="utf-8")

    decision_file = wiki_root / "decisions" / "dec1.md"
    decision_file.parent.mkdir(parents=True, exist_ok=True)
    decision_file.write_text("# Decision 1\n", encoding="utf-8")

    arch_file = wiki_root / "architecture" / "arch1.md"
    arch_file.parent.mkdir(parents=True, exist_ok=True)
    arch_file.write_text("# Architecture 1\n", encoding="utf-8")

    report = migrate_wiki(wiki_root, dry_run=False)
    assert "# Migration Report (APPLIED)" in report
    assert "features/legacy.md" in report

    # Feature gets status: legacy
    meta_feat, _ = parse_frontmatter(feature_file.read_text(encoding="utf-8"))
    assert meta_feat["type"] == "feature"
    assert meta_feat["status"] == "legacy"
    assert meta_feat["version"] == "unknown"

    # Decision gets status: legacy
    meta_dec, _ = parse_frontmatter(decision_file.read_text(encoding="utf-8"))
    assert meta_dec["type"] == "decision"
    assert meta_dec["status"] == "legacy"

    # Architecture gets stability: legacy
    meta_arch, _ = parse_frontmatter(arch_file.read_text(encoding="utf-8"))
    assert meta_arch["type"] == "architecture"
    assert meta_arch["stability"] == "legacy"


def test_suggest_relocations(setup_wiki_root: Path) -> None:
    wiki_root = setup_wiki_root / ".brain-79"
    wrong_loc = wiki_root / "decisions" / "misplaced.md"
    wrong_loc.parent.mkdir(parents=True, exist_ok=True)
    wrong_loc.write_text(
        "---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Misplaced\n",
        encoding="utf-8",
    )

    suggestions = suggest_relocations(wiki_root)
    assert "Move `decisions/misplaced.md` → `features/misplaced.md`" in suggestions


def test_cli_migrate(setup_wiki_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("migrate", ["--dry-run"])
    assert code == 0
    captured = capsys.readouterr()
    assert "# Migration Report (DRY RUN)" in captured.out

    code_reloc = run_cli("migrate", ["--suggest-relocations"])
    assert code_reloc == 0
    captured_reloc = capsys.readouterr()
    assert "# Suggested Article Relocations" in captured_reloc.out


def test_mcp_migrate(setup_wiki_root: Path) -> None:
    res = brain79_migrate(dry_run=True)
    assert "# Migration Report (DRY RUN)" in res


def test_force_validation_skip_injection(setup_wiki_root: Path) -> None:
    # Write invalid content with force_validation_skip=True
    invalid_content = "# Invalid\n\n- Decision: bypass validation\n"
    res = write_article(
        "features/bypass.md", invalid_content, force_validation_skip=True
    )
    assert "Written: features/bypass.md" in res

    wiki_root = setup_wiki_root / ".brain-79"
    written_file = wiki_root / "features" / "bypass.md"
    content = written_file.read_text(encoding="utf-8")
    assert "force_validation_skipped: true" in content

    # Check that linter detects force_validation_skipped
    report = lint_wiki()
    assert "validation=force_skip" in report or "force_validation_skipped" in report
