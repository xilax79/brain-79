from datetime import UTC, datetime
from pathlib import Path
import shutil
import subprocess

import filelock

from brain79.config import get_wiki_root

# Directories excluded from article listings (raw sources are not wiki articles)
_EXCLUDED_DIRS = {"_raw"}

_RG_PATH: str | None = shutil.which("rg")


def _safe_resolve(path: str) -> Path:
    """Resolve a relative wiki path and verify it stays within the wiki root."""
    wiki_root = get_wiki_root().resolve()
    target = (wiki_root / path).resolve()
    if not target.is_relative_to(wiki_root):
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


def write_article(path: str, content: str, timeout: float = 5.0) -> str:
    """
    Write or update an article atomically with file locking. Creates parent directories as needed.

    Note: The .md.lock file remains on disk between writes (standard filelock behavior on Unix).
    It is excluded by .gitignore and article search patterns (*.md).
    For manual cleanup: find .brain-79 -name '*.lock' -delete.
    """
    target = _safe_resolve(path)

    if target.suffix != ".md":
        raise ValueError(f"write_article requires .md paths, got {path}")

    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(".md.lock")
    lock = filelock.FileLock(str(lock_path), timeout=timeout)

    try:
        with lock:
            tmp_path = target.with_suffix(".md.tmp")
            try:
                tmp_path.write_text(content, encoding="utf-8")
                tmp_path.replace(target)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
    except filelock.Timeout:
        raise OSError(
            f"El archivo {path} está bloqueado por otro proceso. Reintenta en unos segundos."
        )

    return f"Written: {path}"


def list_articles(section: str | None = None) -> list[str]:
    """List all markdown articles (excluding _raw/) optionally filtered by section."""
    wiki_root = get_wiki_root()
    if not wiki_root.exists():
        return []

    if section and (
        section in _EXCLUDED_DIRS
        or any(part in _EXCLUDED_DIRS for part in Path(section).parts)
    ):
        return []

    root = wiki_root / section if section else wiki_root
    if not root.exists():
        return []

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


def _search_ripgrep(query: str) -> list[dict[str, str]]:
    wiki_root = get_wiki_root()
    cmd = [
        _RG_PATH or "rg",
        "-i",
        "-F",
        "-n",
        "--null",
        "-g",
        "*.md",
        "-g",
        "!_raw/**",
        "--no-follow",
        query,
        str(wiki_root),
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if res.returncode >= 2:
        raise ValueError(f"ripgrep failed with return code {res.returncode}")

    results: list[dict[str, str]] = []
    seen_files: set[str] = set()

    for line in res.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\0", 1)
        if len(parts) != 2:
            continue
        filepath_str, rest = parts
        try:
            rel = Path(filepath_str).relative_to(wiki_root)
        except ValueError:
            continue

        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue

        rel_str = str(rel)
        if rel_str in seen_files:
            continue
        seen_files.add(rel_str)

        content_parts = rest.split(":", 1)
        excerpt = content_parts[1].strip() if len(content_parts) == 2 else rest.strip()
        results.append({"path": rel_str, "excerpt": excerpt[:200]})

    return results


def _search_python(query: str) -> list[dict[str, str]]:
    wiki_root = get_wiki_root()
    query_lower = query.lower()
    results: list[dict[str, str]] = []

    for p in sorted(wiki_root.rglob("*.md")):
        rel = p.relative_to(wiki_root)
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue

        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue

        if query_lower not in content.lower():
            continue

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


def search_articles(query: str) -> list[dict[str, str]]:
    """Search wiki articles by keyword (case-insensitive). Returns path + excerpt."""
    wiki_root = get_wiki_root()
    if not wiki_root.exists():
        return []

    if not query or not query.strip():
        return []

    if _RG_PATH:
        try:
            return _search_ripgrep(query)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return _search_python(query)

    return _search_python(query)


def save_raw_session(session_summary: str, instructions: str | None = None) -> str:
    """Save a raw session summary to _raw/sessions/ and return the saved path."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S-%f")[:-3]
    rel_path = f"_raw/sessions/session-{timestamp}.md"

    lines = [f"# Session — {timestamp}\n"]
    if instructions:
        lines.append(f"> **Curation instructions:** {instructions}\n")
    lines.append(session_summary)

    write_article(rel_path, "\n".join(lines))
    return rel_path
