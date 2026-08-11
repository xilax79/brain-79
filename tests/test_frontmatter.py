import pytest

from brain79.core.frontmatter import (
    FrontmatterError,
    parse_frontmatter,
    validate_frontmatter,
    validate_location_consistency,
)
from brain79.core.validation import ValidationError


def test_parse_frontmatter_valid_simple() -> None:
    content = "---\ntype: product\nlast_updated: 2026-08-11\n---\n\n# Header\nBody text"
    meta, body = parse_frontmatter(content)
    assert meta == {"type": "product", "last_updated": "2026-08-11"}
    assert body == "# Header\nBody text"


def test_parse_frontmatter_inline_and_multiline_lists() -> None:
    content = (
        "---\n"
        "type: decision\n"
        "status: accepted\n"
        "date: 2026-08-11\n"
        "deciders: [alice, bob]\n"
        "last_updated: 2026-08-11\n"
        "related:\n"
        "  - item1\n"
        "  - item2\n"
        "---\n\n# Body"
    )
    meta, body = parse_frontmatter(content)
    assert meta["deciders"] == ["alice", "bob"]
    assert meta["related"] == ["item1", "item2"]
    assert body == "# Body"


def test_parse_frontmatter_quoted_strings() -> None:
    content = '---\ntype: "product"\nlast_updated: \'2026-08-11\'\n---\n\n# Header'
    meta, body = parse_frontmatter(content)
    assert meta == {"type": "product", "last_updated": "2026-08-11"}


def test_parse_frontmatter_inline_list_with_quotes_and_commas() -> None:
    content = '---\ntype: decision\nstatus: accepted\ndate: 2026-08-11\ndeciders: ["alice, dev", "bob"]\nlast_updated: 2026-08-11\n---\n\n# Body'
    meta, body = parse_frontmatter(content)
    assert meta["deciders"] == ["alice, dev", "bob"]


def test_parse_frontmatter_crlf() -> None:
    content = "---\r\ntype: product\r\nlast_updated: 2026-08-11\r\n---\r\n\r\n# Header\r\nBody"
    meta, body = parse_frontmatter(content)
    assert meta == {"type": "product", "last_updated": "2026-08-11"}
    assert body == "# Header\nBody"


def test_parse_frontmatter_utf8_bom() -> None:
    content = "\ufeff---\ntype: product\nlast_updated: 2026-08-11\n---\n\n# Header"
    meta, body = parse_frontmatter(content)
    assert meta == {"type": "product", "last_updated": "2026-08-11"}


def test_parse_frontmatter_missing_opening() -> None:
    content = "# Title\nNo frontmatter"
    with pytest.raises(FrontmatterError, match="Article lacks frontmatter"):
        parse_frontmatter(content)


def test_parse_frontmatter_missing_closing() -> None:
    content = "---\ntype: product\nlast_updated: 2026-08-11\n# No closing line"
    with pytest.raises(FrontmatterError, match="no closing `---` found"):
        parse_frontmatter(content)


def test_parse_frontmatter_malformed_line() -> None:
    content = "---\ninvalid_line_without_colon\n---"
    with pytest.raises(FrontmatterError, match="Frontmatter malformed"):
        parse_frontmatter(content)


def test_validate_frontmatter_valid_feature() -> None:
    meta = {
        "type": "feature",
        "status": "planned",
        "version": "0.1.0",
        "last_updated": "2026-08-11",
    }
    validate_frontmatter(meta, "features/test.md")  # Should not raise


def test_validate_frontmatter_legacy_status() -> None:
    meta = {
        "type": "decision",
        "status": "legacy",
        "date": "2026-08-11",
        "deciders": ["migrated"],
        "last_updated": "2026-08-11",
    }
    validate_frontmatter(meta, "decisions/test.md")  # legacy status is valid


def test_validate_frontmatter_missing_type() -> None:
    meta = {"last_updated": "2026-08-11"}
    with pytest.raises(ValidationError) as exc_info:
        validate_frontmatter(meta, "features/test.md")
    assert exc_info.value.rule == "frontmatter_missing_type"


def test_validate_frontmatter_invalid_type() -> None:
    meta = {"type": "unknown_type", "last_updated": "2026-08-11"}
    with pytest.raises(ValidationError) as exc_info:
        validate_frontmatter(meta, "features/test.md")
    assert exc_info.value.rule == "frontmatter_invalid_type"


def test_validate_frontmatter_missing_required_field() -> None:
    meta = {"type": "feature", "last_updated": "2026-08-11"}
    with pytest.raises(ValidationError) as exc_info:
        validate_frontmatter(meta, "features/test.md")
    assert exc_info.value.rule == "frontmatter_missing_field"


def test_validate_frontmatter_invalid_enum() -> None:
    meta = {
        "type": "feature",
        "status": "invalid_status",
        "version": "0.1.0",
        "last_updated": "2026-08-11",
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_frontmatter(meta, "features/test.md")
    assert exc_info.value.rule == "frontmatter_invalid_enum"


def test_validate_frontmatter_invalid_date() -> None:
    meta = {
        "type": "product",
        "last_updated": "11-08-2026",  # Not ISO YYYY-MM-DD
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_frontmatter(meta, "product/test.md")
    assert exc_info.value.rule == "frontmatter_invalid_date"


def test_validate_frontmatter_unknown_key() -> None:
    meta = {
        "type": "product",
        "last_updated": "2026-08-11",
        "unknown_extra_key": "val",
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_frontmatter(meta, "product/test.md")
    assert exc_info.value.rule == "frontmatter_unknown_key"


def test_validate_frontmatter_allowed_unknown_key() -> None:
    meta = {
        "type": "product",
        "last_updated": "2026-08-11",
        "force_validation_skipped": True,
    }
    validate_frontmatter(meta, "product/test.md")  # Allowed


def test_validate_location_consistency_valid() -> None:
    meta = {"type": "feature"}
    validate_location_consistency(meta, "features/login.md")


def test_validate_location_consistency_mismatch() -> None:
    meta = {"type": "decision"}
    with pytest.raises(ValidationError) as exc_info:
        validate_location_consistency(meta, "features/login.md")
    assert exc_info.value.rule == "type_location_mismatch"


def test_validate_location_consistency_unknown_location() -> None:
    meta = {"type": "feature"}
    with pytest.raises(ValidationError) as exc_info:
        validate_location_consistency(meta, "random_folder/login.md")
    assert exc_info.value.rule == "location_unknown"
