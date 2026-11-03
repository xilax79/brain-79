"""
Deterministic Code-to-Wiki Drift Detection (Phase 4).

Monitors source code files governed by wiki articles via the `applies_to` frontmatter field.
If workspace files matching `applies_to` globs/paths have been modified in commits (or uncommitted working tree changes)
after the article's `last_updated` date, flags suspected documentation drift.
"""

from datetime import UTC, date, datetime
from pathlib import Path
import re
import subprocess
from typing import Any

from brain79.config import get_project_root, get_wiki_root
from brain79.core.context import _match_applies_to
from brain79.core.frontmatter import parse_frontmatter

_IGNORED_DIRS = frozenset({
    ".git",
    ".brain-79",
    "node_modules",
    ".venv",
    ".uv",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
})

INACTIVE_STATUSES = frozenset({
    "superseded",
    "deprecated",
    "rejected",
    "archived",
    "legacy",
})


def get_file_last_modified_date(file_path: Path, project_root: Path) -> str | None:
    """
    Get the last modification date (YYYY-MM-DD) for a workspace file.

    Prioritizes git commit date (`git log -1 --format=%cs`).
    Only falls back to filesystem mtime if:
    1. Git is unavailable or file is untracked, OR
    2. The file is actively modified in the working tree/index (git status --porcelain is non-empty).
    This prevents false positives when git clone or git checkout updates mtimes on clean files.
    """
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        rel_str = str(file_path.relative_to(project_root))
    except ValueError:
        rel_str = str(file_path)

    # 1. Try git commit author/committer date
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", rel_str],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            commit_date = res.stdout.strip()
            # Verify format YYYY-MM-DD
            if len(commit_date) == 10 and commit_date.count("-") == 2:
                # Check whether working tree has uncommitted local modifications
                try:
                    status_res = subprocess.run(
                        ["git", "status", "--porcelain", "--", rel_str],
                        cwd=str(project_root),
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    # Only if the file is genuinely dirty in Git do we check newer fs mtime
                    if status_res.returncode == 0 and status_res.stdout.strip():
                        mtime = file_path.stat().st_mtime
                        fs_date = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
                        if fs_date > commit_date:
                            return fs_date
                except OSError:
                    pass
                return commit_date
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass

    # 2. Fallback to filesystem mtime (for non-git repos or uncommitted/untracked files)
    try:
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
    except OSError:
        return None


def _is_ignored(path: Path, project_root: Path) -> bool:
    try:
        rel = path.relative_to(project_root)
        return any(part in _IGNORED_DIRS for part in rel.parts)
    except ValueError:
        return True


def find_matching_workspace_files(patterns: list[str], project_root: Path) -> list[Path]:
    """Find all existing files in project_root that match the given applies_to patterns."""
    matched: set[Path] = set()
    p_root = project_root.resolve()

    for pattern in patterns:
        pat = pattern.strip().lstrip("/")
        if pat.startswith("./"):
            pat = pat[2:]
        if not pat:
            continue

        target = (p_root / pat).resolve()
        # Prevent traversal outside project root
        if not target.is_relative_to(p_root):
            continue

        # Direct exact file check
        if target.is_file() and not _is_ignored(target, p_root):
            matched.add(target)
            continue

        # Direct directory check (matches all children inside directory)
        if target.is_dir() and not _is_ignored(target, p_root):
            for child in target.rglob("*"):
                if child.is_file() and not _is_ignored(child, p_root):
                    matched.add(child)
            continue

        # Glob pattern match
        try:
            for child in p_root.glob(pat):
                if child.is_file() and not _is_ignored(child, p_root):
                    try:
                        rel_str = str(child.relative_to(p_root))
                        if _match_applies_to(pat, rel_str):
                            matched.add(child)
                    except ValueError:
                        pass
        except Exception:
            pass

    return sorted(matched)


def check_article_drift(
    article_path: Path,
    wiki_root: Path | None = None,
    project_root: Path | None = None,
) -> list[dict[str, str]]:
    """
    Check if a single wiki article has suspected drift against workspace files it governs.

    Exempts articles that are inactive (superseded, deprecated, rejected, archived, legacy).
    Returns a list of drift records:
        [{"article_path": "...", "workspace_file": "...", "file_date": "...", "article_date": "..."}]
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    p_root = (project_root or w_root.parent or get_project_root()).resolve()

    if not article_path.exists() or not article_path.is_file():
        return []

    try:
        content = article_path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(content)
    except Exception:
        return []

    # Inactive articles (superseded ADRs, deprecated features, etc.) do not report drift
    status = str(meta.get("status", "")).lower()
    stability = str(meta.get("stability", "")).lower()
    if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
        return []

    # Normalize last_updated (handles date, datetime, or string)
    last_updated_raw = meta.get("last_updated")
    if not last_updated_raw:
        return []

    if isinstance(last_updated_raw, (date, datetime)):
        last_updated = last_updated_raw.strftime("%Y-%m-%d")
    else:
        last_updated = str(last_updated_raw).strip()[:10]

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", last_updated):
        return []

    applies_to_val = meta.get("applies_to")
    if not applies_to_val:
        return []

    patterns = (
        [applies_to_val] if isinstance(applies_to_val, str) else [str(x) for x in applies_to_val if x]
    )
    if not patterns:
        return []

    matching_files = find_matching_workspace_files(patterns, p_root)
    drifts: list[dict[str, str]] = []

    try:
        rel_article = str(article_path.relative_to(w_root))
    except ValueError:
        rel_article = str(article_path)

    for ws_file in matching_files:
        file_date = get_file_last_modified_date(ws_file, p_root)
        if file_date and file_date > last_updated:
            try:
                ws_rel = str(ws_file.relative_to(p_root))
            except ValueError:
                ws_rel = str(ws_file)

            drifts.append({
                "article_path": rel_article,
                "workspace_file": ws_rel,
                "file_date": file_date,
                "article_date": last_updated,
            })

    return drifts


def detect_all_drift(
    wiki_root: Path | None = None,
    md_files: list[Path] | None = None,
    project_root: Path | None = None,
) -> list[dict[str, str]]:
    """
    Detect documentation drift across all articles in the wiki.

    Excludes INDEX.md, SCHEMA.md, _raw/, and handoffs/.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    p_root = (project_root or w_root.parent or get_project_root()).resolve()

    files = md_files if md_files is not None else sorted(w_root.rglob("*.md"))
    all_drifts: list[dict[str, str]] = []

    for md_file in files:
        try:
            rel = md_file.relative_to(w_root)
            rel_str = str(rel)
            if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", "handoffs"):
                continue
        except ValueError:
            continue

        drifts = check_article_drift(md_file, wiki_root=w_root, project_root=p_root)
        all_drifts.extend(drifts)

    return all_drifts
