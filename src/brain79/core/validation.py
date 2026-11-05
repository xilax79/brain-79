import os
from pathlib import Path
import re
import sys
from typing import Any

from brain79.core.frontmatter import (
    FrontmatterError,
    ValidationError,
    _normalize_content,
    autofill_deterministic_fields,
    dump_frontmatter,
    generate_frontmatter_template,
    infer_type_for_path,
    normalize_backlink_footer,
    normalize_bullet_colons,
    parse_frontmatter,
    validate_frontmatter,
    validate_location_consistency,
)

# Limits
DEFAULT_INDEX_MAX_LINES = 150


def get_index_max_lines() -> int:
    env_val = os.environ.get("BRAIN79_INDEX_MAX_LINES")
    if env_val:
        try:
            val = int(env_val)
            if 50 <= val <= 500:
                return val
        except ValueError:
            pass
    return DEFAULT_INDEX_MAX_LINES


# Allowed H2 headers in INDEX.md (ADR-008: Pure automated routing table)
INDEX_ALLOWED_H2 = frozenset({
    "Quick navigation",
})

# V5 strict decision / TD patterns in INDEX.md (Appendix B.1)
DECISION_BULLET_STRICT = re.compile(
    r"(?im)^[-*]\s+(?:Decision|ADR-\d+|Decisión|Decidimos|Acordado|Chose|Rejected alternative):"
)
DECISION_HEADER_STRICT = re.compile(r"(?im)^#{2,3}\s+(?:Decision|ADR|Decisión|Decision Log)\b")
TECHNICAL_DEBT_BULLET_STRICT = re.compile(r"(?im)^[-*]\s+TD-\d+:")
TECHNICAL_DEBT_HEADER_STRICT = re.compile(r"(?im)^#{2,3}\s+Technical [Dd]ebt\b")

_INDEX_DECISION_PATTERNS = [
    DECISION_BULLET_STRICT,
    DECISION_HEADER_STRICT,
    TECHNICAL_DEBT_BULLET_STRICT,
    TECHNICAL_DEBT_HEADER_STRICT,
]


def _mask_code_fences(content: str) -> str:
    """Replace lines inside fenced code blocks with placeholders to avoid false positives."""
    lines = content.split("\n")
    in_fence = False
    fence_char: str | None = None
    masked: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence_char = stripped[:3]
                in_fence = True
            masked.append(line)
        else:
            if fence_char and stripped.startswith(fence_char):
                fence_char = None
                in_fence = False
                masked.append(line)
            else:
                masked.append(" " * len(line))
    return "\n".join(masked)


