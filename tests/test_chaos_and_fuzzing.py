"""Phase 9 Deliverable 9.2: Chaos Engineering, Multiprocess Contention & Deterministic Fuzzing.

Implements failure catalog F1, F2, F3, F6, F7, F8:
- Multiprocess contention with 8 workers, Barrier(8), rotating write/edit/navigate/commit.
- Crash recovery (SIGKILL worker holding lock) on POSIX.
- Deterministic seeded stdlib fuzzing across 6 corpus classes (seeds 0..19).
- Environment faults: read-only directory, ENOSPC full disk, KeyboardInterrupt during Pass 3.
- Invariants: all-or-nothing atomicity, zero orphan .tmp, zero leaked locks, lint --strict exit 0.
"""

from __future__ import annotations

import errno
import json
import multiprocessing as mp
import os
from pathlib import Path
import random
import re
import signal
import sys
import time
from typing import Any
import unicodedata
from unittest.mock import patch

import filelock
import pytest

from brain79.config import get_project_root, get_wiki_root, set_project_root
from brain79.core.context import get_context
from brain79.core.drift import WorkspaceIndex, check_article_drift
from brain79.core.frontmatter import (
    FrontmatterError,
    ValidationError,
    parse_frontmatter,
)
from brain79.core.init_project import init_project
from brain79.core.lint import lint_wiki
from brain79.core.locks import (
    LOCKS_DIRNAME,
    acquire_wiki_lock,
    atomic_replace_with_retry,
    get_lock_path,
)
from brain79.core.migration import migrate_wiki
from brain79.core.navigation import regenerate_index_navigation
from brain79.core.orient import orient
from brain79.core.session_commit import commit_session
from brain79.core.validation import (
    MAX_ARTICLE_BYTES,
    MAX_ARTICLE_LINES,
    validate_article_content,
)
from brain79.core.wiki import edit_article, read_article, write_article


# ==============================================================================
# Multiprocess Worker Functions (Top-level for Spawn Pickling)
# ==============================================================================


def _chaos_worker_run(
    worker_id: int,
    project_root_str: str,
    barrier: Any,
    results_queue: Any,
    total_ops: int = 25,
) -> None:
    """Multiprocess spawn worker executing rotating operations under contention."""
    p_root = Path(project_root_str)
    set_project_root(p_root)
    w_root = p_root / ".brain-79"

    successful_ops: list[str] = []
    errors: list[str] = []

    # Synchronize all workers at start line
    try:
        barrier.wait(timeout=30.0)
    except Exception as exc:
        results_queue.put({"worker_id": worker_id, "successes": [], "errors": [f"Barrier timeout: {exc}"]})
        return

    for op in range(total_ops):
        op_type = op % 4
        try:
            if op_type == 0:
                # 1. Distinct write_article
                art_rel = f"topics/w{worker_id}-{op}.md"
                content = (
                    "---\n"
                    "type: topic\n"
                    f"summary: Worker {worker_id} topic operation {op}\n"
                    "last_updated: 2026-11-17\n"
                    "---\n\n"
                    f"# Topic W{worker_id} Op{op}\n\n"
                    "## Overview\n"
                    f"Created by worker {worker_id} during iteration {op}.\n\n"
                    "---\n\n"
                    "[← Volver al Índice](../INDEX.md)\n"
                )
                write_article(art_rel, content, wiki_root=w_root, timeout=15.0)
                successful_ops.append(art_rel)

            elif op_type == 1:
                # 2. Distinct edit_article on previous write, or write if not present
                prev_op = op - 1
                target_rel = f"topics/w{worker_id}-{prev_op}.md"
                if (w_root / target_rel).is_file():
                    edit_article(
                        target_rel,
                        [{"old_text": f"iteration {prev_op}.", "new_text": f"updated iteration {prev_op}."}],
                        wiki_root=w_root,
                        timeout=15.0,
                    )
                    successful_ops.append(f"edit:{target_rel}")
                else:
                    fallback_content = (
                        "---\n"
                        "type: topic\n"
                        f"summary: Worker {worker_id} edit fallback {op}\n"
                        "last_updated: 2026-11-17\n"
                        "---\n\n"
                        f"# Fallback W{worker_id}\n\n"
                        "## Overview\n"
                        f"Fallback content iteration {prev_op}.\n\n"
                        "---\n\n"
                        "[← Volver al Índice](../INDEX.md)\n"
                    )
                    write_article(target_rel, fallback_content, wiki_root=w_root, timeout=15.0)
                    successful_ops.append(target_rel)

            elif op_type == 2:
                # 3. Concurrent navigation regeneration
                regenerate_index_navigation(w_root)
                successful_ops.append(f"regen_nav@{worker_id}-{op}")

            elif op_type == 3:
                # 4. Atomic session commit writing distinct target and shared target under contention
                sess_distinct_rel = f"topics/w{worker_id}-s{op}.md"
                shared_rel = "topics/shared.md"
                distinct_content = (
                    "---\n"
                    "type: topic\n"
                    f"summary: Session committed topic from worker {worker_id} op {op}\n"
                    "last_updated: 2026-11-17\n"
                    "---\n\n"
                    f"# Session Topic W{worker_id} Op{op}\n\n"
                    "## Overview\n"
                    f"Session committed content by worker {worker_id} at op {op}.\n\n"
                    "---\n\n"
                    "[← Volver al Índice](../INDEX.md)\n"
                )
                shared_content = (
                    "---\n"
                    "type: topic\n"
                    f"summary: Shared topic payload from worker {worker_id} op {op}\n"
                    "last_updated: 2026-11-17\n"
                    "---\n\n"
                    "# Shared Topic Under Contention\n\n"
                    "## Overview\n"
                    f"Payload atomically written by worker {worker_id} at op {op}.\n\n"
                    "---\n\n"
                    "[← Volver al Índice](../INDEX.md)\n"
                )
                commit_session(
                    session_summary=f"Worker {worker_id} session {op}",
                    writes=[
                        {"path": sess_distinct_rel, "content": distinct_content},
                        {"path": shared_rel, "content": shared_content},
                    ],
                    wiki_root=w_root,
                    timeout=15.0,
                )
                successful_ops.append(sess_distinct_rel)
                successful_ops.append(f"{shared_rel}@{worker_id}-{op}")

        except (ValidationError, FrontmatterError, OSError, filelock.Timeout) as exc:
            # Expected structured exceptions under heavy lock timeouts or collisions
            errors.append(f"Structured error in op {op} ({type(exc).__name__}): {exc}")
        except Exception as exc:
            # Unexpected exception fails the worker
            errors.append(f"UNEXPECTED FATAL EXCEPTION in op {op} ({type(exc).__name__}): {exc}")

    results_queue.put({"worker_id": worker_id, "successes": successful_ops, "errors": errors})


