---
type: feature
summary: Centralized .locks/ directory isolation, POSIX path and CRLF normalization, cross-platform Git hooks, and local Windows/Linux simulation tests
status: planned
version: 2.1.0
applies_to:
  - src/brain79/core/wiki.py
  - src/brain79/core/navigation.py
  - src/brain79/core/lint.py
  - src/brain79/core/bootstrap.py
  - src/brain79/core/drift.py
  - src/brain79/core/init_project.py
  - src/brain79/core/migration.py
related:
  - architecture/roadmap-industrial-scale.md
last_updated: 2026-11-03
---

# Feature — Cross-Platform Portability & Centralized Lock Isolation (Phase 6 Specification)

## Overview

This specification defines **Phase 6 of the Industrial-Scale Roadmap**: eliminating adjacent `.md.lock` visual clutter via a centralized `.brain-79/.locks/` directory, hardening filesystem and path operations for Windows/Linux/macOS portability, and establishing a deterministic **Local Cross-Platform Simulation Suite** so all OS invariants are tested locally without relying on external CI runners.

---

## Problem Statement

### 1. Visual Pollution from Adjacent `.lock` Files
Currently, `wiki.py`, `navigation.py`, `lint.py`, and `bootstrap.py` create lock files directly adjacent to target files (`target.with_suffix(".md.lock")`, `.navigation_registry.json.lock`, `INDEX.md.lock`, `.bootstrap_state.json.lock`).
- Because `filelock` intentionally leaves empty lock files on disk to prevent POSIX inode unlink race conditions, every edited article leaves a companion `.md.lock` file in `architecture/`, `decisions/`, `features/`, `product/`, and `changelog/`.
- This duplicates visual entries in VS Code, Obsidian, Finder, and directory trees.

### 2. Hidden Cross-Platform Bugs in Core Modules (Windows & Linux)
A static audit of `src/brain79/core/` reveals **6 concrete cross-platform bugs** across Windows and Linux (`ext4`/`xfs`):
1. **Linux Case-Sensitivity (`ext4`/`xfs` vs macOS `APFS` Case-Insensitive):**
   - On macOS default `APFS`, `Path("decisions/ADR-001.md").is_file()` returns `True` even if the file on disk is lowercase `decisions/adr-001.md`. On Linux (`ext4`/`xfs`), it returns `False` (`FileNotFoundError`).
   - In `lint.py` (line 220), when a link target does not match the exact-case dictionary `existing_rel_files`, the code falls back to `target_abs = (wiki_root / norm_rel).resolve()` and `target_abs.is_file()`. On macOS, a wrong-case link like `[ADR-001](ADR-001.md)` silently passes `lint` via the filesystem fallback, and then crashes on Linux!
   - Similarly, in `drift.py`, `applies_to` path matching against workspace files must enforce exact case comparison so stale/mis-cased bindings are caught on macOS before ever reaching Linux.
2. **Linux Unordered Directory Traversal (`os.walk` / `Path.rglob` / `Path.glob`):**
   - On macOS `APFS`, directory entries are often returned in lexicographical order by coincidence; on Linux `ext4`/`xfs` (htree hash indexing), `rglob("*.md")` and `glob("*.md")` return files in arbitrary inode/hash order. Any traversal not explicitly wrapped in `sorted()` produces non-deterministic outputs across Linux machines.
