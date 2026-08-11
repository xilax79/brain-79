from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from brain79.core.frontmatter import (
    LOCATION_TO_TYPE,
    TYPE_SCHEMA,
    parse_frontmatter,
    validate_location_consistency,
)
from brain79.core.navigation import load_registry
from brain79.core.validation import (
    DECISION_BULLET_STRICT,
    DECISION_HEADER_STRICT,
    INDEX_ALLOWED_H2,
    TECHNICAL_DEBT_BULLET_STRICT,
    TECHNICAL_DEBT_HEADER_STRICT,
    _mask_code_fences,
    get_index_max_lines,
)


@dataclass
class OrganizationalIssue:
    rule: str
    path: str
    line: int | None
    severity: Literal["error", "warning", "info"]
    message: str
    actionable: str


def check_index_size(wiki_root: Path) -> list[OrganizationalIssue]:
    """Check if INDEX.md exceeds max line count limit."""
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        return []

    content = index_path.read_text(encoding="utf-8")
    line_count = len(content.splitlines())
    max_lines = get_index_max_lines()

    if line_count > max_lines:
        return [
            OrganizationalIssue(
                rule="index_size_limit",
                path="INDEX.md",
                line=None,
                severity="error",
                message=f"INDEX.md exceeds {max_lines} lines (current: {line_count}).",
                actionable="Run `brain79 lint --suggest-extract` to identify blocks to move.",
            )
        ]
    return []


def check_frontmatter_consistency(wiki_root: Path) -> list[OrganizationalIssue]:
    """Every article (except INDEX.md, SCHEMA.md, and _raw/) MUST have valid frontmatter."""
    issues = []
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = str(rel)
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] == "_raw":
            continue

        if md_file.stat().st_size == 0:
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            if not content.startswith("---\n"):
                issues.append(
                    OrganizationalIssue(
                        rule="frontmatter_missing",
                        path=rel_str,
                        line=1,
                        severity="error",
                        message="Article lacks frontmatter.",
                        actionable="Add frontmatter with `type` and `last_updated` fields.",
                    )
                )
                continue

            meta, _ = parse_frontmatter(content)
            if "type" not in meta:
                issues.append(
                    OrganizationalIssue(
                        rule="frontmatter_missing_type",
                        path=rel_str,
                        line=1,
                        severity="error",
                        message="Frontmatter missing required 'type' key.",
                        actionable="Specify 'type' in frontmatter.",
                    )
                )
            elif "last_updated" not in meta:
                issues.append(
                    OrganizationalIssue(
                        rule="frontmatter_missing_last_updated",
                        path=rel_str,
                        line=1,
                        severity="error",
                        message="Frontmatter missing required 'last_updated' key.",
                        actionable="Specify 'last_updated' (YYYY-MM-DD) in frontmatter.",
                    )
                )
        except Exception as exc:
            issues.append(
                OrganizationalIssue(
                    rule="frontmatter_invalid",
                    path=rel_str,
                    line=1,
                    severity="error",
                    message=f"Invalid frontmatter: {exc}",
                    actionable="Fix frontmatter YAML syntax.",
                )
            )
    return issues


def check_type_location_mismatch(wiki_root: Path) -> list[OrganizationalIssue]:
    """Validate that article frontmatter type matches file location."""
    issues = []
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = str(rel)
        if rel_str in ("SCHEMA.md",) or rel.parts[0] == "_raw":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(content)
            if not meta or "type" not in meta:
                continue

            declared_type = meta["type"]
            if declared_type not in TYPE_SCHEMA:
                issues.append(
                    OrganizationalIssue(
                        rule="type_invalid",
                        path=rel_str,
                        line=None,
                        severity="error",
                        message=f"Unknown frontmatter type '{declared_type}'.",
                        actionable=f"Use one of: {sorted(TYPE_SCHEMA.keys())}",
                    )
                )
                continue

            try:
                validate_location_consistency(meta, rel_str)
            except Exception as exc:
                expected_dirs = [d for d, t in LOCATION_TO_TYPE.items() if t == declared_type]
                issues.append(
                    OrganizationalIssue(
                        rule="type_location_mismatch",
                        path=rel_str,
                        line=None,
                        severity="error",
                        message=str(exc),
                        actionable=f"Move file to '{expected_dirs[0]}/' or change frontmatter type.",
                    )
                )
        except Exception:
            pass
    return issues


