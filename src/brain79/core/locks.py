"""Centralized lock manager and cross-platform filesystem safety utilities.

Provides single authority for:
1. Centralized .brain-79/.locks/ directory isolation and deterministic naming.
2. Cross-platform POSIX path normalization (.as_posix() / normalize_posix_input).
3. Linux case-sensitivity verification on macOS APFS (has_exact_case_path).
4. NTFS atomic file replacement with transient PermissionError retry.
5. Legacy inline lock cleanup.
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Final

import filelock

LOCKS_DIRNAME: Final[str] = ".locks"


def rel_posix(path: Path, root: Path) -> str:
    """Return path relative to root formatted strictly with forward slashes (POSIX style)."""
    return path.relative_to(root).as_posix()


def normalize_posix_input(raw_path: str | Path) -> str:
    """Normalize user or API input path by replacing Windows backslashes with forward slashes."""
    return (raw_path.as_posix() if isinstance(raw_path, Path) else str(raw_path)).replace("\\", "/").strip()


def normalize_wiki_rel_path(raw_path: str | Path) -> str:
    """Normalize a path intended to be relative to the wiki root (.brain-79/).

    Replaces Windows backslashes, strips redundant leading '.brain-79/' or './.brain-79/' or
    '/.brain-79/', without stripping leading slashes from external absolute paths.
    """
    cleaned = normalize_posix_input(raw_path)
    stripped = cleaned
    if stripped.startswith("/.brain-79/"):
        stripped = stripped[len("/.brain-79/"):]
    elif stripped.startswith("./.brain-79/"):
        stripped = stripped[len("./.brain-79/"):]
    elif stripped.startswith(".brain-79/"):
        stripped = stripped[len(".brain-79/"):]
    elif stripped in ("/.brain-79", "./.brain-79", ".brain-79"):
        stripped = ""
    return stripped


def has_exact_case_path(root: Path, rel_posix_path: str) -> bool:
    """Verify segment-by-segment on disk that the relative path matches exact character casing.

    Simulates Linux ext4 case-sensitivity on case-insensitive filesystems (macOS APFS, Windows NTFS).
    Returns False immediately if any directory or filename component on disk has a different casing.
    """
    clean = normalize_posix_input(rel_posix_path).lstrip("/")
    if not clean or clean == ".":
        return root.exists()

    parts = Path(clean).parts
    curr = root.resolve()
    if not curr.is_dir():
        return False

    for part in parts:
        if part in (".", ""):
            continue
        try:
            entries = os.listdir(curr)
        except (OSError, PermissionError):
            return False
        if part not in entries:
            return False
        curr = curr / part

    return True


def get_lock_path(wiki_root: Path, rel_posix_path: str) -> Path:
    """Return canonical path to centralized lock file in .brain-79/.locks/.

    Maps filenames deterministically:
    - .navigation_registry.json -> .locks/_registry.lock
    - .bootstrap_state.json     -> .locks/_bootstrap.lock
    - INDEX.md                  -> .locks/INDEX.md.lock
    - decisions/adr-001.md      -> .locks/decisions__adr-001.md.lock
    """
    clean = normalize_wiki_rel_path(rel_posix_path)
    locks_dir = wiki_root / LOCKS_DIRNAME

    if clean == ".navigation_registry.json":
        return locks_dir / "_registry.lock"
    if clean == ".bootstrap_state.json":
        return locks_dir / "_bootstrap.lock"

    lock_name = clean.replace("/", "__")
    if not lock_name.endswith(".lock"):
        lock_name = f"{lock_name}.lock"

    return locks_dir / lock_name


def acquire_wiki_lock(
    wiki_root: Path,
    rel_posix_path: str,
    timeout: float = 10.0,
) -> filelock.FileLock:
    """Acquire a filelock within the centralized .brain-79/.locks/ directory.

    Automatically ensures .locks/ exists before initializing FileLock.
    """
    lock_file = get_lock_path(wiki_root, rel_posix_path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    return filelock.FileLock(str(lock_file), timeout=timeout)


def atomic_replace_with_retry(
    tmp_path: Path,
    target: Path,
    retries: int = 3,
    delay: float = 0.02,
) -> None:
    """Replace target with tmp_path, retrying on transient PermissionError (e.g. Windows file locking).

    Cleans up tmp_path if all retries are exhausted to prevent orphan file accumulation.
    """
    for attempt in range(retries):
        try:
            tmp_path.replace(target)
            return
        except PermissionError:
            if attempt == retries - 1:
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
                raise
            time.sleep(delay * (attempt + 1))


def cleanup_legacy_inline_locks(wiki_root: Path) -> int:
    """Remove legacy inline *.lock files scattered outside .brain-79/.locks/.

    Returns the number of removed lock files.
    """
    if not wiki_root.exists():
        return 0

    removed = 0
    for lock_file in wiki_root.rglob("*.lock"):
        if LOCKS_DIRNAME in lock_file.parts:
            continue
        try:
            lock_file.unlink()
            removed += 1
        except (OSError, PermissionError):
            pass

    return removed