3. **Backslash Path Strings (`str(path.relative_to(...))`):** Across `wiki.py`, `lint.py`, `drift.py`, `context.py`, `orient.py`, `session_commit.py`, and `handoff.py`, relative paths are converted via `str(p.relative_to(w_root))` instead of `p.relative_to(w_root).as_posix()`. On Windows, `str(Path("decisions/adr-001.md"))` yields `"decisions\\adr-001.md"`, which fails `rel_path.startswith("decisions/")`, corrupts `.navigation_registry.json` keys, and breaks `applies_to` glob matching.
4. **CRLF (`\r\n`) Line Endings on Read/Write/Edit:** Files edited on Windows or checked out with `git config core.autocrlf=true` contain `\r\n`. In `edit_article` (`wiki.py`), `old_text` passed over JSON-RPC uses `\n`, causing exact substring matching (`old_text in content`) to fail against `\r\n` files. Similarly, `write_text()` on Windows converts `\n` to `os.linesep` (`\r\n`) unless `newline="\n"` is explicitly passed.
5. **NTFS Atomic Replace & Cross-Device (`/tmp` vs `/home`) Safety:** On Windows NTFS, `tmp_path.replace(target)` can raise `PermissionError` if an external indexer briefly holds a read handle on `target`. On Linux, if `tmp_path` were ever created in `/tmp` (`tmpfs`) while the repo lives on `/home` (`ext4`), `replace()` would raise `EXDEV` (`Invalid cross-device link`). Keeping `.md.tmp` in the same directory as `target` guarantees same-filesystem atomic rename on Linux.
6. **Pre-Commit Hook PATH & Non-Interactive Shell Resolution:** `PRE_COMMIT_HOOK_SCRIPT` in `init_project.py` invokes bare `brain79`. In Linux non-interactive shells (`/etc/profile` without `~/.bashrc`), Git for Windows (`sh.exe`), and macOS GUI Git clients, `~/.local/bin` and `$XDG_BIN_HOME` are often absent from `$PATH`.

---

## Architecture & Design (4 Pillars)

### Pillar 1: Centralized Lock Manager (`src/brain79/core/locks.py`)
Create a dedicated module `src/brain79/core/locks.py` as the single authority for all interprocess locks:

- **Lock Directory:** `.brain-79/.locks/` (excluded from article scanning in `_EXCLUDED_DIRS` and ignored in `.brain-79/.gitignore`).
- **Deterministic Lock Naming (`get_article_lock_path`):**
  Convert the normalized POSIX relative path into a flat, collision-free filename inside `.brain-79/.locks/` by replacing `/` with `__`:
  - `decisions/adr-001.md` $\rightarrow$ `.brain-79/.locks/decisions__adr-001.md.lock`
  - `INDEX.md` $\rightarrow$ `.brain-79/.locks/INDEX.md.lock`
  - `.navigation_registry.json` $\rightarrow$ `.brain-79/.locks/_registry.lock`
  - `.bootstrap_state.json` $\rightarrow$ `.brain-79/.locks/_bootstrap.lock`
- **Unified Helper Functions:**
  - `get_lock_path(wiki_root: Path, rel_posix_path: str) -> Path`
  - `acquire_wiki_lock(wiki_root: Path, rel_posix_path: str, timeout: float = 10.0) -> filelock.FileLock`
  - `cleanup_legacy_inline_locks(wiki_root: Path) -> int`: Scans `.brain-79/` (excluding `.locks/`) and removes any leftover `*.lock` files from older versions. Called automatically during `brain79 migrate --apply`, `brain79 navigate --regenerate`, and `brain79 init`.

### Pillar 2: Universal POSIX Path, Case-Sensitivity & Line-Ending Normalization
1. **Strict Case-Sensitive Link & Path Resolution (Linux `ext4` Parity on macOS):**
   - In `lint.py`, verify markdown links strictly against the exact-case `existing_rel_files` set (and for non-`.md` files, verify exact filename case against `os.listdir(target_abs.parent)`). A link `[ADR](decisions/ADR-001.md)` pointing to `decisions/adr-001.md` must be flagged as a broken link on macOS just as it fails on Linux.
   - Ensure all `rglob` / `glob` calls in `drift.py`, `migration.py`, `lint_organizational.py`, and `context.py` are deterministically sorted (`sorted(...)`) so Linux `ext4` htree ordering never causes output variation.
2. **Canonical Relative Path Helper (`rel_posix(path: Path, root: Path) -> str`):**
   - Replace every `str(p.relative_to(root))` across the codebase with `p.relative_to(root).as_posix()`.
   - Normalize user-supplied `path` and `paths` arguments (e.g. `decisions\adr-001.md` $\rightarrow$ `decisions/adr-001.md`) at the entry boundary of `_safe_resolve`, `orient`, `context`, and `drift`.
3. **Strict LF (`\n`) Normalization on I/O Boundaries:**
   - When reading markdown/JSON files, normalize `\r\n` $\rightarrow$ `\n`.
   - When writing files (`write_text` / `open`), always pass `newline="\n"` so files written on Windows, Linux, and macOS are byte-for-byte identical.

