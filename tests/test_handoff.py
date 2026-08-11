from pathlib import Path

import pytest

from brain79.config import set_project_root
from brain79.core import handoff as handoff_ops
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
    assert msg1.startswith("handoffs/handoff-")
    assert "**Tipo de sesión:** feature" in read_handoff("latest")[0]

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
    assert msg2.startswith("handoffs/handoff-")
    assert "**Tipo de sesión:** bugfix" in read_handoff("latest")[0]


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
    assert msg.startswith("handoffs/handoff-")


def test_handoff_absent() -> None:
    with pytest.raises(FileNotFoundError):
        read_handoff("latest")
    with pytest.raises(FileNotFoundError):
        read_handoff("none")
    with pytest.raises(FileNotFoundError):
        read_handoff("")


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
    latest_content, latest_promo = read_handoff("latest")
    none_content, none_promo = read_handoff("none")
    empty_content, empty_promo = read_handoff("")

    assert "First session" in latest_content
    assert latest_content == none_content
    assert latest_content == empty_content
    assert latest_promo is False


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
    # save_msg is relative path e.g. "handoffs/handoff-2024-01-01-120000-123.md"
    rel_path = save_msg.split("handoffs/")[1]  # "handoff-2024-01-01-120000-123.md"
    full_stem = rel_path[:-3]  # "handoff-2024-01-01-120000-123"

    # Test reading with exact stem
    content_full, _ = read_handoff(full_stem)
    assert "Partial timestamp test" in content_full

    # Test reading with partial timestamp stem (omitting ms e.g. "2024-01-01-120000" part)
    # Stem is "handoff-YYYY-MM-DD-HHMMSS-mmm" -> prefix up to HHMMSS is 26 chars long
    partial_ts = full_stem[8:25]  # "YYYY-MM-DD-HHMMSS"
    content_partial, _ = read_handoff(partial_ts)
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
    assert write_msg.startswith("handoffs/handoff-")


    content, has_promo = read_handoff("latest")
    assert "=== Handoff: handoffs/handoff-" in content
    assert "**Tipo de sesión:** feature" in content
    assert "Initial session summary" in content
    assert "Completed feature X" in content
    assert "Complete feature Y" in content
    assert "Learned Z" in content
    assert "https://example.com" in content
    assert "Avoid W" in content
    assert "Continue with feature Y" in content
    assert has_promo is True


def test_knowledge_promotion_trigger() -> None:
    from brain79.server import brain79_handoff_read

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
    content, has_promo = read_handoff("latest")
    assert has_promo is True
    assert "ATENCIÓN:" not in content

    # Check MCP tool injects the warning
    mcp_output = brain79_handoff_read("latest")
    assert "ATENCIÓN:" in mcp_output
    assert "brain79_ingest" in mcp_output


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
    content, _ = read_handoff("latest")
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
    content, _ = read_handoff("latest")
    assert "Desviación de la wiki" not in content


# --- purge_handoffs tests ---


def test_purge_handoffs_dry_run_default(setup_wiki_root: Path) -> None:
    """Default is dry-run; files are NOT deleted."""
    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-2026-08-10-200321-173.md").write_text("# H1", encoding="utf-8")
    (handoffs_dir / "handoff-2026-08-10-201816-035.md").write_text("# H2", encoding="utf-8")

    result = handoff_ops.purge_handoffs(wiki_root, apply=False)
    assert "DRY RUN" in result
    assert "Would delete 2 files" in result
    # Files still exist
    assert (handoffs_dir / "handoff-2026-08-10-200321-173.md").exists()
    assert (handoffs_dir / "handoff-2026-08-10-201816-035.md").exists()


def test_purge_handoffs_apply_deletes_all(setup_wiki_root: Path) -> None:
    """apply=True deletes all handoff files."""
    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-A.md").write_text("# A", encoding="utf-8")
    (handoffs_dir / "handoff-B.md").write_text("# B", encoding="utf-8")
    (handoffs_dir / "handoff-C.md").write_text("# C", encoding="utf-8")

    result = handoff_ops.purge_handoffs(wiki_root, apply=True)
    assert "APPLIED" in result
    assert "Deleted 3 files" in result
    # Files are gone
    assert not (handoffs_dir / "handoff-A.md").exists()
    assert not (handoffs_dir / "handoff-B.md").exists()
    assert not (handoffs_dir / "handoff-C.md").exists()


