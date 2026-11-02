"""Unit and integration tests for Phase 1: Declarative Schema & Dual Ontologies.

Tests:
1. load_active_schema defaults to 'software' profile when SCHEMA.md has no frontmatter or is missing.
2. In-memory mtime cache returns identical object when mtime hasn't changed, and invalidates when SCHEMA.md is touched.
3. Declarative 'general' profile loads context/, topics/, decisions/, log/ and corresponding type rules.
4. Custom folders declared in SCHEMA.md frontmatter are parsed and enforced by validate_frontmatter.
5. brain79 init supports --profile software (default) and --profile general.
6. Initializing with --profile general creates context/, topics/, decisions/, log/, _raw/, handoffs/ and proper SCHEMA.md.
7. Articles in general profile validate type: topic, context, decision, log without semver or stability requirements.
8. Linter check_frontmatter_consistency and check_type_location_mismatch respect the active schema dynamically.
9. Technical debt leakage is disabled in 'general' profile, while decision leakage remains active.
10. Backward compatibility with existing software projects is 100% preserved.
"""

from pathlib import Path
import time
import pytest

from brain79.core.frontmatter import (
    ValidationError,
    clear_schema_cache,
    load_active_schema,
    parse_frontmatter,
    validate_frontmatter,
    validate_location_consistency,
)
from brain79.core.init_project import init_project
from brain79.core.lint_organizational import (
    check_frontmatter_consistency,
    lint_organizational,
)
from brain79.core.wiki import read_article, write_article


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_schema_cache()


def test_default_schema_is_software_profile(tmp_path: Path) -> None:
    """When no SCHEMA.md exists or SCHEMA.md has no profile header, profile defaults to software."""
    schema = load_active_schema(tmp_path)
    assert schema.profile == "software"
    assert "product" in schema.types
    assert "architecture" in schema.types
    assert "features" in schema.location_to_type
    assert schema.types["feature"]["required"] == [
        "type",
        "summary",
        "status",
        "version",
        "last_updated",
    ]


def test_schema_mtime_caching_and_invalidation(tmp_path: Path) -> None:
    """load_active_schema should cache result by (wiki_root, mtime_ns) and reload on mutation."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir(parents=True)
    schema_file = wiki_root / "SCHEMA.md"

    # 1. First load: default software
    schema_file.write_text("# Schema\nDefault software schema\n", encoding="utf-8")
    s1 = load_active_schema(wiki_root)
    assert s1.profile == "software"

    # 2. Second load: must be cached instance
    s2 = load_active_schema(wiki_root)
    assert s1 is s2

    # 3. Touch/modify SCHEMA.md to declare general profile
    time.sleep(0.01)  # Ensure mtime_ns changes
    schema_file.write_text(
        "---\nprofile: general\n---\n# General Schema\n", encoding="utf-8"
    )
    s3 = load_active_schema(wiki_root)
    assert s3.profile == "general"
    assert s3 is not s1
    assert "topics" in s3.location_to_type
    assert s3.location_to_type["topics"] == "topic"


def test_general_profile_rules(tmp_path: Path) -> None:
    """General profile validates context, topic, decision, and log types with minimal friction."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir(parents=True)
    schema_file = wiki_root / "SCHEMA.md"
    schema_file.write_text(
        "---\nprofile: general\n---\n# General Knowledge Schema\n",
        encoding="utf-8",
    )

    schema = load_active_schema(wiki_root)
    assert schema.profile == "general"
    assert "topic" in schema.types
    assert "context" in schema.types
    assert "log" in schema.types
    assert "decision" in schema.types

    # In general profile, topic requires type, summary, last_updated; status is optional or enum
    assert "type" in schema.types["topic"]["required"]
    assert "summary" in schema.types["topic"]["required"]
    assert "version" not in schema.types["topic"]["required"]

    # Decision in general profile does not strictly mandate semver or deciders list if configured cleanly
    assert "type" in schema.types["decision"]["required"]
    assert "summary" in schema.types["decision"]["required"]