### Pillar 3: Resilient Atomic Replace & Cross-Platform Pre-Commit Hook
1. **`atomic_replace_with_retry(tmp_path: Path, target: Path)`:**
   - Keeps `tmp_path` in `target.parent` (preventing Linux `EXDEV` cross-device rename errors between `/tmp` and `/home`) and wraps `tmp_path.replace(target)` with a bounded backoff retry (3 attempts over 50ms on `PermissionError`) to handle transient Windows NTFS file-handle locks.
2. **Cross-Platform Pre-Commit Hook (`init_project.py`):**
   - Enhance `PRE_COMMIT_HOOK_SCRIPT` so it augments `PATH` with `$XDG_BIN_HOME`, `$HOME/.local/bin`, `$HOME/.cargo/bin`, and `$USERPROFILE/.local/bin` before resolving `brain79`, ensuring Linux non-interactive shells, Git for Windows (`sh`), and macOS GUI Git clients always find the executable.

### Pillar 4: How to Test Without CI (Local Cross-Platform Simulation Suite)
Because there is no remote CI pipeline required in this workflow, we test Windows and Linux behaviors **deterministically on macOS** in `tests/test_cross_platform_and_locks.py` using 5 simulation techniques:
1. **Linux Case-Sensitivity Simulation on macOS APFS:** Create `decisions/adr-001.md` and an article linking to `decisions/ADR-001.md` (uppercase). Assert that `lint_wiki()` detects the case-mismatched link as `[CRITICAL] Broken Local Links` even when running on a case-insensitive macOS filesystem.
2. **Linux `ext4` Inode Order Simulation:** Shuffle directory iteration results in tests to verify `list_articles`, `lint`, `orient`, and `context` produce 100% deterministic ordering regardless of OS filesystem indexing.
3. **CRLF Injection Tests:** Write raw bytes containing `b"\r\n"` to `.brain-79/` files and verify `read_article`, `edit_article`, `parse_frontmatter`, `lint_wiki`, and `write_article` process them cleanly and emit pure `\n` (`b"\r\n" not in target.read_bytes()`).
4. **Windows Backslash Input Tests:** Pass Windows-style paths (`"decisions\\adr-001.md"`, `paths=["src\\brain79\\server.py"]`) into `read`, `write`, `edit`, `orient`, `context`, and `drift`, verifying they resolve identically to POSIX paths.
5. **NTFS `PermissionError` Retry & Zero Inline `.lock` Invariants:** Mock `Path.replace` to raise `PermissionError` on the first 2 attempts and succeed on the 3rd, and assert after a full session lifecycle that zero `*.lock` files exist outside `.brain-79/.locks/`.

---

## Implementation Checklist (Developer Agent)

1. **Create `src/brain79/core/locks.py`:** Implement `get_lock_path`, `acquire_wiki_lock`, `atomic_replace_with_retry`, and `cleanup_legacy_inline_locks`.
2. **Refactor Lock Consumers:** Update `wiki.py`, `navigation.py`, `lint.py`, and `bootstrap.py` to use `locks.py` and add `".locks"` to `_EXCLUDED_DIRS` and `.gitignore`.
3. **Normalize Paths & Line Endings:** Replace `str(x.relative_to(y))` with `.as_posix()`, accept `\` in user path inputs, and enforce `newline="\n"` on file writes.
4. **Harden Pre-Commit Hook:** Update `PRE_COMMIT_HOOK_SCRIPT` in `init_project.py` to include `~/.local/bin` in `PATH`.
5. **Purge Existing `.lock` Clutter:** Run `cleanup_legacy_inline_locks` on the repository's own `.brain-79/` directory so all legacy `.md.lock` files are removed.
6. **Tests & Documentation:**
   - Update existing lock tests in `tests/test_wiki.py` and `tests/test_lint.py` to use `get_lock_path`.
   - Create `tests/test_cross_platform_and_locks.py` covering all 4 simulation pillars.
   - Record `decisions/adr-014-centralized-locks-and-cross-platform-io.md` and update `features/cross-platform-and-lock-isolation.md` to `status: shipped`.

---

[← Volver al Índice](../INDEX.md)