def test_purge_handoffs_no_handoffs_dir(setup_wiki_root: Path) -> None:
    """If handoffs/ doesn't exist, return clean message."""
    import shutil

    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    if handoffs_dir.exists():
        shutil.rmtree(handoffs_dir)
    result = handoff_ops.purge_handoffs(wiki_root, apply=False)
    assert "No handoffs directory found" in result




def test_purge_handoffs_empty_dir(setup_wiki_root: Path) -> None:
    """If handoffs/ exists but is empty (only .gitkeep), return clean message."""
    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / ".gitkeep").write_text("", encoding="utf-8")
    result = handoff_ops.purge_handoffs(wiki_root, apply=False)
    assert "Handoffs directory is already empty" in result


def test_purge_handoffs_unregisters_navigation(setup_wiki_root: Path) -> None:
    """Purge removes entries from .navigation_registry.json."""
    from brain79.core.navigation import load_registry, register_article

    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-X.md").write_text("# X", encoding="utf-8")

    register_article(wiki_root, "handoffs/handoff-X.md", "Handoff X", "Sum", "handoffs")
    register_article(wiki_root, "features/y.md", "Feature Y", "Sum", "features")

    handoff_ops.purge_handoffs(wiki_root, apply=True)

    registry = load_registry(wiki_root)
    paths = [a["path"] for a in registry["articles"]]
    assert "handoffs/handoff-X.md" not in paths
    assert "features/y.md" in paths  # not touched


def test_purge_handoffs_does_not_touch_raw(setup_wiki_root: Path) -> None:
    """Purge does NOT delete files in _raw/."""
    wiki_root = setup_wiki_root / ".brain-79"
    raw_sessions = wiki_root / "_raw" / "sessions"
    raw_sessions.mkdir(parents=True, exist_ok=True)
    raw_file = raw_sessions / "session-2026-08-10.md"
    raw_file.write_text("# Raw session", encoding="utf-8")

    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-A.md").write_text("# H", encoding="utf-8")

    handoff_ops.purge_handoffs(wiki_root, apply=True)

    assert raw_file.exists()  # _raw untouched


def test_purge_handoffs_deletes_lock_files(setup_wiki_root: Path) -> None:
    """Purge deletes ALL files in handoffs/ (including stale .lock files)."""
    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-A.md").write_text("# A", encoding="utf-8")
    lock = handoffs_dir / "handoff-B.md.lock"
    lock.write_text("", encoding="utf-8")

    handoff_ops.purge_handoffs(wiki_root, apply=True)

    assert not lock.exists()  # .lock files ARE deleted
    assert not (handoffs_dir / "handoff-A.md").exists()


def test_purge_handoffs_preserves_gitkeep(setup_wiki_root: Path) -> None:
    """Purge does NOT delete .gitkeep (keeps the directory in git tracking)."""
    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-A.md").write_text("# A", encoding="utf-8")
    gitkeep = handoffs_dir / ".gitkeep"
    gitkeep.write_text("", encoding="utf-8")

    handoff_ops.purge_handoffs(wiki_root, apply=True)

    assert gitkeep.exists()  # .gitkeep IS preserved
    assert not (handoffs_dir / "handoff-A.md").exists()


def test_purge_handoffs_leaves_dir_empty_except_gitkeep(setup_wiki_root: Path) -> None:
    """End state: handoffs/ contains only .gitkeep."""
    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-1.md").write_text("# 1", encoding="utf-8")
    (handoffs_dir / "handoff-2.md.lock").write_text("", encoding="utf-8")
    (handoffs_dir / ".gitkeep").write_text("", encoding="utf-8")

    handoff_ops.purge_handoffs(wiki_root, apply=True)

    remaining = list(handoffs_dir.iterdir())
    assert len(remaining) == 1
    assert remaining[0].name == ".gitkeep"


def test_purge_handoffs_idempotent(setup_wiki_root: Path) -> None:
    """Running purge twice is safe (second run reports directory is empty)."""
    wiki_root = setup_wiki_root / ".brain-79"
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-A.md").write_text("# A", encoding="utf-8")
    (handoffs_dir / ".gitkeep").write_text("", encoding="utf-8")

    handoff_ops.purge_handoffs(wiki_root, apply=True)
    result = handoff_ops.purge_handoffs(wiki_root, apply=True)

    assert "Handoffs directory is already empty" in result


