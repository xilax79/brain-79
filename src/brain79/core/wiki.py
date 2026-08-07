from datetime import UTC
from pathlib import Path

from brain79.config import get_wiki_root

# Directories excluded from article listings (raw sources are not wiki articles)
_EXCLUDED_DIRS = {"_raw"}


def _safe_resolve(path: str) -> Path:
    """Resolve a relative wiki path and verify it stays within the wiki root."""
    wiki_root = get_wiki_root()
    target = (wiki_root / path).resolve()
    if not str(target).startswith(str(wiki_root.resolve())):
        raise ValueError(f"Path '{path}' resolves outside the wiki directory.")
    return target


def resolve_wiki_path(path: str) -> Path:
    """Public alias to resolve a relative wiki path safely."""
    return _safe_resolve(path)


def read_article(path: str) -> str:
    """Read an article by its relative path within the wiki."""
    target = _safe_resolve(path)
    if not target.exists():
        raise FileNotFoundError(f"Article not found: {path}")
    if not target.is_file():
        raise ValueError(f"Path is not a file: {path}")
    return target.read_text(encoding="utf-8")


def write_article(path: str, content: str) -> str:
    """Write or update an article. Creates parent directories as needed."""
    target = _safe_resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Written: {path}"


def list_articles(section: str | None = None) -> list[str]:
    """List all markdown articles (excluding _raw/) optionally filtered by section."""
    wiki_root = get_wiki_root()
    if not wiki_root.exists():
        return []

    root = wiki_root / section if section else wiki_root

    articles: list[str] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(wiki_root)
        if not any(part in _EXCLUDED_DIRS for part in rel.parts):
            articles.append(str(rel))

    return articles


def get_index() -> str:
    """Return the content of INDEX.md."""
    try:
        return read_article("INDEX.md")
    except FileNotFoundError:
        return (
            "INDEX.md not found.\n"
            "Run `brain79 init --project-root <path>` to initialize the wiki."
        )


def search_articles(query: str) -> list[dict[str, str]]:
    """Search wiki articles by keyword (case-insensitive). Returns path + excerpt."""
    wiki_root = get_wiki_root()
    if not wiki_root.exists():
        return []

    query_lower = query.lower()
    results: list[dict[str, str]] = []

    for p in sorted(wiki_root.rglob("*.md")):
        rel = p.relative_to(wiki_root)
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue

        content = p.read_text(encoding="utf-8")
        if query_lower not in content.lower():
            continue

        # First matching line as excerpt
        excerpt = next(
            (
                line.strip()
                for line in content.splitlines()
                if query_lower in line.lower()
            ),
            "",
        )
        results.append({"path": str(rel), "excerpt": excerpt[:200]})

    return results


def save_raw_session(session_summary: str, instructions: str | None = None) -> str:
    """Save a raw session summary to _raw/sessions/ and return the saved path."""
    from datetime import datetime

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    rel_path = f"_raw/sessions/session-{timestamp}.md"

    lines = [f"# Session — {timestamp}\n"]
    if instructions:
        lines.append(f"> **Curation instructions:** {instructions}\n")
    lines.append(session_summary)

    write_article(rel_path, "\n".join(lines))
    return rel_path
