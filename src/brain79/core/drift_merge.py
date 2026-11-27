"""Deterministic 3-way Git merge driver for `.brain-79/drift.lock`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain79.core.drift import (
    CONFLICT_SENTINEL_DIGEST,
    DRIFT_LOCK_VERSION,
    _corrupt_lock_error,
    parse_drift_lock_text,
    serialize_drift_lock,
)
from brain79.core.locks import atomic_replace_with_retry, create_temp_path


def merge_drift_lock_files(
    base_path: Path,
    ours_path: Path,
    theirs_path: Path,
    *,
    wiki_root: Path | None = None,
) -> int:
    """Perform a deterministic 3-way per-article merge of .brain-79/drift.lock.

    Writes the merged JSON result atomically to ``ours_path`` and returns 0.
    Raises FileNotFoundError if any input file or explicit wiki_root is missing,
    ValidationError(rule='corrupt_drift_lock') on invalid inputs (without touching
    ours_path), and PermissionError/OSError on write failures.
    """
    for label, p in (("base", base_path), ("ours", ours_path), ("theirs", theirs_path)):
        if not p.is_file():
            raise FileNotFoundError(f"Missing {label} drift.lock file: {p}")
    if wiki_root is not None and not wiki_root.is_dir():
        raise FileNotFoundError(f"Wiki root directory does not exist: {wiki_root}")

    def _read_utf8(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise _corrupt_lock_error(f"Invalid UTF-8 in {p.name}: {exc}") from exc

    base_data = parse_drift_lock_text(_read_utf8(base_path), allow_empty=True)
    ours_data = parse_drift_lock_text(_read_utf8(ours_path), allow_empty=False)
    theirs_data = parse_drift_lock_text(_read_utf8(theirs_path), allow_empty=False)

    base_articles: dict[str, Any] = base_data["articles"]
    ours_articles: dict[str, Any] = ours_data["articles"]
    theirs_articles: dict[str, Any] = theirs_data["articles"]

    merged_articles: dict[str, Any] = {}
    all_keys = sorted(base_articles.keys() | ours_articles.keys() | theirs_articles.keys())

    for key in all_keys:
        b = base_articles.get(key)
        o = ours_articles.get(key)
        t = theirs_articles.get(key)

        if o == t:
            if o is not None:
                merged_articles[key] = o
        elif o == b:
            if t is not None:
                merged_articles[key] = t
        elif t == b:
            if o is not None:
                merged_articles[key] = o
        elif b is not None:
            # True conflict (modify/modify or delete/modify) for pre-existing key:
            # revert to base[key], pruning only when --wiki-root confirms .md is absent.
            if wiki_root is not None and not (wiki_root / key).is_file():
                continue
            merged_articles[key] = b
        else:
            # Conflicting add/add of the same article key: emit conflict sentinel.
            merged_articles[key] = {
                "conflict": True,
                "count": 0,
                "digest": CONFLICT_SENTINEL_DIGEST,
                "targets": {},
            }

    content = serialize_drift_lock({"version": DRIFT_LOCK_VERSION, "articles": merged_articles})
    tmp_file = create_temp_path(ours_path)
    try:
        tmp_file.write_text(content, encoding="utf-8", newline="\n")
        atomic_replace_with_retry(tmp_file, ours_path)
    finally:
        tmp_file.unlink(missing_ok=True)

    return 0
