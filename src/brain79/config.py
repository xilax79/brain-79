"""Project and wiki root resolution with ContextVar-backed multi-worktree isolation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class ProjectContext:
    """Immutable scoped project context for isolated multi-worktree execution."""

    project_root: Path
    wiki_root: Path


_project_root: Path | None = None
_PROJECT_CONTEXT: ContextVar[ProjectContext | None] = ContextVar("_project_context", default=None)


def get_project_context() -> ProjectContext | None:
    """Return the active ContextVar-scoped ProjectContext, if any."""
    return _PROJECT_CONTEXT.get()


@contextmanager
def project_context(
    project_root: Path,
    wiki_root: Path | None = None,
) -> Iterator[ProjectContext]:
    """Bind an isolated ProjectContext to the current async task or thread without mutating global state."""
    p_root = project_root.resolve()
    w_root = (wiki_root or (p_root / ".brain-79")).resolve()
    ctx = ProjectContext(project_root=p_root, wiki_root=w_root)
    token = _PROJECT_CONTEXT.set(ctx)
    try:
        yield ctx
    finally:
        _PROJECT_CONTEXT.reset(token)


def set_project_root(path: Path | None) -> None:
    """Set the project root at server startup or reset with None."""
    global _project_root
    if path is None:
        _project_root = None
    else:
        _project_root = path.resolve()


def get_project_root() -> Path:
    """Resolve project root from scoped ProjectContext, explicit override, BRAIN79_PROJECT_ROOT, or ancestor walk."""
    ctx = _PROJECT_CONTEXT.get()
    if ctx is not None:
        return ctx.project_root

    if _project_root is not None:
        return _project_root

    env_root = os.environ.get("BRAIN79_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    cwd = Path.cwd().resolve()
    if (cwd / ".brain-79").is_dir():
        return cwd

    if (cwd / ".git").exists():
        return cwd

    for parent in cwd.parents:
        if (parent / ".brain-79").is_dir():
            return parent
        if (parent / ".git").exists():
            return cwd

    return cwd


def get_wiki_root() -> Path:
    """Resolve wiki root from scoped ProjectContext or `<project_root>/.brain-79`."""
    ctx = _PROJECT_CONTEXT.get()
    if ctx is not None:
        return ctx.wiki_root
    return get_project_root() / ".brain-79"
