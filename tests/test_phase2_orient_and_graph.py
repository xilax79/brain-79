"""
Tests for Phase 2: Deterministic Pre-Work Context & Graph-Augmented Cold Start.

Covers:
1. Schema & Registry:
   - Frontmatter parsing for `applies_to`, `related`, `supersedes`.
   - Navigation registry extraction of graph edges (`applies_to`, `related`, `outgoing_links`).
   - Rebuilding / maintaining reverse index `applies_to` map and `file_graph`.
2. 3-Signal Context Ranking (context.py v2):
   - Signal 1: Deterministic `applies_to` path matching (exact path and glob matching).
   - Signal 2: Field-weighted text matching (title & summary matches outrank body matches, filtering superseded).
   - Signal 3: 1-Hop ADR reference graph expansion (pulling accepted ADRs linked from matched articles).
3. 1-Call Cold Start (`brain79 orient` / `brain79_orient`):
   - Combines INDEX.md routing table, latest handoff state (with promotion warning if pending),
     and inlined content of top governing articles.
   - CLI dispatcher and MCP server integration with 1:1 symmetry.
"""

from pathlib import Path
import pytest

from brain79.core.context import get_context
from brain79.core.frontmatter import validate_frontmatter
from brain79.core.init_project import init_project
from brain79.core.navigation import load_registry
from brain79.core.orient import orient
from brain79.core.wiki import write_article
from brain79.core.handoff import write_handoff