def validate_article_content(
    path: str,
    content: str,
    force_skip: bool = False,
    wiki_root: Path | None = None,
) -> str:
    """Validate article content before writing to disk.

    If validation passes, returns content (potentially with injected metadata if force_skip is True).
    Raises ValidationError if validation fails.
    """
    content = _normalize_content(content)
    rel_path = path.strip("/")

    # Exempt files: SCHEMA.md and anything under _raw/
    if rel_path == "SCHEMA.md" or rel_path.startswith("_raw/"):
        return content

    if force_skip:
        sys.stderr.write(
            "WARNING: Skipping organizational validation. This bypass is logged and visible in brain79 lint.\n"
        )
        if content.startswith("---\n"):
            lines = content.split("\n")
            lines.insert(1, "force_validation_skipped: true")
            return "\n".join(lines)
        else:
            return f"---\nforce_validation_skipped: true\n---\n\n{content}"

    if rel_path == "INDEX.md":
        lines = content.splitlines()
        max_lines = get_index_max_lines()
        if len(lines) > max_lines:
            raise ValidationError(
                rule="index_oversized",
                path=rel_path,
                message=f"INDEX.md has {len(lines)} lines (exceeds limit of {max_lines}).",
                actionable="Extract sections into separate articles in decisions/, features/, architecture/, product/.",
            )

        masked_content = _mask_code_fences(content)
        masked_lines = masked_content.splitlines()

        # Check H2 headers outside code fences
        for line in masked_lines:
            if line.startswith("## "):
                header_title = line[3:].strip()
                if header_title not in INDEX_ALLOWED_H2:
                    raise ValidationError(
                        rule="index_prohibited_header",
                        path=rel_path,
                        message=f"Prohibited header '## {header_title}' in INDEX.md.",
                        actionable=f"INDEX.md H2 headers must be one of: {sorted(INDEX_ALLOWED_H2)}",
                    )

        # Check strict decision patterns in INDEX.md outside code fences
        for pattern in _INDEX_DECISION_PATTERNS:
            if pattern.search(masked_content):
                raise ValidationError(
                    rule="index_prohibited_content",
                    path=rel_path,
                    message="Prohibited decision or technical debt content detected in INDEX.md.",
                    actionable="Move decision declarations and technical debt items to articles in decisions/.",
                )

        # Check optional frontmatter if present
        if content.startswith("---\n"):
            try:
                meta, body = parse_frontmatter(content)
                meta = autofill_deterministic_fields(meta, rel_path, body=body)
                content = dump_frontmatter(meta, body)
                validate_frontmatter(meta, rel_path)
                validate_location_consistency(meta, rel_path)
            except FrontmatterError as e:
                raise ValidationError(
                    rule="frontmatter_malformed",
                    path=rel_path,
                    message=str(e),
                    actionable="Fix frontmatter syntax in INDEX.md.",
                )

        return content

    # Normal articles (not INDEX.md, not SCHEMA.md, not _raw/)
    try:
        meta, body = parse_frontmatter(content)
    except FrontmatterError as e:
        target_t = infer_type_for_path(rel_path)
        tpl = generate_frontmatter_template(target_t) if target_t else ""
        act = "Add YAML frontmatter with `type`, `last_updated`, etc. between `---` delimiters."
        if tpl:
            act += f"\n\nTemplate:\n```yaml\n{tpl}\n```"
        raise ValidationError(
            rule="frontmatter_missing",
            path=rel_path,
            message=str(e),
            actionable=act,
            target_type=target_t,
        )

    from brain79.config import get_wiki_root
    from brain79.core.frontmatter import load_active_schema

    try:
        w_root = (wiki_root or get_wiki_root()).resolve()
        active_s = load_active_schema(w_root)
    except Exception:
        active_s = None

    meta = autofill_deterministic_fields(meta, rel_path, body=body, schema=active_s)
    body = normalize_backlink_footer(body, rel_path)
    body = normalize_bullet_colons(body)
    content = dump_frontmatter(meta, body)
    validate_frontmatter(meta, rel_path, schema=active_s)
    validate_location_consistency(meta, rel_path, schema=active_s)

    return content


def extract_h2_headers(content: str) -> list[str]:
    """Extract all ## H2 heading titles from markdown content, masking code blocks."""
    masked = _mask_code_fences(content)
    headers: list[str] = []
    for line in masked.splitlines():
        if line.startswith("## "):
            headers.append(line[3:].strip())
    return headers


def check_missing_sections(
    content: str,
    target_type: str,
    schema: Any | None = None,
) -> list[str]:
    """Check if content is missing any required H2 sections for the target type.

    Supports synonyms/alternatives when a required section is defined as a list of acceptable titles.
    Decisions strictly require standard ADR sections.
    Inactive articles (superseded, deprecated, rejected, archived, legacy) are exempted.
    Matches headings using exact match or boundary phrases (avoiding partial substring accidents).
    """
    from brain79.core.frontmatter import load_active_schema, parse_frontmatter

    # Exemption for inactive statuses
    try:
        meta, _ = parse_frontmatter(content)
        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        if status in ("superseded", "deprecated", "rejected", "archived", "legacy") or stability == "legacy":
            return []
    except Exception:
        pass

    active = schema or load_active_schema()
    type_cfg = active.types.get(target_type, {})
    req_sections = type_cfg.get("required_sections", [])
    if not req_sections:
        return []

    present_headers = extract_h2_headers(content)
    normalized_headers = [h.strip().lower() for h in present_headers]

    # Any valid H2 section is structurally sound for topic and context across profiles
    if target_type in ("topic", "context"):
        if present_headers:
            return []

    missing: list[str] = []
    for req in req_sections:
        if isinstance(req, str):
            req_name = req
            candidates = [req.lower()]
        else:
            req_name = req[0]
            candidates = [c.lower() for c in req]

        matched = False
        for c in candidates:
            for nh in normalized_headers:
                # 1. Exact match (e.g. "status" == "status", "overview" == "overview")
                if nh == c:
                    matched = True
                    break
                # 2. Strict prefix/suffix match (e.g. "adr status", "decision consequences", "system overview")
                if nh.startswith(c + " ") or nh.endswith(" " + c):
                    matched = True
                    break
                # 3. Word boundary regex match for multi-word phrases (e.g. "general description", "executive summary")
                if " " in c and re.search(rf"\b{re.escape(c)}\b", nh):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            missing.append(req_name)

    return missing
