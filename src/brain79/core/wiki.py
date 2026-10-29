from datetime import UTC, datetime
from pathlib import Path
import shutil
import subprocess

import filelock

from brain79.config import get_wiki_root
from brain79.core.frontmatter import ValidationError
from brain79.core.validation import validate_article_content


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


def write_article(
    path: str,
    content: str,
    timeout: float = 5.0,
    force_validation_skip: bool = False,
    _skip_nav_regen: bool = False,
) -> str:
    """
    Write or update an article atomically with file locking. Creates parent directories as needed.

    Note: The .md.lock file remains on disk between writes (standard filelock behavior on Unix).
    It is excluded by .gitignore and article search patterns (*.md).
    For manual cleanup: find .brain-79 -name '*.lock' -delete.
    """
    target = _safe_resolve(path)

    if target.suffix != ".md":
        raise ValueError(f"write_article requires .md paths, got {path}")

    wiki_root = get_wiki_root().resolve()
    rel_path_str = str(target.relative_to(wiki_root))
    content = validate_article_content(
        rel_path_str, content, force_skip=force_validation_skip
    )

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

    # Best-effort navigation registration & synchronization (P1.1, P0.5)
    try:
        if (
            not force_validation_skip
            and rel_path_str != "INDEX.md"
            and rel_path_str != "SCHEMA.md"
            and not rel_path_str.startswith("_raw/")
            and not rel_path_str.startswith("handoffs/")
        ):
            from brain79.core.navigation import (
                extract_title_and_summary,
                regenerate_index_navigation,
                register_article,
            )

            rel_p = target.relative_to(wiki_root)
            title, summary = extract_title_and_summary(content)
            section = rel_p.parts[0] if len(rel_p.parts) > 1 else "root"
            register_article(wiki_root, str(rel_p), title, summary, section)
            if not _skip_nav_regen:
                try:
                    regenerate_index_navigation(wiki_root)
                except Exception:
                    pass
        elif rel_path_str == "INDEX.md" and "## Quick navigation" in content:
            if not _skip_nav_regen:
                from brain79.core.navigation import regenerate_index_navigation

                try:
                    regenerate_index_navigation(wiki_root)
                except Exception:
                    pass
    except Exception:
        pass

    return f"Written: {path}"


def check_file_health(wiki_root: Path, rel_path: str, content: str) -> list[str]:
    """Run lightweight per-file health checks returning warnings (if any)."""
    warnings: list[str] = []

    # Exempt paths
    if rel_path in ("SCHEMA.md",) or rel_path.startswith("_raw/") or rel_path.startswith("handoffs/"):
        return warnings

    # 1. H1 Header check
    from brain79.core.lint import _extract_raw_link_targets, _has_h1_header
    if not _has_h1_header(content):
        warnings.append(f"Missing H1 header in '{rel_path}'.")

    # 2. Decision leakage in non-decision documents
    if not rel_path.startswith("decisions/") and rel_path != "INDEX.md":
        from brain79.core.validation import (
            DECISION_BULLET_STRICT,
            DECISION_HEADER_STRICT,
            TECHNICAL_DEBT_BULLET_STRICT,
            TECHNICAL_DEBT_HEADER_STRICT,
            _mask_code_fences,
        )
        masked = _mask_code_fences(content)
        if DECISION_HEADER_STRICT.search(masked) or DECISION_BULLET_STRICT.search(masked):
            warnings.append(
                f"Structural decision leakage detected in non-decision article '{rel_path}'. Move decisions to decisions/."
            )
        if TECHNICAL_DEBT_HEADER_STRICT.search(masked) or TECHNICAL_DEBT_BULLET_STRICT.search(masked):
            warnings.append(
                f"Technical debt leakage detected in '{rel_path}'. Move to decisions/ or features/."
            )

    # 3. Broken local links in this article
    from urllib.parse import unquote
    raw_targets = _extract_raw_link_targets(content)
    article_path = wiki_root / rel_path
    for raw_target in raw_targets:
        if (
            raw_target.startswith(
                ("http://", "https://", "mailto:", "ftp://", "file://", "//", "tel:", "data:")
            )
            or "://" in raw_target
        ):
            continue
        path_part = unquote(raw_target.split("#", 1)[0])
        if not path_part:
            continue
        if path_part.startswith("/"):
            target_file = (wiki_root / path_part.lstrip("/")).resolve()
        else:
            target_file = (article_path.parent / path_part).resolve()
        try:
            target_rel = target_file.relative_to(wiki_root)
            if not target_file.exists():
                warnings.append(f"Broken local link: '{raw_target}' -> '{target_rel}' does not exist.")
        except ValueError:
            warnings.append(f"Link points outside wiki: '{raw_target}'.")

    return warnings


