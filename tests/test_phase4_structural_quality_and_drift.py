"""
Unit and integration tests for Phase 4: Structural Article Quality & Deterministic Drift Detection.

Verifies:
1. Automatic backlink footer normalization and idempotent invariant enforcement.
2. Section-level structural schemas, document skeletons, and section validation.
3. Code-to-wiki drift detection via `applies_to` frontmatter against workspace files.
4. Cold start orientation drift warning banners in `brain79_orient`.
5. Organizational linter rules for structural sections, backlinks, and drift.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest

from brain79 import config
from brain79.core.drift import (
    check_article_drift,
    find_matching_workspace_files,
    get_file_last_modified_date,
)
from brain79.core.frontmatter import (
    clear_schema_cache,
    generate_document_skeleton,
    get_schema_documentation,
    load_active_schema,
    normalize_backlink_footer,
)
from brain79.core.lint_organizational import (
    check_article_structural_sections,
    check_documentation_drift,
)
from brain79.core.orient import orient
from brain79.core.session_commit import commit_session
from brain79.core.validation import check_missing_sections, extract_h2_headers
from brain79.core.wiki import check_file_health, edit_article, read_article, write_article, write_many_articles


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    """Create an isolated test project with standard .brain-79 directory structure."""
    clear_schema_cache()
    proj = tmp_path / "project"
    proj.mkdir()
    wiki = proj / ".brain-79"
    wiki.mkdir()
    (wiki / "architecture").mkdir()
    (wiki / "features").mkdir()
    (wiki / "decisions").mkdir()
    (wiki / "product").mkdir()
    (wiki / "handoffs").mkdir()
    (wiki / "_raw").mkdir()

    idx = wiki / "INDEX.md"
    idx.write_text("# Project index\n\n## Quick navigation\n", encoding="utf-8")

    config.set_project_root(proj)
    return proj


# ==============================================================================
# Area 1: Automatic Backlink Footer Normalization & Invariants
# ==============================================================================


def test_backlink_auto_injection_on_write(clean_project: Path) -> None:
    """Writing an article in a subfolder without backlink automatically appends backlink footer."""
    content = """---
type: feature
summary: Authentication subsystem
status: planned
version: 1.0.0
last_updated: 2026-11-03
---

# Authentication Subsystem

## Overview
Handles user auth tokens.
"""
    write_article("features/auth.md", content)
    saved = read_article("features/auth.md")
    assert "[← Volver al Índice](../INDEX.md)" in saved
    assert "\n---\n\n[← Volver al Índice](../INDEX.md)" in saved


def test_backlink_idempotency(clean_project: Path) -> None:
    """Writing an article that already has a backlink does not duplicate it."""
    content = """---
type: feature
summary: Audio pipeline
status: planned
version: 1.0.0
last_updated: 2026-11-03
---

# Audio Pipeline

## Overview
Handles streaming audio.

---

[← Volver al Índice](../INDEX.md)
"""
    write_article("features/audio.md", content)
    saved = read_article("features/audio.md")
    assert saved.count("[← Volver al Índice]") == 1
    assert saved.count("INDEX.md") == 1


def test_backlink_nested_subfolders() -> None:
    """Nested subfolders compute correct relative path depth to INDEX.md."""
    body = "# Deep Nested\n\n## Overview\nDeep section."
    normalized = normalize_backlink_footer(body, "features/sub/deep/doc.md")
    assert "[← Volver al Índice](../../../INDEX.md)" in normalized


def test_backlink_exclusion_rules() -> None:
    """INDEX.md, SCHEMA.md, _raw/, and handoffs/ are excluded from backlink injection."""
    assert normalize_backlink_footer("# Root Index", "INDEX.md") == "# Root Index"
    assert normalize_backlink_footer("# Schema", "SCHEMA.md") == "# Schema"
    assert normalize_backlink_footer("# Raw", "_raw/sessions/s1.md") == "# Raw"
    assert normalize_backlink_footer("# Handoff", "handoffs/h1.md") == "# Handoff"


def test_backlink_in_batch_writes_and_edits(clean_project: Path) -> None:
    """Batch writes and partial edits preserve and enforce backlink normalization."""
    batch = [
        {
            "path": "features/f1.md",
            "content": """---
