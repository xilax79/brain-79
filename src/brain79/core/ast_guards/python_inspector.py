"""Python AST public API signature inspector (Guard C)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from brain79.core.ast_guards.base import SignatureDiff
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


def _extract_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[Any, ...]:
    args = node.args
    pos_args = [a.arg for a in args.args]
    posonly_args = [a.arg for a in getattr(args, "posonlyargs", [])]
    kwonly_args = [a.arg for a in args.kwonlyargs]
    vararg = args.vararg.arg if args.vararg else None
    kwarg = args.kwarg.arg if args.kwarg else None
    defaults = [ast.unparse(d) for d in args.defaults]
    kw_defaults = [ast.unparse(d) if d else None for d in args.kw_defaults]
    returns = ast.unparse(node.returns) if node.returns else None
    decorators = [ast.unparse(dec) for dec in getattr(node, "decorator_list", [])]
    return (posonly_args, pos_args, kwonly_args, vararg, kwarg, defaults, kw_defaults, returns, decorators)


def extract_public_python_signatures(source_code: str) -> dict[str, Any]:
    """Parse Python source and extract public signatures for top-level functions and classes."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return {}

    signatures: dict[str, Any] = {}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                signatures[f"def {node.name}"] = _extract_function_signature(node)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                methods: dict[str, Any] = {}
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name == "__init__" or not item.name.startswith("_"):
                            methods[item.name] = _extract_function_signature(item)
                    elif isinstance(item, ast.AnnAssign):
                        if isinstance(item.target, ast.Name) and not item.target.id.startswith("_"):
                            methods[f"var {item.target.id}"] = ast.unparse(item.annotation)
                signatures[f"class {node.name}"] = methods

    return signatures


class PythonInspector:
    """LanguageInspector implementation for Python (.py) source files."""

    extensions: tuple[str, ...] = (".py",)
    language: str = "python"

    def extract_signatures(self, source_code: str) -> dict[str, Any]:
        return extract_public_python_signatures(source_code)

    def compare_sources(
        self,
        base_source: str,
        current_source: str,
        rel_path: str,
    ) -> SignatureDiff:
        base_sigs = self.extract_signatures(base_source)
        curr_sigs = self.extract_signatures(current_source)

        added = set(curr_sigs.keys()) - set(base_sigs.keys())
        if added:
            return SignatureDiff(True, f"added public symbol '{sorted(added)[0]}' in {rel_path}")

        removed = set(base_sigs.keys()) - set(curr_sigs.keys())
        if removed:
            return SignatureDiff(True, f"removed public symbol '{sorted(removed)[0]}' in {rel_path}")

        for sym in sorted(curr_sigs.keys()):
            if base_sigs.get(sym) != curr_sigs[sym]:
                return SignatureDiff(True, f"changed public signature for '{sym}' in {rel_path}")

        return SignatureDiff(False, "")


def _resolve_contained_path(project_root: Path, rel_posix_path: str) -> Path:
    p_root = project_root.resolve()
    candidate = (p_root / rel_posix_path).resolve()
    if not candidate.is_relative_to(p_root):
        raise ValueError(
            f"Path '{rel_posix_path}' resolves outside project root '{p_root}' (resolved: '{candidate}')."
        )
    return candidate


def has_public_python_api_changes(
    project_root: Path,
    rel_posix_path: str,
    article_path: str,
    current_content: str | None = None,
    wiki_root: Path | None = None,
    git_cache: GitSessionCache | None = None,
) -> tuple[bool, str]:
    """AST Public API Signature Verification (Guard C).

    Checks whether any public function, class, or method signature in a .py file
    was added, removed, or changed compared to the git revision where the governing article
    was last committed (or HEAD). Supports optional GitSessionCache for HEAD/blob reuse.
    """
    if not rel_posix_path.endswith(".py"):
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
                actionable="Ensure the governed Python file is readable valid UTF-8, or update the article directly.",
            ) from exc

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

    inspector = PythonInspector()
    if base_content is None:
        curr_sigs = inspector.extract_signatures(current_content)
        if curr_sigs:
            first_sym = sorted(curr_sigs.keys())[0]
            return True, f"new public symbol '{first_sym}' in {rel_posix_path}"
        return False, ""

    diff = inspector.compare_sources(base_content, current_content, rel_posix_path)
    return diff.has_changes, diff.description
