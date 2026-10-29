from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
import uuid

import filelock

REGISTRY_FILENAME = ".navigation_registry.json"


def _get_lock(wiki_root: Path) -> filelock.FileLock:
    registry_path = wiki_root / REGISTRY_FILENAME
    lock_path = registry_path.with_suffix(".lock")
    return filelock.FileLock(str(lock_path), timeout=5.0)


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
        tmp_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        tmp_path.replace(registry_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def register_article(
    wiki_root: Path, path: str, title: str, summary: str, section: str
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
        ):
            return

        registry["articles"] = [a for a in articles if a.get("path") != path]
        registry["articles"].append({
            "path": path,
            "title": title or path,
            "summary": summary,
            "section": section,
            "registered_at": datetime.now(UTC).isoformat(),
        })
        _save_registry_unlocked(wiki_root, registry)


def unregister_article(wiki_root: Path, path: str) -> None:
    """Remove article from registry (thread-safe and atomic)."""
    lock = _get_lock(wiki_root)
    with lock:
        registry = load_registry(wiki_root)
        registry["articles"] = [a for a in registry.get("articles", []) if a.get("path") != path]
        _save_registry_unlocked(wiki_root, registry)


def extract_title_and_summary(content: str) -> tuple[str, str]:
    """Extract first H1 as title and first non-heading text line as summary."""
    working_content = content
    if working_content.startswith("---\n"):
        end_idx = working_content.find("\n---\n", 4)
        if end_idx != -1:
            working_content = working_content[end_idx + 5:]

    lines = working_content.split("\n")
    title = ""
    summary = ""
    after_h1 = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
            after_h1 = True
            continue
        if after_h1 and stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            summary = stripped
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

    # Use INDEX.md.lock for synchronization with writes (P1.1)
    index_lock_path = index_path.with_suffix(".md.lock")
    index_lock = filelock.FileLock(str(index_lock_path), timeout=5.0)

    with index_lock:
        content = index_path.read_text(encoding="utf-8")

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
            tmp_path.write_text(updated, encoding="utf-8")
            tmp_path.replace(index_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    return "INDEX.md Quick navigation regenerated."
