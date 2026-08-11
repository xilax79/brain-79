import os
import re
import sys

from brain79.core.frontmatter import (
    FrontmatterError,
    ValidationError,
    _normalize_content,
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


# Allowed H2 headers in INDEX.md
INDEX_ALLOWED_H2 = frozenset({
    "Project",
    "Current focus",
    "Quick navigation",
    "Known issues",
    "Roadmap",
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


def validate_article_content(path: str, content: str, force_skip: bool = False) -> str:
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
                meta, _ = parse_frontmatter(content)
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
        meta, _ = parse_frontmatter(content)
    except FrontmatterError as e:
        raise ValidationError(
            rule="frontmatter_missing",
            path=rel_path,
            message=str(e),
            actionable="Add YAML frontmatter with `type`, `last_updated`, etc. between `---` delimiters.",
        )

    validate_frontmatter(meta, rel_path)
    validate_location_consistency(meta, rel_path)

    return content