def test_custom_folder_and_type_declaration(tmp_path: Path) -> None:
    """Users can declare custom folders in SCHEMA.md frontmatter without editing python code."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir(parents=True)
    schema_file = wiki_root / "SCHEMA.md"
    schema_file.write_text(
        "---\n"
        "profile: software\n"
        "custom_types:\n"
        "  runbook:\n"
        "    directory: runbooks\n"
        "    required:\n"
        "      - type\n"
        "      - summary\n"
        "      - target_service\n"
        "      - last_updated\n"
        "    optional:\n"
        "      - owner\n"
        "    enum:\n"
        "      target_service: [api, worker, database]\n"
        "---\n"
        "# Custom Schema\n",
        encoding="utf-8",
    )

    schema = load_active_schema(wiki_root)
    assert "runbook" in schema.types
    assert schema.location_to_type["runbooks"] == "runbook"
    assert "target_service" in schema.types["runbook"]["required"]

    # Validate article against custom schema
    meta = {
        "type": "runbook",
        "summary": "Database failover procedure",
        "target_service": "database",
        "last_updated": "2026-11-02",
    }
    validate_frontmatter(meta, "runbooks/failover.md", schema=schema)
    validate_location_consistency(meta, "runbooks/failover.md", schema=schema)

    # Invalid enum in custom type fails
    invalid_meta = {
        "type": "runbook",
        "summary": "Database failover procedure",
        "target_service": "unknown_svc",
        "last_updated": "2026-11-02",
    }
    with pytest.raises(ValidationError) as exc:
        validate_frontmatter(invalid_meta, "runbooks/failover.md", schema=schema)
    assert exc.value.rule == "frontmatter_invalid_enum"


def test_init_project_with_general_profile(tmp_path: Path) -> None:
    """brain79 init --profile general bootstraps general directories and SCHEMA.md."""
    init_project(tmp_path, install_git_hooks_flag=False, profile="general")
    wiki_root = tmp_path / ".brain-79"

    assert (wiki_root / "context").is_dir()
    assert (wiki_root / "topics").is_dir()
    assert (wiki_root / "decisions").is_dir()
    assert (wiki_root / "log").is_dir()
    assert (wiki_root / "handoffs").is_dir()
    assert (wiki_root / "_raw" / "sessions").is_dir()

    # product and features should NOT be created for general profile
    assert not (wiki_root / "product").exists()
    assert not (wiki_root / "features").exists()

    schema_content = (wiki_root / "SCHEMA.md").read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(schema_content)
    assert meta.get("profile") == "general"


def test_general_profile_write_and_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Writing general profile articles via write_article works seamlessly."""
    from brain79.config import set_project_root
    init_project(tmp_path, install_git_hooks_flag=False, profile="general")
    monkeypatch.chdir(tmp_path)
    set_project_root(tmp_path)
    clear_schema_cache()

    topic_content = (
        "---\n"
        "type: topic\n"
        "summary: Overview of market research methodology\n"
        "status: active\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Market Research\n\n"
        "Details on qualitative and quantitative analysis.\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    msg = write_article("topics/market-research.md", topic_content)
    assert "Written" in msg

    saved = read_article("topics/market-research.md")
    assert "Market Research" in saved

    # Verify INDEX.md navigation was updated with topic
    index_text = read_article("INDEX.md")
    assert "Market Research" in index_text
    assert "topics/market-research.md" in index_text


def test_linter_respects_general_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Organizational linter handles general ontology and ignores tech debt leakage."""
    from brain79.config import set_project_root
    init_project(tmp_path, install_git_hooks_flag=False, profile="general")
    monkeypatch.chdir(tmp_path)
    set_project_root(tmp_path)
    clear_schema_cache()
    wiki_root = tmp_path / ".brain-79"

    topic_file = wiki_root / "topics" / "notes.md"
    topic_file.write_text(
        "---\n"
        "type: topic\n"
        "summary: General project notes\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Project Notes\n\n"
        "Here is some TODO: clean up old meeting drafts.\n",
        encoding="utf-8",
    )

    issues = lint_organizational(wiki_root)
    # In general profile, TODO in topics should NOT trigger technical debt leakage
    assert not any(i.rule == "technical_debt_leakage" for i in issues)

    # But decision leakage still works if a formal decision header/bullet is placed outside decisions/
    bad_topic = wiki_root / "topics" / "bad.md"
    bad_topic.write_text(
        "---\n"
        "type: topic\n"
        "summary: Bad topic with inline decision\n"
        "last_updated: 2026-11-02\n"
        "---\n\n"
        "# Bad Topic\n\n"
        "### Decision\n"
        "We decided to cancel the project.\n",
        encoding="utf-8",
    )
    issues_after = lint_organizational(wiki_root)
    assert any(i.rule == "decision_leakage" and i.path == "topics/bad.md" for i in issues_after)


def test_backward_compatibility_existing_software_projects(tmp_path: Path) -> None:
    """Existing project initialized without profile frontmatter operates exactly as software profile."""
    init_project(tmp_path, install_git_hooks_flag=False, profile="software")
    wiki_root = tmp_path / ".brain-79"

    # Remove profile frontmatter to simulate legacy project
    schema_file = wiki_root / "SCHEMA.md"
    schema_file.write_text("# Legacy Schema without frontmatter\n", encoding="utf-8")

    clear_schema_cache()
    schema = load_active_schema(wiki_root)
    assert schema.profile == "software"
    assert "feature" in schema.types
    assert "architecture" in schema.types
    issues = check_frontmatter_consistency(wiki_root)
    assert len(issues) == 0
