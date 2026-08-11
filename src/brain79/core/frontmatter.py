import csv
from datetime import date
from pathlib import Path
import re
from typing import Any


class FrontmatterError(ValueError):
    """Raised when frontmatter is missing or malformed."""

    pass


class ValidationError(ValueError):
    """Raised when wiki validation fails. Has structured attributes for CLI/MCP reporting."""

    def __init__(self, rule: str, path: str, message: str, actionable: str) -> None:
        super().__init__(message)
        self.rule = rule
        self.path = path
        self.message = message
        self.actionable = actionable

    def format_user_message(self) -> str:
        return f"{self.message}\n\nAction: {self.actionable}"


# Schema per type: required fields + optional fields + enum constraints
TYPE_SCHEMA: dict[str, dict[str, Any]] = {
    "navigation": {
        "required": ["type", "last_updated"],
        "optional": [],
        "enum": {},
    },
    "handoff": {
        "required": ["type", "session_type", "previous_ref", "last_updated"],
        "optional": ["supersedes", "related", "owner", "schema_version"],
        "enum": {
            "session_type": ["feature", "bugfix", "research", "brainstorming"],
        },
    },
    "product": {
        "required": ["type", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {},
    },
    "architecture": {
        "required": ["type", "stability", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {
            "stability": ["experimental", "stable", "legacy"],
        },
    },
    "feature": {
        "required": ["type", "status", "version", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {
            "status": ["planned", "in_progress", "shipped", "deprecated", "legacy"],
        },
    },
    "decision": {
        "required": ["type", "status", "date", "deciders", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {
            "status": ["proposed", "accepted", "superseded", "rejected", "legacy"],
        },
    },
    "changelog": {
        "required": ["type", "version", "date", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {},
    },
    "raw_session": {
        "required": ["type", "session_id", "session_type", "last_updated"],
        "optional": [],
        "enum": {
            "session_type": ["feature", "bugfix", "research", "brainstorming"],
        },
    },
    "raw_commit": {
        "required": ["type", "commit_sha", "last_updated"],
        "optional": [],
        "enum": {},
    },
}

# Mapping of location prefix -> expected type
LOCATION_TO_TYPE: dict[str, str] = {
    "INDEX.md": "navigation",
    "handoffs": "handoff",
    "product": "product",
    "architecture": "architecture",
    "features": "feature",
    "decisions": "decision",
    "changelog": "changelog",
    "_raw/sessions": "raw_session",
    "_raw/commits": "raw_commit",
}

# Allowed unknown keys (for backward compatibility with bootstrap metadata and force skip)
ALLOWED_UNKNOWN_KEYS: set[str] = {
    "bootstrap",
    "generated_by",
    "generated_at",
    "project_type",
    "force_validation_skipped",
}


def _normalize_content(content: str) -> str:
    """Strip BOM and normalize line endings to LF."""
    if content.startswith("\ufeff"):
        content = content[1:]
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _clean_value(val: str) -> str:
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return val.strip()


def _parse_inline_list(val_str: str) -> list[str]:
    reader = csv.reader([val_str], skipinitialspace=True)
    items = next(reader, [])
    return [_clean_value(i) for i in items if i.strip()]


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse line-based frontmatter from markdown content.

    Supports:
        - `key: value` (simple string)
        - `key:` (empty value)
        - `key: [item1, item2]` (inline list)
        - `key:\n  - item1\n  - item2` (multi-line list)

    Returns:
        (metadata_dict, body_without_frontmatter)

    Raises:
        FrontmatterError if frontmatter is missing or malformed.
    """
    content = _normalize_content(content)
    if not content.startswith("---\n") and content != "---":
        raise FrontmatterError(
            "Article lacks frontmatter. Every article (except INDEX.md, SCHEMA.md) "
            "MUST start with YAML frontmatter between `---` delimiters."
        )

    lines = content.split("\n")
    end_idx = next(
        (i for i in range(1, len(lines)) if lines[i] == "---"),
        None,
    )
    if end_idx is None:
        raise FrontmatterError(
            f"Frontmatter opened at line 1 but no closing `---` found "
            f"(searched {len(lines)} lines)."
        )

    metadata: dict[str, Any] = {}
    i = 1
    while i < end_idx:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        m = re.match(r"^([a-z_][a-z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            raise FrontmatterError(
                f"Frontmatter malformed at line {i + 1}: expected `key: value` "
                f"but got `{line!r}`"
            )

        key, raw_val = m.group(1), m.group(2).strip()

        # Multi-line list check
        if raw_val == "" and i + 1 < end_idx and lines[i + 1].lstrip().startswith("- "):
            items: list[str] = []
            i += 1
            while i < end_idx:
                list_match = re.match(r"^\s*-\s+(.*)$", lines[i])
                if not list_match:
                    break
                items.append(_clean_value(list_match.group(1)))
                i += 1
            metadata[key] = items
            continue

        # Inline list check `[a, b, c]`
        if raw_val.startswith("[") and raw_val.endswith("]"):
            metadata[key] = _parse_inline_list(raw_val[1:-1])
            i += 1
            continue

        metadata[key] = _clean_value(raw_val)
        i += 1

    body = "\n".join(lines[end_idx + 1:]).lstrip("\n")
    return metadata, body


def validate_frontmatter(meta: dict[str, Any], path: str) -> None:
    """Validate that frontmatter metadata conforms to the schema for the given path."""
    declared_type = meta.get("type")
    if not declared_type:
        raise ValidationError(
            rule="frontmatter_missing_type",
            path=path,
            message="Frontmatter lacks `type` field.",
            actionable="Add `type: <one of: navigation, handoff, product, architecture, feature, decision, changelog, raw_session, raw_commit>` to frontmatter.",
        )

    if declared_type not in TYPE_SCHEMA:
        raise ValidationError(
            rule="frontmatter_invalid_type",
            path=path,
            message=f"Unknown frontmatter type '{declared_type}'.",
            actionable=f"Use one of: {sorted(TYPE_SCHEMA.keys())}",
        )

    schema = TYPE_SCHEMA[declared_type]

    # Required fields check
    for field in schema["required"]:
        if field not in meta:
            raise ValidationError(
                rule="frontmatter_missing_field",
                path=path,
                message=f"Frontmatter for type='{declared_type}' lacks required field `{field}`.",
                actionable=f"Add `{field}: <value>` to frontmatter.",
            )

    # Enum checks
    for field, allowed_values in schema["enum"].items():
        val = meta.get(field)
        if val is not None and val not in allowed_values:
            raise ValidationError(
                rule="frontmatter_invalid_enum",
                path=path,
                message=f"Field `{field}` has value '{val}' but must be one of: {allowed_values}.",
                actionable=f"Change `{field}` to one of: {allowed_values}",
            )

    # Date check for last_updated
    last_updated = meta.get("last_updated")
    if last_updated:
        try:
            date.fromisoformat(str(last_updated))
        except ValueError:
            raise ValidationError(
                rule="frontmatter_invalid_date",
                path=path,
                message=f"`last_updated` must be ISO date (YYYY-MM-DD), got '{last_updated}'.",
                actionable="Use format YYYY-MM-DD.",
            )

    # Date check for date field if applicable
    if declared_type in ("decision", "changelog") and "date" in meta:
        d_val = str(meta["date"])
        try:
            date.fromisoformat(d_val)
        except ValueError:
            raise ValidationError(
                rule="frontmatter_invalid_date",
                path=path,
                message=f"`date` must be ISO date (YYYY-MM-DD), got '{d_val}'.",
                actionable="Use format YYYY-MM-DD.",
            )

    # Unknown keys check
    for key in meta:
        if (
            key not in schema["required"]
            and key not in schema["optional"]
            and key not in ALLOWED_UNKNOWN_KEYS
        ):
            raise ValidationError(
                rule="frontmatter_unknown_key",
                path=path,
                message=f"Unknown frontmatter key '{key}' for type='{declared_type}'.",
                actionable=f"Remove `{key}` or add it to ALLOWED_UNKNOWN_KEYS if intentional.",
            )


def validate_location_consistency(meta: dict[str, Any], path: str) -> None:
    """Validate that declared type matches expected location.

    Caller MUST pass a relative path that has been resolved against wiki_root.
    Path traversal prevention is handled upstream by _safe_resolve in wiki.py.
    """
    declared_type = meta.get("type")
    if not declared_type:
        return

    rel = Path(path)
    expected_type = None
    for location_prefix, expected in LOCATION_TO_TYPE.items():
        if str(rel) == location_prefix or str(rel).startswith(location_prefix + "/"):
            expected_type = expected
            break

    if expected_type is None:
        raise ValidationError(
            rule="location_unknown",
            path=path,
            message=f"Cannot determine expected type for location '{rel.parts[0] if len(rel.parts) > 1 else rel.name}'.",
            actionable="Move file to a known directory or add the location to LOCATION_TO_TYPE.",
        )

    if declared_type != expected_type:
        raise ValidationError(
            rule="type_location_mismatch",
            path=path,
            message=f"type='{declared_type}' but file is in '{rel.parts[0] if len(rel.parts) > 1 else '.'}' (expected type='{expected_type}').",
            actionable=f"Move file to a directory matching type='{declared_type}', or change frontmatter type to '{expected_type}'.",
        )
