"""Tests for Phase 11 Stage 1: English-first backlink standardization and migration."""

from pathlib import Path

import pytest

from brain79.config import set_project_root
from brain79.core.frontmatter import (
    DEFAULT_BACKLINK_LABEL,
    ActiveSchema,
    clear_schema_cache,
    generate_document_skeleton,
    load_active_schema,
    normalize_backlink_footer,
)
from brain79.core.init_project import init_project
from brain79.core.lint_organizational import check_article_backlinks
from brain79.core.migration import migrate_wiki
from brain79.core.session_commit import commit_session
from brain79.core.wiki import read_article, write_article


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    init_project(tmp_path)
    set_project_root(tmp_path)
    clear_schema_cache()
    return tmp_path


# ==============================================================================
# R-1.1 / AC-11.1 & AC-11.2: ActiveSchema.backlink_label & Skeleton Generation
# ==============================================================================


def test_default_backlink_label_constant_and_schema_default(clean_project: Path) -> None:
    """ActiveSchema defaults to English '← Back to Index'."""
    assert DEFAULT_BACKLINK_LABEL == "← Back to Index"
    schema = load_active_schema(clean_project / ".brain-79")
    assert schema.backlink_label == "← Back to Index"


def test_schema_custom_backlink_label_parsed_and_stripped(clean_project: Path) -> None:
    """Declaring backlink_label in SCHEMA.md frontmatter configures ActiveSchema."""
    schema_file = clean_project / ".brain-79" / "SCHEMA.md"
    schema_file.write_text(
        "---\nprofile: software\nbacklink_label: \"  ← Return to Hub  \"\n---\n# Schema\n",
        encoding="utf-8",
    )
    clear_schema_cache()
    schema = load_active_schema(clean_project / ".brain-79")
    assert schema.backlink_label == "← Return to Hub"


@pytest.mark.parametrize(
    "invalid_yaml_value",
    [
        '""',
        '"   "',
        '"[Bracketed]"',
        '"Has [open"',
        '"Has close]"',
        '"Line1\\nLine2"',
        '"Line1\\rLine2"',
        "123",
        "null",
    ],
)
def test_schema_invalid_backlink_label_falls_back_safely(
    clean_project: Path, invalid_yaml_value: str
) -> None:
    """Invalid backlink_label values fall back safely to DEFAULT_BACKLINK_LABEL."""
    schema_file = clean_project / ".brain-79" / "SCHEMA.md"
    schema_file.write_text(
        f"---\nprofile: software\nbacklink_label: {invalid_yaml_value}\n---\n# Schema\n",
        encoding="utf-8",
    )
    clear_schema_cache()
    schema = load_active_schema(clean_project / ".brain-79")
    assert schema.backlink_label == DEFAULT_BACKLINK_LABEL


def test_generate_document_skeleton_uses_active_backlink_label(clean_project: Path) -> None:
    """generate_document_skeleton emits active schema backlink_label."""
    default_skel = generate_document_skeleton("feature")
    assert "[← Back to Index](../INDEX.md)" in default_skel
    assert "Volver al Índice" not in default_skel

    custom_schema = ActiveSchema(
        profile="software",
        types={"feature": {"required": ["type", "summary", "last_updated"], "required_sections": ["Overview"]}},
        location_to_type={"features": "feature"},
        backlink_label="← Return to Hub",
    )
    custom_skel = generate_document_skeleton("feature", schema=custom_schema)
    assert "[← Return to Hub](../INDEX.md)" in custom_skel


# ==============================================================================
# R-1.2 / AC-11.1 & AC-11.2: normalize_backlink_footer, write, commit, lint
# ==============================================================================


def test_write_article_and_commit_session_inject_english_default(clean_project: Path) -> None:
    """AC-11.1: write_article and commit_session default to [← Back to Index](../INDEX.md)."""
    content = (
        "---\n"
        "type: feature\n"
        "summary: english backlink default\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-20\n"
        "---\n\n"
        "# Feature — English Backlink\n\n"
        "## Overview\n"
        "Body text.\n"
    )
    write_article("features/en-default.md", content)
    saved = read_article("features/en-default.md")
    assert "\n---\n\n[← Back to Index](../INDEX.md)" in saved

    res = commit_session(
        {
            "writes": [
                {
                    "path": "features/en-commit.md",
                    "content": content.replace("English Backlink", "Commit Backlink"),
                }
            ]
        }
    )
    assert res["success"] is True
    saved_commit = read_article("features/en-commit.md")
    assert "\n---\n\n[← Back to Index](../INDEX.md)" in saved_commit


def test_normalize_backlink_footer_root_vs_nested_and_custom_label() -> None:
    """Root articles receive INDEX.md; nested articles receive ../...INDEX.md."""
    body = "# Overview\n\nSome content."
    root_norm = normalize_backlink_footer(body, "overview.md")
    assert root_norm.endswith("---\n\n[← Back to Index](INDEX.md)\n")

    nested_norm = normalize_backlink_footer(
        body, "features/sub/doc.md", backlink_label="← Return to Hub"
    )
    assert nested_norm.endswith("---\n\n[← Return to Hub](../../INDEX.md)\n")


