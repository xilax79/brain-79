import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
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
        if t:
            tpl = generate_frontmatter_template(t)
            res += f"\n\nReady-to-paste frontmatter template for '{t}':\n```yaml\n{tpl}\n```"
        return res


# Built-in Profiles & Ontologies
SOFTWARE_PROFILE_SCHEMA: dict[str, dict[str, Any]] = {
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
        "required": ["type", "summary", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {},
    },
    "architecture": {
        "required": ["type", "summary", "stability", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {
            "stability": ["experimental", "stable", "legacy"],
        },
    },
    "feature": {
        "required": ["type", "summary", "status", "version", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {
            "status": ["planned", "in_progress", "shipped", "deprecated", "legacy"],
        },
    },
    "decision": {
        "required": ["type", "summary", "status", "date", "deciders", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {
            "status": ["proposed", "accepted", "superseded", "rejected", "legacy"],
        },
    },
    "changelog": {
        "required": ["type", "summary", "version", "date", "last_updated"],
        "optional": ["supersedes", "related", "owner"],
        "enum": {},
    },
    "raw_session": {
        "required": ["type", "session_id", "session_type", "last_updated"],
        "optional": ["instructions"],
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

SOFTWARE_LOCATION_TO_TYPE: dict[str, str] = {
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

GENERAL_PROFILE_SCHEMA: dict[str, dict[str, Any]] = {
    "navigation": {
        "required": ["type", "last_updated"],
        "optional": ["summary"],
        "enum": {},
    },
    "handoff": {
        "required": ["type", "session_type", "previous_ref", "last_updated"],
        "optional": ["summary", "supersedes", "related", "owner", "schema_version"],
        "enum": {
            "session_type": ["feature", "bugfix", "research", "brainstorming", "work", "general", "writing", "analysis"],
        },
    },
    "context": {
        "required": ["type", "summary", "last_updated"],
        "optional": ["supersedes", "related", "owner", "scope"],
        "enum": {},
    },
    "topic": {
        "required": ["type", "summary", "last_updated"],
        "optional": ["status", "supersedes", "related", "owner", "tags"],
        "enum": {
            "status": ["draft", "active", "archived", "legacy"],
        },
    },
    "decision": {
        "required": ["type", "summary", "status", "date", "last_updated"],
        "optional": ["deciders", "supersedes", "related", "owner"],
        "enum": {
            "status": ["proposed", "accepted", "superseded", "rejected", "legacy"],
        },
    },
    "log": {
        "required": ["type", "summary", "date", "last_updated"],
        "optional": ["version", "supersedes", "related", "owner"],
        "enum": {},
    },
    "raw_session": {
        "required": ["type", "session_id", "session_type", "last_updated"],
        "optional": ["instructions"],
        "enum": {
            "session_type": ["feature", "bugfix", "research", "brainstorming", "work", "general", "writing", "analysis"],
        },
    },
    "raw_commit": {
        "required": ["type", "commit_sha", "last_updated"],
        "optional": [],
        "enum": {},
    },
}

GENERAL_LOCATION_TO_TYPE: dict[str, str] = {
    "INDEX.md": "navigation",
    "handoffs": "handoff",
    "context": "context",
    "topics": "topic",
    "decisions": "decision",
    "log": "log",
    "_raw/sessions": "raw_session",
    "_raw/commits": "raw_commit",
}

# Backward compatibility module-level references (defaults to software profile)
TYPE_SCHEMA = SOFTWARE_PROFILE_SCHEMA
LOCATION_TO_TYPE = SOFTWARE_LOCATION_TO_TYPE


@dataclass
class ActiveSchema:
    """Represents a validated, resolved wiki schema profile and custom types."""

    profile: str
    types: dict[str, dict[str, Any]]
    location_to_type: dict[str, str]
    supports_technical_debt_leakage: bool = True


# In-memory schema cache: (resolved_wiki_root_str, schema_mtime_ns) -> ActiveSchema
_SCHEMA_CACHE: dict[tuple[str, int], ActiveSchema] = {}


def clear_schema_cache() -> None:
    """Clear in-memory schema cache (primarily used in tests)."""
    _SCHEMA_CACHE.clear()


def load_active_schema(wiki_root: Path | None = None) -> ActiveSchema:
    """Load and return the active schema for the given wiki root, cached by SCHEMA.md mtime."""
    if wiki_root is None:
        from brain79.config import get_wiki_root

        try:
            wiki_root = get_wiki_root()
        except Exception:
            wiki_root = Path.cwd() / ".brain-79"

    resolved_root = wiki_root.resolve()
    schema_file = resolved_root / "SCHEMA.md"

    mtime_ns = 0
    if schema_file.exists():
        try:
            mtime_ns = schema_file.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

    cache_key = (str(resolved_root), mtime_ns)
    if cache_key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[cache_key]

    # Resolve schema profile from SCHEMA.md frontmatter or fallback
    profile = "software"
    custom_types: dict[str, Any] = {}

    if schema_file.exists():
        try:
            content = schema_file.read_text(encoding="utf-8")
            if content.startswith("---\n"):
                meta, _ = parse_frontmatter(content)
                if meta:
                    profile = meta.get("profile", "software").strip().lower()
                    if "custom_types" in meta and isinstance(meta["custom_types"], dict):
                        custom_types = meta["custom_types"]
        except Exception:
            profile = "software"

    # Base profile selection
    if profile == "general":
        base_types = {k: {**v} for k, v in GENERAL_PROFILE_SCHEMA.items()}
        base_loc = {**GENERAL_LOCATION_TO_TYPE}
        supports_td = False
    else:
        profile = "software"
        base_types = {k: {**v} for k, v in SOFTWARE_PROFILE_SCHEMA.items()}
        base_loc = {**SOFTWARE_LOCATION_TO_TYPE}
        supports_td = True

    # Integrate custom_types
    for custom_name, custom_cfg in custom_types.items():
        if not isinstance(custom_cfg, dict):
            continue
        req = custom_cfg.get("required", ["type", "summary", "last_updated"])
        if "type" not in req:
            req.insert(0, "type")
        if "summary" not in req:
            req.insert(1, "summary")
        if "last_updated" not in req:
            req.append("last_updated")

        opt = custom_cfg.get("optional", ["supersedes", "related", "owner"])
        enums = custom_cfg.get("enum", {})
        dir_name = custom_cfg.get("directory", custom_name)

        base_types[custom_name] = {
            "required": req,
            "optional": opt,
            "enum": enums,
        }
        base_loc[dir_name] = custom_name

    active = ActiveSchema(
        profile=profile,
        types=base_types,
        location_to_type=base_loc,
        supports_technical_debt_leakage=supports_td,
    )
    _SCHEMA_CACHE[cache_key] = active
    return active


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


def infer_type_for_path(path: str, schema: ActiveSchema | None = None) -> str | None:
    """Infer expected frontmatter type from relative file path."""
    active_loc = schema.location_to_type if schema else load_active_schema().location_to_type
    rel = Path(path)
    for prefix, expected_type in active_loc.items():
        if str(rel) == prefix or str(rel).startswith(prefix + "/"):
            return expected_type
    return None


def generate_frontmatter_template(target_type: str, schema: ActiveSchema | None = None) -> str:
    """Generate a ready-to-paste frontmatter snippet for target type."""
    today = date.today().isoformat()
    active_types = schema.types if schema else load_active_schema().types

    if target_type == "feature":
        return f"---\ntype: feature\nsummary: <one-line summary of feature>\nstatus: planned  # <planned|in_progress|shipped|deprecated|legacy>\nversion: 0.1.0\nlast_updated: {today}\n---"
    elif target_type == "decision":
        dec_schema = active_types.get("decision", {})
        has_deciders = "deciders" in dec_schema.get("required", [])
        deciders_line = "deciders: [author]\n" if has_deciders else ""
        return f"---\ntype: decision\nsummary: <one-line summary of decision>\nstatus: proposed  # <proposed|accepted|superseded|rejected|legacy>\ndate: {today}\n{deciders_line}last_updated: {today}\n---"
    elif target_type == "architecture":
        return f"---\ntype: architecture\nsummary: <one-line summary of architecture>\nstability: experimental  # <experimental|stable|legacy>\nlast_updated: {today}\n---"
    elif target_type == "product":
        return f"---\ntype: product\nsummary: <one-line summary of product vision or domain>\nlast_updated: {today}\n---"
    elif target_type == "context":
        return f"---\ntype: context\nsummary: <one-line summary of project context or goals>\nlast_updated: {today}\n---"
    elif target_type == "topic":
        return f"---\ntype: topic\nsummary: <one-line summary of topic or research>\nstatus: active  # <draft|active|archived|legacy>\nlast_updated: {today}\n---"
    elif target_type == "log":
        return f"---\ntype: log\nsummary: <one-line summary of log entry>\ndate: {today}\nlast_updated: {today}\n---"
    elif target_type == "changelog":
        return f"---\ntype: changelog\nsummary: <one-line summary of changelog>\nversion: 0.1.0\ndate: {today}\nlast_updated: {today}\n---"
    elif target_type == "navigation":
        return f"---\ntype: navigation\nlast_updated: {today}\n---"
    elif target_type == "handoff":
        return f"---\ntype: handoff\nsession_type: feature  # <feature|bugfix|research|brainstorming>\nprevious_ref: latest\nlast_updated: {today}\n---"
    else:
        # Dynamic template for custom types
        cfg = active_types.get(target_type, {})
        lines = ["---", f"type: {target_type}", "summary: <one-line summary>"]
        for req in cfg.get("required", []):
            if req not in ("type", "summary", "last_updated"):
                enum_opts = cfg.get("enum", {}).get(req)
                comment = f"  # <{'|'.join(enum_opts)}>" if enum_opts else ""
                val = enum_opts[0] if enum_opts else f"<{req}>"
                lines.append(f"{req}: {val}{comment}")
        lines.append(f"last_updated: {today}")
        lines.append("---")
        return "\n".join(lines)


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
            s_val = str(v)
            # Quote if value contains characters that could break naive YAML parsers or SafeLoader
            # like leading brackets, colons, asterisks, or backticks
            if any(ch in s_val for ch in (":", "`", "*", "&", "#", "{", "}", "[", "]", "%", "@", "!")):
                clean_s = s_val.replace('"', '\\"')
                lines.append(f'{k}: "{clean_s}"')
            else:
                lines.append(f"{k}: {s_val}")
    lines.append("---")
    lines.append("")
    clean_body = body.lstrip("\n")
    return "\n".join(lines) + ("\n" + clean_body if clean_body else "")


def sanitize_summary(summary_text: str) -> str:
    """Sanitize summary text into a clean single line safe for frontmatter serialization.

    Prevents raw newlines, leading/trailing whitespace, and ensures text starting/ending
    with brackets is not accidentally deserialized as a YAML list by parse_frontmatter.
    """
    clean = " ".join(summary_text.replace("\r", " ").replace("\n", " ").split()).strip()
    if not clean:
        return ""

    # If the text starts with '[' and ends with ']' or contains quotes, quote it safely
    # so YAML parsers treat it strictly as a string, not an inline list.
    if clean.startswith("[") and clean.endswith("]"):
        clean = f'"{clean}"'

    return clean


def autofill_deterministic_fields(
    meta: dict[str, Any],
    path: str,
    body: str = "",
    schema: ActiveSchema | None = None,
) -> dict[str, Any]:
    """Auto-fill deterministic frontmatter fields and strip hallucinated keys."""
    today = date.today().isoformat()
    active = schema or load_active_schema()
    active_types = active.types

    # 1. Infer type if missing (for non-INDEX files)
    if ("type" not in meta or not meta["type"]) and path != "INDEX.md":
        inferred = infer_type_for_path(path, schema=active)
        if inferred:
            meta["type"] = inferred

    # 2. Auto-fill summary if missing from body if available
    if ("summary" not in meta or not meta["summary"]) and path != "INDEX.md" and body:
        from brain79.core.navigation import extract_title_and_summary

        _, extracted_summary = extract_title_and_summary(body)
        if extracted_summary:
            meta["summary"] = sanitize_summary(extracted_summary)
    elif "summary" in meta and meta["summary"] and isinstance(meta["summary"], str):
        meta["summary"] = sanitize_summary(meta["summary"])

    # 3. Set last_updated to today if missing or empty
    if "last_updated" not in meta or not meta["last_updated"]:
        meta["last_updated"] = today

    # 4. Default date to today if 'date' is required or accepted on this type
    declared_type = meta.get("type")
    type_cfg = active_types.get(declared_type, {}) if declared_type else {}
    if ("date" in type_cfg.get("required", []) or declared_type in ("decision", "changelog", "log")) and "date" not in meta:
        meta["date"] = today

    # 5. Strip commonly hallucinated keys only if they are NOT allowed in the active type
    allowed_keys = set(type_cfg.get("required", [])) | set(type_cfg.get("optional", []))
    for candidate in ("title", "tags", "created"):
        if candidate not in allowed_keys:
            meta.pop(candidate, None)

    return meta


def get_schema_documentation(
    target_type: str | None = None, schema: ActiveSchema | None = None
) -> str:
    """Generate schema documentation and templates directly from active schema."""
    active = schema or load_active_schema()
    active_types = active.types
    types_to_show = [target_type] if target_type and target_type in active_types else sorted(active_types.keys())

    if target_type and target_type not in active_types:
        return f"Unknown type '{target_type}'. Valid types for profile '{active.profile}': {', '.join(sorted(active_types.keys()))}"

    lines = [f"# Brain-79 Frontmatter Schema Reference (Profile: {active.profile})", ""]
    for t in types_to_show:
        cfg = active_types[t]
        lines.append(f"## Type: `{t}`")
        lines.append(f"- **Required fields**: {', '.join(cfg['required']) if cfg['required'] else 'none'}")
        lines.append(f"- **Optional fields**: {', '.join(cfg['optional']) if cfg['optional'] else 'none'}")
        if cfg["enum"]:
            for field, vals in cfg["enum"].items():
                lines.append(f"- **Enum `{field}`**: {', '.join(vals)}")
        lines.append("\nTemplate:")
        lines.append("```yaml")
        lines.append(generate_frontmatter_template(t, schema=active))
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

    # Parse YAML mapping while keeping dates as ISO strings
    raw_yaml_block = "\n".join(lines[1:end_idx])
    metadata: dict[str, Any] = {}
    try:
        import yaml
        parsed = yaml.safe_load(raw_yaml_block)
        if isinstance(parsed, dict):
            # Normalize dates/numbers to strings where expected (e.g. date objects to YYYY-MM-DD)
            norm: dict[str, Any] = {}
            for k, v in parsed.items():
                if isinstance(v, (date, datetime)):
                    norm[k] = v.isoformat()
                else:
                    norm[k] = v
            metadata = norm
        elif parsed is not None:
            raise FrontmatterError("Frontmatter malformed: must be a YAML mapping (key-value dictionary).")
    except Exception as e:
        if isinstance(e, FrontmatterError):
            raise
        raise FrontmatterError(f"Frontmatter malformed YAML: {e}")

    body = "\n".join(lines[end_idx + 1:]).lstrip("\n")
    return metadata, body


def validate_frontmatter(
    meta: dict[str, Any], path: str, schema: ActiveSchema | None = None
) -> None:
    """Validate that frontmatter metadata conforms to the schema for the given path.

    Collects all violations across fields, enums, dates, and unknown keys in a single pass.
    """
    issues: list[dict[str, str]] = []
    active = schema or load_active_schema()
    active_types = active.types

    declared_type = meta.get("type")
    if not declared_type:
        issues.append({
            "rule": "frontmatter_missing_type",
            "message": "Frontmatter lacks `type` field.",
            "actionable": f"Add `type: <one of: {', '.join(sorted(active_types.keys()))}>` to frontmatter.",
        })
    elif declared_type not in active_types:
        issues.append({
            "rule": "frontmatter_invalid_type",
            "message": f"Unknown frontmatter type '{declared_type}'.",
            "actionable": f"Use one of: {sorted(active_types.keys())}",
        })

    if declared_type and declared_type in active_types:
        type_cfg = active_types[declared_type]

        # Required fields check
        for field in type_cfg["required"]:
            if field not in meta:
                issues.append({
                    "rule": "frontmatter_missing_field",
                    "message": f"Frontmatter for type='{declared_type}' lacks required field `{field}`.",
                    "actionable": f"Add `{field}: <value>` to frontmatter.",
                })

        # Enum checks
        for field, allowed_values in type_cfg["enum"].items():
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
        if "date" in type_cfg["required"] or "date" in meta:
            d_val = str(meta.get("date", ""))
            if d_val:
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
                key not in type_cfg["required"]
                and key not in type_cfg["optional"]
                and key not in ALLOWED_UNKNOWN_KEYS
            ):
                issues.append({
                    "rule": "frontmatter_unknown_key",
                    "message": f"Unknown frontmatter key '{key}' for type='{declared_type}'.",
                    "actionable": f"Remove `{key}` or add it to ALLOWED_UNKNOWN_KEYS if intentional.",
                })

    if issues:
        target_t = declared_type if declared_type in active_types else infer_type_for_path(path, schema=active)
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


def validate_location_consistency(
    meta: dict[str, Any], path: str, schema: ActiveSchema | None = None
) -> None:
    """Validate that declared type matches expected location.

    Caller MUST pass a relative path that has been resolved against wiki_root.
    Path traversal prevention is handled upstream by _safe_resolve in wiki.py.
    """
    declared_type = meta.get("type")
    if not declared_type:
        return

    active = schema or load_active_schema()
    rel = Path(path)
    expected_type = None
    for location_prefix, expected in active.location_to_type.items():
        if str(rel) == location_prefix or str(rel).startswith(location_prefix + "/"):
            expected_type = expected
            break

    if expected_type is None:
        raise ValidationError(
            rule="location_unknown",
            path=path,
            message=f"Cannot determine expected type for location '{rel.parts[0] if len(rel.parts) > 1 else rel.name}'.",
            actionable="Move file to a known directory or add the location to SCHEMA.md.",
        )

    if declared_type != expected_type:
        raise ValidationError(
            rule="type_location_mismatch",
            path=path,
            message=f"type='{declared_type}' but file is in '{rel.parts[0] if len(rel.parts) > 1 else '.'}' (expected type='{expected_type}').",
            actionable=f"Move file to a directory matching type='{declared_type}', or change frontmatter type to '{expected_type}'.",
        )
