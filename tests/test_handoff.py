from pathlib import Path

import pytest

from brain79.config import set_project_root
from brain79.core.handoff import _normalize_list, read_handoff, write_handoff
from brain79.core.init_project import init_project


@pytest.fixture(autouse=True)
def setup_wiki_root(tmp_path: Path) -> Path:
    """Set project root to a temporary directory with initialized wiki for each test."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_normalize_list() -> None:
    raw = ["  item1 ", "None", "none", "", "  ", "item2"]
    normalized = _normalize_list(raw)
    assert normalized == ["item1", "item2"]
    assert _normalize_list([]) == []


def test_invalid_session_type() -> None:
    with pytest.raises(ValueError, match="Invalid session_type"):
        write_handoff(
            session_type="invalid_type",
            previous_handoff_ref="",
            summary="Test summary",
            completed_work=["Task 1"],
            pending_work=["Task 2"],
            knowledge_pending_promotion=[],
            resources=[],
            gotchas=[],
            boot_instruction="Execute next step",
        )


def test_session_type_whitespace_and_case_tolerance() -> None:
    msg1 = write_handoff(
        session_type="  FEATURE ",
        previous_handoff_ref="",
        summary="Whitespace tolerance test",
        completed_work=["Task 1"],
        pending_work=["Task 2"],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="Execute next step",
    )
    assert "Handoff successfully saved" in msg1
    assert "**Tipo de sesión:** feature" in read_handoff("latest")

    msg2 = write_handoff(
        session_type="BugFix",
        previous_handoff_ref="",
        summary="Mixed case test",
        completed_work=["Task 1"],
        pending_work=["Task 2"],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="Execute next step",
    )
    assert "Handoff successfully saved" in msg2
    assert "**Tipo de sesión:** bugfix" in read_handoff("latest")


def test_empty_summary_raises_error() -> None:
    with pytest.raises(ValueError, match="summary cannot be empty"):
        write_handoff(
            session_type="feature",
            previous_handoff_ref="",
            summary="   ",
            completed_work=["Task 1"],
            pending_work=["Task 2"],
            knowledge_pending_promotion=[],
            resources=[],
            gotchas=[],
            boot_instruction="Execute next step",
        )


def test_missing_ref() -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        write_handoff(
            session_type="feature",
            previous_handoff_ref="nonexistent-ref",
            summary="Test summary",
            completed_work=["Task 1"],
            pending_work=["Task 2"],
            knowledge_pending_promotion=[],
            resources=[],
            gotchas=[],
            boot_instruction="Execute next step",
        )


def test_empty_boot_instruction_hallucination() -> None:
    with pytest.raises(ValueError, match="boot_instruction cannot be empty"):
        write_handoff(
            session_type="feature",
            previous_handoff_ref="",
            summary="Test summary",
            completed_work=["Task 1"],
            pending_work=[],
            knowledge_pending_promotion=[],
            resources=[],
            gotchas=[],
            boot_instruction="   ",
        )

    with pytest.raises(ValueError, match="hallucinates next steps"):
        write_handoff(
            session_type="feature",
            previous_handoff_ref="",
            summary="Test summary",
            completed_work=["Task 1"],
            pending_work=[],
            knowledge_pending_promotion=[],
            resources=[],
            gotchas=[],
            boot_instruction="Do something next",
        )

    # Valid boot_instruction when pending_work is empty
    msg = write_handoff(
        session_type="feature",
        previous_handoff_ref="",
        summary="Test summary",
        completed_work=["Task 1"],
        pending_work=[],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="No hay tareas pendientes por hacer.",
    )
    assert "Handoff successfully saved" in msg


def test_handoff_absent() -> None:
    assert read_handoff("latest") == "No handoffs saved yet."
    assert read_handoff("none") == "No handoffs saved yet."
    assert read_handoff("") == "No handoffs saved yet."


def test_read_handoff_none_aliases_to_latest() -> None:
    write_handoff(
        session_type="feature",
        previous_handoff_ref="",
        summary="First session",
        completed_work=["Work 1"],
        pending_work=["Work 2"],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="Execute next step",
    )
    latest_content = read_handoff("latest")
    none_content = read_handoff("none")
    empty_content = read_handoff("")

    assert "First session" in latest_content
    assert latest_content == none_content
    assert latest_content == empty_content


def test_read_handoff_with_full_and_partial_timestamp() -> None:
    save_msg = write_handoff(
        session_type="research",
        previous_handoff_ref="",
        summary="Partial timestamp test",
        completed_work=["Task A"],
        pending_work=["Task B"],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="Execute step",
    )
    # Extract relative path from return message (e.g. "handoffs/handoff-2024-01-01-120000-123.md")
    rel_path = save_msg.split("handoffs/")[1]  # "handoff-2024-01-01-120000-123.md"
    full_stem = rel_path[:-3]  # "handoff-2024-01-01-120000-123"

    # Test reading with exact stem
    content_full = read_handoff(full_stem)
    assert "Partial timestamp test" in content_full

    # Test reading with partial timestamp stem (omitting ms e.g. "2024-01-01-120000" part)
    # Stem is "handoff-YYYY-MM-DD-HHMMSS-mmm" -> prefix up to HHMMSS is 26 chars long
    partial_ts = full_stem[8:25]  # "YYYY-MM-DD-HHMMSS"
    content_partial = read_handoff(partial_ts)
    assert "Partial timestamp test" in content_partial


def test_round_trip() -> None:
    write_msg = write_handoff(
        session_type="feature",
        previous_handoff_ref="",
        summary="Initial session summary",
        completed_work=["Completed feature X"],
        pending_work=["Complete feature Y"],
        knowledge_pending_promotion=["Learned Z"],
        resources=["https://example.com"],
        gotchas=["Avoid W"],
        boot_instruction="Continue with feature Y",
    )
    assert "Handoff successfully saved" in write_msg

    content = read_handoff("latest")
    assert "=== Handoff: handoffs/handoff-" in content
    assert "**Tipo de sesión:** feature" in content
    assert "Initial session summary" in content
    assert "Completed feature X" in content
    assert "Complete feature Y" in content
    assert "Learned Z" in content
    assert "https://example.com" in content
    assert "Avoid W" in content
    assert "Continue with feature Y" in content


def test_knowledge_promotion_trigger() -> None:
    write_handoff(
        session_type="research",
        previous_handoff_ref="",
        summary="Research notes",
        completed_work=[],
        pending_work=["Task"],
        knowledge_pending_promotion=["Crucial architectural insight"],
        resources=[],
        gotchas=[],
        boot_instruction="Implement insight",
    )
    content = read_handoff("latest")
    assert "ATENCIÓN:" in content
    assert "brain79_ingest" in content


def test_wiki_deviation_section_renders() -> None:
    write_handoff(
        session_type="bugfix",
        previous_handoff_ref="",
        summary="Temporary workaround",
        completed_work=["Patched bug"],
        pending_work=["Fix root cause"],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="Investigate root cause",
        wiki_deviation_justification="Deviating from schema due to hotfix requirements.",
    )
    content = read_handoff("latest")
    assert "## ⚠️ Desviación de la wiki (Temporal)" in content
    assert "Deviating from schema due to hotfix requirements." in content


def test_wiki_deviation_section_skipped() -> None:
    write_handoff(
        session_type="bugfix",
        previous_handoff_ref="",
        summary="Standard fix",
        completed_work=["Patched bug"],
        pending_work=["Add tests"],
        knowledge_pending_promotion=[],
        resources=[],
        gotchas=[],
        boot_instruction="Add tests",
        wiki_deviation_justification="",
    )
    content = read_handoff("latest")
    assert "Desviación de la wiki" not in content
