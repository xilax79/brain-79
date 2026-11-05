from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
import uuid

import filelock

from brain79.core.locks import (
    acquire_wiki_lock,
    atomic_replace_with_retry,
    cleanup_legacy_inline_locks,
)

REGISTRY_FILENAME = ".navigation_registry.json"


def _get_lock(wiki_root: Path) -> filelock.FileLock:
    return acquire_wiki_lock(wiki_root, REGISTRY_FILENAME, timeout=5.0)


def load_registry(wiki_root: Path) -> dict[str, Any]:
    """Load navigation registry. Returns empty structure if missing/corrupt."""
    registry_path = wiki_root / REGISTRY_FILENAME
    if not registry_path.exists():
        return {"articles": []}
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "articles" in data and isinstance(data["articles"], list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"articles": []}


def _save_registry_unlocked(wiki_root: Path, registry: dict[str, Any]) -> None:
    """Atomic write of registry (expects lock already held)."""
    registry_path = wiki_root / REGISTRY_FILENAME
    tmp_path = registry_path.with_suffix(f".tmp.{uuid.uuid4().hex}")
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

    # Exclude handoffs from navigation registry (P0.5)
    if path.startswith("handoffs/") or section == "handoffs":
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

        # Avoid updating registered_at if content metadata has not changed (P2.2)
        existing = next((a for a in articles if a.get("path") == path), None)
        if (
            existing is not None
            and existing.get("title") == (title or path)
            and existing.get("summary") == summary
            and existing.get("section") == section
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
            "section": section,
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


def generate_quick_navigation(wiki_root: Path) -> str:
    """Generate Quick navigation section, grouped by section, sorted by title."""
    registry = load_registry(wiki_root)
    by_section: dict[str, list[dict[str, Any]]] = {}
    for article in registry.get("articles", []):
        path_str = article.get("path", "")
        sec = article.get("section", "root")
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


def regenerate_index_navigation(wiki_root: Path) -> str:
    """Regenerate Quick navigation section in INDEX.md from navigation registry (atomic & locked)."""
    index_path = wiki_root / "INDEX.md"
    if not index_path.exists():
        raise FileNotFoundError("INDEX.md not found.")

    # Self-heal registry: purge any handoff articles that may have been previously registered (P0.5)
    lock_reg = _get_lock(wiki_root)
    with lock_reg:
        registry = load_registry(wiki_root)
        articles = registry.get("articles", [])
        cleaned = [
            a for a in articles
            if not a.get("path", "").startswith("handoffs/") and a.get("section") != "handoffs"
        ]
        if len(cleaned) != len(articles):
            registry["articles"] = cleaned
            _save_registry_unlocked(wiki_root, registry)

    new_section = generate_quick_navigation(wiki_root)

    # Use centralized INDEX.md.lock for synchronization with writes (P1.1, Phase 6)
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

        tmp_path = index_path.with_suffix(f".tmp.{uuid.uuid4().hex}")
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
