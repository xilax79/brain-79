"""Language-agnostic Guard C orchestrator for AST public-API verification."""

from __future__ import annotations

from pathlib import Path

from brain79.core.frontmatter import ValidationError
from brain79.core.git_ops import (
    GitError,
    GitSessionCache,
    GitTimeoutError,
    NotAGitRepoError,
    git_last_commit_for_path,
    git_rev_parse_head,
    git_show_blob,
)
from brain79.core.locks import normalize_wiki_rel_path, rel_posix

MAX_AST_SOURCE_BYTES = 2_097_152


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
    rel_wiki_path = f"{wiki_rel}/{clean_art}"
    base_rev: str | None = None

    try:
        base_rev = git_last_commit_for_path(
            p_root, rel_wiki_path, fmt="%H", timeout=2.0, cache=git_cache
        )
        if not base_rev:
            base_rev = git_rev_parse_head(p_root, timeout=2.0, cache=git_cache)
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
