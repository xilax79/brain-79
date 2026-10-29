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

    def __init__(
        self,
        rule: str,
        path: str,
        message: str,
        actionable: str,
        issues: list[dict[str, str]] | None = None,
        target_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.rule = rule
        self.path = path
        self.message = message
        self.actionable = actionable
        self.issues = issues or [
            {"rule": rule, "path": path, "message": message, "actionable": actionable}
        ]
        self.target_type = target_type

    def format_user_message(self) -> str:
        if len(self.issues) <= 1:
            res = f"{self.message}\n\nAction: {self.actionable}"
        else:
            lines = [f"Validation failed for '{self.path}' with {len(self.issues)} errors:"]
            for issue in self.issues:
                lines.append(f"- [{issue['rule']}] {issue['message']}")
                lines.append(f"  Fix: {issue['actionable']}")
            res = "\n".join(lines)

        t = self.target_type or infer_type_for_path(self.path)
        if t and t in TYPE_SCHEMA:
            tpl = generate_frontmatter_template(t)
            res += f"\n\nReady-to-paste frontmatter template for '{t}':\n```yaml\n{tpl}\n```"
        return res


# Schema per type: required fields + optional fields + enum constraints
TYPE_SCHEMA: dict[str, dict[str, Any]] = {
    "navigation": {
        "required": ["type", "last_updated"],
        "optional": ["summary"],
        "enum": {},
    },
    "handoff": {
        "required": ["type", "session_type", "previous_ref", "last_updated"],
        "optional": ["summary", "supersedes", "related", "owner", "schema_version"],
        "enum": {
            "session_type": ["feature", "bugfix", "research", "brainstorming"],
        },
    },
    "product": {
        "required": ["type", "last_updated"],
        "optional": ["summary", "supersedes", "related", "owner"],
        "enum": {},
    },
    "architecture": {
        "required": ["type", "stability", "last_updated"],
        "optional": ["summary", "supersedes", "related", "owner"],
        "enum": {
            "stability": ["experimental", "stable", "legacy"],
        },
    },
    "feature": {
        "required": ["type", "status", "version", "last_updated"],
        "optional": ["summary", "supersedes", "related", "owner"],
        "enum": {
            "status": ["planned", "in_progress", "shipped", "deprecated", "legacy"],
        },
    },
    "decision": {
        "required": ["type", "status", "date", "deciders", "last_updated"],
        "optional": ["summary", "supersedes", "related", "owner"],
        "enum": {
            "status": ["proposed", "accepted", "superseded", "rejected", "legacy"],
        },
    },
    "changelog": {
        "required": ["type", "version", "date", "last_updated"],
        "optional": ["summary", "supersedes", "related", "owner"],
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
    "summary",
    "title",
    "tags",
    "created",
}


def infer_type_for_path(path: str) -> str | None:
    """Infer expected frontmatter type from relative file path."""
    rel = Path(path)
    for prefix, expected_type in LOCATION_TO_TYPE.items():
        if str(rel) == prefix or str(rel).startswith(prefix + "/"):
            return expected_type
    return None


def generate_frontmatter_template(target_type: str) -> str:
    """Generate a ready-to-paste frontmatter snippet for target type."""
    today = date.today().isoformat()
    if target_type == "feature":
        return f"---\ntype: feature\nsummary: <one-line summary of feature>\nstatus: planned  # <planned|in_progress|shipped|deprecated|legacy>\nversion: 0.1.0\nlast_updated: {today}\n---"
    elif target_type == "decision":
        return f"---\ntype: decision\nsummary: <one-line summary of decision>\nstatus: proposed  # <proposed|accepted|superseded|rejected|legacy>\ndate: {today}\ndeciders: [author]\nlast_updated: {today}\n---"
    elif target_type == "architecture":
        return f"---\ntype: architecture\nsummary: <one-line summary of architecture>\nstability: experimental  # <experimental|stable|legacy>\nlast_updated: {today}\n---"
    elif target_type == "product":
        return f"---\ntype: product\nsummary: <one-line summary of product vision or domain>\nlast_updated: {today}\n---"
    elif target_type == "changelog":
        return f"---\ntype: changelog\nsummary: <one-line summary of changelog>\nversion: 0.1.0\ndate: {today}\nlast_updated: {today}\n---"
    elif target_type == "navigation":
        return f"---\ntype: navigation\nlast_updated: {today}\n---"
    elif target_type == "handoff":
        return f"---\ntype: handoff\nsession_type: feature  # <feature|bugfix|research|brainstorming>\nprevious_ref: latest\nlast_updated: {today}\n---"
    else:
        return f"---\ntype: {target_type}\nsummary: <one-line summary>\nlast_updated: {today}\n---"


def dump_frontmatter(meta: dict[str, Any], body: str) -> str:
    """Format metadata dictionary and body into markdown with YAML frontmatter."""
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    clean_body = body.lstrip("\n")
    return "\n".join(lines) + ("\n" + clean_body if clean_body else "")


def autofill_deterministic_fields(meta: dict[str, Any], path: str) -> dict[str, Any]:
    """Auto-fill deterministic frontmatter fields and strip hallucinated keys."""
    today = date.today().isoformat()

    # 1. Infer type if missing (for non-INDEX files)
    if ("type" not in meta or not meta["type"]) and path != "INDEX.md":
        inferred = infer_type_for_path(path)
        if inferred:
            meta["type"] = inferred

    # 2. Set last_updated to today if missing or empty
    if "last_updated" not in meta or not meta["last_updated"]:
        meta["last_updated"] = today

    # 3. Default date to today for decision and changelog if missing
    if meta.get("type") in ("decision", "changelog") and "date" not in meta:
        meta["date"] = today

    # 4. Strip commonly hallucinated keys so files stay clean
    for hallucinated in ("title", "tags", "created"):
        meta.pop(hallucinated, None)

    return meta


def get_schema_documentation(target_type: str | None = None) -> str:
    """Generate schema documentation and templates directly from TYPE_SCHEMA."""
    types_to_show = [target_type] if target_type and target_type in TYPE_SCHEMA else sorted(TYPE_SCHEMA.keys())

    if target_type and target_type not in TYPE_SCHEMA:
        return f"Unknown type '{target_type}'. Valid types: {', '.join(sorted(TYPE_SCHEMA.keys()))}"

    lines = ["# Brain-79 Frontmatter Schema Reference", ""]
    for t in types_to_show:
        schema = TYPE_SCHEMA[t]
        lines.append(f"## Type: `{t}`")
        lines.append(f"- **Required fields**: {', '.join(schema['required']) if schema['required'] else 'none'}")
        lines.append(f"- **Optional fields**: {', '.join(schema['optional']) if schema['optional'] else 'none'}")
        if schema["enum"]:
            for field, vals in schema["enum"].items():
                lines.append(f"- **Enum `{field}`**: {', '.join(vals)}")
        lines.append("\nTemplate:")
        lines.append("```yaml")
        lines.append(generate_frontmatter_template(t))
        lines.append("```\n")

    return "\n".join(lines).rstrip()


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
    """Validate that frontmatter metadata conforms to the schema for the given path.

    Collects all violations across fields, enums, dates, and unknown keys in a single pass.
    """
    issues: list[dict[str, str]] = []

    declared_type = meta.get("type")
    if not declared_type:
        issues.append({
            "rule": "frontmatter_missing_type",
            "message": "Frontmatter lacks `type` field.",
            "actionable": f"Add `type: <one of: {', '.join(sorted(TYPE_SCHEMA.keys()))}>` to frontmatter.",
        })
    elif declared_type not in TYPE_SCHEMA:
        issues.append({
            "rule": "frontmatter_invalid_type",
            "message": f"Unknown frontmatter type '{declared_type}'.",
            "actionable": f"Use one of: {sorted(TYPE_SCHEMA.keys())}",
        })

    if declared_type and declared_type in TYPE_SCHEMA:
        schema = TYPE_SCHEMA[declared_type]

        # Required fields check
        for field in schema["required"]:
            if field not in meta:
                issues.append({
                    "rule": "frontmatter_missing_field",
                    "message": f"Frontmatter for type='{declared_type}' lacks required field `{field}`.",
                    "actionable": f"Add `{field}: <value>` to frontmatter.",
                })

        # Enum checks
        for field, allowed_values in schema["enum"].items():
            val = meta.get(field)
            if val is not None and val not in allowed_values:
                issues.append({
                    "rule": "frontmatter_invalid_enum",
                    "message": f"Field `{field}` has value '{val}' but must be one of: {allowed_values}.",
                    "actionable": f"Change `{field}` to one of: {allowed_values}",
                })

        # Date check for last_updated
        last_updated = meta.get("last_updated")
        if last_updated:
            try:
                date.fromisoformat(str(last_updated))
            except ValueError:
                issues.append({
                    "rule": "frontmatter_invalid_date",
                    "message": f"`last_updated` must be ISO date (YYYY-MM-DD), got '{last_updated}'.",
                    "actionable": "Use format YYYY-MM-DD.",
                })

        # Date check for date field if applicable
        if declared_type in ("decision", "changelog") and "date" in meta:
            d_val = str(meta["date"])
            try:
                date.fromisoformat(d_val)
            except ValueError:
                issues.append({
                    "rule": "frontmatter_invalid_date",
                    "message": f"`date` must be ISO date (YYYY-MM-DD), got '{d_val}'.",
                    "actionable": "Use format YYYY-MM-DD.",
                })

        # Unknown keys check
        for key in meta:
            if (
                key not in schema["required"]
                and key not in schema["optional"]
                and key not in ALLOWED_UNKNOWN_KEYS
            ):
                issues.append({
                    "rule": "frontmatter_unknown_key",
                    "message": f"Unknown frontmatter key '{key}' for type='{declared_type}'.",
                    "actionable": f"Remove `{key}` or add it to ALLOWED_UNKNOWN_KEYS if intentional.",
                })

    if issues:
        target_t = declared_type if declared_type in TYPE_SCHEMA else infer_type_for_path(path)
        if len(issues) == 1:
            raise ValidationError(
                rule=issues[0]["rule"],
                path=path,
                message=issues[0]["message"],
                actionable=issues[0]["actionable"],
                issues=issues,
                target_type=target_t,
            )
        else:
            msg_lines = "\n".join(f"- {i['message']}" for i in issues)
            act_lines = "\n".join(f"- {i['rule']}: {i['actionable']}" for i in issues)
            raise ValidationError(
                rule=issues[0]["rule"],
                path=path,
                message=f"Frontmatter validation failed for '{path}' with {len(issues)} violations:\n{msg_lines}",
                actionable=act_lines,
                issues=issues,
                target_type=target_t,
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
