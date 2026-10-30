"""Tests for performance improvements and optimizations from 2026-10-29 performance report."""
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from brain79.config import get_wiki_root, set_project_root
from brain79.core.frontmatter import (
    ValidationError,
    get_schema_documentation,
    validate_frontmatter,
)
from brain79.core.handoff import write_handoff
from brain79.core.init_project import init_project
from brain79.core.navigation import load_registry, regenerate_index_navigation
from brain79.core.wiki import edit_article, read_article, write_article, write_many_articles
from brain79.server import brain79_write, mcp


@pytest.fixture
def setup_wiki(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_multi_error_validation_contains_all_violations_and_template() -> None:
    """P0.1: validate_frontmatter collects all issues at once and formats ready-to-paste template."""
    bad_fm = {
        "type": "feature",
        "unknown_extra_foo": "bar",
        # missing: status, version, last_updated
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_frontmatter(bad_fm, "features/test.md")

    err = exc_info.value
    assert len(err.issues) >= 3
    # Check that status, version, last_updated are all listed in issues
    rules_and_msgs = " ".join([i["message"] for i in err.issues])
    assert "status" in rules_and_msgs
    assert "version" in rules_and_msgs
    assert "last_updated" in rules_and_msgs
    assert "unknown_extra_foo" in rules_and_msgs

    # Check formatted user message includes actionable fixes and template
    user_msg = err.format_user_message()
    assert "Ready-to-paste frontmatter template for 'feature':" in user_msg
    assert "type: feature" in user_msg
    assert "status: planned" in user_msg


def test_mcp_write_error_includes_actionable() -> None:
    """P0.1: MCP brain79_write error includes format_user_message with actionable guidance."""
    bad_content = """---
type: feature
---
# Incomplete Feature
"""
    res = brain79_write("features/bad.md", bad_content)
    assert res.startswith("Error:")
    assert "status" in res
    assert "version" in res
    assert "Action:" in res or "Fix:" in res
    assert "Ready-to-paste frontmatter template" in res


def test_autofill_deterministic_fields_on_write(setup_wiki: Path) -> None:
    """P0.3: Server fills in type from location, last_updated, and strips hallucinated keys."""
    # Write feature omitting type and last_updated, but with hallucinated title/tags/created
    raw_content = """---
status: planned
version: 1.0.0
title: "Hallucinated Title"
tags: ["tag1", "tag2"]
created: "2026-01-01"
---

# Auto Inferred Feature

Body text here.
"""
    msg = write_article("features/inferred.md", raw_content)
    assert "Written: features/inferred.md" in msg

    saved = read_article("features/inferred.md")
    assert "type: feature" in saved
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert f"last_updated: {today}" in saved
    # Hallucinated keys stripped
    assert "title:" not in saved
    assert "tags:" not in saved
    assert "created:" not in saved


def test_autofill_decision_date_default_to_today(setup_wiki: Path) -> None:
    """P0.3: Decision without date defaults date to today."""
    raw_content = """---
status: accepted
deciders: [developer]
---

# Decision on Cache
Body text.
"""
    write_article("decisions/cache.md", raw_content)
    saved = read_article("decisions/cache.md")
    assert "type: decision" in saved
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert f"date: {today}" in saved


@pytest.mark.asyncio
async def test_fastmcp_output_schema_none() -> None:
    """P0.4: Tools have output_schema=None to prevent duplicated structuredContent."""
    tools = await mcp.list_tools()
    assert len(tools) > 0
    for t in tools:
        assert getattr(t, "output_schema", None) is None, f"Tool {t.name} has non-None output_schema"


def test_handoff_excluded_from_navigation_registry_and_index(setup_wiki: Path) -> None:
    """P0.5: Handoff write does not pollute navigation registry or INDEX.md."""
    write_handoff(
        session_type="feature",
        previous_handoff_ref="none",
        summary="Testing handoff nav isolation",
        completed_work=["Step 1"],
        pending_work=["Step 2"],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="Continue Step 2",
    )

    wiki_root = get_wiki_root()
    reg = load_registry(wiki_root)
    handoff_articles = [a for a in reg.get("articles", []) if a.get("path", "").startswith("handoffs/")]
    assert len(handoff_articles) == 0

    regenerate_index_navigation(wiki_root)
    idx_content = read_article("INDEX.md")
    assert "### Handoffs" not in idx_content
    assert "handoff-" not in idx_content


def test_auto_regenerate_navigation_on_write(setup_wiki: Path) -> None:
    """P1.1: Quick navigation is automatically regenerated when a new article is written."""
    article_content = """---
type: feature
status: shipped
version: 1.0.0
last_updated: 2026-10-29
---

# Brand New Feature

This is a newly added feature.
"""
    write_article("features/brand-new.md", article_content)

    idx_content = read_article("INDEX.md")
    assert "Brand New Feature" in idx_content
    assert "features/brand-new.md" in idx_content


def test_per_file_health_check_in_write_response(setup_wiki: Path) -> None:
    """P1.2: Server brain79_write returns inline lint OK or warnings."""
    # Write valid article
    valid_content = """---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# Valid Feature
Description.
"""
    res = brain79_write("features/valid.md", valid_content)
    assert "Written: features/valid.md · lint OK" in res

    # Write article with decision leakage
    leaking_content = """---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# Leaking Feature

## Decision
We decided to use Redis.
"""
    res2 = brain79_write("features/leak.md", leaking_content)
    assert "Lint warnings:" in res2
    assert "decision leakage" in res2.lower()


def test_edit_article_partial_replacement(setup_wiki: Path) -> None:
    """P1.3: edit_article modifies existing text in-place atomically."""
    # Initial article
    write_article(
        "features/edit-me.md",
        """---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# Initial Title

Line to remain.
Line to be replaced.
""",
    )

    # Partial edit
    res = edit_article(
        "features/edit-me.md",
        [{"old_text": "Line to be replaced.", "new_text": "Updated content line."}],
    )
    assert "Written: features/edit-me.md" in res

    content = read_article("features/edit-me.md")
    assert "Updated content line." in content
    assert "Line to be replaced." not in content
    assert "Line to remain." in content


def test_edit_article_failure_modes(setup_wiki: Path) -> None:
    """P1.3: edit_article rejects missing or ambiguous old_text."""
    write_article(
        "features/edit-err.md",
        """---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# Title
dup dup
""",
    )
    # Missing old_text
    with pytest.raises(ValueError, match="not found"):
        edit_article("features/edit-err.md", [{"old_text": "non_existent", "new_text": "x"}])

    # Ambiguous old_text
    with pytest.raises(ValueError, match="ambiguous"):
        edit_article("features/edit-err.md", [{"old_text": "dup", "new_text": "x"}])


def test_write_many_articles_batch(setup_wiki: Path) -> None:
    """P1.4: write_many_articles validates all articles first and writes atomically."""
    batch = [
        {
            "path": "features/batch1.md",
            "content": """---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# Batch 1
Content 1
""",
        },
        {
            "path": "features/batch2.md",
            "content": """---
type: feature
status: shipped
version: 1.0.0
last_updated: 2026-10-29
---

# Batch 2
Content 2
""",
        },
    ]

    res = write_many_articles(batch)
    assert "Batch write succeeded: 2 article(s) written" in res
    assert "features/batch1.md" in res
    assert "features/batch2.md" in res

    assert "Batch 1" in read_article("features/batch1.md")
    assert "Batch 2" in read_article("features/batch2.md")

    # Quick navigation should contain both
    idx = read_article("INDEX.md")
    assert "Batch 1" in idx
    assert "Batch 2" in idx


def test_write_many_articles_all_or_nothing_validation(setup_wiki: Path) -> None:
    """P1.4: If any article fails validation in write_many, none are written."""
    batch = [
        {
            "path": "features/good.md",
            "content": """---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# Good
Content
""",
        },
        {
            "path": "features/bad.md",
            "content": """---
type: feature
# missing status and version
last_updated: 2026-10-29
---

# Bad
Content
""",
        },
    ]

    with pytest.raises(ValidationError) as exc_info:
        write_many_articles(batch)

    err = exc_info.value
    assert "Batch validation failed for 1 article(s)" in err.message

    # good.md should NOT have been written to disk
    wiki_root = get_wiki_root()
    assert not (wiki_root / "features" / "good.md").exists()


def test_handoff_flexible_previous_ref(setup_wiki: Path) -> None:
    """P1.5: Handoff accepts latest when empty, none, and initial gracefully."""
    # When no handoffs exist, latest defaults to none gracefully
    path1 = write_handoff(
        session_type="feature",
        previous_handoff_ref="latest",
        summary="First session",
        boot_instruction="No pending tasks.",
    )
    assert path1.startswith("handoffs/handoff-")

    # Next session referencing latest
    path2 = write_handoff(
        session_type="feature",
        previous_handoff_ref="latest",
        summary="Second session",
        boot_instruction="All done.",
    )
    assert path2.startswith("handoffs/handoff-")

    # Session with 'initial'
    path3 = write_handoff(
        session_type="research",
        previous_handoff_ref="initial",
        summary="Third session",
        boot_instruction="Ninguna tarea pendiente.",
    )
    assert path3.startswith("handoffs/handoff-")


def test_write_many_articles_single_nav_regeneration(
    setup_wiki: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """write_many_articles regenerates navigation exactly once at the end of the batch."""
    from brain79.core import navigation

    calls = 0
    orig_regen = navigation.regenerate_index_navigation

    def counting_regen(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return orig_regen(*args, **kwargs)

    monkeypatch.setattr(navigation, "regenerate_index_navigation", counting_regen)

    batch = [
        {
            "path": "features/single1.md",
            "content": "---\ntype: feature\nstatus: planned\nversion: 1.0.0\nlast_updated: 2026-10-29\n---\n# S1\nText\n",
        },
        {
            "path": "features/single2.md",
            "content": "---\ntype: feature\nstatus: planned\nversion: 1.0.0\nlast_updated: 2026-10-29\n---\n# S2\nText\n",
        },
        {
            "path": "features/single3.md",
            "content": "---\ntype: feature\nstatus: planned\nversion: 1.0.0\nlast_updated: 2026-10-29\n---\n# S3\nText\n",
        },
    ]

    write_many_articles(batch)
    assert calls == 1, f"Expected 1 nav regeneration, got {calls}"


def test_schema_documentation_generation() -> None:
    """P0.2: get_schema_documentation returns valid schema and templates."""
    doc_all = get_schema_documentation()
    assert "Brain-79 Frontmatter Schema Reference" in doc_all
    assert "## Type: `feature`" in doc_all
    assert "## Type: `decision`" in doc_all

    doc_feature = get_schema_documentation("feature")
    assert "**Required fields**: type, status, version, last_updated" in doc_feature
    assert "planned, in_progress, shipped, deprecated, legacy" in doc_feature

    doc_unknown = get_schema_documentation("unknown_type")
    assert "Unknown type 'unknown_type'" in doc_unknown
