from pathlib import Path
import shutil

import pytest

from brain79.cli.dispatch import run_cli
from brain79.config import set_project_root
from brain79.core.frontmatter import parse_frontmatter
from brain79.core.lint import lint_wiki
from brain79.core.navigation import regenerate_index_navigation
from brain79.core.migration import migrate_wiki

SNAPSHOT_DIR = Path(__file__).parent / "fixtures" / "truco_arena_snapshot"


@pytest.fixture
def truco_arena_workdir(tmp_path: Path) -> Path:
    """Create a temporary copy of the Truco Arena snapshot for isolated testing."""
    target_project = tmp_path / "truco_arena_copy"
    target_project.mkdir()

    snapshot_wiki = SNAPSHOT_DIR / ".brain-79"
    target_wiki = target_project / ".brain-79"

    shutil.copytree(snapshot_wiki, target_wiki)
    set_project_root(target_project)
    return target_project


def test_truco_arena_initial_state_has_known_violations(truco_arena_workdir: Path) -> None:
    """PINS the problem: Truco Arena snapshot has initial organizational violations."""
    report = lint_wiki()
    assert "[Status: CRITICAL]" in report or "[Status: WARNING]" in report
    # Snapshot INDEX.md or articles have missing frontmatter or oversized index
    assert "index_oversized" in report or "frontmatter_missing" in report or "Prohibited" in report


def test_truco_arena_migrate_adds_legacy_frontmatter(truco_arena_workdir: Path) -> None:
    """Migration adds frontmatter to all legacy articles in Truco Arena snapshot."""
    wiki_root = truco_arena_workdir / ".brain-79"

    # Verify architecture/game-table.md lacks frontmatter initially if present
    game_table = wiki_root / "architecture" / "game-table.md"
    if game_table.exists():
        assert not game_table.read_text(encoding="utf-8").startswith("---\n")

    report = migrate_wiki(wiki_root, dry_run=False)
    assert "# Migration Report (APPLIED)" in report

    if game_table.exists():
        content = game_table.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        meta, _ = parse_frontmatter(content)
        assert meta["type"] == "architecture"
        assert meta["stability"] == "legacy"


def test_truco_arena_migrate_uses_legacy_status(truco_arena_workdir: Path) -> None:
    """All migrated decisions in Truco Arena snapshot use status: legacy (not accepted/planned)."""
    wiki_root = truco_arena_workdir / ".brain-79"
    dec_file = wiki_root / "decisions" / "adr-001.md"
    dec_file.parent.mkdir(parents=True, exist_ok=True)
    dec_file.write_text("# Decision 1\n\nLegacy decision text.\n", encoding="utf-8")

    migrate_wiki(wiki_root, dry_run=False)

    meta, _ = parse_frontmatter(dec_file.read_text(encoding="utf-8"))
    assert meta["type"] == "decision"
    assert meta["status"] == "legacy"


def test_truco_arena_full_remediation_passes_lint_strict(truco_arena_workdir: Path) -> None:
    """After migrate + human review update + compliant INDEX.md + navigation regeneration, lint --strict passes."""
    wiki_root = truco_arena_workdir / ".brain-79"

    # Step 1: Migrate legacy frontmatter
    migrate_wiki(wiki_root, dry_run=False)

    # Step 2: Update legacy article status after human review
    game_table = wiki_root / "architecture" / "game-table.md"
    if game_table.exists():
        game_table.write_text(
            "---\ntype: architecture\nstability: stable\nlast_updated: 2026-08-11\n---\n\n# Game Table Architecture\n",
            encoding="utf-8",
        )

    # Step 3: Replace oversized/non-compliant INDEX.md with clean compliant structure linking to all sections
    index_file = wiki_root / "INDEX.md"
    index_file.write_text(
        "# Project index\n\n"
        "> Entry point to Truco Arena wiki.\n\n"
        "## Project\n"
        "**Name:** Truco Arena\n"
        "**Purpose:** Multiplayer Truco card game platform.\n"
        "**Status:** Active development.\n\n"
        "## Current focus\n"
        "- Refactoring game engine and state synchronization.\n\n"
        "## Quick navigation\n"
        "- [Schema](SCHEMA.md)\n"
        "- [Product Overview](product/overview.md)\n"
        "- [Game Table Architecture](architecture/game-table.md)\n"
        "- [Handoffs](handoffs/)\n\n"
        "## Known issues\n"
        "- None currently reported.\n\n"
        "## Roadmap\n"
        "- Complete organizational enforcement migration.\n",
        encoding="utf-8",
    )

    # Step 4: Regenerate Quick navigation section
    regenerate_index_navigation(wiki_root)

    # Step 5: Verify lint --strict passes cleanly
    code = run_cli("lint", ["--strict"])
    assert code == 0

    report = lint_wiki()
    assert "[Status: OK]" in report
