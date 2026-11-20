from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Literal

from brain79.config import get_wiki_root
from brain79.core.drift import WorkspaceIndex
from brain79.core.frontmatter import (
    INACTIVE_STATUSES,
    LEGACY_BACKLINK_MARKERS,
    PRE_IMPLEMENTATION_STATUSES,
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
    MAX_ARTICLE_BYTES,
    MAX_ARTICLE_LINES,
    SHIPPED_SPECIFICATION_REGEX,
    TECHNICAL_DEBT_BULLET_STRICT,
    TECHNICAL_DEBT_HEADER_STRICT,
    TEMPORAL_MILESTONE_REGEX,
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
    """Detect non-atomic or overly large articles (>400 lines, >20480 bytes, or >7 H2 headings)."""
    issues = []
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    for md_file in files:
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel.parts[0] in ("_raw", ".locks", "handoffs", "decisions", "changelog") or rel_str in ("INDEX.md", "SCHEMA.md"):
            continue

        content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        try:
            meta, _ = parse_frontmatter(content)
        except Exception:
            meta = {}
        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
            continue

        lines = content.splitlines()
        byte_len = len(content.encode("utf-8"))
        masked_content = _mask_code_fences(content)
        masked_lines = masked_content.splitlines()
        h2_count = sum(1 for line in masked_lines if line.startswith("## "))

        if len(lines) > MAX_ARTICLE_LINES or byte_len > MAX_ARTICLE_BYTES:
            issues.append(
                OrganizationalIssue(
                    rule="article_too_large",
                    path=rel_str,
                    line=None,
                    severity="warning",
                    message=f"Article has {len(lines)} lines and {byte_len} bytes (max recommended: {MAX_ARTICLE_LINES} lines / {MAX_ARTICLE_BYTES} bytes).",
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

    schema = load_active_schema(wiki_root)
    active_label = schema.backlink_label
    backlink_markers = tuple(dict.fromkeys((f"[{active_label}]".lower(), *LEGACY_BACKLINK_MARKERS)))

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
                        actionable=f"Add `[{active_label}](../INDEX.md)` at the end of the article, or rewrite via brain79 to auto-inject it.",
                    )
                )
        except Exception:
            pass
    return issues


def check_documentation_drift(
    wiki_root: Path,
    md_files: list[Path] | None = None,
    workspace_index: WorkspaceIndex | None = None,
) -> list[OrganizationalIssue]:
    """Verify that articles with `applies_to` frontmatter have not fallen behind workspace code changes."""
    from brain79.core.drift import detect_all_drift

    drifts = detect_all_drift(
        wiki_root=wiki_root,
        md_files=md_files,
        workspace_index=workspace_index,
    )
    issues: list[OrganizationalIssue] = []

    for d in drifts:
        file_date = d.get("file_date")
        art_date = d.get("article_date")
        if file_date and art_date:
            msg = (
                f"Article '{d['article_path']}' governs '{d['workspace_file']}' "
                f"(modified {file_date}), but article was last updated {art_date}."
            )
        else:
            msg = (
                f"Article '{d['article_path']}' governs '{d['workspace_file']}': "
                f"{d.get('message', 'drift detected')}."
            )

        issues.append(
            OrganizationalIssue(
                rule="documentation_drift_suspected",
                path=d["article_path"],
                line=None,
                severity="info",
                message=msg,
                actionable=(
                    f"Verify accuracy of '{d['article_path']}' against recent changes in "
                    f"'{d['workspace_file']}' and update frontmatter `last_updated`."
                ),
            )
        )
    return issues


def check_unanchored_governance(
    wiki_root: Path, md_files: list[Path] | None = None
) -> list[OrganizationalIssue]:
    """Flag strictly active architecture and feature articles missing applies_to in software profile."""
    if not (wiki_root / "SCHEMA.md").is_file():
        return []
    schema = load_active_schema(wiki_root)
    if schema.profile != "software":
        return []

    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    issues: list[OrganizationalIssue] = []

    for f in files:
        try:
            rel_str = f.relative_to(wiki_root).as_posix()
        except ValueError:
            continue
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel_str.startswith("_raw/") or rel_str.startswith("handoffs/"):
            continue

        try:
            content = f.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(content)
        except Exception:
            continue

        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
        if status in non_active or stability in non_active:
            continue

        doc_type = str(meta.get("type", "")).lower()
        if doc_type in ("architecture", "feature"):
            applies = meta.get("applies_to")
            if not applies or (isinstance(applies, list) and len(applies) == 0):
                issues.append(
                    OrganizationalIssue(
                        rule="unanchored_governance_article",
                        path=rel_str,
                        line=None,
                        severity="warning",
                        message=f"Active {doc_type} article '{rel_str}' lacks applies_to governance pattern in frontmatter.",
                        actionable=f"Add 'applies_to: [...]' to frontmatter of '{rel_str}' specifying the code or intra-wiki files it governs.",
                    )
                )

    return issues


def check_applies_to_target_missing(
    wiki_root: Path,
    md_files: list[Path] | None = None,
    workspace_index: WorkspaceIndex | None = None,
) -> list[OrganizationalIssue]:
    """Emit info issue when an active article's applies_to pattern resolves to 0 files in workspace."""
    from brain79.config import get_project_root
    p_root = (wiki_root.parent or get_project_root()).resolve()
    ws = workspace_index or WorkspaceIndex.build(p_root, wiki_root)

    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    issues: list[OrganizationalIssue] = []

    for f in files:
        try:
            rel_str = f.relative_to(wiki_root).as_posix()
        except ValueError:
            continue
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel_str.startswith("_raw/") or rel_str.startswith("handoffs/"):
            continue

        try:
            content = f.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(content)
        except Exception:
            continue

        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
        if status in non_active or stability in non_active:
            continue

        applies = meta.get("applies_to")
        if applies:
            patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
            for pat in patterns:
                matches = ws.find_matching_files([pat])
                if not matches:
                    issues.append(
                        OrganizationalIssue(
                            rule="applies_to_target_missing",
                            path=rel_str,
                            line=None,
                            severity="info",
                            message=f"applies_to pattern '{pat}' does not match any file in workspace index.",
                            actionable=f"Verify that governed files exist or update applies_to pattern in '{rel_str}'.",
                        )
                    )

    return issues


def check_shared_leaf_targets(
    wiki_root: Path,
    md_files: list[Path] | None = None,
    workspace_index: WorkspaceIndex | None = None,
) -> list[OrganizationalIssue]:
    """Flag overlapping governance targets among active sibling articles without supersedes or allow_overlapping_governance."""
    schema = load_active_schema(wiki_root)
    if schema.profile != "software":
        return []

    p_root = wiki_root.parent
    ws = workspace_index or WorkspaceIndex.build(p_root, wiki_root)
    files = md_files if md_files is not None else _filter_md_files(wiki_root)

    target_to_articles: dict[str, list[tuple[str, dict[str, Any]]]] = {}

    non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES

    for md_p in files:
        rel_str = md_p.relative_to(wiki_root).as_posix()
        if (
            rel_str in ("INDEX.md", "SCHEMA.md")
            or rel_str.startswith("_raw/")
            or rel_str.startswith("handoffs/")
        ):
            continue
        try:
            meta, _ = parse_frontmatter(md_p.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        if status in non_active or stability in non_active:
            continue
        if meta.get("allow_overlapping_governance") is True:
            continue

        applies = meta.get("applies_to")
        if not applies:
            continue
        patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]

        # Exclude umbrella articles (those governing intra-wiki articles or .md files)
        if any(".brain-79/" in p or p.endswith(".md") for p in patterns):
            continue

        for pat in patterns:
            matched = ws.find_matching_files([pat])
            for m in matched:
                if m.startswith(".brain-79/") or m.startswith(".git/") or m == ".brain-79":
                    continue
                target_to_articles.setdefault(m, []).append((rel_str, meta))

    issues: list[OrganizationalIssue] = []
    seen_pairs: set[tuple[str, str]] = set()

    for target, articles in sorted(target_to_articles.items()):
        if len(articles) <= 1:
            continue
        for i, (art_a, meta_a) in enumerate(articles):
            for art_b, meta_b in articles[i + 1:]:
                # Sibling leaf articles must share the same document type
                if meta_a.get("type") != meta_b.get("type"):
                    continue

                supersedes_a = {str(x).strip().lstrip("/") for x in (meta_a.get("supersedes") or [])}
                supersedes_b = {str(x).strip().lstrip("/") for x in (meta_b.get("supersedes") or [])}
                related_a = {str(x).strip().lstrip("/") for x in (meta_a.get("related") or [])}
                related_b = {str(x).strip().lstrip("/") for x in (meta_b.get("related") or [])}

                if (
                    art_b in supersedes_a
                    or art_a in supersedes_b
                    or art_b in related_a
                    or art_a in related_b
                ):
                    continue

                pair_key = (art_a, target)
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    issues.append(
                        OrganizationalIssue(
                            rule="shared_target_in_leaf_article",
                            path=art_a,
                            line=None,
                            severity="info",
                            message=f"Shared workspace file '{target}' is also governed by sibling article '{art_b}'.",
                            actionable="Consider delegating transversal platform files to an umbrella architecture article or declare allow_overlapping_governance: true.",
                        )
                    )

    return issues


SOURCE_CODE_EXTENSIONS = (
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".c",
    ".cpp",
    ".cs",
    ".php",
)


def check_uncovered_source_files(
    wiki_root: Path,
    md_files: list[Path] | None = None,
    workspace_index: WorkspaceIndex | None = None,
) -> list[OrganizationalIssue]:
    """Flag source code files in the workspace not covered by any active applies_to frontmatter."""
    schema = load_active_schema(wiki_root)
    if schema.profile != "software":
        return []

    p_root = wiki_root.parent
    ws = workspace_index or WorkspaceIndex.build(p_root, wiki_root)
    files = md_files if md_files is not None else _filter_md_files(wiki_root)

    governed_files: set[str] = set()

    for md_p in files:
        rel_str = md_p.relative_to(wiki_root).as_posix()
        if (
            rel_str in ("INDEX.md", "SCHEMA.md")
            or rel_str.startswith("_raw/")
            or rel_str.startswith("handoffs/")
        ):
            continue
        try:
            meta, _ = parse_frontmatter(md_p.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
            continue

        applies = meta.get("applies_to")
        if not applies:
            continue
        patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
        for pat in patterns:
            matched = ws.find_matching_files([pat])
            governed_files.update(matched)

    issues: list[OrganizationalIssue] = []

    for path_str in sorted(ws.all_paths):
        posix_p = path_str.replace("\\", "/").strip().lstrip("/")
        if (
            posix_p.startswith(".brain-79/")
            or posix_p.startswith(".git/")
            or posix_p.startswith("tests/")
            or posix_p.startswith("test/")
            or posix_p.startswith("scripts/")
            or posix_p.startswith(".venv/")
            or posix_p.startswith("node_modules/")
        ):
            continue

        if not any(posix_p.endswith(ext) for ext in SOURCE_CODE_EXTENSIONS):
            continue

        base_name = posix_p.split("/")[-1]
        if (
            base_name.startswith("test_")
            or base_name.endswith("_test.py")
            or base_name.endswith(".test.js")
            or base_name.endswith(".spec.js")
            or base_name.endswith(".test.ts")
            or base_name.endswith(".spec.ts")
        ):
            continue

        if posix_p not in governed_files:
            issues.append(
                OrganizationalIssue(
                    rule="uncovered_source_files",
                    path=posix_p,
                    line=None,
                    severity="info",
                    message=f"Source file '{posix_p}' is not governed by any active feature or architecture article.",
                    actionable=f"Declare '{posix_p}' in the applies_to frontmatter of a governing architecture or feature article.",
                )
            )

    return issues


def check_architectural_decision_deficit(
    wiki_root: Path,
    md_files: list[Path] | None = None,
) -> list[OrganizationalIssue]:
    """Flag software projects with >= 3 feature/architecture articles but zero active ADRs."""
    schema = load_active_schema(wiki_root)
    if schema.profile != "software":
        return []

    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    feat_arch_count = 0
    active_adr_count = 0

    for md_p in files:
        rel_str = md_p.relative_to(wiki_root).as_posix()
        if (
            rel_str in ("INDEX.md", "SCHEMA.md")
            or rel_str.startswith("_raw/")
            or rel_str.startswith("handoffs/")
        ):
            continue
        try:
            meta, _ = parse_frontmatter(md_p.read_text(encoding="utf-8"))
        except Exception:
            continue

        doc_type = str(meta.get("type", "")).strip()
        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
            continue

        if doc_type in ("feature", "architecture"):
            feat_arch_count += 1
        elif doc_type == "decision":
            active_adr_count += 1

    if feat_arch_count >= 3 and active_adr_count == 0:
        return [
            OrganizationalIssue(
                rule="architectural_decision_deficit",
                path="decisions",
                line=None,
                severity="info",
                message=f"Project wiki has {feat_arch_count} active feature/architecture articles but zero architectural decision records (ADRs).",
                actionable="Record key technical decisions, trade-offs, and state models under decisions/adr-*.md.",
            )
        ]

    return []


def check_git_repository(
    wiki_root: Path,
    project_root: Path | None = None,
) -> list[OrganizationalIssue]:
    """Flag software profile wiki lacking an active git repository."""
    from brain79.core.handoff_freshness import is_git_workspace

    schema = load_active_schema(wiki_root)
    if schema.profile != "software":
        return []

    p_root = project_root or wiki_root.parent
    if not is_git_workspace(p_root):
        return [
            OrganizationalIssue(
                rule="missing_git_repository",
                path=".",
                line=None,
                severity="info",
                message="Software profile wiki is not inside a git repository.",
                actionable="Initialize git via `git init` to enable code digest mutation tracking and pre-commit hooks.",
            )
        ]
    return []


def check_temporal_contamination(
    wiki_root: Path,
    md_files: list[Path] | None = None,
) -> list[OrganizationalIssue]:
    """Flag temporal project management markers in living manuals (features, architecture, product)."""
    files = md_files if md_files is not None else _filter_md_files(wiki_root)
    issues: list[OrganizationalIssue] = []

    living_dirs = ("features", "architecture", "product")

    for md_p in files:
        rel_str = md_p.relative_to(wiki_root).as_posix()
        if (
            rel_str in ("INDEX.md", "SCHEMA.md")
            or rel_str.startswith("_raw/")
            or rel_str.startswith("handoffs/")
        ):
            continue

        parts = rel_str.split("/")
        top_dir = parts[0]
        if top_dir not in living_dirs:
            continue

        # Roadmaps are by definition milestone schedules and exempt
        if "roadmap" in rel_str.lower():
            continue

        try:
            content = md_p.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
        except Exception:
            continue

        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        # Inactive / archived articles are historical records and exempt
        if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
            continue

        # 1. Check frontmatter summary
        summary = str(meta.get("summary") or "")
        m_summary = TEMPORAL_MILESTONE_REGEX.search(summary)
        if m_summary:
            issues.append(
                OrganizationalIssue(
                    rule="temporal_contamination_in_summary",
                    path=rel_str,
                    line=None,
                    severity="warning",
                    message=f"Living manual summary contains temporal project management marker '{m_summary.group(0)}'.",
                    actionable="Remove temporal milestone tags from summary. Living manuals must describe software capabilities evergreenly.",
                )
            )

        # 2. Check title (H1) and headings (H2/H3)
        body_masked = _mask_code_fences(body)
        is_shipped = status == "shipped" or stability == "stable"

        for line_no, raw_line in enumerate(body_masked.splitlines(), start=1):
            line = raw_line.strip()
            if line.startswith("# "):
                title_text = line[2:].strip()
                m_title = TEMPORAL_MILESTONE_REGEX.search(title_text)
                if m_title:
                    issues.append(
                        OrganizationalIssue(
                            rule="temporal_contamination_in_title",
                            path=rel_str,
                            line=line_no,
                            severity="warning",
                            message=f"Living manual title contains temporal project management marker '{m_title.group(0)}'.",
                            actionable="Remove temporal milestone tags (e.g. '(Phase X)') from title. Record release delivery in changelog/ instead.",
                        )
                    )
                if is_shipped:
                    m_spec = SHIPPED_SPECIFICATION_REGEX.search(title_text)
                    if m_spec:
                        issues.append(
                            OrganizationalIssue(
                                rule="shipped_specification_title",
                                path=rel_str,
                                line=line_no,
                                severity="warning",
                                message="Shipped living manual title contains 'specification'.",
                                actionable="Rename title to describe active capability directly (e.g. 'Feature — Subsystem') rather than a specification.",
                            )
                        )
            elif line.startswith("## ") or line.startswith("### "):
                heading_text = line.lstrip("#").strip()
                m_heading = TEMPORAL_MILESTONE_REGEX.search(heading_text)
                if m_heading:
                    issues.append(
                        OrganizationalIssue(
                            rule="temporal_contamination_in_heading",
                            path=rel_str,
                            line=line_no,
                            severity="warning",
                            message=f"Living manual heading contains temporal project management marker '{m_heading.group(0)}'.",
                            actionable="Remove temporal milestone tags from heading. Keep living manual structure timeless.",
                        )
                    )

    return issues


def lint_organizational(wiki_root: Path) -> list[OrganizationalIssue]:
    """Run all organizational health checks on the wiki."""
    p_root = wiki_root.parent
    ws = WorkspaceIndex.build(p_root, wiki_root)
    md_files = _filter_md_files(wiki_root)
    issues: list[OrganizationalIssue] = []
    issues.extend(check_git_repository(wiki_root))
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
    issues.extend(check_documentation_drift(wiki_root, md_files=md_files, workspace_index=ws))
    issues.extend(check_unanchored_governance(wiki_root, md_files=md_files))
    issues.extend(check_applies_to_target_missing(wiki_root, md_files=md_files, workspace_index=ws))
    issues.extend(check_shared_leaf_targets(wiki_root, md_files=md_files, workspace_index=ws))
    issues.extend(check_architectural_decision_deficit(wiki_root, md_files=md_files))
    issues.extend(check_uncovered_source_files(wiki_root, md_files=md_files, workspace_index=ws))
    issues.extend(check_temporal_contamination(wiki_root, md_files=md_files))
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
