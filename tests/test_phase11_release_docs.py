"""Tests for Phase 11 Stage 4: Honest README positioning and CHANGELOG release notes (AC-11.9)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_readme_documents_limitations_profiles_and_native_harnesses() -> None:
    """AC-11.9: README.md contains Limitations and trade-offs, core/full profiles, and native harnesses."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Limitations and trade-offs" in readme
    assert "Python 3.11+" in readme
    assert "AST Guard C" in readme
    assert "TF-IDF" in readme

    # Focused MCP surface & CLI superset
    assert "9 hot-path tools" in readme
    assert "25-command" in readme

    # Native harnesses
    for harness_path in (
        "AGENTS.md",
        "CLAUDE.md",
        ".cursor/rules/brain79.mdc",
        ".github/copilot-instructions.md",
        ".agents/plugins/brain79/",
    ):
        assert harness_path in readme, f"README.md must document {harness_path}"


def test_changelog_documents_pre_ga_policy_and_v0_12_0_migration_notes() -> None:
    """AC-11.9: CHANGELOG.md documents ADR-017 pre-GA policy and v0.12.0 migration notes."""
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "ADR-017" in changelog
    assert "0.y.z" in changelog
    assert "## [0.12.0]" in changelog
    assert "--mcp-profile full" in changelog
    assert "BRAIN79_MCP_PROFILE=full" in changelog
    assert "brain79 update-project" in changelog
