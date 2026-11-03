"""Tests for Phase 3: Zero-Turn Session Execution.

Covers:
1. Section-projected extraction in read_article(path, sections=[...]).
2. Multi-article batch reading in read_batch_articles(requests).
3. 1-hop ADR footer hints in read_article and read_batch_articles.
4. Atomic session commit (commit_session) with pre-flight validation,
   all-or-nothing rollback on validation failure, session log ingestion,
   writes, edits, handoff creation, and unified receipt.
5. Strict FastMCP and CLI dispatcher symmetry.
"""

from collections.abc import Generator
from pathlib import Path
from typing import Any
import pytest

from brain79.config import set_project_root
from brain79.core.frontmatter import ValidationError, clear_schema_cache
from brain79.core.init_project import init_project
from brain79.core.wiki import (
    extract_sections_from_markdown,
    read_article,
    read_batch_articles,
    write_article,
)
from brain79.core.session_commit import commit_session


@pytest.fixture(autouse=True)
def clean_project(tmp_path: Path) -> Generator[Path, None, None]:
    """Set up a fresh test project with software ontology for each test."""
    set_project_root(tmp_path)
    clear_schema_cache()
    init_project(tmp_path, profile="software")
    yield tmp_path
    set_project_root(None)
    clear_schema_cache()


# ============================================================================
# 1. Section-Projected Article Reading
# ============================================================================

def test_extract_sections_from_markdown() -> None:
    """Verify section extraction preserves frontmatter, H1 title, and requested H2s."""
    sample = """---
type: architecture
summary: High level architecture
stability: stable
last_updated: 2026-11-02
---

# Architecture Overview

Intro paragraph before any H2.

## Components

Here are the components.
- Subsystem A
- Subsystem B

## Data Flow

Flow description goes here.

## Security

Security guarantees and encryption.
"""
    # 1. Exact match single section
    proj = extract_sections_from_markdown(sample, ["Components"])
    assert "type: architecture" in proj
    assert "# Architecture Overview" in proj
    assert "## Components" in proj
    assert "Subsystem A" in proj
    assert "## Data Flow" not in proj
    assert "## Security" not in proj

    # 2. Case-insensitive and trimmed match with multiple sections
    proj_multi = extract_sections_from_markdown(sample, ["data flow", "  SECURITY  "])
    assert "## Data Flow" in proj_multi
    assert "Flow description goes here." in proj_multi
    assert "## Security" in proj_multi
    assert "## Components" not in proj_multi

    # 3. Requesting non-existent sections returns frontmatter + title with notice
    proj_none = extract_sections_from_markdown(sample, ["NonExistent"])
    assert "# Architecture Overview" in proj_none
    assert "## Components" not in proj_none
    assert "(No matching sections found for: NonExistent)" in proj_none


def test_read_article_with_sections_and_adr_footer() -> None:
    """Verify read_article with sections extracts sections and appends linked ADR hints."""
    # Write an ADR first
    adr_content = """---
type: decision
summary: Testing ADR
status: accepted
date: 2026-11-02
deciders: [tester]
last_updated: 2026-11-02
---

# ADR-099 — Testing ADR

## Context
Context details.
"""
    write_article("decisions/adr-099-test.md", adr_content)

    # Write an article linking to that ADR
    arch_content = """---
type: architecture
summary: Architecture doc linking to ADR
stability: stable
related:
  - decisions/adr-099-test.md
last_updated: 2026-11-02
---

# Architecture Doc

## Section One
Content of section one with [ADR 099](../decisions/adr-099-test.md).

## Section Two
Content of section two.
"""
    write_article("architecture/test-arch.md", arch_content)

    # Read with sections
    res = read_article("architecture/test-arch.md", sections=["Section One"])
    assert "## Section One" in res
    assert "## Section Two" not in res
    assert "💡 Linked ADRs:" in res
    assert "decisions/adr-099-test.md" in res


# ============================================================================
# 2. Batch Article Reading
# ============================================================================

