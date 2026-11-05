import collections
import os
import posixpath
import re
import time
from pathlib import Path
from urllib.parse import unquote

import filelock

from brain79.config import get_wiki_root
from brain79.core.lint_organizational import OrganizationalIssue
from brain79.core.locks import (
    get_lock_path,
    has_exact_case_path,
)

# Directories excluded from article listings (raw sources and locks are not wiki articles)
_EXCLUDED_DIRS = {"_raw", ".locks"}

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

TIMEOUT_SECONDS = 15.0
MAX_REPORT_ITEMS = 50


def _clean_markdown_for_links(content: str) -> str:
    """Strip frontmatter, fenced code blocks, images, and inline code before extracting links."""
    # 1. Frontmatter
    cleaned = re.sub(r"(?s)^---.*?---", "", content)
    # 2. Fenced code blocks (``` and ~~~)
    cleaned = re.sub(r"(?s)```.*?```|~~~.*?~~~", "", cleaned)
    # 3. Images
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", cleaned)
    # 4. Inline code (multi-backtick spans first, then single-backtick spans)
    cleaned = re.sub(r"`{2,}.*?`{2,}", "", cleaned)
    cleaned = re.sub(r"`[^`\n]+`", "", cleaned)
    return cleaned


def _has_h1_header(content: str) -> bool:
    """Check if markdown content contains an H1 header."""
    cleaned = _clean_markdown_for_links(content)
    if re.search(r"^#\s+.*", cleaned, re.MULTILINE):
        return True
    if re.search(r"^[^\n]+\n=+\s*$", cleaned, re.MULTILINE):
        return True
    return False


def _extract_raw_link_targets(content: str) -> list[str]:
    """Extract raw link targets from cleaned markdown content."""
    cleaned = _clean_markdown_for_links(content)
    raw_targets: list[str] = []

    # 1. Reference-style links: [ref]: url "Title"
    for match in re.finditer(r"^\s*\[([^\]]+)\]:\s*(\S+)", cleaned, re.MULTILINE):
        raw_url = match.group(2).strip()
        if raw_url.startswith("<") and raw_url.endswith(">"):
            raw_url = raw_url[1:-1].strip()
        raw_url = re.sub(r'\s+["\'(].*$', "", raw_url)
        if raw_url:
            raw_targets.append(raw_url)

    # 2. Inline links: [text](url) or [text](url "Title")
    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", cleaned):
        link_body = match.group(2).strip()
        if not link_body:
            continue
        title_match = re.match(r'^(.*?)\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\))$', link_body)
        target_str = title_match.group(1).strip() if title_match else link_body
        if target_str.startswith("<") and target_str.endswith(">"):
            target_str = target_str[1:-1].strip()
        if target_str:
            raw_targets.append(target_str)

    return raw_targets


