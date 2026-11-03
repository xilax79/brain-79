"""Adversarial test suite for Phase 3: Zero-Turn Session Execution.

Tests all 6 adversarial defects:
- Defect 1: Rupture of atomicity / partial commit in session_commit when handoff has invalid boot_instruction or non-existent lineage.
- Defect 2: ADR hints contaminating pure read_article callers and creating write contamination.
- Defect 3: Code fences inside Markdown documents causing premature H1 / H2 section splitting in extract_sections_from_markdown.
- Defect 4: Conflict resolution when session_commit contains writes and edits on the same path, or edits on newly created files.
- Defect 5: wiki_root parameter propagation in commit_session across all phases.
- Defect 6: Empty session_commit ({}) returning success and dirtying INDEX.md.
"""

from collections.abc import Generator
from pathlib import Path
from typing import Any
import pytest

from brain79.config import set_project_root
from brain79.core.frontmatter import ValidationError, clear_schema_cache
from brain79.core.init_project import init_project
from brain79.core.session_commit import commit_session
from brain79.core.wiki import (
    extract_sections_from_markdown,
    read_article,
    write_article,
)


@pytest.fixture(autouse=True)
def clean_project(tmp_path: Path) -> Generator[Path, None, None]:
    """Set up fresh project for each test."""
    set_project_root(tmp_path)
    clear_schema_cache()
    init_project(tmp_path, profile="software")
    yield tmp_path
    set_project_root(None)
    clear_schema_cache()


# ============================================================================
# Defect 1: Full Handoff Validation in Pre-Flight (True Atomicity)
# ============================================================================

def test_defect_1_boot_instruction_anti_hallucination_preflight_rollback(clean_project: Path) -> None:
    """If boot_instruction hallucinates pending work when pending_work is empty, zero files hit disk."""
    payload = {
        "session_summary": "Should be rolled back",
        "writes": [
            {
                "path": "features/auth.md",
                "content": """---
type: feature
summary: Authentication
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Auth Feature
""",
            }
        ],
        "handoff": {
            "session_type": "feature",
            "summary": "Completed feature",
            "completed_work": ["Auth"],
            "pending_work": [],  # Empty pending work!
            # Hallucinating next steps without stating "no pending tasks"
            "boot_instruction": "Continue implementing the payments gateway in payments.py",
        },
    }

    with pytest.raises((ValueError, ValidationError)):
        commit_session(payload)

    # ZERO files must exist on disk!
    assert not (clean_project / ".brain-79" / "features" / "auth.md").exists()
    raw_sessions = list((clean_project / ".brain-79" / "_raw" / "sessions").glob("*.md"))
    assert len(raw_sessions) == 0
    handoffs = list((clean_project / ".brain-79" / "handoffs").glob("*.md"))
    assert len(handoffs) == 0


def test_defect_1_invalid_lineage_preflight_rollback(clean_project: Path) -> None:
    """If previous_handoff_ref points to a non-existent ref, pre-flight aborts before writes."""
    payload = {
        "session_summary": "Should be rolled back",
        "writes": [
            {
                "path": "features/auth.md",
                "content": """---
type: feature
summary: Authentication
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Auth Feature
""",
            }
        ],
        "handoff": {
            "session_type": "feature",
            "previous_handoff_ref": "handoff-nonexistent-12345",
            "summary": "Completed feature",
            "completed_work": ["Auth"],
            "pending_work": [],
            "boot_instruction": "No pending tasks.",
        },
    }

    with pytest.raises((FileNotFoundError, ValueError, ValidationError)):
        commit_session(payload)

    assert not (clean_project / ".brain-79" / "features" / "auth.md").exists()


# ============================================================================
# Defect 2: Pure read_article() and Non-Polluting ADR Hints
# ============================================================================

def test_defect_2_read_article_returns_pure_content_by_default() -> None:
    """read_article() must return exact content without appending ADR hints unless requested."""
    write_article(
        "decisions/adr-001.md",
        """---
type: decision
summary: Decision 1
status: accepted
date: 2026-11-02
deciders: [test]
last_updated: 2026-11-02
---

# ADR-001 — Decision 1
""",
    )
    original_text = """---
type: architecture
summary: Core architecture
stability: stable
related:
  - decisions/adr-001.md
last_updated: 2026-11-02
---

# Core Architecture

## Overview
Content referencing [ADR-001](../decisions/adr-001.md).

---

[← Volver al Índice](../INDEX.md)
"""
    write_article("architecture/core.md", original_text)

    # Pure read
    content = read_article("architecture/core.md")
    assert "💡 Linked ADRs:" not in content
    # Read-Modify-Write cycle does not accumulate junk
    write_article("architecture/core.md", content)
    saved = read_article("architecture/core.md")
    assert "💡 Linked ADRs:" not in saved

    # Explicit opt-in for presentation/tools
    content_with_hints = read_article("architecture/core.md", include_adr_hints=True)
    assert "💡 Linked ADRs: decisions/adr-001.md" in content_with_hints


