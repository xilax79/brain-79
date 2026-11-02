"""Tests for Phase 0: Core Bug Fixes and Invariant Alignment.

Verifies:
1. Phase 0.1: bootstrap manifest compliance with frontmatter validation and pure routing table.
2. Phase 0.2: full validator-linter parity (check_frontmatter_consistency uses validate_frontmatter).
3. Phase 0.3: strict ADR-008 enforcement (INDEX_ALLOWED_H2 only Quick navigation).
4. Phase 0.4: raw_session frontmatter generation and required summary on indexable articles.
"""

from pathlib import Path

import pytest

from brain79.config import get_wiki_root, set_project_root
from brain79.core.bootstrap import run_bootstrap
from brain79.core.curate import prepare_curation_guide
from brain79.core.frontmatter import (
    TYPE_SCHEMA,
    parse_frontmatter,
)
from brain79.core.init_project import init_project
from brain79.core.lint_organizational import (
    check_frontmatter_consistency,
    check_prohibited_content,
    generate_extraction_suggestions,
)
from brain79.core.validation import INDEX_ALLOWED_H2, ValidationError, validate_article_content
from brain79.core.wiki import read_article, save_raw_session, write_article


@pytest.fixture
def project_env(tmp_path: Path) -> Path:
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


# ==============================================================================
# Phase 0.1: bootstrap manifest compliance
# ==============================================================================


def test_bootstrap_manifest_instructions_for_overview_pass_validation(project_env: Path) -> None:
    """The seed templates provided by bootstrap manifest must pass write_article validation without errors."""
    manifest = run_bootstrap()
    assert "INDEX.md already exists; update it in place" not in manifest
    assert "product/overview.md" in manifest
    assert "architecture/overview.md" in manifest

    # Simulate an agent writing the required articles using the manifest's templates
    overview_content = (
        "---\n"
        "type: architecture\n"
        "summary: Overview of project architecture\n"
        "stability: stable\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Architecture — Overview\n\n"
        "## Overview\nProject architecture.\n"
    )
    result = write_article("architecture/overview.md", overview_content)
    assert "Written: architecture/overview.md" in result


def test_bootstrap_manifest_does_not_instruct_prose_in_index(project_env: Path) -> None:
    """Bootstrap manifest must not instruct agents to write prose in INDEX.md."""
    manifest = run_bootstrap()
    # Should instruct to write product/overview.md or let navigation handle INDEX.md
    assert "Update with project name, one-sentence purpose" not in manifest


# ==============================================================================
# Phase 0.2: Validator & Linter Parity (check_frontmatter_consistency)
# ==============================================================================


def test_linter_detects_missing_required_fields_beyond_type_and_date(project_env: Path) -> None:
    """Files edited on disk missing required fields (e.g. stability on architecture) must be flagged by linter."""
    wiki_root = get_wiki_root()
    arch_file = wiki_root / "architecture" / "flawed.md"
    arch_file.write_text(
        "---\n"
        "type: architecture\n"
        "summary: Flawed article\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Flawed\n\nMissing stability.\n",
        encoding="utf-8",
    )

    issues = check_frontmatter_consistency(wiki_root)
    assert any(i.rule == "frontmatter_missing_field" and i.path == "architecture/flawed.md" for i in issues)


def test_linter_detects_invalid_enums_in_frontmatter(project_env: Path) -> None:
    """Files with invalid enum values must be flagged by organizational linter."""
    wiki_root = get_wiki_root()
    feat_file = wiki_root / "features" / "bad_enum.md"
    feat_file.write_text(
        "---\n"
        "type: feature\n"
        "summary: Bad enum\n"
        "status: nonexistent_status\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Bad Enum\n",
        encoding="utf-8",
    )

    issues = check_frontmatter_consistency(wiki_root)
    assert any(i.rule == "frontmatter_invalid_enum" and i.path == "features/bad_enum.md" for i in issues)


def test_linter_detects_unknown_frontmatter_keys(project_env: Path) -> None:
    """Files with unknown frontmatter keys must be flagged by organizational linter."""
    wiki_root = get_wiki_root()
    prod_file = wiki_root / "product" / "unknown_key.md"
    prod_file.write_text(
        "---\n"
        "type: product\n"
        "summary: Product doc\n"
        "custom_hallucination: invalid\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Product Doc\n",
        encoding="utf-8",
    )

    issues = check_frontmatter_consistency(wiki_root)
    assert any(i.rule == "frontmatter_unknown_key" and i.path == "product/unknown_key.md" for i in issues)


# ==============================================================================
# Phase 0.3: Strict ADR-008 Enforcement (INDEX_ALLOWED_H2)
# ==============================================================================


def test_index_allowed_h2_restricted_strictly_to_quick_navigation() -> None:
    """INDEX_ALLOWED_H2 must strictly only allow 'Quick navigation'."""
    assert INDEX_ALLOWED_H2 == frozenset({"Quick navigation"})


def test_index_rejects_legacy_h2_headers_in_validation() -> None:
    """Legacy sections like 'Project', 'Current focus', 'Known issues', 'Roadmap' must be rejected in INDEX.md."""
    legacy_sections = ["Project", "Current focus", "Known issues", "Roadmap"]
    for section in legacy_sections:
        content = f"# Index\n\n## {section}\nSome narrative content.\n"
        with pytest.raises(ValidationError) as exc_info:
            validate_article_content("INDEX.md", content)
        assert exc_info.value.rule == "index_prohibited_header"