def test_read_batch_articles_basic_and_projected() -> None:
    """Verify read_batch_articles can read full articles and section projections."""
    write_article(
        "features/auth.md",
        """---
type: feature
summary: Auth feature
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Auth Feature

## Overview
Auth overview.

## Endpoints
Login, logout.
""",
    )

    write_article(
        "architecture/core.md",
        """---
type: architecture
summary: Core architecture
stability: stable
last_updated: 2026-11-02
---

# Core Architecture

## Pipeline
Pipeline details.
""",
    )

    requests: list[dict[str, Any]] = [
        {"path": "features/auth.md", "sections": ["Endpoints"]},
        {"path": "architecture/core.md"},
    ]

    res = read_batch_articles(requests)
    assert len(res) == 2
    assert res[0]["path"] == "features/auth.md"
    assert "## Endpoints" in res[0]["content"]
    assert "## Overview" not in res[0]["content"]

    assert res[1]["path"] == "architecture/core.md"
    assert "## Pipeline" in res[1]["content"]


def test_read_batch_articles_missing_file_handling() -> None:
    """Missing files return an error in their batch slot without aborting the rest."""
    write_article(
        "features/auth.md",
        """---
type: feature
summary: Auth feature
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Auth Feature
""",
    )

    requests: list[dict[str, Any]] = [
        {"path": "features/auth.md"},
        {"path": "features/nonexistent.md"},
    ]

    res = read_batch_articles(requests)
    assert len(res) == 2
    assert res[0]["error"] is None
    assert "Auth Feature" in res[0]["content"]

    assert res[1]["content"] is None
    assert "not found" in res[1]["error"].lower()


# ============================================================================
# 3. Atomic Session Commit (commit_session)
# ============================================================================

def test_commit_session_atomic_success(clean_project: Path) -> None:
    """Verify successful atomic commit executes raw log, writes, edits, and handoff."""
    # Write an initial article to edit
    write_article(
        "architecture/system.md",
        """---
type: architecture
summary: System overview
stability: stable
last_updated: 2026-11-02
---

# System Overview

## State
Initial system state.
""",
    )

    payload = {
        "session_summary": "Shipped new authentication subsystem and updated system overview.",
        "writes": [
            {
                "path": "features/auth.md",
                "content": """---
type: feature
summary: User authentication subsystem
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Authentication Subsystem

## Overview
Handles JWT token issuance and revocation.
""",
            }
        ],
        "edits": [
            {
                "path": "architecture/system.md",
                "edits": [
                    {
                        "old_text": "Initial system state.",
                        "new_text": "System state updated with auth subsystem.",
                    }
                ],
            }
        ],
        "handoff": {
            "session_type": "feature",
            "summary": "Completed authentication subsystem implementation.",
            "completed_work": [
                "Implemented JWT issuance",
                "Updated system architecture overview",
            ],
            "pending_work": ["Add rate limiting middleware"],
            "boot_instruction": "Resume by implementing rate limiting middleware.",
        },
    }

    result = commit_session(payload)
    assert result["success"] is True
    assert result["session_raw_path"] is not None
    assert result["handoff_path"] is not None
    assert len(result["written_articles"]) == 1
    assert len(result["edited_articles"]) == 1
    assert result["health_status"] == "ok"

    # Verify disk state
    auth_article = read_article("features/auth.md")
    assert "Authentication Subsystem" in auth_article

    sys_article = read_article("architecture/system.md")
    assert "System state updated with auth subsystem." in sys_article

    # Verify raw session was saved
    raw_file = clean_project / ".brain-79" / result["session_raw_path"]
    assert raw_file.exists()
    assert "Shipped new authentication subsystem" in raw_file.read_text(encoding="utf-8")

    # Verify handoff was created
    handoff_file = clean_project / ".brain-79" / result["handoff_path"]
    assert handoff_file.exists()
    assert "Completed authentication subsystem implementation" in handoff_file.read_text(encoding="utf-8")

    # Verify INDEX.md quick navigation was synchronized
    index_content = read_article("INDEX.md")
    assert "features/auth.md" in index_content
    assert "User authentication subsystem" in index_content


