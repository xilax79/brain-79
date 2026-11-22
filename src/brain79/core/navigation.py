from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid

import filelock

from brain79.core.locks import (
    acquire_wiki_lock,
    atomic_replace_with_retry,
    cleanup_legacy_inline_locks,
    create_temp_path,
)

REGISTRY_FILENAME = ".navigation_registry.json"


def _get_lock(wiki_root: Path) -> filelock.FileLock:
    return acquire_wiki_lock(wiki_root, REGISTRY_FILENAME, timeout=5.0)


_EXCLUDED_SCAN_DIRS: frozenset[str] = frozenset({"_raw", ".locks", "handoffs"})
_EXCLUDED_SCAN_FILES: frozenset[str] = frozenset({"INDEX.md", "SCHEMA.md"})


def _scan_indexable_md_files(wiki_root: Path) -> list[tuple[str, Path]]:
    """Return sorted (rel_posix_path, abs_path) pairs for all indexable .md files (followlinks=False)."""
    if not wiki_root.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(wiki_root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(wiki_root)
        # Prune excluded top-level directories
        if not rel_dir.parts:
            dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDED_SCAN_DIRS)
        else:
            dirnames[:] = sorted(dirnames)
        for fname in sorted(filenames):
            if not fname.endswith(".md"):
                continue
            full_path = Path(dirpath) / fname
            if full_path.is_symlink():
                continue
            rel_posix_path = full_path.relative_to(wiki_root).as_posix()
            if rel_posix_path in _EXCLUDED_SCAN_FILES:
                continue
            found.append((rel_posix_path, full_path))
    found.sort(key=lambda item: item[0])
    return found


def _build_registry_from_disk(wiki_root: Path) -> dict[str, Any]:
    """Scan indexable .md files on disk and construct a deterministic navigation registry dict."""
    articles: list[dict[str, Any]] = []
    now_iso = datetime.now(UTC).isoformat()

    for rel_path, full_path in _scan_indexable_md_files(wiki_root):
        try:
            content = full_path.read_text(encoding="utf-8")
        except OSError:
            continue

        title, summary = extract_title_and_summary(content)
        try:
            graph_meta = extract_graph_metadata(content, rel_path=rel_path)
        except Exception:
            graph_meta = {}

        parts = Path(rel_path).parts
        section = parts[0].strip().lower() if len(parts) > 1 else "root"
        if not section:
            section = "root"

        entry: dict[str, Any] = {
            "path": rel_path,
            "title": title or rel_path,
            "summary": summary,
            "section": section,
            "registered_at": now_iso,
        }
        if graph_meta.get("applies_to"):
            entry["applies_to"] = graph_meta["applies_to"]
        if graph_meta.get("related"):
            entry["related"] = graph_meta["related"]
        if graph_meta.get("supersedes"):
            entry["supersedes"] = graph_meta["supersedes"]
        if graph_meta.get("outgoing_links"):
            entry["outgoing_links"] = graph_meta["outgoing_links"]

        articles.append(entry)

    articles.sort(key=lambda a: str(a.get("path", "")))
    return {"articles": articles}


def rebuild_navigation_registry(wiki_root: Path, *, persist: bool = True) -> dict[str, Any]:
    """Deterministically rebuild .navigation_registry.json from Markdown files on disk.

    Scans .md files excluding _raw/, .locks/, handoffs/, INDEX.md, SCHEMA.md (followlinks=False),
    sorts by path ascending, and atomically persists under _registry.lock when persist=True.
    Gracefully returns the in-memory registry on read-only filesystems (PermissionError/OSError).
    """
    registry = _build_registry_from_disk(wiki_root)
    if persist:
        try:
            lock = _get_lock(wiki_root)
            with lock:
                _save_registry_unlocked(wiki_root, registry)
        except (PermissionError, OSError):
            pass
    return registry