def edit_article(
    path: str,
    edits: list[dict[str, str]],
    timeout: float = 5.0,
    force_validation_skip: bool = False,
) -> str:
    """Apply one or more text replacements to an article, validate, and write atomically."""
    if not edits:
        raise ValueError("edits list cannot be empty.")

    target = _safe_resolve(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Article not found: {path}")

    content = target.read_text(encoding="utf-8")

    for idx, edit in enumerate(edits):
        old_text = edit.get("old_text")
        new_text = edit.get("new_text")
        if old_text is None or new_text is None:
            raise ValueError(f"Edit #{idx + 1} must contain 'old_text' and 'new_text'.")
        if not old_text:
            raise ValueError(f"Edit #{idx + 1} 'old_text' cannot be empty.")

        count = content.count(old_text)
        if count == 0:
            snippet = old_text[:60] + "..." if len(old_text) > 60 else old_text
            raise ValueError(f"Edit #{idx + 1} failed: 'old_text' not found: {snippet!r}")
        if count > 1:
            snippet = old_text[:60] + "..." if len(old_text) > 60 else old_text
            raise ValueError(f"Edit #{idx + 1} ambiguous: 'old_text' matches {count} times: {snippet!r}")

        content = content.replace(old_text, new_text, 1)

    return write_article(
        path, content, timeout=timeout, force_validation_skip=force_validation_skip
    )


def write_many_articles(
    articles: list[dict[str, str]],
    timeout: float = 5.0,
    force_validation_skip: bool = False,
) -> str:
    """Validate all articles in batch first; if all valid, write them atomically."""
    if not articles:
        raise ValueError("articles list cannot be empty.")

    wiki_root = get_wiki_root().resolve()
    validated_contents: list[tuple[str, str]] = []
    validation_errors: list[str] = []

    # 1. Validation pass (all-or-nothing)
    for idx, item in enumerate(articles):
        p = item.get("path")
        c = item.get("content")
        if not p or c is None:
            raise ValueError(f"Article #{idx + 1} must have 'path' and 'content'.")

        target = _safe_resolve(p)
        if target.suffix != ".md":
            raise ValueError(f"write_many_articles requires .md paths, got {p}")

        rel_path_str = str(target.relative_to(wiki_root))
        try:
            val_c = validate_article_content(rel_path_str, c, force_skip=force_validation_skip)
            validated_contents.append((p, val_c))
        except ValidationError as exc:
            validation_errors.append(f"[{p}]\n{exc.format_user_message()}")
        except Exception as exc:
            validation_errors.append(f"[{p}] {exc}")

    if validation_errors:
        raise ValidationError(
            rule="batch_validation_failed",
            path="batch",
            message=f"Batch validation failed for {len(validation_errors)} article(s):\n\n"
            + "\n\n".join(validation_errors),
            actionable="Fix all validation errors listed above before re-submitting batch.",
        )

    # 2. Write pass
    written: list[str] = []
    for p, val_c in validated_contents:
        write_article(
            p,
            val_c,
            timeout=timeout,
            force_validation_skip=force_validation_skip,
            _skip_nav_regen=True,
        )
        written.append(p)

    # 3. Single navigation regeneration at the end of the batch
    try:
        from brain79.core.navigation import regenerate_index_navigation

        regenerate_index_navigation(wiki_root)
    except Exception:
        pass

    return f"Batch write succeeded: {len(written)} article(s) written: {', '.join(written)} · lint OK"


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