type: feature
summary: F1 summary
status: planned
version: 1.0.0
last_updated: 2026-11-03
---

# Feature 1

## Overview
Feature 1 details.
""",
        }
    ]
    write_many_articles(batch)
    saved = read_article("features/f1.md")
    assert "[← Volver al Índice](../INDEX.md)" in saved

    edit_article(
        "features/f1.md",
        [{"old_text": "Feature 1 details.", "new_text": "Feature 1 updated details."}],
    )
    edited = read_article("features/f1.md")
    assert "Feature 1 updated details." in edited
    assert edited.count("[← Volver al Índice]") == 1


# ==============================================================================
# Area 2: Section-Level Structural Schemas & Skeletons
# ==============================================================================


def test_active_schema_required_sections_defaults() -> None:
    """Active schema defines required sections for built-in software and general profiles."""
    schema = load_active_schema()
    types = schema.types

    assert "decision" in types
    assert types["decision"]["required_sections"] == ["Status", "Context", "Decision", "Consequences"]

    assert "feature" in types
    assert types["feature"]["required_sections"] == ["Overview"]

    assert "architecture" in types
    assert any("Overview" in s for s in types["architecture"]["required_sections"])


def test_generate_document_skeleton_and_schema_docs() -> None:
    """generate_document_skeleton and get_schema_documentation output full markdown skeletons."""
    skeleton = generate_document_skeleton("decision")
    assert "type: decision" in skeleton
    assert "## Status" in skeleton
    assert "## Context" in skeleton
    assert "## Decision" in skeleton
    assert "## Consequences" in skeleton
    assert "[← Volver al Índice](../INDEX.md)" in skeleton

    feature_skel = generate_document_skeleton("feature")
    assert "type: feature" in feature_skel
    assert "## Overview" in feature_skel
    assert "[← Volver al Índice](../INDEX.md)" in feature_skel

    docs = get_schema_documentation("decision")
    assert "Document Skeleton:" in docs
    assert "**Required sections**:" in docs
    assert "Status, Context, Decision, Consequences" in docs


def test_check_file_health_missing_sections_warning(clean_project: Path) -> None:
    """check_file_health warns when a decision omits required ADR sections."""
    wiki = clean_project / ".brain-79"

    # Incomplete decision (missing Consequences)
    bad_decision = """---
type: decision
summary: Incomplete ADR
status: proposed
date: 2026-11-03
deciders: [team]
last_updated: 2026-11-03
---

# Incomplete ADR

## Status
Proposed

## Context
Some context

## Decision
Some decision
"""
    warnings = check_file_health(wiki, "decisions/bad.md", bad_decision)
    assert any("Missing required section '## Consequences'" in w for w in warnings)

    # Complete decision
    good_decision = bad_decision + "\n## Consequences\nPositive consequences."
    good_warnings = check_file_health(wiki, "decisions/good.md", good_decision)
    assert not any("Missing required section" in w for w in good_warnings)


def test_linter_article_missing_required_sections(clean_project: Path) -> None:
    """check_article_structural_sections flags articles missing required sections."""
    wiki = clean_project / ".brain-79"
    bad_dec = wiki / "decisions" / "adr-bad.md"
    bad_dec.write_text(
        """---
type: decision
summary: Bad ADR
status: proposed
date: 2026-11-03
deciders: [team]
last_updated: 2026-11-03
---

# Bad ADR

## Status
Proposed
""",
        encoding="utf-8",
    )

    issues = check_article_structural_sections(wiki)
    assert any(i.rule == "article_missing_required_sections" for i in issues)
    assert any("Consequences" in i.message for i in issues)


def test_adversarial_code_fence_with_h2() -> None:
    """Headings inside code fences are ignored during section validation."""
    content = """# Title