def load_registry(wiki_root: Path, *, persist: bool = False) -> dict[str, Any]:
    """Load navigation registry, auto-rebuilding from disk if missing, corrupt, or out of sync."""
    registry_path = wiki_root / REGISTRY_FILENAME
    on_disk_items = _scan_indexable_md_files(wiki_root)
    on_disk_paths = {rel_path for rel_path, _ in on_disk_items}

    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "articles" in data and isinstance(data["articles"], list):
                if not on_disk_items:
                    return data
                cached_paths = {
                    str(a.get("path", ""))
                    for a in data["articles"]
                    if isinstance(a, dict) and a.get("path")
                }
                if cached_paths == on_disk_paths and len(cached_paths) == len(data["articles"]):
                    return data
        except (OSError, json.JSONDecodeError):
            pass

    if on_disk_items:
        return rebuild_navigation_registry(wiki_root, persist=persist)
    return {"articles": []}


def _save_registry_unlocked(wiki_root: Path, registry: dict[str, Any]) -> None:
    """Atomic write of registry (expects lock already held)."""
    registry_path = wiki_root / REGISTRY_FILENAME
    tmp_path = create_temp_path(registry_path)
    try:
        tmp_path.write_text(json.dumps(registry, indent=2), encoding="utf-8", newline="\n")
        atomic_replace_with_retry(tmp_path, registry_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def extract_graph_metadata(content: str, rel_path: str | None = None) -> dict[str, Any]:
    """Extract applies_to, related, and outgoing markdown links from article content.

    If rel_path is provided, relative Markdown links (e.g. `../decisions/adr-001.md`)
    are normalized relative to the article's parent directory, producing clean wiki-root relative paths.
    """
    import posixpath
    from brain79.core.frontmatter import parse_frontmatter
    from brain79.core.lint import _extract_raw_link_targets

    meta, body = parse_frontmatter(content)
    meta = meta or {}

    applies_to_val = meta.get("applies_to", [])
    if isinstance(applies_to_val, str):
        applies_to = [applies_to_val]
    elif isinstance(applies_to_val, list):
        applies_to = [str(x) for x in applies_to_val if x]
    else:
        applies_to = []

    related_val = meta.get("related", [])
    if isinstance(related_val, str):
        related = [related_val]
    elif isinstance(related_val, list):
        related = [str(x) for x in related_val if x]
    else:
        related = []

    supersedes_val = meta.get("supersedes", [])
    if isinstance(supersedes_val, str):
        supersedes = [supersedes_val]
    elif isinstance(supersedes_val, list):
        supersedes = [str(x) for x in supersedes_val if x]
    else:
        supersedes = []

    # Outgoing markdown links
    raw_targets = _extract_raw_link_targets(body or content)
    outgoing_links: list[str] = []
    parent_dir = posixpath.dirname(rel_path.replace("\\", "/")) if rel_path else ""

    for raw in raw_targets:
        if "://" in raw or raw.startswith(("#", "mailto:", "//")):
            continue
        cleaned = raw.split("#", 1)[0].strip()
        if cleaned.endswith(".md"):
            # If target begins with a known top-level wiki directory or is already relative to root,
            # or if it begins with ../, resolve accurately
            if parent_dir and not cleaned.startswith("/"):
                # If cleaned is something like "../decisions/adr-001.md"
                joined = posixpath.normpath(posixpath.join(parent_dir, cleaned))
                # If user wrote "decisions/adr-001.md" directly from subfolder, check if it already targets a top-level folder
                top_level_dirs = {"product", "architecture", "features", "decisions", "changelog", "context", "topics", "log", "_raw"}
                first_part = cleaned.split("/", 1)[0]
                if first_part in top_level_dirs and not cleaned.startswith("../"):
                    normalized = posixpath.normpath(cleaned)
                else:
                    normalized = joined
            else:
                normalized = posixpath.normpath(cleaned.lstrip("/"))

            # Avoid resolving outside wiki root
            if not normalized.startswith("..") and normalized not in outgoing_links:
                outgoing_links.append(normalized)

    return {
        "applies_to": applies_to,
        "related": related,
        "supersedes": supersedes,
        "outgoing_links": outgoing_links,
    }


def register_article(
    wiki_root: Path,
    path: str,
    title: str,
    summary: str,
    section: str,
    graph_meta: dict[str, Any] | None = None,
) -> None:
    """Add or update article in navigation registry (thread-safe and atomic)."""
    if not path or not path.strip():
        raise ValueError(f"Invalid path for navigation registry: {path}")

    p = Path(path)
    if ".." in p.parts or path.startswith("/") or p.is_absolute():
        raise ValueError(f"Invalid path for navigation registry: {path}")

    # Normalize section key to lowercase (R-1.1)
    norm_section = (section or "root").strip().lower() or "root"

    # Exclude handoffs from navigation registry
    if path.startswith("handoffs/") or norm_section == "handoffs":
        return

    graph_meta = graph_meta or {}
    applies_to = graph_meta.get("applies_to", [])
    related = graph_meta.get("related", [])
    supersedes = graph_meta.get("supersedes", [])
    outgoing_links = graph_meta.get("outgoing_links", [])

    lock = _get_lock(wiki_root)
    with lock:
        registry = load_registry(wiki_root)
        articles = registry.get("articles", [])

        # Avoid updating registered_at if content metadata has not changed and on-disk registry is already in sync
        existing = next((a for a in articles if a.get("path") == path), None)
        registry_file = wiki_root / REGISTRY_FILENAME
        disk_in_sync = False
        if registry_file.is_file() and existing is not None:
            try:
                disk_data = json.loads(registry_file.read_text(encoding="utf-8"))
                disk_articles = disk_data.get("articles", []) if isinstance(disk_data, dict) else []
                disk_paths = {a.get("path") for a in disk_articles if isinstance(a, dict) and a.get("path")}
                mem_paths = {a.get("path") for a in articles if isinstance(a, dict) and a.get("path")}
                disk_in_sync = len(disk_articles) == len(articles) and disk_paths == mem_paths
            except (OSError, json.JSONDecodeError):
                disk_in_sync = False
        if (
            disk_in_sync
            and existing is not None
            and existing.get("title") == (title or path)
            and existing.get("summary") == summary
            and existing.get("section") == norm_section
            and existing.get("applies_to", []) == applies_to
            and existing.get("related", []) == related
            and existing.get("supersedes", []) == supersedes
            and existing.get("outgoing_links", []) == outgoing_links
        ):
            return

        registry["articles"] = [a for a in articles if a.get("path") != path]
        entry: dict[str, Any] = {
            "path": path,
            "title": title or path,
            "summary": summary,
            "section": norm_section,
            "registered_at": datetime.now(UTC).isoformat(),
        }
        if applies_to:
            entry["applies_to"] = applies_to
        if related:
            entry["related"] = related
        if supersedes:
            entry["supersedes"] = supersedes
        if outgoing_links:
            entry["outgoing_links"] = outgoing_links

        registry["articles"].append(entry)
        _save_registry_unlocked(wiki_root, registry)


def unregister_article(wiki_root: Path, path: str) -> None:
    """Remove article from registry (thread-safe and atomic)."""
    lock = _get_lock(wiki_root)
    with lock:
        registry = load_registry(wiki_root)
        registry["articles"] = [a for a in registry.get("articles", []) if a.get("path") != path]
        _save_registry_unlocked(wiki_root, registry)


def extract_title_and_summary(content: str) -> tuple[str, str]:
    """Extract first H1 as title and summary from frontmatter or lead paragraph."""
    working_content = content
    summary = ""
    title = ""

    # 1. Try to extract summary and title from frontmatter if present
    if working_content.startswith("---\n") or working_content == "---":
        try:
            from brain79.core.frontmatter import parse_frontmatter
            meta, body = parse_frontmatter(working_content)
            if meta and meta.get("summary"):
                s = " ".join(str(meta["summary"]).strip().strip('"\'').split())
                if s:
                    summary = s
            if meta and meta.get("title") and not title:
                t = str(meta["title"]).strip()
                if t:
                    title = t
            working_content = body
        except Exception:
            # Fallback to manual split if frontmatter parsing fails
            end_idx = working_content.find("\n---\n", 4)
            if end_idx != -1:
                working_content = working_content[end_idx + 5:]

    lines = working_content.split("\n")
    after_h1 = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
            after_h1 = True
            continue

        # If summary was already extracted from frontmatter, only title was needed
        if summary:
            if title:
                break
            continue

        if after_h1:
            # Stop if we hit a subheading before finding a lead paragraph
            if stripped.startswith("## ") or stripped.startswith("### "):
                break
            # Skip empty lines, blockquotes, list items, code fences
            if (
                not stripped
                or stripped.startswith("#")
                or stripped.startswith(">")
                or stripped.startswith("- ")
                or stripped.startswith("* ")
                or stripped.startswith("1. ")
                or stripped.startswith("```")
                or stripped.startswith("~~~")
            ):
                continue
            # Skip lines ending with colon (like "Problem:", "Requirements:")
            if stripped.endswith(":"):
                continue
            # Found clean lead paragraph
            summary = stripped
            if title:
                break

    # Secondary fallback for summary if still empty and we have lines after H1
    if not summary and after_h1:
        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith(">")
                and not stripped.startswith("```")
                and not stripped.startswith("~~~")
            ):
                summary = stripped.rstrip(":")
                break

    return title, summary