def check_decision_leakage(wiki_root: Path) -> list[OrganizationalIssue]:
    """Detect structural decision declarations in non-decision directories."""
    issues = []
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = str(rel)
        if rel.parts[0] in ("decisions", "_raw", "handoffs") or rel_str in ("INDEX.md", "SCHEMA.md"):
            continue

        content = md_file.read_text(encoding="utf-8")
        masked_content = _mask_code_fences(content)

        for line_no, line in enumerate(masked_content.splitlines(), start=1):
            if DECISION_BULLET_STRICT.search(line) or DECISION_HEADER_STRICT.search(line):
                issues.append(
                    OrganizationalIssue(
                        rule="decision_leakage",
                        path=rel_str,
                        line=line_no,
                        severity="warning",
                        message=f"Decision declaration detected: `{line[:80].strip()}`",
                        actionable=f"Move to 'decisions/{rel.stem}.md' if this is a structural decision.",
                    )
                )
    return issues


def check_article_atomicity(wiki_root: Path) -> list[OrganizationalIssue]:
    """Detect non-atomic or overly large articles (>400 lines or >7 H2 headings)."""
    issues = []
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = str(rel)
        if rel.parts[0] in ("_raw", "handoffs", "decisions") or rel_str in ("INDEX.md", "SCHEMA.md"):
            continue

        content = md_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        h2_count = sum(1 for line in lines if line.startswith("## "))

        if len(lines) > 400:
            issues.append(
                OrganizationalIssue(
                    rule="article_too_large",
                    path=rel_str,
                    line=None,
                    severity="warning",
                    message=f"Article has {len(lines)} lines (max recommended: 400).",
                    actionable="Split into multiple focused articles.",
                )
            )

        if h2_count > 7:
            issues.append(
                OrganizationalIssue(
                    rule="article_not_atomic",
                    path=rel_str,
                    line=None,
                    severity="warning",
                    message=f"Article has {h2_count} H2 sections (max recommended: 7).",
                    actionable="Consider splitting into multiple articles, one topic each.",
                )
            )
    return issues


def check_prohibited_content(wiki_root: Path) -> list[OrganizationalIssue]:
    """Check INDEX.md for non-whitelisted H2 headers or structural decision bullets."""
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        return []

    issues = []
    content = index_path.read_text(encoding="utf-8")
    masked_content = _mask_code_fences(content)

    for line_no, line in enumerate(masked_content.splitlines(), start=1):
        if line.startswith("## "):
            h2_text = line[3:].strip()
            if h2_text not in INDEX_ALLOWED_H2:
                issues.append(
                    OrganizationalIssue(
                        rule="index_prohibited_header",
                        path="INDEX.md",
                        line=line_no,
                        severity="error",
                        message=f"Prohibited section header '## {h2_text}' in INDEX.md.",
                        actionable=f"Allowed H2 headers in INDEX.md: {sorted(INDEX_ALLOWED_H2)}",
                    )
                )

        if (
            DECISION_BULLET_STRICT.search(line)
            or DECISION_HEADER_STRICT.search(line)
            or TECHNICAL_DEBT_BULLET_STRICT.search(line)
            or TECHNICAL_DEBT_HEADER_STRICT.search(line)
        ):
            issues.append(
                OrganizationalIssue(
                    rule="index_prohibited_content",
                    path="INDEX.md",
                    line=line_no,
                    severity="error",
                    message=f"Prohibited decision or technical debt entry in INDEX.md: `{line[:80].strip()}`",
                    actionable="Move decisions to 'decisions/' and technical debt to 'features/'.",
                )
            )

    return issues