def test_index_check_prohibited_content_flags_legacy_headers(project_env: Path) -> None:
    """Organizational linter check_prohibited_content must flag legacy sections."""
    wiki_root = get_wiki_root()
    index_file = wiki_root / "INDEX.md"
    index_file.write_text("# Index\n\n## Project\nName: Test\n\n## Quick navigation\n", encoding="utf-8")

    issues = check_prohibited_content(wiki_root)
    assert any(i.rule == "index_prohibited_header" and "## Project" in i.message for i in issues)


def test_curate_guide_mandates_pure_routing_table(project_env: Path) -> None:
    """Curation guide must state that INDEX.md only permits Quick navigation."""
    wiki_root = get_wiki_root()
    guide = prepare_curation_guide(wiki_root)
    assert "Quick navigation" in guide
    assert "Project" not in guide or "Current focus" not in guide


def test_generate_extraction_suggestions_flags_legacy_headers(project_env: Path) -> None:
    """Extraction suggestions should highlight lines under legacy headers for extraction."""
    wiki_root = get_wiki_root()
    index_file = wiki_root / "INDEX.md"
    index_file.write_text("# Index\n\n## Project\nProject description line\n\n## Quick navigation\n", encoding="utf-8")

    suggestions = generate_extraction_suggestions(wiki_root)
    assert "Project description line" in suggestions


# ==============================================================================
# Phase 0.4: raw_session Frontmatter & Required Summary
# ==============================================================================


def test_save_raw_session_generates_valid_frontmatter(project_env: Path) -> None:
    """save_raw_session must write YAML frontmatter with type: raw_session."""
    saved_path = save_raw_session("Session summary text", instructions="Investigate performance")
    content = read_article(saved_path)

    assert content.startswith("---\n")
    meta, body = parse_frontmatter(content)
    assert meta["type"] == "raw_session"
    assert "session_id" in meta
    assert "session_type" in meta
    assert "last_updated" in meta
    assert "Session summary text" in body


def test_summary_required_for_all_indexable_types() -> None:
    """summary must be in required fields for product, architecture, feature, decision, changelog."""
    indexable_types = ["product", "architecture", "feature", "decision", "changelog"]
    for t in indexable_types:
        assert "summary" in TYPE_SCHEMA[t]["required"]
        assert "summary" not in TYPE_SCHEMA[t]["optional"]


def test_writing_article_without_summary_raises_validation_error(project_env: Path) -> None:
    """Writing an indexable article without summary in frontmatter or extractable from body must fail validation."""
    content = (
        "---\n"
        "type: architecture\n"
        "stability: stable\n"
        "last_updated: 2026-11-02\n"
        "---\n"
    )
    with pytest.raises(ValidationError) as exc_info:
        write_article("architecture/test.md", content)
    assert exc_info.value.rule == "frontmatter_missing_field"
    assert "summary" in exc_info.value.message


# ==============================================================================
# Adversarial Findings Tests
# ==============================================================================


def test_schema_md_declares_summary_as_required(project_env: Path) -> None:
    """Finding 1: SCHEMA.md (both template and project root) must declare summary as required."""
    schema_path = project_env / ".brain-79" / "SCHEMA.md"
    content = schema_path.read_text(encoding="utf-8")

    # In Required Fields table lines
    assert "`type`, `summary`, `last_updated`" in content
    assert "`type`, `summary`, `stability`, `last_updated`" in content
    assert "`type`, `summary`, `status`, `version`, `last_updated`" in content

    # In Optional Fields note
    assert "Optional fields accepted across all types: `summary`" not in content


def test_migrate_wiki_repairs_missing_summary_in_existing_frontmatter(project_env: Path) -> None:
    """Finding 2: migrate_wiki must add summary to articles that have frontmatter but lack summary."""
    from brain79.core.migration import migrate_wiki

    wiki_root = project_env / ".brain-79"
    legacy_file = wiki_root / "features" / "has_fm_no_summary.md"
    legacy_file.write_text(
        "---\n"
        "type: feature\n"
        "status: shipped\n"
        "version: 1.0.0\n"
        "last_updated: 2026-10-29\n"
        "---\n\n"
        "# Feature Without Summary\n\n"
        "This feature was created before summary was mandatory.\n",
        encoding="utf-8",
    )

    report = migrate_wiki(wiki_root, dry_run=False)
    assert "features/has_fm_no_summary.md" in report

    # Verify that summary was added and linter passes
    meta, _ = parse_frontmatter(legacy_file.read_text(encoding="utf-8"))
    assert "summary" in meta
    assert meta["summary"] == "This feature was created before summary was mandatory."

    issues = check_frontmatter_consistency(wiki_root)
    assert not any(i.path == "features/has_fm_no_summary.md" for i in issues)


def test_autofill_sanitizes_bracket_and_newline_summaries(project_env: Path) -> None:
    """Finding 3: Auto-extracted summary must not be corrupted by leading brackets or newlines."""
    body_with_brackets = (
        "# Bracket Feature\n\n"
        "[RFC-101] Core architecture for user authentication.\n"
    )
    content = (
        "---\n"
        "type: feature\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "---\n\n"
    ) + body_with_brackets

    write_article("features/bracket.md", content)
    saved = read_article("features/bracket.md")
    meta, _ = parse_frontmatter(saved)

    # Must be a string, NOT parsed as list ['RFC-101']
    assert isinstance(meta["summary"], str)
    assert "RFC-101" in meta["summary"]
    assert "\n" not in meta["summary"]

