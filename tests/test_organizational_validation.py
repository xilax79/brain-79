from pathlib import Path

import pytest

from brain79.config import set_project_root
from brain79.core.init_project import init_project
from brain79.core.validation import ValidationError, validate_article_content
from brain79.core.wiki import write_article


@pytest.fixture
def setup_wiki_root(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_validate_valid_feature_article() -> None:
    content = (
        "---\n"
        "type: feature\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-08-11\n"
        "---\n\n"
        "# Feature Title\n"
    )
    result = validate_article_content("features/my-feature.md", content)
    assert result == content


def test_validate_missing_frontmatter_raises() -> None:
    content = "# Feature without frontmatter"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("features/my-feature.md", content)
    assert exc_info.value.rule == "frontmatter_missing"


def test_validate_exempt_files() -> None:
    # SCHEMA.md and _raw/ files bypass validation
    raw_content = "# Raw session without frontmatter"
    res1 = validate_article_content("_raw/sessions/session1.md", raw_content)
    assert res1 == raw_content

    schema_content = "# Schema Template"
    res2 = validate_article_content("SCHEMA.md", schema_content)
    assert res2 == schema_content


def test_validate_force_skip() -> None:
    content = "# Content without frontmatter"
    res = validate_article_content("features/skip.md", content, force_skip=True)
    assert "force_validation_skipped: true" in res


def test_validate_index_oversized(monkeypatch: pytest.MonkeyPatch) -> None:
    # Build INDEX.md with 151 lines
    lines = ["# Index"] + [f"- item {i}" for i in range(155)]
    content = "\n".join(lines)
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "index_oversized"


def test_validate_index_max_lines_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAIN79_INDEX_MAX_LINES", "200")
    lines = ["# Index"] + [f"- item {i}" for i in range(155)]
    content = "\n".join(lines)
    res = validate_article_content("INDEX.md", content)
    assert res == content


def test_validate_index_prohibited_header() -> None:
    content = "# Index\n\n## Project\nText\n\n## Invalid Section Header\nText\n"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "index_prohibited_header"


def test_index_does_not_block_project_narrative() -> None:
    content = "# Index\n\n## Project\n- We chose Postgres for the backend.\n- Trade-off between simplicity and flexibility.\n- The team decided to ship Friday.\n"
    res = validate_article_content("INDEX.md", content)
    assert res == content


def test_index_does_not_block_decision_in_code_fence() -> None:
    content = "# Index\n\n## Project\n\n```yaml\n- Decision: use this format\n## ADR Log\n```\n"
    res = validate_article_content("INDEX.md", content)
    assert res == content


def test_index_does_not_block_decision_in_mixed_fence() -> None:
    content = (
        "# Index\n\n## Project\n\n"
        "```markdown\n"
        "To use tilde fences:\n\n"
        "~~~yaml\n"
        "- Decision: example\n"
        "~~~\n"
        "```\n"
    )
    res = validate_article_content("INDEX.md", content)
    assert res == content


def test_index_blocks_decision_bullet() -> None:
    content = "# Index\n\n## Project\n- Decision: use Yjs for real-time sync.\n"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "index_prohibited_content"


def test_index_blocks_adr_bullet() -> None:
    content = "# Index\n\n## Project\n- ADR-001: Adopt event sourcing.\n"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "index_prohibited_content"


def test_index_blocks_spanish_decision() -> None:
    content = "# Index\n\n## Project\n- Decisión: stack MERN.\n"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "index_prohibited_content"


def test_index_blocks_td_bullet() -> None:
    content = "# Index\n\n## Project\n- TD-123: Fix memory leak.\n"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "index_prohibited_content"


def test_index_with_valid_frontmatter() -> None:
    content = "---\ntype: navigation\nlast_updated: 2026-08-11\n---\n\n# Index\n\n## Project\nProject overview\n"
    res = validate_article_content("INDEX.md", content)
    assert res == content


def test_index_with_invalid_frontmatter_type() -> None:
    content = "---\ntype: product\nlast_updated: 2026-08-11\n---\n\n# Index\n"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "type_location_mismatch"


def test_index_with_missing_frontmatter_type() -> None:
    content = "---\nlast_updated: 2026-08-11\n---\n\n# Index\n"
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("INDEX.md", content)
    assert exc_info.value.rule == "frontmatter_missing_type"


def test_write_article_validation_integration(setup_wiki_root: Path) -> None:
    valid_content = (
        "---\n"
        "type: feature\n"
        "status: planned\n"
        "version: 0.1.0\n"
        "last_updated: 2026-08-11\n"
        "---\n\n"
        "# Integration Feature\n"
    )
    msg = write_article("features/integration.md", valid_content)
    assert msg == "Written: features/integration.md"

    # Writing invalid article without force skip should fail
    invalid_content = "# No frontmatter"
    with pytest.raises(ValidationError):
        write_article("features/invalid.md", invalid_content)

    # Writing invalid article with force skip should succeed
    msg2 = write_article("features/invalid.md", invalid_content, force_validation_skip=True)
    assert msg2 == "Written: features/invalid.md"