def check_navigation_freshness(wiki_root: Path) -> list[OrganizationalIssue]:
    """Detect desync between navigation registry and INDEX.md Quick navigation."""
    issues = []
    registry = load_registry(wiki_root)
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        return []

    index_content = index_path.read_text(encoding="utf-8")
    qn_match = re.search(r"## Quick navigation\n(.*?)(?=\n## |\Z)", index_content, re.DOTALL)
    qn_content = qn_match.group(1) if qn_match else ""

    for article in registry.get("articles", []):
        path_str = article.get("path", "")
        if path_str and path_str not in qn_content:
            issues.append(
                OrganizationalIssue(
                    rule="navigation_desync",
                    path="INDEX.md",
                    line=None,
                    severity="warning",
                    message=f"Registered article '{path_str}' is missing from INDEX.md Quick navigation.",
                    actionable="Run `brain79 navigate --regenerate` to sync Quick navigation.",
                )
            )
    return issues


def check_legacy_articles(wiki_root: Path) -> list[OrganizationalIssue]:
    """Report articles with status=legacy or stability=legacy."""
    issues = []
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = str(rel)
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", "handoffs"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(content)
            if meta.get("status") == "legacy" or meta.get("stability") == "legacy":
                issues.append(
                    OrganizationalIssue(
                        rule="legacy_needs_review",
                        path=rel_str,
                        line=None,
                        severity="info",
                        message="Article has status/stability=legacy; needs review.",
                        actionable="Review content and update status to shipped/accepted/stable.",
                    )
                )
        except Exception:
            pass
    return issues


def check_force_skipped_articles(wiki_root: Path) -> list[OrganizationalIssue]:
    """Report articles created with validation=force_skip."""
    issues = []
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = str(rel)
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", "handoffs"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(content)
            if (
                meta.get("validation") == "force_skip"
                or meta.get("force_validation_skipped") is True
                or str(meta.get("force_validation_skipped")).lower() == "true"
            ):
                issues.append(
                    OrganizationalIssue(
                        rule="force_skipped_article",
                        path=rel_str,
                        line=None,
                        severity="warning",
                        message="Article was written with validation=force_skip.",
                        actionable="Review article content and remove validation=force_skip flag when compliant.",
                    )
                )
        except Exception:
            pass
    return issues


def lint_organizational(wiki_root: Path) -> list[OrganizationalIssue]:
    """Run all organizational health checks on the wiki."""
    issues: list[OrganizationalIssue] = []
    issues.extend(check_index_size(wiki_root))
    issues.extend(check_frontmatter_consistency(wiki_root))
    issues.extend(check_type_location_mismatch(wiki_root))
    issues.extend(check_decision_leakage(wiki_root))
    issues.extend(check_article_atomicity(wiki_root))
    issues.extend(check_prohibited_content(wiki_root))
    issues.extend(check_navigation_freshness(wiki_root))
    issues.extend(check_legacy_articles(wiki_root))
    issues.extend(check_force_skipped_articles(wiki_root))
    return issues


def generate_extraction_suggestions(wiki_root: Path) -> str:
    """Generate extraction suggestions for INDEX.md content blocks."""
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        return "INDEX.md not found."

    content = index_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    suggestions: list[str] = ["## Suggested Extractions from INDEX.md", ""]

    current_h2 = ""
    block_lines: list[tuple[int, str]] = []

    for line_no, line in enumerate(lines, start=1):
        if line.startswith("## "):
            current_h2 = line[3:].strip()
            continue

        if (
            DECISION_BULLET_STRICT.search(line)
            or DECISION_HEADER_STRICT.search(line)
            or current_h2 not in INDEX_ALLOWED_H2
        ) and line.strip():
            block_lines.append((line_no, line))

    if not block_lines:
        suggestions.append("No non-standard or decision content detected in INDEX.md.")
    else:
        suggestions.append(f"Detected {len(block_lines)} candidate line(s) for extraction:")
        for line_no, line in block_lines[:10]:
            suggestions.append(f"  - Line {line_no}: `{line[:80].strip()}`")
            suggestions.append("    Suggested path: decisions/extracted_decision.md")
            suggestions.append("    Suggested type: decision")

    return "\n".join(suggestions)
