"""Tests for the 5 integration holes identified in Phase 1 audit.

1. handoff session_type allows general profile session_types ('work', 'writing', 'analysis', etc.)
   via core handoff, CLI dispatch, and server MCP tool.
2. autofill_deterministic_fields preserves 'tags' when declared in active schema (e.g. topic)
   and autofills 'date' for 'log' or any type whose schema requires 'date'.
3. check_file_health in wiki.py does not emit technical debt leakage warnings in general profile.
4. migration.py uses active schema location_to_type and provides migration defaults for topic, context, log.
5. pyyaml is a direct package dependency.
"""

from pathlib import Path
import pytest

from brain79.config import set_project_root
from brain79.core.frontmatter import (
    autofill_deterministic_fields,
    clear_schema_cache,
    load_active_schema,
    parse_frontmatter,
)
from brain79.core.handoff import write_handoff
from brain79.core.init_project import init_project
from brain79.core.migration import migrate_wiki
from brain79.core.wiki import check_file_health
from brain79.server import brain79_handoff_write


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_schema_cache()


def test_handoff_supports_general_profile_session_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hole 1: In a project with profile: general, session_type 'work' or 'writing' must succeed."""
    init_project(tmp_path, install_git_hooks_flag=False, profile="general")
    monkeypatch.chdir(tmp_path)
    set_project_root(tmp_path)
    clear_schema_cache()

    # Core write_handoff should succeed
    path = write_handoff(
        session_type="work",
        summary="Conducted market research and qualitative analysis.",
        previous_handoff_ref="none",
        completed_work=["Interviewed 5 users"],
        pending_work=["Synthesize notes"],
        boot_instruction="Review notes in topics/",
    )
    assert path.startswith("handoffs/")

    # Server tool brain79_handoff_write should also succeed
    result = brain79_handoff_write(
        session_type="writing",
        summary="Drafted executive summary.",
        previous_handoff_ref=path,
        completed_work=["First draft written"],
        pending_work=["Grammar pass"],
        boot_instruction="Review draft",
        wiki_deviation_justification="Drafting phase exploratory writing",
    )
    assert "Handoff successfully saved" in result


def test_autofill_preserves_tags_and_autofills_date_for_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hole 2: autofill must preserve tags on topic and autofill date on log."""
    init_project(tmp_path, install_git_hooks_flag=False, profile="general")
    monkeypatch.chdir(tmp_path)
    set_project_root(tmp_path)
    clear_schema_cache()

    schema = load_active_schema(tmp_path / ".brain-79")

    # Topic with tags
    topic_meta = {
        "type": "topic",
        "summary": "AI Memory and Cognitive Architectures",
        "tags": ["ai", "memory"],
    }
    filled_topic = autofill_deterministic_fields(
        topic_meta, "topics/memory.md", body="Body text", schema=schema
    )
    assert "tags" in filled_topic
    assert filled_topic["tags"] == ["ai", "memory"]

    # Log missing date
    log_meta = {
        "type": "log",
        "summary": "Completed Milestone 1",
    }
    filled_log = autofill_deterministic_fields(
        log_meta, "log/milestone-1.md", body="Log entry", schema=schema
    )
    assert "date" in filled_log
    assert filled_log["date"]  # Should be ISO today date


def test_check_file_health_skips_tech_debt_in_general_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hole 3: check_file_health in wiki.py must not warn on TODO/tech debt in general profile."""
    init_project(tmp_path, install_git_hooks_flag=False, profile="general")
    monkeypatch.chdir(tmp_path)
    set_project_root(tmp_path)
    clear_schema_cache()

    wiki_root = tmp_path / ".brain-79"
    content = (
        "---\n"
        "type: topic\n"
        "summary: Notes with todo item\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Project Ideas\n\n"
        "## Technical Debt\n"
        "- TD-01: Need to reorganize paper index.\n"
    )
    warnings = check_file_health(wiki_root, "topics/ideas.md", content)
    assert not any("Technical debt" in w for w in warnings)


def test_migration_supports_general_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hole 4: migrate_wiki infers topic, context, and log in a general profile wiki."""
    init_project(tmp_path, install_git_hooks_flag=False, profile="general")
    monkeypatch.chdir(tmp_path)
    set_project_root(tmp_path)
    clear_schema_cache()

    wiki_root = tmp_path / ".brain-79"

    # Create unformatted articles in topics/ and log/
    topic_file = wiki_root / "topics" / "unformatted.md"
    topic_file.write_text("# Unformatted Topic\n\nNotes about topic.\n", encoding="utf-8")

    log_file = wiki_root / "log" / "entry.md"
    log_file.write_text("# Weekly Log\n\nThis week we completed user interviews.\n", encoding="utf-8")

    report = migrate_wiki(wiki_root, dry_run=False)
    assert "topics/unformatted.md" in report
    assert "log/entry.md" in report

    # Verify frontmatter was correctly populated
    meta_topic, _ = parse_frontmatter(topic_file.read_text(encoding="utf-8"))
    assert meta_topic["type"] == "topic"
    assert "summary" in meta_topic

    meta_log, _ = parse_frontmatter(log_file.read_text(encoding="utf-8"))
    assert meta_log["type"] == "log"
    assert "date" in meta_log