def test_defect_2_adr_hints_filters_superseded_and_self_links() -> None:
    """ADR hints must filter out superseded ADRs and avoid self-referencing when reading an ADR."""
    write_article(
        "decisions/adr-old.md",
        """---
type: decision
summary: Old Decision
status: superseded
date: 2026-11-02
deciders: [test]
last_updated: 2026-11-02
---

# ADR-Old
""",
    )
    write_article(
        "features/feature_a.md",
        """---
type: feature
summary: Feature A
status: shipped
version: 1.0.0
related:
  - decisions/adr-old.md
last_updated: 2026-11-02
---

# Feature A
Content linking to [Old ADR](../decisions/adr-old.md).
""",
    )

    res = read_article("features/feature_a.md", include_adr_hints=True)
    # Since adr-old is superseded, it should NOT be promoted as an active governing ADR hint
    assert "💡 Linked ADRs:" not in res


# ============================================================================
# Defect 3: Code Fence Masking in extract_sections_from_markdown
# ============================================================================

def test_defect_3_code_fences_do_not_split_sections() -> None:
    """Headings like '# Full comment' or '## Example' inside code fences must NOT split sections."""
    doc = """---
type: architecture
summary: Code fence test
stability: stable
last_updated: 2026-11-02
---

# Architecture With Code

## Overview
Here is code that mentions headers:

```python
# This is a Python comment that starts with hash space!
def foo():
    pass
## This is another comment
```

Still in Overview section!

## Second Section
Content of second section.
"""
    extracted = extract_sections_from_markdown(doc, ["Overview"])
    assert "## Overview" in extracted
    assert "Still in Overview section!" in extracted
    assert "def foo():" in extracted
    assert "## Second Section" not in extracted


# ============================================================================
# Defect 4: Virtual FS in session_commit for Overlapping Writes and Edits
# ============================================================================

def test_defect_4_session_commit_handles_write_then_edit_same_path() -> None:
    """A commit creating an article in 'writes' and subsequently modifying it in 'edits' must succeed atomically."""
    payload = {
        "session_summary": "Create and patch feature",
        "writes": [
            {
                "path": "features/new_tool.md",
                "content": """---
type: feature
summary: New tool
status: planned
version: 1.0.0
last_updated: 2026-11-02
---

# New Tool

## Setup
Initial placeholder setup.
""",
            }
        ],
        "edits": [
            {
                "path": "features/new_tool.md",
                "edits": [
                    {
                        "old_text": "Initial placeholder setup.",
                        "new_text": "Final calibrated setup instructions.",
                    }
                ],
            }
        ],
        "handoff": {
            "session_type": "feature",
            "summary": "Done",
            "completed_work": ["Setup tool"],
            "pending_work": [],
            "boot_instruction": "No pending tasks.",
        },
    }

    receipt = commit_session(payload)
    assert receipt["success"] is True

    final_content = read_article("features/new_tool.md")
    assert "Final calibrated setup instructions." in final_content
    assert "Initial placeholder setup." not in final_content


# ============================================================================
# Defect 5: wiki_root Propagation Across All session_commit Phases
# ============================================================================

def test_defect_5_session_commit_propagates_custom_wiki_root(tmp_path: Path) -> None:
    """When a custom wiki_root is provided, all writes, logs, and handoffs hit custom_wiki_root, NOT global."""
    other_project = tmp_path / "other-project"
    other_project.mkdir()
    init_project(other_project, profile="general")
    c_w_root = other_project / ".brain-79"

    payload = {
        "session_summary": "Custom root session",
        "writes": [
            {
                "path": "context/custom.md",
                "content": """---
type: context
summary: Custom context
last_updated: 2026-11-02
---

# Custom Context
""",
            }
        ],
        "handoff": {
            "session_type": "work",  # Valid in general profile!
            "summary": "General handoff",
            "completed_work": ["Work"],
            "pending_work": [],
            "boot_instruction": "No pending tasks.",
        },
    }

    receipt = commit_session(payload, wiki_root=c_w_root)
    assert receipt["success"] is True
    assert (c_w_root / "context" / "custom.md").exists()
    assert (c_w_root / receipt["handoff_path"]).exists()
    assert (c_w_root / receipt["session_raw_path"]).exists()


# ============================================================================
# Defect 6: Empty Transaction Rejection & Zero Navigation Modification
# ============================================================================

def test_defect_6_empty_session_commit_rejected() -> None:
    """Calling session_commit({}) with zero operations raises ValueError and makes zero changes."""
    payload: dict[str, Any] = {}

    with pytest.raises(ValueError) as exc:
        commit_session(payload)

    assert "empty" in str(exc.value).lower()
