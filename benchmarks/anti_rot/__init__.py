"""Longitudinal anti-rot benchmark suite (SPEC-016)."""

from __future__ import annotations

import shutil
from pathlib import Path

ANTI_ROT_ROOT: Path = Path(__file__).resolve().parent
FIXTURE_DIR: Path = ANTI_ROT_ROOT / "fixture"
CONTROL_AGENTS_PATH: Path = ANTI_ROT_ROOT / "control_agents.md"
CONTRACTS_DIR: Path = ANTI_ROT_ROOT / "contracts"

_MACOS_CLT_GIT = Path("/Library/Developer/CommandLineTools/usr/bin/git")
_SOURCE_EXTENSIONS = frozenset({".py", ".ts", ".js", ".mjs"})


def resolve_git_bin() -> str:
    """Return a working git binary path, preferring macOS CommandLineTools git."""
    if _MACOS_CLT_GIT.is_file():
        return str(_MACOS_CLT_GIT)
    return shutil.which("git") or "git"


def discover_canonical_sources(workspace: Path) -> list[str]:
    """Return sorted POSIX relative paths of non-test source files under src/."""
    src_root = workspace / "src"
    if not src_root.is_dir():
        return []
    paths: list[str] = []
    for candidate in src_root.rglob("*"):
        if not candidate.is_file():
            continue
        if "__pycache__" in candidate.parts:
            continue
        if candidate.suffix.lower() not in _SOURCE_EXTENSIONS:
            continue
        paths.append(candidate.relative_to(workspace).as_posix())
    return sorted(paths)


__all__ = [
    "ANTI_ROT_ROOT",
    "CONTRACTS_DIR",
    "CONTROL_AGENTS_PATH",
    "FIXTURE_DIR",
    "discover_canonical_sources",
    "resolve_git_bin",
]