_ESCAPE_CHARS = str.maketrans({
    "[": "\\[",
    "]": "\\]",
    "*": "\\*",
    "_": "\\_",
    "<": "\\<",
    ">": "\\>",
    "|": "\\|",
    "~": "\\~",
    # ` removed — backticks in link text are valid inline code (BUG-12 fix)
})


def _escape_markdown(text: str) -> str:
    """Escape markdown special chars in titles and summaries for safe rendering."""
    return text.translate(_ESCAPE_CHARS)


def _render_quick_navigation(registry: dict[str, Any]) -> str:
    """Render Quick navigation section from an in-memory registry snapshot."""
    by_section: dict[str, list[dict[str, Any]]] = {}
    for article in registry.get("articles", []):
        path_str = article.get("path", "")
        sec = str(article.get("section", "root") or "root").strip().lower() or "root"
        if path_str.startswith("handoffs/") or sec == "handoffs":
            continue
        by_section.setdefault(sec, []).append(article)

    lines = ["## Quick navigation", ""]
    if not by_section:
        lines.append("*No registered articles.*")
        return "\n".join(lines)

    for section_name in sorted(by_section.keys()):
        articles = sorted(by_section[section_name], key=lambda a: str(a.get("title", "")))
        header_name = "General" if section_name == "root" else section_name.capitalize()
        lines.append(f"### {header_name}")
        for article in articles:
            title_safe = _escape_markdown(article["title"])
            sum_raw = article.get("summary")
            summary = f" — {_escape_markdown(sum_raw)}" if sum_raw else ""
            lines.append(f"- [{title_safe}]({article['path']}){summary}")
        lines.append("")
    return "\n".join(lines).rstrip()