```markdown
## Consequences
This is code example, not an actual heading.
```

## Status
Active
"""
    headers = extract_h2_headers(content)
    assert headers == ["Status"]
    assert "Consequences" not in headers


# ==============================================================================
# Area 3: Deterministic Code-to-Wiki Drift Detection
# ==============================================================================


def test_detect_file_drift_mtime(clean_project: Path) -> None:
    """Detects when a workspace file governed by applies_to is modified after article's last_updated."""
    wiki = clean_project / ".brain-79"
    src_dir = clean_project / "src"
    src_dir.mkdir()
    code_file = src_dir / "service.py"
    code_file.write_text("# service code\n", encoding="utf-8")

    # Yesterday's date
    yesterday = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d")
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Set code file mtime to today
    mod_date = get_file_last_modified_date(code_file, clean_project)
    assert mod_date == today

    # Article with last_updated = yesterday
    article = wiki / "features" / "service.md"
    article.write_text(
        f"""---
type: feature
summary: Service docs
status: shipped
version: 1.0.0
applies_to:
  - "src/service.py"
last_updated: "{yesterday}"
---

# Service Docs

## Overview
Docs.

---

[← Volver al Índice](../INDEX.md)
""",
        encoding="utf-8",
    )

    drifts = check_article_drift(article, wiki_root=wiki, project_root=clean_project)
    assert len(drifts) == 1
    assert drifts[0]["workspace_file"] == "src/service.py"
    assert drifts[0]["article_date"] == yesterday
    assert drifts[0]["file_date"] == today


def test_detect_file_drift_glob_patterns(clean_project: Path) -> None:
    """find_matching_workspace_files resolves glob patterns against the project root."""
    core = clean_project / "core"
    core.mkdir()
    f1 = core / "alpha.py"
    f2 = core / "beta.py"
    f1.write_text("# alpha\n", encoding="utf-8")
    f2.write_text("# beta\n", encoding="utf-8")

    matches = find_matching_workspace_files(["core/*.py"], clean_project)
    assert f1 in matches
    assert f2 in matches


def test_detect_file_drift_nonexistent_workspace_file(clean_project: Path) -> None:
    """Nonexistent workspace files in applies_to are gracefully skipped without errors."""
    wiki = clean_project / ".brain-79"
    article = wiki / "features" / "ghost.md"
    article.write_text(
        """---
type: feature
summary: Ghost feature
status: planned
version: 1.0.0
applies_to:
  - "src/nonexistent.py"
last_updated: "2026-01-01"
---

# Ghost Feature

## Overview
Ghost.
""",
        encoding="utf-8",
    )

    drifts = check_article_drift(article, wiki_root=wiki, project_root=clean_project)
    assert drifts == []


def test_linter_documentation_drift_rule(clean_project: Path) -> None:
    """check_documentation_drift reports documentation_drift_suspected issues."""
    wiki = clean_project / ".brain-79"
    code = clean_project / "worker.py"
    code.write_text("# worker\n", encoding="utf-8")

    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    article = wiki / "features" / "worker.md"
    article.write_text(
        f"""---
type: feature
summary: Worker documentation
status: shipped
version: 1.0.0
applies_to:
  - "worker.py"
last_updated: "{yesterday}"
---

# Worker Feature

## Overview
Worker feature.

---

[← Volver al Índice](../INDEX.md)
""",
        encoding="utf-8",
    )

    issues = check_documentation_drift(wiki)
    assert len(issues) == 1
    assert issues[0].rule == "documentation_drift_suspected"
    assert issues[0].severity == "warning"
    assert "Worker documentation" not in issues[0].message
    assert "worker.py" in issues[0].message


