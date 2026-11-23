"""Comprehensive tests for defect backlog remediations (BUG-001, BUG-002, INEF-001, INEF-002)."""

from pathlib import Path

from brain79.config import set_project_root
from brain79.core.frontmatter import normalize_backlink_footer
from brain79.core.init_project import init_project
from brain79.core.lint import lint_wiki
from brain79.core.lint_organizational import check_article_atomicity
from brain79.core.orient import orient
from brain79.server import brain79_edit, brain79_session_commit


# ==============================================================================
# BUG-001: Broken local link in SCHEMA_GENERAL.md and root backlink normalization
# ==============================================================================

def test_init_general_profile_has_no_broken_links(tmp_path: Path) -> None:
    """Initializing with profile='general' must produce a wiki that passes strict lint with zero broken links."""
    init_project(tmp_path, profile="general")
    wiki_root = tmp_path / ".brain-79"
    schema_content = (wiki_root / "SCHEMA.md").read_text(encoding="utf-8")

    assert "../INDEX.md" not in schema_content, "SCHEMA.md at root should link to INDEX.md, not ../INDEX.md"
    assert "[← Back to Index](INDEX.md)" in schema_content

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


def test_normalize_backlink_footer_preserves_code_fences_in_root_files() -> None:
    """normalize_backlink_footer must NOT corrupt example backlinks inside code blocks in root files (e.g. SCHEMA.md)."""
    schema_body = (
        "# Schema Documentation\n\n"
        "### Back-Navigation Links\n\n"
        "Subdirectory articles conclude with:\n\n"
        "```markdown\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
        "```\n\n"
        "### Next Section\n\n"
        "More text.\n"
    )
    normalized = normalize_backlink_footer(schema_body, "SCHEMA.md")
    assert "[← Volver al Índice](../INDEX.md)" in normalized, "Example backlink inside code fence must remain intact"
    assert normalized == schema_body


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