def generate_quick_navigation(wiki_root: Path) -> str:
    """Generate Quick navigation section, grouped by section, sorted by title."""
    registry = load_registry(wiki_root)
    return _render_quick_navigation(registry)


def regenerate_index_navigation(wiki_root: Path, *, rebuild: bool = False) -> str:
    """Regenerate Quick navigation section in INDEX.md from navigation registry (atomic & locked).

    Follows the global lock hierarchy:
        _registry.lock -> _drift_manifest.lock -> INDEX.md.lock
    Computes the rendered Quick navigation section from the registry snapshot captured under
    _registry.lock and writes INDEX.md under INDEX.md.lock before releasing _registry.lock,
    eliminating any unlocked read window (TOCTOU).
    """
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        raise FileNotFoundError("INDEX.md not found.")

    # Self-heal registry & drift manifest under _registry.lock, then write INDEX.md under INDEX.md.lock
    lock_reg = _get_lock(wiki_root)
    with lock_reg:
        if rebuild:
            registry = _build_registry_from_disk(wiki_root)
            try:
                _save_registry_unlocked(wiki_root, registry)
            except (PermissionError, OSError):
                pass
        else:
            registry = load_registry(wiki_root)
        articles = registry.get("articles", [])
        cleaned: list[dict[str, Any]] = []
        registry_mutated = False
        if not rebuild:
            reg_file = wiki_root / REGISTRY_FILENAME
            if not reg_file.is_file():
                registry_mutated = bool(articles)
            else:
                try:
                    disk_raw = json.loads(reg_file.read_text(encoding="utf-8"))
                    disk_arts = disk_raw.get("articles", []) if isinstance(disk_raw, dict) else []
                    disk_paths = {a.get("path") for a in disk_arts if isinstance(a, dict) and a.get("path")}
                    mem_paths = {a.get("path") for a in articles if isinstance(a, dict) and a.get("path")}
                    if len(disk_arts) != len(articles) or disk_paths != mem_paths:
                        registry_mutated = True
                except (OSError, json.JSONDecodeError):
                    registry_mutated = True
        for a in articles:
            path_str = a.get("path", "")
            raw_sec = a.get("section", "root")
            norm_sec = str(raw_sec or "root").strip().lower() or "root"
            if path_str.startswith("handoffs/") or norm_sec == "handoffs":
                registry_mutated = True
                continue
            if not (wiki_root / path_str).is_file():
                registry_mutated = True
                continue
            if raw_sec != norm_sec:
                a = dict(a)
                a["section"] = norm_sec
                registry_mutated = True
            cleaned.append(a)

        if registry_mutated:
            registry["articles"] = cleaned
            _save_registry_unlocked(wiki_root, registry)

        manifest_file = wiki_root / ".drift_manifest.json"
        if manifest_file.is_file():
            try:
                drift_lock = acquire_wiki_lock(wiki_root, ".drift_manifest.json", timeout=5.0)
                with drift_lock:
                    if manifest_file.is_file():
                        m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                        m_articles = m_data.get("articles", {})
                        cleaned_m = {
                            p: entry for p, entry in m_articles.items()
                            if (wiki_root / p).is_file()
                        }
                        if len(cleaned_m) != len(m_articles):
                            m_data["articles"] = cleaned_m
                            tmp_m = create_temp_path(manifest_file)
                            try:
                                tmp_m.write_text(
                                    json.dumps(m_data, indent=2, sort_keys=True) + "\n",
                                    encoding="utf-8",
                                    newline="\n",
                                )
                                atomic_replace_with_retry(tmp_m, manifest_file)
                            finally:
                                if tmp_m.exists():
                                    try:
                                        tmp_m.unlink()
                                    except OSError:
                                        pass
            except Exception:
                pass

        # Render Quick navigation from the locked registry snapshot (zero unlocked read window)
        new_section = _render_quick_navigation(registry)

        # Acquire INDEX.md.lock while still holding _registry.lock (strict lock order: 1 -> 3)
        index_lock = acquire_wiki_lock(wiki_root, "INDEX.md", timeout=5.0)
        with index_lock:
            content = index_path.read_text(encoding="utf-8").replace("\r\n", "\n")

            # Update last_updated date in frontmatter to today
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            if content.startswith("---\n"):
                content = re.sub(
                    r"^last_updated:\s*.*$",
                    f"last_updated: {today}",
                    content,
                    flags=re.MULTILINE,
                )

            # Remove ALL existing Quick navigation sections to avoid duplicates
            cleaned_content = re.sub(
                r"## Quick navigation\n.*?(?=\n## |\Z)",
                "",
                content,
                flags=re.DOTALL,
            ).rstrip()

            # Insert the new Quick navigation section
            updated = cleaned_content + "\n\n" + new_section + "\n"

            tmp_path = create_temp_path(index_path)
            try:
                tmp_path.write_text(updated, encoding="utf-8", newline="\n")
                atomic_replace_with_retry(tmp_path, index_path)
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass

    cleanup_legacy_inline_locks(wiki_root)
    return "INDEX.md Quick navigation regenerated."


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NAV_LINK_RE = re.compile(r"^- \[.*?\]\(([^)]+)\)")


