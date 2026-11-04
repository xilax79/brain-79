"""Comprehensive tests for defect backlog remediations (BUG-001, BUG-002, INEF-001, INEF-002)."""

from pathlib import Path
import pytest

from brain79.config import set_project_root
from brain79.core.frontmatter import normalize_backlink_footer
from brain79.core.init_project import init_project
from brain79.core.lint import lint_wiki
from brain79.core.lint_organizational import check_article_atomicity
from brain79.core.orient import orient
from brain79.server import brain79_write, brain79_edit, brain79_write_many


# ==============================================================================
# BUG-001: Broken local link in SCHEMA_GENERAL.md and root backlink normalization
# ==============================================================================

def test_init_general_profile_has_no_broken_links(tmp_path: Path) -> None:
    """Initializing with profile='general' must produce a wiki that passes strict lint with zero broken links."""
    init_project(tmp_path, profile="general")
    wiki_root = tmp_path / ".brain-79"
    schema_content = (wiki_root / "SCHEMA.md").read_text(encoding="utf-8")

    assert "../INDEX.md" not in schema_content, "SCHEMA.md at root should link to INDEX.md, not ../INDEX.md"
    assert "[← Volver al Índice](INDEX.md)" in schema_content

    # Strict linting must be completely OK out of the box
    set_project_root(tmp_path)
    report = lint_wiki()
    assert "[Status: OK]" in report
    assert "Broken Local Links (0)" in report
    assert "SCHEMA.md →" not in report


