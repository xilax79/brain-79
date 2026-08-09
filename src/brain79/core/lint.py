import collections
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote

import filelock

from brain79.config import get_wiki_root

# Directories excluded from article listings (raw sources are not wiki articles)
_EXCLUDED_DIRS = {"_raw"}

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


def lint_wiki() -> str:
    """
    Run a deterministic health check scan on the project wiki (.brain-79/).

    Returns a Markdown-formatted report listing broken local links, namespace violations,
    structural errors/warnings, and orphan articles.
    """
    wiki_root = get_wiki_root().resolve()
    start_time = time.time()
    timeout_reached = False

    broken_links: list[tuple[str, str]] = []
    namespace_violations: list[tuple[str, str]] = []
    structural_errors: list[tuple[str, str]] = []
    file_graph: dict[str, set[str]] = collections.defaultdict(set)

    if not wiki_root.exists() or not wiki_root.is_dir():
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
    for root, dirs, files in os.walk(str(wiki_root), followlinks=False):
        rel_root = Path(root).relative_to(wiki_root)
        if any(part in _EXCLUDED_DIRS for part in rel_root.parts):
            dirs.clear()
            continue
        dirs[:] = sorted([d for d in dirs if d not in _EXCLUDED_DIRS])

        for f in sorted(files):
            if f.endswith(".md"):
                wiki_files.append(Path(root) / f)

    index_roots: list[str] = []

    for p in wiki_files:
        if time.time() - start_time > TIMEOUT_SECONDS:
            timeout_reached = True
            break

        rel_path = str(p.relative_to(wiki_root))
        if p.name == "INDEX.md":
            index_roots.append(rel_path)

        lock_path = p.with_suffix(".md.lock")
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
            content = p.read_text(encoding="utf-8")
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

            # 3. Resolve target path
            if path_part.startswith("/"):
                target_abs = (wiki_root / path_part.lstrip("/")).resolve()
            else:
                target_abs = (p.parent / path_part).resolve()

            # Check if within wiki root
            try:
                target_rel = target_abs.relative_to(wiki_root)
            except ValueError:
                broken_links.append((rel_path, raw_target))
                continue

            # 4. Check Namespace Violation
            if any(part in _EXCLUDED_DIRS for part in target_rel.parts):
                namespace_violations.append((rel_path, raw_target))
                continue

            # 5. Check Existence & extension
            if not target_abs.is_file():
                broken_links.append((rel_path, raw_target))
            else:
                file_graph[rel_path].add(str(target_rel))

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

    all_rel_files = set(str(p.relative_to(wiki_root)) for p in wiki_files)
    orphans = sorted(list(all_rel_files - visited))

    status = (
        "CRITICAL"
        if (broken_links or namespace_violations)
        else ("WARNING" if (structural_errors or orphans) else "OK")
    )

    return _format_report(
        status=status,
        timeout_reached=timeout_reached,
        broken_links=broken_links,
        namespace_violations=namespace_violations,
        structural_errors=structural_errors,
        orphans=orphans,
    )


def _format_report(
    status: str,
    timeout_reached: bool,
    broken_links: list[tuple[str, str]],
    namespace_violations: list[tuple[str, str]],
    structural_errors: list[tuple[str, str]],
    orphans: list[str],
) -> str:
    lines: list[str] = [
        "# Brain-79 Lint Report",
        f"[Status: {status}] [timeout_reached: {str(timeout_reached).lower()}]",
        "",
        f"## [CRITICAL] Broken Local Links ({len(broken_links)})",
    ]
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