def _parse_index_for_merge(text: str) -> tuple[dict[str, Any], str, dict[str, tuple[str, str]]]:
    """Parse INDEX.md into (frontmatter_dict, preamble_text, nav_entries[path -> (section_lower, bullet_line)])."""
    from brain79.core.frontmatter import parse_frontmatter

    norm = text.replace("\r\n", "\n")
    meta: dict[str, Any] = {}
    body = norm
    if norm.startswith("---\n") or norm == "---":
        try:
            meta, body = parse_frontmatter(norm)
        except Exception:
            meta = {}
            body = norm

    # Split body at `## Quick navigation`
    m_nav = re.search(r"(?m)^## Quick navigation\s*$", body)
    if not m_nav:
        return meta, body.strip(), {}

    preamble = body[: m_nav.start()].strip()
    nav_block = body[m_nav.end() :]
    # Stop if another H2 follows Quick navigation
    m_next_h2 = re.search(r"(?m)^## ", nav_block)
    if m_next_h2:
        nav_block = nav_block[: m_next_h2.start()]

    entries: dict[str, tuple[str, str]] = {}
    current_section = "root"
    for raw_line in nav_block.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            header = line[4:].strip().lower()
            current_section = "root" if header == "general" else header
        elif line.startswith("- ["):
            m_link = _NAV_LINK_RE.match(line)
            if m_link:
                rel_p = m_link.group(1).strip()
                entries[rel_p] = (current_section, line)

    return meta, preamble, entries


