"""Centralized lock manager and cross-platform filesystem safety utilities.

Provides single authority for:
1. Centralized .brain-79/.locks/ directory isolation and deterministic naming.
2. Cross-platform POSIX path normalization (.as_posix() / normalize_posix_input).
3. Linux case-sensitivity verification on macOS APFS (has_exact_case_path).
4. NTFS atomic file replacement with transient PermissionError retry.
5. Legacy inline lock cleanup.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import threading
import time
from typing import Any, Final
import uuid

import filelock

LOCKS_DIRNAME: Final[str] = ".locks"

# Global lock acquisition hierarchy (highest to lowest precedence).
# No code path may acquire a lock with a lower index while holding one with a higher index.
LOCK_HIERARCHY: Final[tuple[str, ...]] = (
    "_transaction.lock",
    "_registry.lock",
    "_drift_lock.lock",
    "_drift_manifest.lock",
    "INDEX.md.lock",
)
_LOCK_RANK: Final[dict[str, int]] = {name: idx for idx, name in enumerate(LOCK_HIERARCHY)}
_HELD_LOCKS = threading.local()
_TX_TEMP_FILES: ContextVar[list[Path] | None] = ContextVar("_tx_temp_files", default=None)


def register_tx_temp_file(path: Path) -> Path:
    """Register a temp file with the active transaction_temp_scope(), if any."""
    active = _TX_TEMP_FILES.get()
    if active is not None:
        active.append(path)
    return path


def create_temp_path(target: Path, suffix: str | None = None) -> Path:
    """Create a temp path adjacent to target and register it in any active transaction scope."""
    tmp_suffix = suffix if suffix is not None else f".tmp.{uuid.uuid4().hex}"
    tmp_path = target.with_suffix(tmp_suffix)
    return register_tx_temp_file(tmp_path)


@contextmanager
def transaction_temp_scope() -> Iterator[list[Path]]:
    """Context manager tracking transaction-owned temp files for scoped rollback cleanup."""
    tracked: list[Path] = []
    token = _TX_TEMP_FILES.set(tracked)
    try:
        yield tracked
    finally:
        _TX_TEMP_FILES.reset(token)


def _get_held_locks() -> list[tuple[int, str, int]]:
    held: list[tuple[int, str, int]] | None = getattr(_HELD_LOCKS, "stack", None)
    if held is None:
        held = []
        _HELD_LOCKS.stack = held
    return held


class OrderedFileLock(filelock.FileLock):
    """FileLock subclass enforcing global lock acquisition order within a thread.

    Global lock hierarchy:
        _transaction.lock -> _registry.lock -> _drift_lock.lock -> _drift_manifest.lock -> INDEX.md.lock
    """

    def __init__(self, lock_file: str | os.PathLike[str], timeout: float = -1) -> None:
        super().__init__(lock_file, timeout=timeout)
        self._lock_basename = Path(lock_file).name
        self._lock_rank = _LOCK_RANK.get(self._lock_basename)

    def acquire(self, *args: Any, **kwargs: Any) -> Any:
        if self._lock_rank is not None:
            held = _get_held_locks()
            for _, held_name, held_rank in held:
                if held_rank > self._lock_rank:
                    raise RuntimeError(
                        f"Lock hierarchy violation: cannot acquire '{self._lock_basename}' "
                        f"(rank {self._lock_rank}) while holding '{held_name}' (rank {held_rank}). "
                        f"Required order: {' -> '.join(LOCK_HIERARCHY)}."
                    )
        proxy = super().acquire(*args, **kwargs)
        if self._lock_rank is not None:
            _get_held_locks().append((id(self), self._lock_basename, self._lock_rank))
        return proxy

    def release(self, force: bool = False) -> None:
        was_locked = self.is_locked
        try:
            super().release(force=force)
        finally:
            if was_locked and self._lock_rank is not None:
                held = _get_held_locks()
                self_id = id(self)
                if force:
                    held[:] = [entry for entry in held if entry[0] != self_id]
                else:
                    for idx in range(len(held) - 1, -1, -1):
                        if held[idx][0] == self_id:
                            held.pop(idx)
                            break


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
    - drift.lock                -> .locks/_drift_lock.lock
    - .drift_manifest.json      -> .locks/_drift_manifest.lock
    - _transaction.lock         -> .locks/_transaction.lock
    - INDEX.md                  -> .locks/INDEX.md.lock
    - decisions/adr-001.md      -> .locks/decisions__adr-001.md.lock
    """
    clean = normalize_wiki_rel_path(rel_posix_path)
    locks_dir = wiki_root / LOCKS_DIRNAME

    if clean == ".navigation_registry.json":
        return locks_dir / "_registry.lock"
    if clean == ".bootstrap_state.json":
        return locks_dir / "_bootstrap.lock"
    if clean == "drift.lock":
        return locks_dir / "_drift_lock.lock"
    if clean == ".drift_manifest.json":
        return locks_dir / "_drift_manifest.lock"
    if clean in ("_transaction.lock", "_transaction"):
        return locks_dir / "_transaction.lock"

    lock_name = clean.replace("/", "__")
    if not lock_name.endswith(".lock"):
        lock_name = f"{lock_name}.lock"

    return locks_dir / lock_name


def acquire_wiki_lock(
    wiki_root: Path,
    rel_posix_path: str,
    timeout: float = 10.0,
) -> filelock.FileLock:
    """Acquire an ordered filelock within the centralized .brain-79/.locks/ directory.

    Automatically ensures .locks/ exists before initializing OrderedFileLock.
    Enforces the global lock hierarchy:
        _transaction.lock -> _registry.lock -> _drift_lock.lock -> _drift_manifest.lock -> INDEX.md.lock
    """
    lock_file = get_lock_path(wiki_root, rel_posix_path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    return OrderedFileLock(str(lock_file), timeout=timeout)


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
            if lock_file.relative_to(wiki_root).as_posix() == "drift.lock":
                continue
        except ValueError:
            pass
        try:
            lock_file.unlink()
            removed += 1
        except (OSError, PermissionError):
            pass

    return removed
