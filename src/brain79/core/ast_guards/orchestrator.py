"""Language-agnostic Guard C orchestrator for AST public-API verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain79.core.frontmatter import FrontmatterError, ValidationError, parse_frontmatter
from brain79.core.git_ops import (
    GitError,
    GitSessionCache,
    GitTimeoutError,
    NotAGitRepoError,
    git_first_parent_log,
    git_rev_parse_head,
    git_show_blob,
)
from brain79.core.locks import normalize_wiki_rel_path, rel_posix

MAX_AST_SOURCE_BYTES = 2_097_152


def _extract_fm_digest(blob_text: str | None) -> str | None:
    if blob_text is None:
        return None
    try:
        meta, _ = parse_frontmatter(blob_text)
    except (FrontmatterError, Exception):
        return None
    val = meta.get("applies_to_digest")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def resolve_article_baseline_commit(
    project_root: Path,
    wiki_rel: str,
    rel_article: str,
    *,
    max_commits: int = 50,
    timeout: float = 2.0,
    git_cache: GitSessionCache | None = None,
) -> str | None:
    """Resolve the baseline Git commit for Guard C using bounded first-parent walks.

    Skips pure migration commits and volatile-only Markdown edits while anchoring on
    substantive article updates or non-migration drift.lock verification updates.
    """
    from brain79.core.drift import (
        DRIFT_LOCK_FILENAME,
        compute_wiki_article_digest,
        parse_drift_lock_text,
    )

    p_root = project_root.resolve()
    clean_art = normalize_wiki_rel_path(rel_article)
    rel_wiki_path = f"{wiki_rel}/{clean_art}"
    lock_rel_path = f"{wiki_rel}/{DRIFT_LOCK_FILENAME}"

    def _load_lock_at(rev: str | None) -> dict[str, Any] | None:
        if rev is None:
            return None
        raw = git_show_blob(p_root, rev, lock_rel_path, timeout=timeout, cache=git_cache)
        if raw is None:
            return None
        try:
            return parse_drift_lock_text(raw, allow_empty=False)
        except ValidationError:
            return None

    def _effective_prev_digest(parent_rev: str | None) -> str | None:
        if parent_rev is None:
            return None
        p_lock = _load_lock_at(parent_rev)
        if p_lock is not None:
            p_entry = p_lock.get("articles", {}).get(clean_art)
            if isinstance(p_entry, dict) and p_entry.get("conflict") is not True:
                dig = p_entry.get("digest")
                if isinstance(dig, str) and dig:
                    return dig
        p_md = git_show_blob(p_root, parent_rev, rel_wiki_path, timeout=timeout, cache=git_cache)
        return _extract_fm_digest(p_md)

    def _is_substantive_md_change(c_md: str | None, p_rev: str | None) -> bool:
        if c_md is None:
            return False
        if p_rev is None:
            return True
        p_md = git_show_blob(p_root, p_rev, rel_wiki_path, timeout=timeout, cache=git_cache)
        if p_md is None:
            return True
        return compute_wiki_article_digest(c_md) != compute_wiki_article_digest(p_md)

    def _is_legacy_fm_update(c_md: str | None, p_rev: str | None) -> bool:
        c_fm = _extract_fm_digest(c_md)
        if not c_fm:
            return False
        if p_rev is None:
            return True
        p_md = git_show_blob(p_root, p_rev, rel_wiki_path, timeout=timeout, cache=git_cache)
        return c_fm != _extract_fm_digest(p_md)

    # Pass 1: combined bounded first-parent walk over drift.lock and rel_article
    pass1 = git_first_parent_log(
        p_root,
        [lock_rel_path, rel_wiki_path],
        max_commits=max_commits,
        timeout=timeout,
        cache=git_cache,
    )
    for c_rev, p_rev in pass1:
        c_md = git_show_blob(p_root, c_rev, rel_wiki_path, timeout=timeout, cache=git_cache)
        # Rule 1: substantive .md change
        if _is_substantive_md_change(c_md, p_rev):
            return c_rev

        # Rule 2: non-migration drift.lock digest change
        c_lock = _load_lock_at(c_rev)
        c_entry = c_lock.get("articles", {}).get(clean_art) if c_lock is not None else None
        if isinstance(c_entry, dict) and c_entry.get("conflict") is not True:
            c_dig = c_entry.get("digest")
            if isinstance(c_dig, str) and c_dig and c_dig != _effective_prev_digest(p_rev):
                return c_rev

        # Rule 3: legacy frontmatter digest update when absent from drift.lock
        if c_entry is None and _is_legacy_fm_update(c_md, p_rev):
            return c_rev

    # Pass 2: article-only fallback walk when busy drift.lock pushes article history past 50 commits
    pass2 = git_first_parent_log(
        p_root,
        [rel_wiki_path],
        max_commits=max_commits,
        timeout=timeout,
        cache=git_cache,
    )
    for c_rev, p_rev in pass2:
        c_md = git_show_blob(p_root, c_rev, rel_wiki_path, timeout=timeout, cache=git_cache)
        if _is_substantive_md_change(c_md, p_rev):
            return c_rev
        c_lock = _load_lock_at(c_rev)
        c_entry = c_lock.get("articles", {}).get(clean_art) if c_lock is not None else None
        if c_entry is None and _is_legacy_fm_update(c_md, p_rev):
            return c_rev

    if pass2:
        return pass2[-1][0]
    if pass1:
        return pass1[-1][0]
    return git_rev_parse_head(p_root, timeout=timeout, cache=git_cache)


def _resolve_contained_path(project_root: Path, rel_posix_path: str) -> Path:
    p_root = project_root.resolve()
    candidate = (p_root / rel_posix_path).resolve()
    if not candidate.is_relative_to(p_root):
        raise ValueError(
            f"Path '{rel_posix_path}' resolves outside project root '{p_root}' (resolved: '{candidate}')."
        )
    return candidate


def has_public_api_changes(
    project_root: Path,
    rel_posix_path: str,
    article_path: str,
    current_content: str | None = None,
    wiki_root: Path | None = None,
    git_cache: GitSessionCache | None = None,
) -> tuple[bool, str]:
    """Verify whether any public symbol signature changed in a governed source file.

    Dispatches to the registered LanguageInspector for ``rel_posix_path``'s
    extension, enforcing path containment, 2 MB source-size bounds, and
    fail-closed Git/parser error handling.
    """
    from brain79.core.ast_guards import get_inspector_for_path

    inspector = get_inspector_for_path(rel_posix_path)
    if inspector is None:
        return False, ""

    p_root = project_root.resolve()
    try:
        target_disk = _resolve_contained_path(p_root, rel_posix_path)
    except ValueError as exc:
        raise ValidationError(
            rule="path_outside_project_root",
            path=article_path,
            message=str(exc),
            actionable="Remove symlinks or path traversals pointing outside the project root from applies_to.",
        ) from exc

    if current_content is None:
        if not target_disk.is_file():
            return False, ""
        try:
            current_content = target_disk.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValidationError(
                rule="ast_verification_failed",
                path=article_path,
                message=f"Cannot read target '{rel_posix_path}' for AST verification ({type(exc).__name__}: {exc}).",
                actionable="Ensure the governed file is readable valid UTF-8, or update the article directly.",
            ) from exc

    if len(current_content.encode("utf-8")) > MAX_AST_SOURCE_BYTES:
        return False, ""

    w_root = (wiki_root or (p_root / ".brain-79")).resolve()
    try:
        wiki_rel = rel_posix(w_root, p_root)
    except ValueError:
        wiki_rel = ".brain-79"

    clean_art = normalize_wiki_rel_path(article_path)
    base_rev: str | None = None

    try:
        base_rev = resolve_article_baseline_commit(
            p_root, wiki_rel, clean_art, timeout=2.0, git_cache=git_cache
        )
    except NotAGitRepoError:
        return False, ""
    except (GitTimeoutError, GitError, OSError) as exc:
        raise ValidationError(
            rule="ast_verification_failed",
            path=article_path,
            message=f"Git operational error while resolving base revision for '{rel_posix_path}': {exc}",
            actionable="Check Git repository health or update the article directly in writes/edits.",
        ) from exc

    if not base_rev:
        return False, ""

    try:
        base_content = git_show_blob(
            p_root, base_rev, rel_posix_path, timeout=2.0, cache=git_cache
        )
    except NotAGitRepoError:
        return False, ""
    except (GitTimeoutError, GitError, OSError) as exc:
        raise ValidationError(
            rule="ast_verification_failed",
            path=article_path,
            message=f"Git operational error while loading base blob '{base_rev}:{rel_posix_path}': {exc}",
            actionable="Check Git repository health or update the article directly in writes/edits.",
        ) from exc

    if base_content is not None and len(base_content.encode("utf-8")) > MAX_AST_SOURCE_BYTES:
        return False, ""

    try:
        if base_content is None:
            curr_sigs = inspector.extract_signatures(current_content)
            if curr_sigs:
                first_sym = sorted(curr_sigs.keys())[0]
                return True, f"new public symbol '{first_sym}' in {rel_posix_path}"
            return False, ""

        diff = inspector.compare_sources(base_content, current_content, rel_posix_path)
        return diff.has_changes, diff.description
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(
            rule="ast_verification_failed",
            path=article_path,
            message=f"AST inspector '{type(inspector).__name__}' failed for '{rel_posix_path}' ({type(exc).__name__}: {exc}).",
            actionable="Check the source file syntax or update the article directly in writes/edits.",
        ) from exc