def _render_merged_quick_nav(entries: dict[str, tuple[str, str]]) -> str:
    """Render merged Quick navigation entries canonically matching _render_quick_navigation()."""
    by_section: dict[str, list[tuple[str, str]]] = {}
    for path_str, (sec, bullet) in entries.items():
        norm_sec = (sec or "root").strip().lower() or "root"
        if path_str.startswith("handoffs/") or norm_sec == "handoffs":
            continue
        # Extract display title for sorting (matches _render_quick_navigation sorting by title)
        m_title = re.match(r"^- \[([^\]]*)\]", bullet)
        sort_key = m_title.group(1) if m_title else path_str
        by_section.setdefault(norm_sec, []).append((sort_key, bullet))

    lines = ["## Quick navigation", ""]
    if not by_section:
        lines.append("*No registered articles.*")
        return "\n".join(lines)

    for section_name in sorted(by_section.keys()):
        header_name = "General" if section_name == "root" else section_name.capitalize()
        lines.append(f"### {header_name}")
        for _, bullet in sorted(by_section[section_name], key=lambda item: (item[0], item[1])):
            lines.append(bullet)
        lines.append("")
    return "\n".join(lines).rstrip()


def _reextract_entry_from_disk(wiki_root: Path, rel_path: str) -> tuple[str, str] | None:
    """Re-extract (section_lower, bullet_line) from wiki_root / rel_path if present on disk."""
    target = wiki_root / rel_path
    if not target.is_file():
        return None
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return None
    title, summary = extract_title_and_summary(content)
    parts = Path(rel_path).parts
    section = parts[0].strip().lower() if len(parts) > 1 else "root"
    title_safe = _escape_markdown(title or rel_path)
    summary_part = f" — {_escape_markdown(summary)}" if summary else ""
    bullet = f"- [{title_safe}]({rel_path}){summary_part}"
    return (section or "root", bullet)