def test_normalize_backlink_footer_rewrites_root_level_traversal() -> None:
    """normalize_backlink_footer should rewrite any '../INDEX.md' to 'INDEX.md' for root-level files."""
    body_with_bad_root_link = (
        "# Root Document\n\n"
        "Some text.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    normalized = normalize_backlink_footer(body_with_bad_root_link, "SCHEMA.md")
    assert "[← Volver al Índice](INDEX.md)" in normalized
    assert "../INDEX.md" not in normalized


# ==============================================================================
# BUG-002: Linter H2 atomicity, code-fence masking, and composite thresholds
# ==============================================================================

def test_atomicity_masks_code_fences(tmp_path: Path) -> None:
    """H2 sections inside markdown code blocks must not count toward article atomicity limit."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    feat_dir = wiki_root / "features"
    feat_dir.mkdir()

    # Article with 3 real H2 sections, but 8 simulated H2s inside a code fence
    content = (
        "---\n"
        "type: feature\n"
        "summary: Testing code fence masking in atomicity\n"
        "status: planned\n"
        "---\n\n"
        "# Feature Title\n\n"
        "## Real Section 1\n\n"
        "Here is documentation containing code blocks:\n\n"
        "```markdown\n"
        "## Fake Header 1\n"
        "## Fake Header 2\n"
        "## Fake Header 3\n"
        "## Fake Header 4\n"
        "## Fake Header 5\n"
        "## Fake Header 6\n"
        "## Fake Header 7\n"
        "## Fake Header 8\n"
        "```\n\n"
        "## Real Section 2\n\n"
        "More content.\n\n"
        "## Real Section 3\n\n"
        "Final content.\n"
    )
    (feat_dir / "masked-doc.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 0, f"Code block headers should be masked, got issues: {atomicity_issues}"


def test_atomicity_checklist_exemption(tmp_path: Path) -> None:
    """Checklist/roadmap articles with task checkboxes or checklist tags allow up to 15 H2 sections."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir()

    # Article with 9 H2 sections and task checkboxes (typical checklist document)
    sections = [
        "---\n"
        "type: topic\n"
        "summary: Master checklist for research\n"
        "status: active\n"
        "tags:\n"
        "  - checklist\n"
        "---\n\n"
        "# Master Research Checklist\n\n"
        "## Overview\n\n"
        "Checklist overview.\n"
    ]
    for i in range(1, 9):
        sections.append(f"## Section {i}\n- [ ] Task {i}.1\n- [ ] Task {i}.2\n")

    content = "\n".join(sections)
    (topics_dir / "checklist-investigacion-libro.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 0, f"Checklist document with 9 H2s should be permitted, got: {atomicity_issues}"


def test_atomicity_short_compact_outline_exemption(tmp_path: Path) -> None:
    """Structured outline or compact checklist articles allow up to 15 concise H2 sections without warning."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    feat_dir = wiki_root / "features"
    feat_dir.mkdir()

    sections = [
        "---\n"
        "type: feature\n"
        "summary: Short compact outline\n"
        "status: planned\n"
        "tags:\n"
        "  - outline\n"
        "---\n\n"
        "# Compact Feature Outline\n"
    ]
    for i in range(1, 10):
        sections.append(f"## Quick Point {i}\nShort description.\n")

    content = "\n".join(sections)
    assert len(content.splitlines()) < 150

    (feat_dir / "compact-outline.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 0, f"Compact outline with 9 H2s should be permitted, got: {atomicity_issues}"


def test_atomicity_long_prose_flags_over_10_h2(tmp_path: Path) -> None:
    """Long standard prose articles (> 150 lines) without checklist traits trigger warning if H2 > 10."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    feat_dir = wiki_root / "features"
    feat_dir.mkdir()

    sections = [
        "---\n"
        "type: feature\n"
        "summary: Long sprawling monolithic article\n"
        "status: planned\n"
        "---\n\n"
        "# Monolithic Feature\n"
    ]
    # Create 11 H2 sections with extensive prose paragraphs totaling > 150 lines
    for i in range(1, 12):
        sections.append(
            f"## Deep Dive Section {i}\n"
            + ("This is a long paragraph detailing architectural considerations and nuances.\n" * 15)
        )

    content = "\n".join(sections)
    assert len(content.splitlines()) > 150

    (feat_dir / "monolith.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 1
    assert "monolith.md" in atomicity_issues[0].path


# ==============================================================================
# INEF-001: Server write receipts with auto-synced navigation confirmation
# ==============================================================================

def test_server_write_receipt_includes_auto_synced(tmp_path: Path) -> None:
    """brain79_write, brain79_edit, and brain79_write_many receipts must state that INDEX.md was auto-synced."""
    init_project(tmp_path)
    set_project_root(tmp_path)

    write_res = brain79_write(
        path="features/test-receipt.md",
        content=(
            "---\n"
            "type: feature\n"
            "summary: Testing receipt wording\n"
            "status: planned\n"
            "version: 0.1.0\n"
            "---\n\n"
            "# Test Receipt\n\n"
            "## Overview\n"
            "Overview here.\n"
        ),
    )
    assert "INDEX.md auto-synced" in write_res
    assert "lint OK" in write_res

    edit_res = brain79_edit(
        path="features/test-receipt.md",
        edits=[{"old_text": "Overview here.", "new_text": "Updated overview here."}],
    )
    assert "INDEX.md auto-synced" in edit_res
    assert "lint OK" in edit_res

    batch_res = brain79_write_many(
        articles=[
            {
                "path": "features/test-batch-receipt.md",
                "content": (
                    "---\n"
                    "type: feature\n"
                    "summary: Testing batch receipt wording\n"
                    "status: planned\n"
                    "version: 0.1.0\n"
                    "---\n\n"
                    "# Test Batch Receipt\n\n"
                    "## Overview\n"
                    "Batch overview.\n"
                ),
            }
        ]
    )
    assert "INDEX.md auto-synced" in batch_res


# ==============================================================================
# INEF-002: brain79_orient includes Active Schema Summary
# ==============================================================================

def test_orient_includes_active_schema_summary(tmp_path: Path) -> None:
    """brain79_orient output must include a compact Active Schema Summary block."""
    init_project(tmp_path, profile="software")
    set_project_root(tmp_path)

    orient_out = orient(task="Develop a new feature")
    assert "## 📐 Active Schema Summary" in orient_out
    assert "**Profile:** `software`" in orient_out
    assert "features/" in orient_out
    assert "decisions/" in orient_out