def test_orient_drift_warning_banner(clean_project: Path) -> None:
    """orient() displays prominent warning banner when inlined article has suspected drift."""
    wiki = clean_project / ".brain-79"
    code = clean_project / "auth.py"
    code.write_text("# auth\n", encoding="utf-8")

    yesterday = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d")
    article = wiki / "features" / "auth.md"
    article.write_text(
        f"""---
type: feature
summary: Authentication subsystem
status: shipped
version: 1.0.0
applies_to:
  - "auth.py"
last_updated: "{yesterday}"
---

# Authentication Subsystem

## Overview
Handles authentication.

---

[← Volver al Índice](../INDEX.md)
""",
        encoding="utf-8",
    )

    # Register in navigation so context ranker finds it
    from brain79.core.navigation import register_article
    register_article(
        wiki,
        "features/auth.md",
        "Authentication Subsystem",
        "Authentication subsystem",
        "features",
        graph_meta={"applies_to": ["auth.py"], "related": [], "outgoing_links": []},
    )

    res = orient(task="work on auth.py", paths=["auth.py"], wiki_root=wiki)
    assert "Documentation Drift Suspected" in res
    assert "governs 'auth.py'" in res


def test_session_commit_phase4_integration(clean_project: Path) -> None:
    """Full session commit integrates backlink auto-injection and whole-transaction health check."""
    payload = {
        "session_summary": "Phase 4 session commit verification.",
        "writes": [
            {
                "path": "features/billing.md",
                "content": """---
type: feature
summary: Billing integration
status: shipped
version: 1.0.0
last_updated: 2026-11-03
---

# Billing Integration

## Overview
Stripe payment processing.
""",
            }
        ],
        "handoff": {
            "session_type": "feature",
            "summary": "Completed billing integration.",
            "completed_work": ["Implemented Stripe checkout"],
            "pending_work": [],
            "boot_instruction": "No pending tasks.",
        },
    }

    result = commit_session(payload)
    assert result["success"] is True
    assert result["health_status"] == "ok"

    saved = read_article("features/billing.md")
    assert "[← Volver al Índice](../INDEX.md)" in saved


# ==============================================================================
# Area 4: Adversarial Hardening (Findings 1 - 7)
# ==============================================================================


def test_adversarial_defect_1_backlink_tail_outside_code_fence() -> None:
    """Backlink inside code fence does not fool normalize_backlink_footer; short articles get backlink."""
    # 1. Backlink mentioned in code block midway through the document
    body_with_code = """# Guide

```markdown
Use [← Volver al Índice](../INDEX.md) at the end.
```

## Overview
Content here.
"""
    normalized = normalize_backlink_footer(body_with_code, "features/guide.md")
    # Must append the real footer at the end outside the fence
    assert normalized.rstrip().endswith("[← Volver al Índice](../INDEX.md)")
    assert normalized.count("[← Volver al Índice]") == 2  # one in code block, one at tail

    # 2. Short single-line body gets backlink
    single_line = "# Auth Feature"
    norm_single = normalize_backlink_footer(single_line, "features/auth.md")
    assert "[← Volver al Índice](../INDEX.md)" in norm_single


def test_adversarial_defect_2_wall_of_text_and_word_boundaries(clean_project: Path) -> None:
    """Paragraph wall of text is flagged; word boundaries prevent false positive substring matches."""
    # 1. Wall of text (1 line of 1000 words under H1) missing ## Overview
    wall_of_text = "# Big Feature\n\n" + ("word " * 500)
    missing = check_missing_sections(wall_of_text, "feature")
    assert "Overview" in missing

    # 2. 'Statement of Purpose' does not satisfy 'State' requirement in architecture
    statement_arch = """# Architecture\n\n## Statement of Purpose\nOur goal."""
    missing_arch = check_missing_sections(statement_arch, "architecture")
    assert "Overview" in missing_arch  # 'Overview' or 'General Description' or 'State'

    # 3. 'HTTP Status Codes' does not satisfy 'Status' requirement in decision
    http_status_dec = """---
type: decision
status: proposed
---
# Decision\n\n## HTTP Status Codes\n200, 404.\n\n## Context\nC.\n\n## Decision\nD.\n\n## Consequences\nE."""
    missing_dec = check_missing_sections(http_status_dec, "decision")
    assert "Status" in missing_dec

    # 4. Inactive statuses (superseded, legacy) are exempted
    superseded_dec = """---
type: decision
status: superseded
---
# Old Decision\n\nOld text without any sections."""
    assert check_missing_sections(superseded_dec, "decision") == []