def test_normalize_backlink_footer_recognizes_legacy_without_canonicalizing_by_default() -> None:
    """Without canonicalize_legacy, existing Spanish backlink is preserved without duplication."""
    body = "# Legacy\n\n## Overview\nText.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n"
    normalized = normalize_backlink_footer(body, "features/legacy.md")
    assert normalized == body
    assert normalized.count("INDEX.md") == 1


def test_normalize_backlink_footer_canonicalize_legacy_rewrites_and_is_idempotent() -> None:
    """With canonicalize_legacy=True, legacy markers rewrite cleanly without duplicating ---."""
    body = "# Legacy\n\n## Overview\nText.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n"
    once = normalize_backlink_footer(body, "features/legacy.md", canonicalize_legacy=True)
    assert "[← Back to Index](../INDEX.md)" in once
    assert "Volver al Índice" not in once
    assert once.count("---") == 1

    twice = normalize_backlink_footer(once, "features/legacy.md", canonicalize_legacy=True)
    assert twice == once


def test_normalize_backlink_footer_canonicalize_preserves_earlier_links_and_backslashes() -> None:
    """Canonicalization only rewrites the matched backlink and handles backslashes in custom labels."""
    body = "# Legacy\n\n[See Docs](docs.md) | [← Volver al Índice](../INDEX.md)\n"
    rewritten = normalize_backlink_footer(
        body,
        "features/legacy.md",
        backlink_label=r"← Back \ Index",
        canonicalize_legacy=True,
    )
    assert "[See Docs](docs.md) | [← Back \\ Index](../INDEX.md)" in rewritten


def test_normalize_backlink_footer_code_fence_edge_case() -> None:
    """Legacy marker inside a code fence is never rewritten or mistaken for a tail backlink."""
    body = (
        "# Guide\n\n"
        "```markdown\n"
        "[← Volver al Índice](../INDEX.md)\n"
        "```\n"
    )
    normalized = normalize_backlink_footer(body, "features/guide.md", canonicalize_legacy=True)
    assert "[← Volver al Índice](../INDEX.md)\n```" in normalized
    assert normalized.rstrip().endswith("[← Back to Index](../INDEX.md)")


def test_custom_backlink_label_end_to_end_write_and_lint(clean_project: Path) -> None:
    """AC-11.2: custom backlink_label in SCHEMA.md drives write normalization and lint."""
    wiki_root = clean_project / ".brain-79"
    (wiki_root / "SCHEMA.md").write_text(
        "---\nprofile: software\nbacklink_label: \"← Return to Hub\"\n---\n# Schema\n",
        encoding="utf-8",
    )
    clear_schema_cache()

    content = (
        "---\n"
        "type: feature\n"
        "summary: custom hub backlink\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-20\n"
        "---\n\n"
        "# Feature — Hub\n\n"
        "## Overview\n"
        "Text.\n"
    )
    write_article("features/hub.md", content)
    saved = read_article("features/hub.md")
    assert "[← Return to Hub](../INDEX.md)" in saved

    issues = check_article_backlinks(wiki_root)
    assert issues == []

    # Missing backlink actionable message should suggest the active label
    missing_file = wiki_root / "features" / "missing.md"
    missing_file.write_text(content, encoding="utf-8")
    issues_missing = check_article_backlinks(wiki_root)
    assert len(issues_missing) == 1
    assert "[← Return to Hub](../INDEX.md)" in issues_missing[0].actionable


# ==============================================================================
# R-1.3 / AC-11.3: migrate_wiki canonicalization, dry_run, idempotence, lint
# ==============================================================================


def test_legacy_spanish_backlink_passes_lint_and_migrates_cleanly(clean_project: Path) -> None:
    """AC-11.3: Spanish backlink passes lint; migrate_wiki rewrites it idempotently."""
    wiki_root = clean_project / ".brain-79"
    art = wiki_root / "features" / "legacy-es.md"
    art.parent.mkdir(parents=True, exist_ok=True)
    legacy_content = (
        "---\n"
        "type: feature\n"
        "summary: legacy spanish footer article\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-11-20\n"
        "---\n\n"
        "# Feature — Legacy\n\n"
        "## Overview\n"
        "Still valid.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    art.write_text(legacy_content, encoding="utf-8")

    # 1. Passes lint backlink check
    assert check_article_backlinks(wiki_root) == []

    # 2. Dry-run reports the file without mutating disk
    dry_report = migrate_wiki(wiki_root, dry_run=True)
    assert "features/legacy-es.md" in dry_report
    assert "[← Volver al Índice](../INDEX.md)" in art.read_text(encoding="utf-8")

    # 3. Apply migrates to English default
    apply_report = migrate_wiki(wiki_root, dry_run=False)
    assert "features/legacy-es.md" in apply_report
    migrated = art.read_text(encoding="utf-8")
    assert "[← Back to Index](../INDEX.md)" in migrated
    assert "Volver al Índice" not in migrated

    # 4. Idempotent on second run
    second_report = migrate_wiki(wiki_root, dry_run=False)
    assert "features/legacy-es.md: up-to-date" in second_report
    assert art.read_text(encoding="utf-8") == migrated