def merge_index_files(
    base_path: Path,
    ours_path: Path,
    theirs_path: Path,
    *,
    wiki_root: Path | None = None,
) -> int:
    """Deterministic 3-way Git merge driver for INDEX.md (%O, %A, %B).

    Writes the merged result atomically to `ours_path` with LF line endings.
    Returns 0 on clean merge, 1 on preamble conflict (with standard Git conflict markers).
    Operates purely on the three input files without requiring .navigation_registry.json or .locks/.
    """
    from brain79.core.frontmatter import dump_frontmatter

    base_meta, base_pre, base_nav = _parse_index_for_merge(base_path.read_text(encoding="utf-8"))
    ours_meta, ours_pre, ours_nav = _parse_index_for_merge(ours_path.read_text(encoding="utf-8"))
    theirs_meta, theirs_pre, theirs_nav = _parse_index_for_merge(theirs_path.read_text(encoding="utf-8"))

    # 1. Merge frontmatter
    merged_meta: dict[str, Any] = {}
    all_keys = set(base_meta.keys()) | set(ours_meta.keys()) | set(theirs_meta.keys())
    for k in sorted(all_keys):
        if k in ("type", "last_updated"):
            continue
        b_v = base_meta.get(k)
        o_v = ours_meta.get(k)
        t_v = theirs_meta.get(k)
        if o_v == t_v:
            if o_v is not None:
                merged_meta[k] = o_v
        elif o_v == b_v:
            if t_v is not None:
                merged_meta[k] = t_v
        else:
            if o_v is not None:
                merged_meta[k] = o_v

    merged_meta["type"] = "navigation"
    o_date = str(ours_meta.get("last_updated", "")).strip()
    t_date = str(theirs_meta.get("last_updated", "")).strip()
    valid_dates = [d for d in (o_date, t_date) if _ISO_DATE_RE.match(d)]
    if valid_dates:
        merged_meta["last_updated"] = max(valid_dates)
    elif o_date:
        merged_meta["last_updated"] = o_date
    elif t_date:
        merged_meta["last_updated"] = t_date

    # 2. Merge preamble (3-way)
    preamble_conflict = False
    if ours_pre == theirs_pre or theirs_pre == base_pre:
        merged_pre = ours_pre
    elif ours_pre == base_pre:
        merged_pre = theirs_pre
    else:
        preamble_conflict = True
        merged_pre = f"<<<<<<< ours\n{ours_pre}\n=======\n{theirs_pre}\n>>>>>>> theirs"

    # 3. Merge Quick navigation entries (3-way)
    merged_nav: dict[str, tuple[str, str]] = {}
    all_paths = set(base_nav.keys()) | set(ours_nav.keys()) | set(theirs_nav.keys())
    for p in sorted(all_paths):
        b_e = base_nav.get(p)
        o_e = ours_nav.get(p)
        t_e = theirs_nav.get(p)

        if o_e == t_e:
            if o_e is not None:
                merged_nav[p] = o_e
        elif o_e == b_e:
            # Ours unchanged -> take theirs (including deletion if t_e is None)
            if t_e is not None:
                merged_nav[p] = t_e
        elif t_e == b_e:
            # Theirs unchanged -> take ours (including deletion if o_e is None)
            if o_e is not None:
                merged_nav[p] = o_e
        else:
            # Both sides diverged on this entry
            if o_e is None and t_e is not None:
                merged_nav[p] = t_e
            elif t_e is None and o_e is not None:
                merged_nav[p] = o_e
            else:
                reextracted = _reextract_entry_from_disk(wiki_root, p) if wiki_root is not None else None
                if reextracted is not None:
                    merged_nav[p] = reextracted
                elif o_e is not None:
                    merged_nav[p] = o_e

    rendered_nav = _render_merged_quick_nav(merged_nav)
    body_parts = [part for part in (merged_pre, rendered_nav) if part]
    final_body = "\n\n".join(body_parts) + "\n"
    final_content = dump_frontmatter(merged_meta, final_body)

    tmp_path = create_temp_path(ours_path)
    try:
        tmp_path.write_text(final_content, encoding="utf-8", newline="\n")
        atomic_replace_with_retry(tmp_path, ours_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return 1 if preamble_conflict else 0