def test_commit_session_preflight_validation_rollback(clean_project: Path) -> None:
    """Verify that if ANY write or edit fails validation, ZERO files are modified on disk."""
    write_article(
        "architecture/system.md",
        """---
type: architecture
summary: System overview
stability: stable
last_updated: 2026-11-02
---

# System Overview

## State
Untouched initial system state.
""",
    )

    # Invalid write: missing required 'summary' and invalid status
    payload = {
        "session_summary": "Attempt with broken article",
        "writes": [
            {
                "path": "features/broken.md",
                "content": """---
type: feature
status: invalid_status_value
version: 1.0.0
---

# Broken Feature
""",
            }
        ],
        "edits": [
            {
                "path": "architecture/system.md",
                "edits": [
                    {
                        "old_text": "Untouched initial system state.",
                        "new_text": "THIS SHOULD NEVER HIT DISK.",
                    }
                ],
            }
        ],
        "handoff": {
            "session_type": "feature",
            "summary": "Attempt handoff",
            "completed_work": ["Nothing"],
            "pending_work": [],
            "boot_instruction": "No work",
        },
    }

    with pytest.raises(ValidationError):
        commit_session(payload)

    # Verify disk was NEVER modified
    broken_file = clean_project / ".brain-79" / "features" / "broken.md"
    assert not broken_file.exists()

    sys_article = read_article("architecture/system.md")
    assert "THIS SHOULD NEVER HIT DISK." not in sys_article
    assert "Untouched initial system state." in sys_article

    # Verify no raw session or handoff was written
    raw_sessions = list((clean_project / ".brain-79" / "_raw" / "sessions").glob("*.md"))
    assert len(raw_sessions) == 0

    handoffs = list((clean_project / ".brain-79" / "handoffs").glob("*.md"))
    assert len(handoffs) == 0


def test_commit_session_anti_hallucination_validation_rollback(clean_project: Path) -> None:
    """Verify handoff validation failures prevent any article write or raw log creation."""
    payload = {
        "session_summary": "Session with bad handoff",
        "writes": [
            {
                "path": "features/test.md",
                "content": """---
type: feature
summary: Valid feature
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Valid Feature
""",
            }
        ],
        "handoff": {
            "session_type": "invalid_session_type",  # Invalid type triggers ValueError
            "summary": "Bad handoff",
            "completed_work": [],
            "pending_work": [],
            "boot_instruction": "instruction",
        },
    }

    with pytest.raises(ValueError) as exc_info:
        commit_session(payload)

    assert "Invalid session_type" in str(exc_info.value)

    # Verify no write occurred
    test_file = clean_project / ".brain-79" / "features" / "test.md"
    assert not test_file.exists()


# ============================================================================
# 4. CLI Symmetry for Phase 3
# ============================================================================

def test_cli_read_sections(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify brain79 read with --sections."""
    write_article(
        "features/cli_test.md",
        """---
type: feature
summary: CLI test
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# CLI Test

## First Section
First content.

## Second Section
Second content.
""",
    )
    from brain79.cli.dispatch import dispatch_cmd

    ret = dispatch_cmd("read", ["features/cli_test.md", "--sections", "Second Section"])
    assert ret == 0
    out = capsys.readouterr().out
    assert "## Second Section" in out
    assert "## First Section" not in out


def test_cli_read_batch(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """Verify brain79 read-batch via JSON input file."""
    write_article(
        "features/b1.md",
        """---
type: feature
summary: Batch 1
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# Batch One
""",
    )
    batch_file = tmp_path / "batch.json"
    batch_file.write_text('[{"path": "features/b1.md"}]', encoding="utf-8")

    from brain79.cli.dispatch import dispatch_cmd

    ret = dispatch_cmd("read-batch", ["--file", str(batch_file)])
    assert ret == 0
    out = capsys.readouterr().out
    assert "Batch One" in out


def test_cli_session_commit(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """Verify brain79 session-commit via JSON input file."""
    payload_file = tmp_path / "commit.json"
    import json

    payload = {
        "session_summary": "CLI session commit test",
        "writes": [
            {
                "path": "features/cli_commit.md",
                "content": """---
type: feature
summary: CLI commit feature
status: shipped
version: 1.0.0
last_updated: 2026-11-02
---

# CLI Commit Feature
""",
            }
        ],
        "handoff": {
            "session_type": "feature",
            "summary": "CLI session commit handoff",
            "completed_work": ["Done"],
            "pending_work": [],
            "boot_instruction": "No pending tasks.",
        },
    }
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    from brain79.cli.dispatch import dispatch_cmd

    ret = dispatch_cmd("session-commit", ["--file", str(payload_file)])
    assert ret == 0
    out = capsys.readouterr().out
    assert "Transaction Committed Successfully" in out
    assert "features/cli_commit.md" in out

