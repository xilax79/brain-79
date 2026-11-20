"""Tests for scoped ProjectContext ContextVar isolation (Phase 10 Stage 4: R-4.4, AC-10.13)."""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import brain79.config as cfg
from brain79.config import (
    ProjectContext,
    get_project_context,
    get_project_root,
    get_wiki_root,
    project_context,
    set_project_root,
)


def test_project_context_is_immutable(tmp_path: Path) -> None:
    """R-4.4: ProjectContext is a frozen immutable dataclass."""
    ctx = ProjectContext(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
    with pytest.raises(FrozenInstanceError):
        ctx.project_root = tmp_path / "other"  # type: ignore[misc]


def test_project_context_isolates_async_tasks_without_mutating_global(tmp_path: Path) -> None:
    """AC-10.13: Concurrent async tasks observe isolated roots without mutating global _project_root."""
    root_a = (tmp_path / "proj_a").resolve()
    root_b = (tmp_path / "proj_b").resolve()
    root_a.mkdir()
    root_b.mkdir()

    prev_global = cfg._project_root
    set_project_root(None)
    try:
        async def _worker(target: Path, delay: float) -> tuple[Path, Path]:
            with project_context(target):
                await asyncio.sleep(delay)
                ctx = get_project_context()
                assert ctx is not None
                assert ctx.project_root == target
                return get_project_root(), get_wiki_root()

        async def _run() -> tuple[tuple[Path, Path], tuple[Path, Path]]:
            res_a, res_b = await asyncio.gather(
                _worker(root_a, 0.03),
                _worker(root_b, 0.01),
            )
            return res_a, res_b

        (pa, wa), (pb, wb) = asyncio.run(_run())
        assert pa == root_a and wa == root_a / ".brain-79"
        assert pb == root_b and wb == root_b / ".brain-79"
        assert cfg._project_root is None
    finally:
        set_project_root(prev_global)


def test_project_context_isolates_threads_without_mutating_global(tmp_path: Path) -> None:
    """AC-10.13: Concurrent threads observe isolated roots without mutating global _project_root."""
    roots = []
    for i in range(4):
        r = (tmp_path / f"thread_proj_{i}").resolve()
        r.mkdir()
        roots.append(r)

    prev_global = cfg._project_root
    set_project_root(None)
    try:
        def _thread_worker(target: Path) -> Path:
            with project_context(target):
                return get_project_root()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_thread_worker, roots))

        assert results == roots
        assert cfg._project_root is None
    finally:
        set_project_root(prev_global)