def test_atomicity_compact_article_exempt_up_to_12_h2(tmp_path: Path) -> None:
    """Compact articles (<= 150 lines) with normal names/tags are exempt up to 12 H2 sections."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    feat_dir = wiki_root / "features"
    feat_dir.mkdir()

    # Normal article with no checklist tags or keywords in name
    sections = [
        "---\n"
        "type: feature\n"
        "summary: Short compact feature documentation\n"
        "status: planned\n"
        "---\n\n"
        "# Standard Compact Feature\n"
    ]
    for i in range(1, 12):  # 11 H2 sections
        sections.append(f"## Point {i}\nShort description.\n")

    content = "\n".join(sections)
    assert len(content.splitlines()) <= 150

    (feat_dir / "user-guide.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 0, f"Compact article with 11 H2s (<= 12) must pass, got: {atomicity_issues}"


def test_atomicity_compact_article_flags_over_12_h2(tmp_path: Path) -> None:
    """Compact articles (<= 150 lines) exceeding 12 H2 sections are flagged."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    feat_dir = wiki_root / "features"
    feat_dir.mkdir()

    sections = [
        "---\n"
        "type: feature\n"
        "summary: Compact article with excessive sections\n"
        "status: planned\n"
        "---\n\n"
        "# Compact Excess\n"
    ]
    for i in range(1, 14):  # 13 H2 sections
        sections.append(f"## Point {i}\nShort description.\n")

    content = "\n".join(sections)
    assert len(content.splitlines()) <= 150

    (feat_dir / "excess-sections.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 1
    assert "excess-sections.md" in atomicity_issues[0].path


def test_atomicity_long_prose_passes_up_to_10_h2(tmp_path: Path) -> None:
    """Long prose articles (> 150 lines) pass when having up to 10 H2 sections."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    feat_dir = wiki_root / "features"
    feat_dir.mkdir()

    sections = [
        "---\n"
        "type: feature\n"
        "summary: Long feature article within limits\n"
        "status: planned\n"
        "---\n\n"
        "# Detailed Feature\n"
    ]
    # Exactly 10 H2 sections with extensive prose totaling > 150 lines
    for i in range(1, 11):
        sections.append(
            f"## Deep Dive Section {i}\n"
            + ("This is a long paragraph detailing architectural considerations and nuances.\n" * 15)
        )

    content = "\n".join(sections)
    assert len(content.splitlines()) > 150

    (feat_dir / "detailed.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 0, f"Prose article with 10 H2s (<= 10) must pass, got: {atomicity_issues}"


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


def test_atomicity_checklist_flags_over_15_h2(tmp_path: Path) -> None:
    """Checklist articles exceeding 15 H2 sections are flagged."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir()

    sections = [
        "---\n"
        "type: topic\n"
        "summary: Sprawling checklist exceeding 15 H2 sections\n"
        "status: active\n"
        "tags:\n"
        "  - checklist\n"
        "---\n\n"
        "# Sprawling Checklist\n\n"
        "## Overview\n\n"
        "Checklist overview.\n"
    ]
    for i in range(1, 16):  # 1 + 15 = 16 H2 sections
        sections.append(f"## Task Section {i}\n- [ ] Task {i}.1\n- [ ] Task {i}.2\n")

    content = "\n".join(sections)
    (topics_dir / "sprawling-checklist.md").write_text(content, encoding="utf-8")

    issues = check_article_atomicity(wiki_root)
    atomicity_issues = [i for i in issues if i.rule == "article_not_atomic"]
    assert len(atomicity_issues) == 1
    assert "sprawling-checklist.md" in atomicity_issues[0].path


# ==============================================================================
# INEF-001: Server write receipts with auto-synced navigation confirmation
# ==============================================================================

def test_server_write_receipt_includes_auto_synced(tmp_path: Path) -> None:
    """brain79_session_commit and brain79_edit receipts must report health and INDEX.md sync."""
    init_project(tmp_path)
    set_project_root(tmp_path)

    commit_res = brain79_session_commit(
        writes=[
            {
                "path": "features/test-receipt.md",
                "content": (
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
            }
        ]
    )
    assert "Transaction Committed Successfully" in commit_res
    assert "`ok`" in commit_res

    edit_res = brain79_edit(
        path="features/test-receipt.md",
        edits=[{"old_text": "Overview here.", "new_text": "Updated overview here."}],
    )
    assert "INDEX.md auto-synced" in edit_res
    assert "lint OK" in edit_res

    batch_res = brain79_session_commit(
        writes=[
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
    assert "Transaction Committed Successfully" in batch_res


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


# ==============================================================================
# BUG-003: Profile-aware Git repository enforcement and fallback code digest
# ==============================================================================

def test_bug_003_init_software_auto_initializes_git(tmp_path: Path) -> None:
    """In software profile, init_project should auto-run git init and install pre-commit hooks."""
    proj = tmp_path / "sw_project"
    proj.mkdir()
    init_project(proj, profile="software")

    assert (proj / ".git").is_dir(), "Software profile must auto-initialize git if absent"
    hook_file = proj / ".git" / "hooks" / "pre-commit"
    assert hook_file.is_file(), "Pre-commit hook must be installed"


def test_bug_003_init_general_does_not_initialize_git(tmp_path: Path) -> None:
    """In general profile, init_project must NEVER initialize git."""
    proj = tmp_path / "gen_project"
    proj.mkdir()
    init_project(proj, profile="general")

    assert not (proj / ".git").exists(), "General profile must remain 100% git-free"


def test_bug_003_init_software_can_disable_git(tmp_path: Path) -> None:
    """When auto_git_init=False, software profile should not initialize git."""
    proj = tmp_path / "sw_no_git"
    proj.mkdir()
    init_project(proj, profile="software", auto_git_init=False)

    assert not (proj / ".git").exists()


def test_bug_003_linter_warns_missing_git_only_for_software_profile(tmp_path: Path) -> None:
    """Linter issues missing_git_repository rule strictly for software profile without git."""
    from brain79.core.lint_organizational import lint_organizational

    sw_proj = tmp_path / "sw_gitless"
    sw_proj.mkdir()
    init_project(sw_proj, profile="software", auto_git_init=False)
    sw_issues = lint_organizational(sw_proj / ".brain-79")
    sw_rules = [i.rule for i in sw_issues]
    assert "missing_git_repository" in sw_rules

    gen_proj = tmp_path / "gen_gitless"
    gen_proj.mkdir()
    init_project(gen_proj, profile="general")
    gen_issues = lint_organizational(gen_proj / ".brain-79")
    gen_rules = [i.rule for i in gen_issues]
    assert "missing_git_repository" not in gen_rules


def test_bug_003_code_digest_fallback_for_software_without_git(tmp_path: Path) -> None:
    """Software project without git computes real cryptographic digest over code files via fallback."""
    from brain79.core.handoff_freshness import compute_code_digest

    sw_proj = tmp_path / "sw_code_digest"
    sw_proj.mkdir()
    init_project(sw_proj, profile="software", auto_git_init=False)

    code_file = sw_proj / "app.py"
    code_file.write_text("print('version 1')\n", encoding="utf-8")

    digest1 = compute_code_digest(sw_proj, wiki_root=sw_proj / ".brain-79")
    assert digest1 != "none"
    assert len(digest1) == 64

    code_file.write_text("print('version 2')\n", encoding="utf-8")
    digest2 = compute_code_digest(sw_proj, wiki_root=sw_proj / ".brain-79")
    assert digest2 != "none"
    assert digest2 != digest1
    assert len(digest2) == 64

    # General profile returns 'none'
    gen_proj = tmp_path / "gen_code_digest"
    gen_proj.mkdir()
    init_project(gen_proj, profile="general")
    (gen_proj / "data.csv").write_text("a,b,c\n", encoding="utf-8")
    assert compute_code_digest(gen_proj, wiki_root=gen_proj / ".brain-79") == "none"


# ==============================================================================
# BUG-004: Shared umbrella file governance and sibling leaf article conflicts
# ==============================================================================

def test_bug_004_sibling_leaf_article_overlap_advisory(tmp_path: Path) -> None:
    """Linter emits advisory shared_target_in_leaf_article (severity: info) on overlapping leaf targets."""
    from brain79.core.lint_organizational import lint_organizational
    from brain79.core.wiki import write_article

    proj = tmp_path / "overlap_proj"
    proj.mkdir()
    init_project(proj, profile="software", auto_git_init=False)
    wiki_root = proj / ".brain-79"

    # Shared file
    (proj / "style.css").write_text("body { color: red; }\n", encoding="utf-8")

    write_article(
        "features/game-roulette.md",
        (
            "---\n"
            "type: feature\n"
            "summary: roulette game engine\n"
            "status: shipped\n"
            "version: 1.0.0\n"
            "applies_to:\n"
            "  - style.css\n"
            "---\n\n"
            "# Roulette\n\n"
            "## Overview\n"
            "Roulette game.\n"
        ),
        wiki_root=wiki_root,
    )

    write_article(
        "features/game-crash.md",
        (
            "---\n"
            "type: feature\n"
            "summary: crash game engine\n"
            "status: shipped\n"
            "version: 1.0.0\n"
            "applies_to:\n"
            "  - style.css\n"
            "---\n\n"
            "# Crash\n\n"
            "## Overview\n"
            "Crash game.\n"
        ),
        force_validation_skip=True,
        wiki_root=wiki_root,
    )

    issues = lint_organizational(wiki_root)
    overlap_issues = [i for i in issues if i.rule == "shared_target_in_leaf_article"]
    assert len(overlap_issues) >= 1
    assert overlap_issues[0].severity == "info"
    assert "style.css" in overlap_issues[0].message


def test_bug_004_overlap_suppressed_with_allow_overlapping_governance(tmp_path: Path) -> None:
    """When allow_overlapping_governance: true is set, shared_target_in_leaf_article is suppressed."""
    from brain79.core.lint_organizational import lint_organizational
    from brain79.core.wiki import write_article

    proj = tmp_path / "overlap_suppressed"
    proj.mkdir()
    init_project(proj, profile="software", auto_git_init=False)
    wiki_root = proj / ".brain-79"

    (proj / "style.css").write_text("body { color: blue; }\n", encoding="utf-8")

    write_article(
        "features/game-roulette.md",
        (
            "---\n"
            "type: feature\n"
            "summary: roulette game engine\n"
            "status: planned\n"
            "version: 1.0.0\n"
            "allow_overlapping_governance: true\n"
            "applies_to:\n"
            "  - style.css\n"
            "---\n\n"
            "# Roulette\n\n"
            "## Overview\n"
            "Roulette game.\n"
        ),
        wiki_root=wiki_root,
    )

    write_article(
        "features/game-crash.md",
        (
            "---\n"
            "type: feature\n"
            "summary: crash game engine\n"
            "status: planned\n"
            "version: 1.0.0\n"
            "allow_overlapping_governance: true\n"
            "applies_to:\n"
            "  - style.css\n"
            "---\n\n"
            "# Crash\n\n"
            "## Overview\n"
            "Crash game.\n"
        ),
        wiki_root=wiki_root,
    )

    issues = lint_organizational(wiki_root)
    overlap_issues = [i for i in issues if i.rule == "shared_target_in_leaf_article"]
    assert len(overlap_issues) == 0


# ==============================================================================
# BUG-005: Architectural decision deficit heuristic (advisory, non-blocking)
# ==============================================================================

def test_bug_005_architectural_decision_deficit_advisory(tmp_path: Path) -> None:
    """Linter emits architectural_decision_deficit (severity: info) when >= 3 features/arch and 0 ADRs."""
    from brain79.core.lint_organizational import lint_organizational
    from brain79.core.wiki import write_article
    from brain79.core.orient import orient

    proj = tmp_path / "adr_deficit_proj"
    proj.mkdir()
    init_project(proj, profile="software", auto_git_init=False)
    wiki_root = proj / ".brain-79"

    for i in range(3):
        write_article(
            f"features/feature-{i}.md",
            (
                "---\n"
                "type: feature\n"
                f"summary: feature {i} description\n"
                "status: planned\n"
                "version: 1.0.0\n"
                "---\n\n"
                f"# Feature {i}\n\n"
                "## Overview\n"
                f"Feature {i} overview.\n"
            ),
            wiki_root=wiki_root,
        )

    issues = lint_organizational(wiki_root)
    deficit_issues = [i for i in issues if i.rule == "architectural_decision_deficit"]
    assert len(deficit_issues) == 1
    assert deficit_issues[0].severity == "info"
    assert "decisions" in deficit_issues[0].path

    set_project_root(proj)
    orient_out = orient(task="Review project architecture")
    assert "architectural decision" in orient_out.lower() or "adr" in orient_out.lower()


def test_bug_005_adr_present_clears_deficit(tmp_path: Path) -> None:
    """When at least 1 active ADR is present, architectural_decision_deficit is not emitted."""
    from brain79.core.lint_organizational import lint_organizational
    from brain79.core.wiki import write_article

    proj = tmp_path / "adr_present_proj"
    proj.mkdir()
    init_project(proj, profile="software", auto_git_init=False)
    wiki_root = proj / ".brain-79"

    for i in range(3):
        write_article(
            f"features/feature-{i}.md",
            (
                "---\n"
                "type: feature\n"
                f"summary: feature {i} description\n"
                "status: planned\n"
                "version: 1.0.0\n"
                "---\n\n"
                f"# Feature {i}\n\n"
                "## Overview\n"
                f"Feature {i} overview.\n"
            ),
            wiki_root=wiki_root,
        )

    write_article(
        "decisions/adr-001-state-store.md",
        (
            "---\n"
            "type: decision\n"
            "summary: reactive state store decision\n"
            "status: accepted\n"
            "date: 2026-11-12\n"
            "deciders:\n"
            "  - Lead Architect\n"
            "---\n\n"
            "# ADR-001 — Reactive state store\n\n"
            "## Status\nAccepted.\n\n"
            "## Context\nNeed state management.\n\n"
            "## Decision\nUse pub/sub store.\n\n"
            "## Consequences\nDecoupled modules.\n"
        ),
        wiki_root=wiki_root,
    )

    issues = lint_organizational(wiki_root)
    deficit_issues = [i for i in issues if i.rule == "architectural_decision_deficit"]
    assert len(deficit_issues) == 0


# ==============================================================================
# BUG-006: Source code coverage gap detection (uncovered source files)
# ==============================================================================

def test_bug_006_uncovered_source_files_heuristic(tmp_path: Path) -> None:
    """Linter emits advisory uncovered_source_files (severity: info) for unanchored source code files."""
    from brain79.core.lint_organizational import lint_organizational
    from brain79.core.wiki import write_article

    proj = tmp_path / "coverage_gap_proj"
    proj.mkdir()
    init_project(proj, profile="software", auto_git_init=False)
    wiki_root = proj / ".brain-79"

    # Create two source files
    src_dir = proj / "src"
    src_dir.mkdir()
    (src_dir / "governed_service.py").write_text("def run(): pass\n", encoding="utf-8")
    (src_dir / "orphaned_service.py").write_text("def orphan(): pass\n", encoding="utf-8")

    # Feature article only governs governed_service.py
    write_article(
        "features/service.md",
        (
            "---\n"
            "type: feature\n"
            "summary: service engine\n"
            "status: planned\n"
            "version: 1.0.0\n"
            "applies_to:\n"
            "  - src/governed_service.py\n"
            "---\n\n"
            "# Service\n\n"
            "## Overview\n"
            "Service overview.\n"
        ),
        wiki_root=wiki_root,
    )

    issues = lint_organizational(wiki_root)
    uncovered = [i for i in issues if i.rule == "uncovered_source_files"]
    assert len(uncovered) == 1
    assert uncovered[0].severity == "info"
    assert "src/orphaned_service.py" in uncovered[0].path


# ==============================================================================
# BUG-007: Frontmatter summary casing normalization and changelog slug standard
# ==============================================================================

def test_bug_007_changelog_slug_validation(tmp_path: Path) -> None:
    """Changelog articles must use kebab-case version slugs (e.g. v1-1-0.md, not 1.1.0.md)."""
    import pytest
    from brain79.core.frontmatter import ValidationError
    from brain79.core.wiki import write_article

    proj = tmp_path / "changelog_slug_proj"
    proj.mkdir()
    init_project(proj, profile="software", auto_git_init=False)
    wiki_root = proj / ".brain-79"

    # Dotted slug should be rejected
    with pytest.raises(ValidationError) as exc_info:
        write_article(
            "changelog/1.1.0.md",
            (
                "---\n"
                "type: changelog\n"
                "summary: release 1.1.0\n"
                "version: 1.1.0\n"
                "date: 2026-11-12\n"
                "---\n\n"
                "# Changelog 1.1.0\n\n"
                "## Overview\n"
                "Release notes.\n"
            ),
            wiki_root=wiki_root,
        )
    assert exc_info.value.rule == "invalid_changelog_slug"

    # Standard kebab-case vX-Y-Z slug should succeed
    res = write_article(
        "changelog/v1-1-0.md",
        (
            "---\n"
            "type: changelog\n"
            "summary: release 1.1.0\n"
            "version: 1.1.0\n"
            "date: 2026-11-12\n"
            "---\n\n"
            "# Changelog 1.1.0\n\n"
            "## Overview\n"
            "Release notes.\n"
        ),
        wiki_root=wiki_root,
    )
    assert "changelog/v1-1-0.md" in res


def test_bug_007_summary_initial_lowercase_normalization() -> None:
    """sanitize_summary normalizes initial words to lowercase, preserving acronyms and proper nouns."""
    from brain79.core.frontmatter import sanitize_summary

    assert sanitize_summary("Arquitectura del motor") == "arquitectura del motor"
    assert sanitize_summary("CLI and MCP symmetry") == "CLI and MCP symmetry"
    assert sanitize_summary("FastMCP server integration") == "FastMCP server integration"
    assert sanitize_summary("Python packaging and distribution") == "Python packaging and distribution"
    assert sanitize_summary("   Docker container deployment   ") == "Docker container deployment"