def lint_wiki(wiki_root: Path | None = None) -> str:
    """
    Run a deterministic health check scan on the project wiki (.brain-79/).

    Returns a Markdown-formatted report listing broken local links, namespace violations,
    structural errors/warnings, and orphan articles.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    start_time = time.time()
    timeout_reached = False

    broken_links: list[tuple[str, str]] = []
    namespace_violations: list[tuple[str, str]] = []
    structural_errors: list[tuple[str, str]] = []
    file_graph: dict[str, set[str]] = collections.defaultdict(set)

    if not w_root.exists() or not w_root.is_dir():
        return _format_report(
            status="OK",
            timeout_reached=False,
            broken_links=[],
            namespace_violations=[],
            structural_errors=[],
            orphans=[],
        )

    # Gather all .md files excluding _EXCLUDED_DIRS (follow_symlinks=False)
    wiki_files: list[Path] = []
    for root, dirs, files in os.walk(str(w_root), followlinks=False):
        rel_root = Path(root).relative_to(w_root)
        if any(part in _EXCLUDED_DIRS for part in rel_root.parts):
            dirs.clear()
            continue
        dirs[:] = sorted([d for d in dirs if d not in _EXCLUDED_DIRS])

        for f in sorted(files):
            if f.endswith(".md"):
                wiki_files.append(Path(root) / f)

    index_roots: list[str] = []
    existing_rel_files = {f.relative_to(w_root).as_posix(): f for f in wiki_files}

    for p in wiki_files:
        if time.time() - start_time > TIMEOUT_SECONDS:
            timeout_reached = True
            break

        rel_path = p.relative_to(w_root).as_posix()
        if p.name == "INDEX.md":
            index_roots.append(rel_path)

        lock_path = get_lock_path(w_root, rel_path)
        if lock_path.exists():
            try:
                lock = filelock.FileLock(str(lock_path), timeout=0)
                lock.acquire()
                lock.release()
            except filelock.Timeout:
                structural_errors.append((rel_path, "locked (skipped)"))
                continue

        try:
            st = p.stat(follow_symlinks=False)
        except (PermissionError, OSError):
            structural_errors.append(
                (rel_path, "permission_denied or decode_error (skipped)")
            )
            continue

        if st.st_size > MAX_FILE_SIZE:
            structural_errors.append((rel_path, "file_too_large (skipped)"))
            continue

        if st.st_size == 0:
            structural_errors.append((rel_path, "empty (0 bytes)"))
            continue

        try:
            content = p.read_text(encoding="utf-8").replace("\r\n", "\n")
        except (UnicodeDecodeError, PermissionError, OSError):
            structural_errors.append(
                (rel_path, "permission_denied or decode_error (skipped)")
            )
            continue

        if not content.strip():
            structural_errors.append((rel_path, "empty (0 bytes)"))
            continue

        if not _has_h1_header(content):
            structural_errors.append((rel_path, "missing H1 header"))

        raw_targets = _extract_raw_link_targets(content)
        for raw_target in raw_targets:
            # 1. Ignore external URLs
            if (
                raw_target.startswith(
                    (
                        "http://",
                        "https://",
                        "mailto:",
                        "ftp://",
                        "file://",
                        "//",
                        "tel:",
                        "data:",
                    )
                )
                or "://" in raw_target
            ):
                continue

            # 2. Strip anchor fragment & decode URL-encoded paths
            path_part = unquote(raw_target.split("#", 1)[0])
            if not path_part:
                continue

            # 3. Fast normalized relative target calculation (avoids thousands of resolve() syscalls)
            if path_part.startswith("/"):
                norm_rel = posixpath.normpath(path_part.lstrip("/"))
            else:
                parent_rel = p.parent.relative_to(w_root).as_posix()
                combined = (parent_rel + "/" + path_part) if parent_rel != "." else path_part
                norm_rel = posixpath.normpath(combined)

            if norm_rel.startswith("../") or norm_rel == "..":
                broken_links.append((rel_path, raw_target))
                continue

            # Check Namespace Violation first
            if any(part in _EXCLUDED_DIRS for part in Path(norm_rel).parts):
                namespace_violations.append((rel_path, raw_target))
                continue

            if norm_rel in existing_rel_files:
                file_graph[rel_path].add(norm_rel)
                continue

            # Strict check for .md files: must exist in existing_rel_files with exact case
            if norm_rel.endswith(".md"):
                broken_links.append((rel_path, raw_target))
                continue

            # Fallback to filesystem resolution for non-md files or special paths
            target_abs = (w_root / norm_rel).resolve()
            try:
                target_rel = target_abs.relative_to(w_root)
            except ValueError:
                broken_links.append((rel_path, raw_target))
                continue

            # 4. Check Namespace Violation
            if any(part in _EXCLUDED_DIRS for part in target_rel.parts):
                namespace_violations.append((rel_path, raw_target))
                continue

            # 5. Check Existence & exact case for non-md files
            target_rel_posix = target_rel.as_posix()
            if not target_abs.is_file() or not has_exact_case_path(w_root, target_rel_posix):
                broken_links.append((rel_path, raw_target))
            else:
                file_graph[rel_path].add(target_rel_posix)

    # BFS Multi-root from all INDEX.md
    visited: set[str] = set(index_roots)
    queue: collections.deque[str] = collections.deque(index_roots)

    while queue and not timeout_reached:
        if time.time() - start_time > TIMEOUT_SECONDS:
            timeout_reached = True
            break
        curr = queue.popleft()
        for neighbor in sorted(file_graph.get(curr, set())):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    all_rel_files = set(
        p.relative_to(w_root).as_posix()
        for p in wiki_files
        if p.name != "SCHEMA.md" and not p.relative_to(w_root).as_posix().startswith("handoffs/")
    )
    orphans = sorted(list(all_rel_files - visited))

    # Run organizational checks
    from brain79.core.lint_organizational import lint_organizational
    org_issues = lint_organizational(w_root)

    org_errors = [i for i in org_issues if i.severity == "error"]
    org_warnings = [i for i in org_issues if i.severity == "warning"]

    status = (
        "CRITICAL"
        if (broken_links or namespace_violations or org_errors)
        else ("WARNING" if (structural_errors or orphans or org_warnings) else "OK")
    )

    return _format_report(
        status=status,
        timeout_reached=timeout_reached,
        broken_links=broken_links,
        namespace_violations=namespace_violations,
        structural_errors=structural_errors,
        orphans=orphans,
        org_issues=org_issues,
    )


def _format_report(
    status: str,
    timeout_reached: bool,
    broken_links: list[tuple[str, str]],
    namespace_violations: list[tuple[str, str]],
    structural_errors: list[tuple[str, str]],
    orphans: list[str],
    org_issues: list[OrganizationalIssue] | None = None,
) -> str:
    lines: list[str] = [
        "# Brain-79 Lint Report",
        f"[Status: {status}] [timeout_reached: {str(timeout_reached).lower()}]",
        "",
    ]

    if org_issues:
        lines.append("## Organizational Health")
        org_errors = [i for i in org_issues if i.severity == "error"]
        org_warnings = [i for i in org_issues if i.severity == "warning"]
        org_infos = [i for i in org_issues if i.severity == "info"]

        if org_errors:
            lines.append(f"### Errors ({len(org_errors)})")
            for issue in org_errors[:MAX_REPORT_ITEMS]:
                line_str = f" line {issue.line}" if issue.line else ""
                lines.append(f"**ERROR**: `{issue.path}`{line_str}: {issue.message}")
                lines.append(f"  → {issue.actionable}")
            lines.append("")

        if org_warnings:
            lines.append(f"### Warnings ({len(org_warnings)})")
            for issue in org_warnings[:MAX_REPORT_ITEMS]:
                line_str = f" line {issue.line}" if issue.line else ""
                lines.append(f"**WARN**: `{issue.path}`{line_str}: {issue.message}")
                lines.append(f"  → {issue.actionable}")
            lines.append("")

        if org_infos:
            lines.append(f"### Info ({len(org_infos)})")
            for issue in org_infos[:MAX_REPORT_ITEMS]:
                line_str = f" line {issue.line}" if issue.line else ""
                lines.append(f"**INFO**: `{issue.path}`{line_str}: {issue.message}")
                lines.append(f"  → {issue.actionable}")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append(f"## [CRITICAL] Broken Local Links ({len(broken_links)})")
    for origin, target in broken_links[:MAX_REPORT_ITEMS]:
        lines.append(f"- {origin} → `{target}`: target not found")
    if len(broken_links) > MAX_REPORT_ITEMS:
        lines.append(f"... y {len(broken_links) - MAX_REPORT_ITEMS} más ocultos")

    lines.append("")
    lines.append(f"## [CRITICAL] Namespace Violations ({len(namespace_violations)})")
    for origin, target in namespace_violations[:MAX_REPORT_ITEMS]:
        lines.append(f"- {origin} → `{target}`: invalid namespace")
    if len(namespace_violations) > MAX_REPORT_ITEMS:
        lines.append(
            f"... y {len(namespace_violations) - MAX_REPORT_ITEMS} más ocultos"
        )

    lines.append("")
    lines.append(
        f"## [WARNING] Structural Errors & Warnings ({len(structural_errors)})"
    )
    for rel, err in structural_errors[:MAX_REPORT_ITEMS]:
        lines.append(f"- {rel}: {err}")
    if len(structural_errors) > MAX_REPORT_ITEMS:
        lines.append(f"... y {len(structural_errors) - MAX_REPORT_ITEMS} más ocultos")

    lines.append("")
    lines.append(f"## [INFO] Orphans ({len(orphans)})")
    for orphan in orphans[:MAX_REPORT_ITEMS]:
        lines.append(f"- {orphan}")
    if len(orphans) > MAX_REPORT_ITEMS:
        lines.append(f"... y {len(orphans) - MAX_REPORT_ITEMS} más ocultos")

    return "\n".join(lines)