def _lock_holding_worker(project_root_str: str, lock_target: str, started_event: Any) -> None:
    """Worker that acquires a lock and holds it indefinitely until killed."""
    w_root = Path(project_root_str) / ".brain-79"
    lock = acquire_wiki_lock(w_root, lock_target, timeout=10.0)
    with lock:
        started_event.set()
        time.sleep(60.0)


# ==============================================================================
# Multiprocess Contention & Crash Recovery Tests
# ==============================================================================


@pytest.mark.chaos
def test_multiprocess_contention_and_invariants(tmp_path: Path) -> None:
    """8 spawn workers run 25 ops each under contention; asserts zero corruption and zero leaks."""
    ctx = mp.get_context("spawn")
    ws = tmp_path / "workspace"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    # Seed initial shared article
    initial_shared = (
        "---\n"
        "type: topic\n"
        "summary: Initial shared topic baseline\n"
        "last_updated: 2026-11-17\n"
        "---\n\n"
        "# Shared Topic Under Contention\n\n"
        "## Overview\n"
        "Initial content before chaos testing.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    write_article("topics/shared.md", initial_shared, wiki_root=w_root)

    num_workers = 8
    ops_per_worker = 25
    barrier = ctx.Barrier(num_workers)
    results_queue = ctx.Queue()

    workers: list[Any] = []
    for i in range(num_workers):
        p = ctx.Process(
            target=_chaos_worker_run,
            args=(i, str(ws), barrier, results_queue, ops_per_worker),
        )
        p.start()
        workers.append(p)

    # Join workers with 90s deadline
    deadline = time.time() + 90.0
    for p in workers:
        remaining = max(0.1, deadline - time.time())
        p.join(timeout=remaining)
        if p.is_alive():
            p.kill()
            pytest.fail(f"Worker {p.pid} hung beyond 90s deadline")

    # Collect results
    all_results: list[dict[str, Any]] = []
    while not results_queue.empty():
        all_results.append(results_queue.get_nowait())

    assert len(all_results) == num_workers, f"Expected results from all {num_workers} workers"

    # Verify zero unexpected exceptions
    for res in all_results:
        fatal_errors = [e for e in res["errors"] if "UNEXPECTED" in e]
        assert not fatal_errors, f"Worker {res['worker_id']} encountered unexpected exceptions:\n" + "\n".join(fatal_errors)

    # --- Assertion 1: Valid JSON in registries ---
    registry_file = w_root / ".navigation_registry.json"
    if registry_file.exists():
        json.loads(registry_file.read_text(encoding="utf-8"))

    manifest_file = w_root / ".drift_manifest.json"
    if manifest_file.exists():
        json.loads(manifest_file.read_text(encoding="utf-8"))

    # --- Assertion 2: Zero leftover temp files ---
    temp_files = list(w_root.rglob("*.tmp")) + list(w_root.rglob("*.tmp.*")) + list(w_root.rglob("*.md.tmp"))
    assert temp_files == [], f"Found leftover temporary files after contention: {temp_files}"

    # --- Assertion 3: Every lock acquirable with timeout=0 ---
    locks_dir = w_root / LOCKS_DIRNAME
    if locks_dir.exists():
        for lock_file in locks_dir.glob("*.lock"):
            fl = filelock.FileLock(str(lock_file), timeout=0)
            try:
                fl.acquire()
                fl.release()
            except filelock.Timeout:
                pytest.fail(f"Lock '{lock_file.name}' was left held after worker termination")

    # --- Assertion 4: Distinct articles exist & parse; shared article has atomic payload (no torn writes) ---
    distinct_articles_checked = 0
    for res in all_results:
        for item in res["successes"]:
            if item.startswith("topics/w"):
                p = w_root / item
                assert p.is_file(), f"Reported successful article does not exist on disk: {item}"
                raw = p.read_text(encoding="utf-8")
                item_meta, _ = parse_frontmatter(raw)
                assert item_meta.get("type") == "topic", f"Invalid type in {item}"
                distinct_articles_checked += 1
            elif item.startswith("edit:topics/w"):
                rel_p = item[len("edit:"):]
                p = w_root / rel_p
                assert p.is_file(), f"Reported edited article does not exist on disk: {rel_p}"
                raw = p.read_text(encoding="utf-8")
                item_meta, _ = parse_frontmatter(raw)
                assert item_meta.get("type") == "topic"
                distinct_articles_checked += 1
    assert distinct_articles_checked > 0, "Expected distinct articles written and verified"

    shared_path = w_root / "topics" / "shared.md"
    assert shared_path.is_file(), "Shared article must exist"
    shared_content = shared_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(shared_content)
    assert meta.get("type") == "topic"
    assert "Shared Topic Under Contention" in body
    assert "[← Volver al Índice](../INDEX.md)" in shared_content

    # Strict check: summary and body must belong to the exact same worker and op
    m_sum = re.search(r"worker (\d+) op (\d+)", str(meta.get("summary", "")))
    m_body = re.search(r"worker (\d+) at op (\d+)", body)
    assert m_sum and m_body, "Shared article missing worker and op identifiers"
    assert m_sum.groups() == m_body.groups(), (
        f"TORN WRITE detected in shared.md! Summary has {m_sum.groups()} but body has {m_body.groups()}"
    )

    # --- Assertion 5: Final wiki strict lint passes clean ---
    regenerate_index_navigation(w_root)
    report = lint_wiki(wiki_root=w_root)
    assert "[CRITICAL] Broken Local Links (0)" in report
    assert "[CRITICAL] Namespace Violations (0)" in report


@pytest.mark.chaos
@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL crash test is POSIX only")
def test_sigkill_lock_recovery(tmp_path: Path) -> None:
    """SIGKILL a worker holding a lock; next operation completes within lock timeout with zero orphans."""
    ctx = mp.get_context("spawn")
    ws = tmp_path / "workspace"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    started_event = ctx.Event()
    worker = ctx.Process(
        target=_lock_holding_worker,
        args=(str(ws), "topics/crashed.md", started_event),
    )
    worker.start()

    # Wait until worker acquires lock
    assert started_event.wait(timeout=10.0), "Worker failed to acquire lock in time"

    # Verify lock file exists
    lock_file = get_lock_path(w_root, "topics/crashed.md")
    assert lock_file.exists()

    # Kill worker with SIGKILL
    assert worker.pid is not None
    os.kill(worker.pid, signal.SIGKILL)
    worker.join(timeout=5.0)

    # Next write operation must succeed within lock timeout (<= 10s) and clean up
    content = (
        "---\n"
        "type: topic\n"
        "summary: Post-crash recovery article\n"
        "last_updated: 2026-11-17\n"
        "---\n\n"
        "# Post-Crash Recovery\n\n"
        "## Overview\n"
        "Written after SIGKILL recovery.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    t0 = time.time()
    res = write_article("topics/crashed.md", content, wiki_root=w_root, timeout=10.0)
    duration = time.time() - t0

    assert "topics/crashed.md" in res
    assert duration <= 10.0

    # Ensure no leftover temporary files
    temp_files = list(w_root.rglob("*.tmp*"))
    assert temp_files == []


# ==============================================================================
# Deterministic Seeded Fuzzing Suite (6 Corpus Classes)
# ==============================================================================


def _generate_fuzz_seeds() -> list[int]:
    """Retrieve seeds from BRAIN79_FUZZ_SEED environment variable or return default 0..19."""
    env_seed = os.environ.get("BRAIN79_FUZZ_SEED")
    if env_seed is not None and env_seed.strip():
        try:
            return [int(env_seed.strip())]
        except ValueError:
            pass
    return list(range(20))


@pytest.mark.chaos
@pytest.mark.parametrize("seed", _generate_fuzz_seeds())
def test_deterministic_fuzzing_corpus(tmp_path: Path, seed: int) -> None:
    """Deterministic stdlib fuzzing across 6 corpus classes against frontmatter, validation, and migration."""
    rng = random.Random(seed)
    ws = tmp_path / f"fuzz_ws_{seed}"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    # Corpus 1: Hostile YAML shapes
    yaml_candidates = [
        "--- unterminated frontmatter",
        "---\n- list item instead of mapping\n---",
        "---\nscalar value\n---",
        "---\n[1, 2]: complex key\n---",
        "---\n123: numeric key\n---",
        "---\nkey:\t\ttabs_value\n---",
        "---\na: &a [*a, *a]\n---",
        "---\nexploit: !!python/object/apply:os.system ['echo pwned']\n---",
        "---\ntype: topic\ntype: feature\nsummary: duplicate keys\nlast_updated: 2026-11-17\n---\n# Dup\n",
        "---\n" + "\n".join(f"key_{i}: value_{i}" for i in range(5000)) + "\n---",
    ]
    hostile_yaml = rng.choice(yaml_candidates)
    try:
        t0 = time.time()
        parse_frontmatter(f"{hostile_yaml}\n\n# Body\n")
        assert time.time() - t0 <= 5.0, "parse_frontmatter exceeded 5s timeout"
    except (FrontmatterError, ValidationError, ValueError):
        pass  # Structured errors allowed
    except Exception as exc:
        pytest.fail(f"[Seed {seed}] Hostile YAML caused unexpected {type(exc).__name__}: {exc}")

    # Corpus 2: Hostile Encodings & Boundary Strings
    encoding_candidates = [
        "\ufeff---\ntype: topic\nsummary: BOM test\nlast_updated: 2026-11-17\n---\n\n# BOM\n",
        "---\ntype: topic\nsummary: Surrogates \ud800\udc00\nlast_updated: 2026-11-17\n---\n\n# Surr\n",
        "---\ntype: topic\nsummary: Null byte \x00 test\nlast_updated: 2026-11-17\n---\n\n# Null\n",
        "---\r\ntype: topic\r\nsummary: CRLF test\r\nlast_updated: 2026-11-17\r\n---\r\n\r\n# CRLF\r\n",
        "---\ntype: topic\rsummary: Mixed\rlast_updated: 2026-11-17\n---\n\n# Mixed\n",
    ]
    hostile_enc = rng.choice(encoding_candidates)
    try:
        t0 = time.time()
        validate_article_content("topics/enc.md", hostile_enc, wiki_root=w_root)
        assert time.time() - t0 <= 5.0
    except (ValidationError, FrontmatterError, ValueError):
        pass
    except Exception as exc:
        pytest.fail(f"[Seed {seed}] Hostile encoding caused unexpected {type(exc).__name__}: {exc}")

    # Corpus 3: Unicode Edge Cases (RTL, ZWJ, Emoji, Lengthy Slugs)
    unicode_slug = "مرحبا_עולם_👩‍👩‍👧‍👦_" + "a" * rng.randint(50, 200)
    unicode_content = (
        "---\n"
        "type: topic\n"
        "summary: RTL and ZWJ test \u200e\u200f\u200d\n"
        "last_updated: 2026-11-17\n"
        "---\n\n"
        f"# Heading {unicode_slug}\n\n"
        "## Overview\n"
        "Unicode validation.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    try:
        t0 = time.time()
        validate_article_content(f"topics/{unicode_slug[:50]}.md", unicode_content, wiki_root=w_root)
        assert time.time() - t0 <= 5.0
    except (ValidationError, FrontmatterError, ValueError):
        pass
    except Exception as exc:
        pytest.fail(f"[Seed {seed}] Unicode edge case caused unexpected {type(exc).__name__}: {exc}")

    # Corpus 4: Size and Line Count Boundaries
    # 20,479, 20,480 (accepted) vs 20,481 (rejected)
    from brain79.core.frontmatter import dump_frontmatter
    meta_dict: dict[str, Any] = {
        "type": "topic",
        "summary": "Size boundary test",
        "last_updated": "2026-11-17",
        "status": "active",
    }
    h1 = "# Size Test\n\n## Overview\n"
    backlink = "\n\n---\n\n[← Volver al Índice](../INDEX.md)\n"

    probe = dump_frontmatter(meta_dict, h1 + backlink)
    needed = MAX_ARTICLE_BYTES - len(probe.encode("utf-8"))

    # 20,479 bytes (accepted)
    valid_20479 = dump_frontmatter(meta_dict, h1 + ("x" * (needed - 1)) + backlink)
    assert len(valid_20479.encode("utf-8")) == MAX_ARTICLE_BYTES - 1
    validate_article_content("topics/exact20479.md", valid_20479, wiki_root=w_root)

    # 20,480 bytes (accepted)
    valid_exact = dump_frontmatter(meta_dict, h1 + ("x" * needed) + backlink)
    assert len(valid_exact.encode("utf-8")) == MAX_ARTICLE_BYTES
    validate_article_content("topics/exact20480.md", valid_exact, wiki_root=w_root)

    # 20,481 bytes (rejected)
    invalid_oversized = dump_frontmatter(meta_dict, h1 + ("x" * (needed + 1)) + backlink)
    assert len(invalid_oversized.encode("utf-8")) == MAX_ARTICLE_BYTES + 1
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("topics/over20480.md", invalid_oversized, wiki_root=w_root)
    assert exc_info.value.rule == "article_too_large"

    # 3-byte character boundaries using '€' (3 bytes per character in UTF-8)
    char_3b = "€"
    probe_3b = dump_frontmatter(meta_dict, h1 + backlink)
    base_bytes = len(probe_3b.encode("utf-8"))

    # 20,479 bytes via 3-byte characters (accepted)
    remaining_20479 = (MAX_ARTICLE_BYTES - 1) - base_bytes
    num_3b_20479 = remaining_20479 // 3
    ascii_pad_20479 = remaining_20479 % 3
    valid_20479_3b = dump_frontmatter(meta_dict, h1 + (char_3b * num_3b_20479) + ("y" * ascii_pad_20479) + backlink)
    assert len(valid_20479_3b.encode("utf-8")) == MAX_ARTICLE_BYTES - 1
    validate_article_content("topics/exact20479_3b.md", valid_20479_3b, wiki_root=w_root)

    # 20,480 bytes via 3-byte characters (accepted)
    remaining_bytes = MAX_ARTICLE_BYTES - base_bytes
    num_3b = remaining_bytes // 3
    ascii_pad = remaining_bytes % 3
    valid_exact_3b = dump_frontmatter(meta_dict, h1 + (char_3b * num_3b) + ("y" * ascii_pad) + backlink)
    assert len(valid_exact_3b.encode("utf-8")) == MAX_ARTICLE_BYTES
    validate_article_content("topics/exact20480_3b.md", valid_exact_3b, wiki_root=w_root)

    # 20,481 bytes via 3-byte characters (rejected)
    invalid_oversized_3b = dump_frontmatter(meta_dict, h1 + (char_3b * num_3b) + ("y" * (ascii_pad + 1)) + backlink)
    assert len(invalid_oversized_3b.encode("utf-8")) == MAX_ARTICLE_BYTES + 1
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("topics/over20480_3b.md", invalid_oversized_3b, wiki_root=w_root)
    assert exc_info.value.rule == "article_too_large"

    # Line count boundaries: 400 lines (accepted) vs 401 lines (rejected)
    head_lines = [
        "---",
        "type: topic",
        "summary: Size boundary test",
        "last_updated: 2026-11-17",
        "status: active",
        "---",
        "",
        "# Size Test",
        "",
        "## Overview",
    ]
    foot_lines = ["", "---", "", "[← Volver al Índice](../INDEX.md)"]
    filler_count = MAX_ARTICLE_LINES - len(head_lines) - len(foot_lines)
    filler_400 = [f"- bullet {i}" for i in range(filler_count)]

    valid_400_lines = "\n".join(head_lines + filler_400 + foot_lines) + "\n"
    assert len(valid_400_lines.splitlines()) == MAX_ARTICLE_LINES
    validate_article_content("topics/exact400lines.md", valid_400_lines, wiki_root=w_root)

    invalid_401_lines = "\n".join(head_lines + filler_400 + ["- extra bullet"] + foot_lines) + "\n"
    assert len(invalid_401_lines.splitlines()) == MAX_ARTICLE_LINES + 1
    with pytest.raises(ValidationError) as exc_info:
        validate_article_content("topics/over400lines.md", invalid_401_lines, wiki_root=w_root)
    assert exc_info.value.rule == "article_too_large"

    # Corpus 5: Hostile Paths (traversal, absolute, reserved names, trailing dots/spaces)
    hostile_paths = [
        "../outside.md",
        "../../etc/passwd.md",
        "/absolute/path.md",
        "topics/CON.md",
        "topics/NUL.md",
        "topics/COM1.md",
        "topics/trailing_dot..md",
        "topics/trailing_space .md",
    ]
    chosen_path = rng.choice(hostile_paths)
    with pytest.raises(ValueError):
        write_article(chosen_path, valid_exact, wiki_root=w_root)
    assert not (w_root / chosen_path).exists(), f"Rejected path '{chosen_path}' was created on disk!"

    # Symlink escape check
    outside_file = ws / "outside_target.txt"
    outside_file.write_text("classified content", encoding="utf-8")
    escape_link = w_root / "topics" / f"escape_{seed}.md"
    try:
        escape_link.symlink_to(outside_file)
        with pytest.raises(ValueError):
            read_article(f"topics/escape_{seed}.md", wiki_root=w_root)
        with pytest.raises(ValueError):
            write_article(f"topics/escape_{seed}.md", valid_exact, wiki_root=w_root)
        assert outside_file.read_text(encoding="utf-8") == "classified content", "Outside file was mutated via symlink!"
    except (OSError, NotImplementedError):
        pass


@pytest.mark.chaos
def test_graph_cycles_and_long_chains(tmp_path: Path) -> None:
    """Wiki graph cycles (A -> B -> C -> A), self-references, and 200-node chains terminate <= 5s."""
    ws = tmp_path / "cycle_workspace"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    # 1. 3-Node Cycle: A -> B -> C -> A via transactional commit
    cycle_writes = []
    for src, dst in [("a", "b"), ("b", "c"), ("c", "a")]:
        c = (
            "---\n"
            "type: topic\n"
            f"summary: Cycle node {src}\n"
            "last_updated: 2026-11-17\n"
            "applies_to:\n"
            f"  - .brain-79/topics/{dst}.md\n"
            "related:\n"
            f"  - topics/{dst}.md\n"
            "---\n\n"
            f"# Cycle Node {src.upper()}\n\n"
            "## Overview\n"
            f"Points to {dst}.\n\n"
            "---\n\n"
            "[← Volver al Índice](../INDEX.md)\n"
        )
        cycle_writes.append({"path": f"topics/{src}.md", "content": c})

    commit_session(session_summary="Commit 3-node cycle", writes=cycle_writes, wiki_root=w_root)

    # 2. Self-reference: S -> S
    self_ref = (
        "---\n"
        "type: topic\n"
        "summary: Self reference\n"
        "last_updated: 2026-11-17\n"
        "applies_to:\n"
        "  - .brain-79/topics/self.md\n"
        "related:\n"
        "  - topics/self.md\n"
        "---\n\n"
        "# Self Referencing\n\n"
        "## Overview\n"
        "Self reference.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    commit_session(session_summary="Commit self ref", writes=[{"path": "topics/self.md", "content": self_ref}], wiki_root=w_root)

    # 3. 200-Node Chain: node-0 -> node-1 -> ... -> node-199
    chain_writes = []
    for i in range(200):
        next_target = f"node-{i + 1}" if i < 199 else "node-0"
        node_content = (
            "---\n"
            "type: topic\n"
            f"summary: Chain node {i}\n"
            "last_updated: 2026-11-17\n"
            "related:\n"
            f"  - topics/{next_target}.md\n"
            "---\n\n"
            f"# Node {i}\n\n"
            "## Overview\n"
            f"Chain link {i}.\n\n"
            "---\n\n"
            "[← Volver al Índice](../INDEX.md)\n"
        )
        chain_writes.append({"path": f"topics/node-{i}.md", "content": node_content})

    commit_session(session_summary="Commit 200-node chain", writes=chain_writes, wiki_root=w_root)

    regenerate_index_navigation(w_root)

    # Execution must complete <= 5.0 seconds
    t0 = time.time()
    orient_res = orient(task="test cycle resolution", wiki_root=w_root)
    assert time.time() - t0 <= 5.0
    assert orient_res is not None

    t0 = time.time()
    drift_res = check_article_drift("topics/a.md", wiki_root=w_root, project_root=ws)
    assert time.time() - t0 <= 5.0
    assert isinstance(drift_res, list)

    t0 = time.time()
    report = lint_wiki(wiki_root=w_root)
    assert time.time() - t0 <= 5.0
    assert "[CRITICAL] Broken Local Links (0)" in report


# ==============================================================================
# Environment Faults & Rollback Atomicity Tests
# ==============================================================================


@pytest.mark.chaos
def test_environment_fault_disk_full_enospc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Disk full (ENOSPC) during commit_session rolls back cleanly; no partial files or orphan tmp."""
    ws = tmp_path / "enospc_workspace"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    # Pre-existing baseline article
    baseline_content = (
        "---\n"
        "type: topic\n"
        "summary: Existing article\n"
        "last_updated: 2026-11-17\n"
        "---\n\n"
        "# Existing\n\n"
        "## Overview\n"
        "Original state.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    write_article("topics/existing.md", baseline_content, wiki_root=w_root)
    baseline_content = (w_root / "topics" / "existing.md").read_text(encoding="utf-8")

    real_write_text = Path.write_text

    call_count = 0

    def faulty_write_text(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
        nonlocal call_count
        call_count += 1
        if "faulty" in self.name or call_count > 3:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", faulty_write_text)

    new_article_content = (
        "---\n"
        "type: topic\n"
        "summary: Faulty new article\n"
        "last_updated: 2026-11-17\n"
        "---\n\n"
        "# Faulty\n\n"
        "## Overview\n"
        "Should not persist.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )

    with pytest.raises(OSError) as exc_info:
        commit_session(
            session_summary="Attempt with ENOSPC fault",
            writes=[{"path": "topics/faulty.md", "content": new_article_content}],
            wiki_root=w_root,
        )
    assert exc_info.value.errno == errno.ENOSPC

    # Rollback assertion: topics/faulty.md must NOT exist
    assert not (w_root / "topics" / "faulty.md").exists()
    # Baseline article must remain identical
    assert (w_root / "topics" / "existing.md").read_text(encoding="utf-8") == baseline_content

    # Zero orphan temporary files
    assert list(w_root.rglob("*.tmp*")) == []

    # Transaction lock released
    tx_lock = acquire_wiki_lock(w_root, "_transaction.lock", timeout=0)
    tx_lock.acquire()
    tx_lock.release()


@pytest.mark.chaos
def test_environment_fault_keyboard_interrupt_during_pass3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """KeyboardInterrupt during commit_session Pass 3 triggers rollback; lock released and zero tmp."""
    ws = tmp_path / "interrupt_workspace"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    baseline_content = (
        "---\n"
        "type: topic\n"
        "summary: Existing article\n"
        "last_updated: 2026-11-17\n"
        "---\n\n"
        "# Existing\n\n"
        "## Overview\n"
        "Original state.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    write_article("topics/existing.md", baseline_content, wiki_root=w_root)
    baseline_content = (w_root / "topics" / "existing.md").read_text(encoding="utf-8")

    # Monkeypatch write_article to raise KeyboardInterrupt on second article
    from brain79.core import session_commit

    real_write_article = session_commit.write_article
    write_calls = 0

    def interrupt_write_article(*args: Any, **kwargs: Any) -> str:
        nonlocal write_calls
        write_calls += 1
        if write_calls >= 2:
            raise KeyboardInterrupt("Simulated Ctrl-C during Pass 3 persistence")
        return real_write_article(*args, **kwargs)

    monkeypatch.setattr(session_commit, "write_article", interrupt_write_article)

    art1 = (
        "---\n"
        "type: topic\n"
        "summary: Article 1\n"
        "last_updated: 2026-11-17\n"
        "---\n\n"
        "# Art 1\n\n"
        "## Overview\n"
        "One.\n\n"
        "---\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    art2 = art1.replace("Article 1", "Article 2").replace("Art 1", "Art 2")

    with pytest.raises(KeyboardInterrupt):
        commit_session(
            session_summary="Session interrupted",
            writes=[
                {"path": "topics/art1.md", "content": art1},
                {"path": "topics/art2.md", "content": art2},
            ],
            wiki_root=w_root,
        )

    # Rollback assertion: art1 and art2 must not exist
    assert not (w_root / "topics" / "art1.md").exists()
    assert not (w_root / "topics" / "art2.md").exists()

    # Zero orphan temporary files
    assert list(w_root.rglob("*.tmp*")) == []

    # Transaction lock released
    tx_lock = acquire_wiki_lock(w_root, "_transaction.lock", timeout=0)
    tx_lock.acquire()
    tx_lock.release()


@pytest.mark.chaos
def test_fuzz_migrate_wiki_and_corrupt_bytes_on_disk(tmp_path: Path) -> None:
    """migrate_wiki, read_article, edit_article, and commit_session against hostile/corrupt files on disk."""
    ws = tmp_path / "hostile_disk_ws"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    # Plant corrupt raw bytes (invalid UTF-8)
    corrupt_file = w_root / "topics" / "corrupt_utf8.md"
    corrupt_file.write_bytes(b"\xff\xfe\xfd\x00---not valid utf8")

    # Plant duplicate YAML keys file
    dup_file = w_root / "topics" / "duplicate_keys.md"
    dup_file.write_text(
        "---\ntype: topic\ntype: feature\nsummary: duplicate keys\nlast_updated: 2026-11-17\n---\n# Dup\n",
        encoding="utf-8",
    )

    # Plant valid article to verify migration continues past corrupt files
    valid_file = w_root / "topics" / "valid_art.md"
    valid_file.write_text(
        "---\ntype: topic\nsummary: Valid article\nlast_updated: 2026-11-17\n---\n\n# Valid Art\n\n## Overview\nValid.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    )

    # migrate_wiki must not crash and cleanly report/skip corrupt files
    report = migrate_wiki(w_root, dry_run=False)
    assert "corrupt_utf8.md: invalid UTF-8 encoding" in report or "corrupt_utf8.md" in report

    # read_article on corrupt bytes raises ValidationError(rule="invalid_utf8_encoding")
    with pytest.raises(ValidationError) as exc_info:
        read_article("topics/corrupt_utf8.md", wiki_root=w_root)
    assert exc_info.value.rule == "invalid_utf8_encoding"

    # edit_article on corrupt bytes raises ValidationError(rule="invalid_utf8_encoding")
    with pytest.raises(ValidationError) as exc_info:
        edit_article("topics/corrupt_utf8.md", [{"old_text": "foo", "new_text": "bar"}], wiki_root=w_root)
    assert exc_info.value.rule == "invalid_utf8_encoding"

    # commit_session editing corrupt bytes raises ValidationError
    with pytest.raises(ValidationError):
        commit_session(
            session_summary="Edit corrupt article",
            edits=[{"path": "topics/corrupt_utf8.md", "edits": [{"old_text": "foo", "new_text": "bar"}]}],
            wiki_root=w_root,
        )


@pytest.mark.chaos
def test_environment_fault_readonly_directory(tmp_path: Path) -> None:
    """Read-only wiki directory fault triggers clean rollback, zero orphan tmp, and releases lock."""
    ws = tmp_path / "readonly_workspace"
    ws.mkdir()
    init_project(ws, install_git_hooks_flag=False)
    w_root = ws / ".brain-79"

    baseline = (
        "---\ntype: topic\nsummary: Baseline topic\nlast_updated: 2026-11-17\n---\n\n# Baseline\n\n## Overview\nContent.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n"
    )
    write_article("topics/baseline.md", baseline, wiki_root=w_root)
    saved_baseline = (w_root / "topics" / "baseline.md").read_text(encoding="utf-8")

    topics_dir = w_root / "topics"
    orig_mode = topics_dir.stat().st_mode

    try:
        new_art = baseline.replace("Baseline", "New Article")
        if sys.platform == "win32":
            # On Windows CRT, os.chmod on directories does not prevent file creation.
            # Simulate read-only directory fault via PermissionError fault injection on write.
            orig_atomic = atomic_replace_with_retry

            def mock_atomic(src_p: Path, dst_p: Path) -> None:
                if "blocked.md" in dst_p.name:
                    raise PermissionError(13, "Access is denied: 'topics\\\\blocked.md'")
                orig_atomic(src_p, dst_p)

            with patch("brain79.core.wiki.atomic_replace_with_retry", side_effect=mock_atomic), \
                 patch("brain79.core.session_commit.atomic_replace_with_retry", side_effect=mock_atomic):
                with pytest.raises((OSError, ValidationError)):
                    commit_session(
                        session_summary="Attempt to write in read-only directory",
                        writes=[{"path": "topics/blocked.md", "content": new_art}],
                        wiki_root=w_root,
                    )
        else:
            # Make topics directory read-only
            os.chmod(topics_dir, 0o555)

            with pytest.raises((OSError, ValidationError)):
                commit_session(
                    session_summary="Attempt to write in read-only directory",
                    writes=[{"path": "topics/blocked.md", "content": new_art}],
                    wiki_root=w_root,
                )
    finally:
        # Restore permissions for teardown
        if sys.platform != "win32":
            os.chmod(topics_dir, orig_mode)

    # Rollback assertion: blocked article was not persisted
    assert not (w_root / "topics" / "blocked.md").exists()
    # Baseline remained intact
    assert (w_root / "topics" / "baseline.md").read_text(encoding="utf-8") == saved_baseline
    # No orphan temporary files
    assert list(w_root.rglob("*.tmp*")) == []
    # Transaction lock released
    tx_lock = acquire_wiki_lock(w_root, "_transaction.lock", timeout=0)
    tx_lock.acquire()
    tx_lock.release()