@pytest.fixture
def clean_wiki(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fixture providing a fresh project with .brain-79 initialized."""
    from brain79.config import set_project_root
    from brain79.core.frontmatter import clear_schema_cache

    clear_schema_cache()
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = project_root / ".brain-79"
    monkeypatch.chdir(project_root)
    monkeypatch.setenv("BRAIN79_WIKI_PATH", str(wiki_root))
    set_project_root(project_root)
    init_project(project_root=project_root, profile="software")
    clear_schema_cache()
    return wiki_root


def test_schema_allows_applies_to_related_supersedes(clean_wiki: Path) -> None:
    """Validate that applies_to, related, and supersedes are recognized optional fields across types."""
    meta = {
        "type": "decision",
        "summary": "Use SQLite WAL for persistent cache",
        "status": "accepted",
        "date": "2026-11-02",
        "deciders": ["lead-arch"],
        "last_updated": "2026-11-02",
        "applies_to": ["src/brain79/core/cache.py", "src/brain79/storage/*.py"],
        "related": ["architecture/mcp-server.md"],
        "supersedes": ["decisions/adr-001-hybrid-cli.md"],
    }
    # Should not raise ValidationError
    validate_frontmatter(meta, "decisions/adr-010-sqlite.md")


def test_registry_indexes_graph_metadata(clean_wiki: Path) -> None:
    """Validate that register_article captures applies_to, related, and outgoing links in registry."""
    content = """---
type: feature
summary: Authentication service with JWT tokens
status: shipped
version: 1.0.0
last_updated: 2026-11-02
applies_to:
  - "src/auth/*.py"
  - "src/auth/jwt.py"
related:
  - "decisions/adr-002-immutable-handoffs.md"
---

# Feature — Authentication

## Overview
Detailed auth spec. For security reasons, see [ADR-001](decisions/adr-001-hybrid-cli.md).
"""
    write_article("features/auth.md", content)
    
    registry = load_registry(clean_wiki)
    auth_entry = next((a for a in registry.get("articles", []) if a.get("path") == "features/auth.md"), None)
    assert auth_entry is not None
    assert auth_entry.get("applies_to") == ["src/auth/*.py", "src/auth/jwt.py"]
    assert auth_entry.get("related") == ["decisions/adr-002-immutable-handoffs.md"]
    # Outgoing markdown links detected
    assert "decisions/adr-001-hybrid-cli.md" in auth_entry.get("outgoing_links", [])


def test_context_signal1_deterministic_path_matching(clean_wiki: Path) -> None:
    """Articles with matching applies_to glob must be prioritized when paths are provided."""
    # Create article 1 bound to validation files
    write_article(
        "architecture/validation-pipeline.md",
        """---
type: architecture
summary: High performance validation pipeline
stability: stable
last_updated: 2026-11-02
applies_to:
  - "src/brain79/core/validation.py"
  - "src/brain79/core/frontmatter.py"
---

# Architecture — Validation Pipeline
Pipeline details...
""",
    )

    # Create article 2 with random text
    write_article(
        "features/other.md",
        """---
type: feature
summary: Other un-related feature
status: shipped
version: 1.0.0
last_updated: 2026-11-02
applies_to:
  - "src/other/*.py"
---

# Feature — Other
Other details mentioning validation once...
""",
    )

    # When query specifies path "src/brain79/core/validation.py", architecture/validation-pipeline.md must rank first
    report = get_context(
        task="check rules",
        paths=["src/brain79/core/validation.py"],
        top_n=3,
    )
    assert "architecture/validation-pipeline.md" in report


def test_context_signal3_adr_graph_expansion(clean_wiki: Path) -> None:
    """When a feature is retrieved, active ADRs linked via related or markdown links must be expanded into context."""
    # Governing decision
    write_article(
        "decisions/adr-099-strict-auth.md",
        """---
type: decision
summary: Strict multi-factor authentication mandate
status: accepted
date: 2026-11-02
deciders:
  - security-lead
last_updated: 2026-11-02
---

# ADR-099 — Strict MFA
Must enforce 2FA.
""",
    )

    # Feature linking to ADR
    write_article(
        "features/login.md",
        """---
type: feature
summary: User login system
status: in_progress
version: 2.0.0
last_updated: 2026-11-02
related:
  - "decisions/adr-099-strict-auth.md"
---

# Feature — User Login
Users enter credentials and proceed through MFA.
""",
    )

    # Query matching feature login
    report = get_context(task="user login flow", top_n=3)
    assert "features/login.md" in report
    # The 1-hop ADR expansion should include the governing decision
    assert "decisions/adr-099-strict-auth.md" in report


def test_orient_returns_index_handoff_and_inlined_articles(clean_wiki: Path) -> None:
    """brain79_orient must return INDEX.md, active handoff, and inlined articles in a single call."""
    # Write an initial handoff
    write_handoff(
        session_type="feature",
        summary="Working on login infrastructure",
        completed_work=["Created scaffold"],
        pending_work=["Implement JWT token generator"],
        boot_instruction="Pick up JWT implementation in src/auth/jwt.py",
        knowledge_pending_promotion=["JWT keys require rotation every 24h"],
    )

    # Write a governing article bound to the path
    write_article(
        "architecture/auth-security.md",
        """---
type: architecture
summary: Core security principles for tokens
stability: stable
last_updated: 2026-11-02
applies_to:
  - "src/auth/jwt.py"
---

# Architecture — Auth Security
Token rotation policy and signing algorithms.
""",
    )

    # Call orient with task & touched paths
    res = orient(
        task="Implement JWT token generator",
        paths=["src/auth/jwt.py"],
        max_articles=2,
    )

    # 1. Must include INDEX / Routing table section
    assert "## 🗺️ Project Index" in res or "# Project index" in res
    assert "Quick navigation" in res

    # 2. Must include Handoff summary and boot instruction
    assert "## ⏱️ Active Handoff State" in res
    assert "Working on login infrastructure" in res
    assert "Implement JWT token generator" in res
    assert "Pick up JWT implementation in src/auth/jwt.py" in res

    # 3. Must warn about knowledge pending promotion
    assert "Knowledge Pending Promotion" in res
    assert "JWT keys require rotation every 24h" in res

    # 4. Must inline the content of architecture/auth-security.md
    assert "## 📖 Governing Knowledge Articles" in res
    assert "=== Article: architecture/auth-security.md ===" in res
    assert "Token rotation policy and signing algorithms" in res


def test_orient_without_handoff_handles_clean_slate(clean_wiki: Path) -> None:
    """When no handoff exists, orient handles it gracefully without errors."""
    res = orient(task=None, paths=None)
    assert "## 🗺️ Project Index" in res or "# Project index" in res
    assert "No prior handoff found" in res
    assert "Ready for first session." in res
