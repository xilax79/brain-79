from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from brain79.core.frontmatter import (
    ValidationError,
    load_active_schema,
    parse_frontmatter,
    validate_frontmatter,
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


def _filter_md_files(wiki_root: Path) -> list[Path]:
    """Return all markdown files excluding _raw/ and .locks/."""
    return [f for f in sorted(wiki_root.rglob("*.md")) if "_raw" not in f.parts and ".locks" not in f.parts]


def check_index_size(wiki_root: Path) -> list[OrganizationalIssue]:
    """Check if INDEX.md exceeds max line count limit."""
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        return []

    content = index_path.read_text(encoding="utf-8").replace("\r\n", "\n")
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


def check_frontmatter_consistency(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Every article (except INDEX.md, SCHEMA.md, and _raw/) MUST have valid frontmatter."""
    issues = []
    schema = load_active_schema(wiki_root)
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks"):
            continue

        if md_file.stat().st_size == 0:
            continue

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
            if not content.startswith("---\n"):
                issues.append(
                    OrganizationalIssue(
                        rule="frontmatter_missing",
                        path=rel_str,
                        line=1,
                        severity="error",
                        message="Article lacks frontmatter.",
                        actionable="Add frontmatter with `type`, `summary`, and `last_updated` fields.",
                    )
                )
                continue

            meta, _ = parse_frontmatter(content)
            try:
                validate_frontmatter(meta, rel_str, schema=schema)
            except ValidationError as ve:
                for vi in ve.issues:
                    issues.append(
                        OrganizationalIssue(
                            rule=vi.get("rule", "frontmatter_invalid"),
                            path=rel_str,
                            line=1,
                            severity="error",
                            message=vi.get("message", str(ve)),
                            actionable=vi.get("actionable", "Review schema requirements."),
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


def check_type_location_mismatch(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Validate that article frontmatter type matches file location."""
    issues = []
    schema = load_active_schema(wiki_root)
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel_str in ("SCHEMA.md",) or rel.parts[0] in ("_raw", ".locks"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
            meta, _ = parse_frontmatter(content)
            if not meta or "type" not in meta:
                continue

            declared_type = meta["type"]
            if declared_type not in schema.types:
                issues.append(
                    OrganizationalIssue(
                        rule="type_invalid",
                        path=rel_str,
                        line=None,
                        severity="error",
                        message=f"Unknown frontmatter type '{declared_type}'.",
                        actionable=f"Use one of: {sorted(schema.types.keys())}",
                    )
                )
                continue

            try:
                validate_location_consistency(meta, rel_str, schema=schema)
            except Exception as exc:
                expected_dirs = [d for d, t in schema.location_to_type.items() if t == declared_type]
                exp_msg = f"'{expected_dirs[0]}/'" if expected_dirs else "matching directory"
                issues.append(
                    OrganizationalIssue(
                        rule="type_location_mismatch",
                        path=rel_str,
                        line=None,
                        severity="error",
                        message=str(exc),
                        actionable=f"Move file to {exp_msg} or change frontmatter type.",
                    )
                )
        except Exception:
            pass
    return issues


def check_decision_leakage(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Detect structural decision declarations in non-decision directories."""
    issues = []
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel.parts[0] in ("decisions", "_raw", ".locks", "handoffs") or rel_str in ("INDEX.md", "SCHEMA.md"):
            continue

        content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
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


def check_technical_debt_leakage(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Detect technical debt declarations outside features/ or decisions/ (software profile only)."""
    schema = load_active_schema(wiki_root)
    if not schema.supports_technical_debt_leakage:
        return []

    issues = []
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel.parts[0] in ("features", "decisions", "_raw", ".locks", "handoffs") or rel_str in ("INDEX.md", "SCHEMA.md"):
            continue

        content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        masked_content = _mask_code_fences(content)

        for line_no, line in enumerate(masked_content.splitlines(), start=1):
            if TECHNICAL_DEBT_BULLET_STRICT.search(line) or TECHNICAL_DEBT_HEADER_STRICT.search(line):
                issues.append(
                    OrganizationalIssue(
                        rule="technical_debt_leakage",
                        path=rel_str,
                        line=line_no,
                        severity="warning",
                        message=f"Technical debt declaration detected: `{line[:80].strip()}`",
                        actionable="Move technical debt items to 'features/' or 'decisions/'.",
                    )
                )
    return issues


def check_article_atomicity(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Detect non-atomic or overly large articles (>400 lines or >7 H2 headings)."""
    issues = []
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel.parts[0] in ("_raw", ".locks", "handoffs", "decisions") or rel_str in ("INDEX.md", "SCHEMA.md"):
            continue

        content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        lines = content.splitlines()
        masked_content = _mask_code_fences(content)
        masked_lines = masked_content.splitlines()
        h2_count = sum(1 for line in masked_lines if line.startswith("## "))

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

        # Composite heuristic for maximum allowed H2 sections:
        # 1. Checklists, roadmaps, backlogs, glossaries, or outlines: up to 15 H2s
        # 2. Compact articles (<= 150 lines): up to 12 H2s
        # 3. Standard prose articles (> 150 lines): up to 10 H2s
        lower_name = md_file.name.lower()
        is_structured_list = any(
            term in lower_name for term in ("checklist", "roadmap", "backlog", "glossary", "outline")
        )
        if not is_structured_list:
            task_checkboxes = sum(
                1 for line in masked_lines if line.strip().startswith(("- [ ]", "- [x]", "- [X]"))
            )
            if task_checkboxes >= 5:
                is_structured_list = True
            elif "tags:" in content:
                for line in lines[:30]:
                    if line.strip().startswith("---") and lines[:30].index(line) > 0:
                        break
                    if any(
                        term in line.lower()
                        for term in ("checklist", "roadmap", "backlog", "glossary", "outline")
                    ):
                        is_structured_list = True
                        break

        if is_structured_list:
            max_h2 = 15
        elif len(lines) <= 150:
            max_h2 = 12
        else:
            max_h2 = 10

        if h2_count > max_h2:
            issues.append(
                OrganizationalIssue(
                    rule="article_not_atomic",
                    path=rel_str,
                    line=None,
                    severity="warning",
                    message=f"Article has {h2_count} H2 sections (max recommended: {max_h2}).",
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
    content = index_path.read_text(encoding="utf-8").replace("\r\n", "\n")
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

    index_content = index_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    qn_match = re.search(r"## Quick navigation\n(.*?)(?=\n## |\Z)", index_content, re.DOTALL)
    qn_content = qn_match.group(1) if qn_match else ""

    for article in registry.get("articles", []):
        path_str = article.get("path", "")
        if path_str.startswith("handoffs/") or article.get("section") == "handoffs":
            continue
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


def check_legacy_articles(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Report articles with status=legacy or stability=legacy."""
    issues = []
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks", "handoffs"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
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


def check_force_skipped_articles(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Report articles created with validation=force_skip."""
    issues = []
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks", "handoffs"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
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


UNFILLED_PLACEHOLDER_PATTERNS = re.compile(
    r"<!--\s*((?:project\s+name|one\s+sentence|e\.g\.,?\s+active|e\.g\.?|active\s+development|beta|production|maintenance|fill\s+in).*?)\s*-->",
    re.IGNORECASE,
)


def check_unfilled_placeholders(wiki_root: Path) -> list[OrganizationalIssue]:
    """Detect unfilled HTML comment placeholders in INDEX.md.

    The default brain79 init template leaves several `<!-- placeholder -->` comments
    in INDEX.md for users to fill in. This check ensures those are completed.

    Returns:
        List of OrganizationalIssue with rule='index_unfilled_placeholder'.
    """
    issues: list[OrganizationalIssue] = []
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        return issues

    content = index_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    masked = _mask_code_fences(content)

    for line_no, line in enumerate(masked.splitlines(), start=1):
        for match in UNFILLED_PLACEHOLDER_PATTERNS.finditer(line):
            issues.append(
                OrganizationalIssue(
                    rule="index_unfilled_placeholder",
                    path="INDEX.md",
                    line=line_no,
                    severity="warning",
                    message=f"Unfilled template placeholder: '{match.group(0)}'",
                    actionable=(
                        "Replace this placeholder with the actual value, "
                        "or remove the comment if not applicable. "
                        "Run `brain79 init` to see the template structure."
                    ),
                )
            )
    return issues


def check_article_structural_sections(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Verify that articles contain required structural H2 sections for their type."""
    from brain79.core.validation import check_missing_sections

    schema = load_active_schema(wiki_root)
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    issues: list[OrganizationalIssue] = []

    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks", "handoffs"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
            meta, _ = parse_frontmatter(content)
            status = str(meta.get("status", "")).lower()
            stability = str(meta.get("stability", "")).lower()
            if status in ("superseded", "deprecated", "rejected", "archived", "legacy") or stability == "legacy":
                continue
            doc_type = meta.get("type")
            if not doc_type:
                continue
            missing = check_missing_sections(content, doc_type, schema=schema)
            if missing:
                missing_str = ", ".join(f"'## {s}'" for s in missing)
                issues.append(
                    OrganizationalIssue(
                        rule="article_missing_required_sections",
                        path=rel_str,
                        line=None,
                        severity="warning",
                        message=f"Article '{rel_str}' is missing required sections for type '{doc_type}': {missing_str}.",
                        actionable=f"Add missing sections ({missing_str}) to '{rel_str}'.",
                    )
                )
        except Exception:
            pass
    return issues


def check_article_backlinks(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Verify that all articles in subfolders have a backlink navigation footer to INDEX.md."""
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    issues: list[OrganizationalIssue] = []

    backlink_markers = (
        "[← volver al índice]",
        "[← return to index]",
        "[← back to index]",
        "[volver al índice]",
    )

    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if len(rel.parts) <= 1 or rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks", "handoffs"):
            continue

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
            meta, body = parse_frontmatter(content)
            status = str(meta.get("status", "")).lower()
            stability = str(meta.get("stability", "")).lower()
            if status in ("superseded", "deprecated", "rejected", "archived", "legacy") or stability == "legacy":
                continue

            stripped_body = body.strip()
            if not stripped_body:
                continue

            masked = _mask_code_fences(body)
            non_empty_masked = [line.strip().lower() for line in masked.splitlines() if line.strip()]
            tail_lines = non_empty_masked[-5:] if non_empty_masked else []

            has_backlink = any(
                any(marker in line for marker in backlink_markers)
                for line in tail_lines
            )

            if not has_backlink:
                issues.append(
                    OrganizationalIssue(
                        rule="article_missing_backlink",
                        path=rel_str,
                        line=None,
                        severity="warning",
                        message=f"Article '{rel_str}' is missing backlink navigation footer to INDEX.md.",
                        actionable="Add `[← Volver al Índice](../INDEX.md)` at the end of the article, or rewrite via brain79 to auto-inject it.",
                    )
                )
        except Exception:
            pass
    return issues


def check_documentation_drift(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Verify that articles with `applies_to` frontmatter have not fallen behind workspace code changes."""
    from brain79.core.drift import detect_all_drift

    drifts = detect_all_drift(wiki_root=wiki_root, md_files=md_files)
    issues: list[OrganizationalIssue] = []

    for d in drifts:
        issues.append(
            OrganizationalIssue(
                rule="documentation_drift_suspected",
                path=d["article_path"],
                line=None,
                severity="warning",
                message=(
                    f"Article '{d['article_path']}' governs '{d['workspace_file']}' "
                    f"(modified {d['file_date']}), but article was last updated {d['article_date']}."
                ),
                actionable=(
                    f"Verify accuracy of '{d['article_path']}' against recent changes in "
                    f"'{d['workspace_file']}' and update frontmatter `last_updated`."
                ),
            )
        )
    return issues


def lint_organizational(wiki_root: Path) -> list[OrganizationalIssue]:
    """Run all organizational health checks on the wiki."""
    md_files = _filter_md_files(wiki_root)
    issues: list[OrganizationalIssue] = []
    issues.extend(check_index_size(wiki_root))
    issues.extend(check_frontmatter_consistency(wiki_root, md_files=md_files))
    issues.extend(check_type_location_mismatch(wiki_root, md_files=md_files))
    issues.extend(check_decision_leakage(wiki_root, md_files=md_files))
    issues.extend(check_technical_debt_leakage(wiki_root, md_files=md_files))
    issues.extend(check_article_atomicity(wiki_root, md_files=md_files))
    issues.extend(check_prohibited_content(wiki_root))
    issues.extend(check_navigation_freshness(wiki_root))
    issues.extend(check_legacy_articles(wiki_root, md_files=md_files))
    issues.extend(check_force_skipped_articles(wiki_root, md_files=md_files))
    issues.extend(check_unfilled_placeholders(wiki_root))
    issues.extend(check_article_structural_sections(wiki_root, md_files=md_files))
    issues.extend(check_article_backlinks(wiki_root, md_files=md_files))
    issues.extend(check_documentation_drift(wiki_root, md_files=md_files))
    return issues


def generate_extraction_suggestions(wiki_root: Path) -> str:
    """Generate extraction suggestions for INDEX.md content blocks."""
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        return "INDEX.md not found."

    content = index_path.read_text(encoding="utf-8").replace("\r\n", "\n")
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