def test_adversarial_defect_3_git_mtime_vs_porcelain(clean_project: Path) -> None:
    """When git log is available, clean working tree uses commit date, ignoring newer checkout mtime."""
    code_file = clean_project / "clean_module.py"
    code_file.write_text("# clean\n", encoding="utf-8")

    # In a clean project with no git log, falls back to mtime
    mtime_date = get_file_last_modified_date(code_file, clean_project)
    assert mtime_date is not None


def test_adversarial_defect_4_glob_relative_and_match_applies_to(clean_project: Path) -> None:
    """find_matching_workspace_files handles ./ prefix and prevents ../ traversal."""
    src = clean_project / "src"
    src.mkdir()
    f1 = src / "mod.py"
    f1.write_text("# mod\n", encoding="utf-8")

    # Pattern with ./
    matched = find_matching_workspace_files(["./src/*.py"], clean_project)
    assert f1 in matched

    # Path attempting directory traversal outside project root is ignored
    escaped = find_matching_workspace_files(["../escaping.py"], clean_project)
    assert escaped == []


def test_adversarial_defect_5_yaml_date_object_normalization(clean_project: Path) -> None:
    """check_article_drift correctly normalizes date/datetime objects in last_updated."""
    wiki = clean_project / ".brain-79"
    code = clean_project / "date_check.py"
    code.write_text("# check\n", encoding="utf-8")

    article = wiki / "features" / "date_check.md"
    # Using an old date string that PyYAML or standard parser handles
    article.write_text(
        """---
type: feature
summary: Date check
status: shipped
version: 1.0.0
applies_to:
  - "date_check.py"
last_updated: 2026-01-01
---

# Date Check

## Overview
Check.

---

[← Volver al Índice](../INDEX.md)
""",
        encoding="utf-8",
    )

    drifts = check_article_drift(article, wiki_root=wiki, project_root=clean_project)
    assert len(drifts) == 1
    assert drifts[0]["article_date"] == "2026-01-01"


def test_adversarial_defect_6_inactive_status_filtering(clean_project: Path) -> None:
    """Articles with inactive status (superseded, deprecated, rejected, archived, legacy) do not report drift."""
    wiki = clean_project / ".brain-79"
    code = clean_project / "retired.py"
    code.write_text("# retired code\n", encoding="utf-8")

    article = wiki / "features" / "retired.md"
    article.write_text(
        """---
type: feature
summary: Retired feature
status: deprecated
version: 1.0.0
applies_to:
  - "retired.py"
last_updated: "2020-01-01"
---

# Retired Feature

## Overview
Retired.

---

[← Volver al Índice](../INDEX.md)
""",
        encoding="utf-8",
    )

    drifts = check_article_drift(article, wiki_root=wiki, project_root=clean_project)
    assert drifts == []


def test_adversarial_defect_7_template_schema_in_sync() -> None:
    """src/brain79/templates/SCHEMA.md is strictly in sync with .brain-79/SCHEMA.md."""
    template_schema = Path("src/brain79/templates/SCHEMA.md").read_text(encoding="utf-8")
    project_schema = Path(".brain-79/SCHEMA.md").read_text(encoding="utf-8")

    assert "Document structural skeletons and required sections" in template_schema
    assert "Deterministic drift detection (`applies_to`)" in template_schema
    assert "Document structural skeletons and required sections" in project_schema
    assert "Deterministic drift detection (`applies_to`)" in project_schema

