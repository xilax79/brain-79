---
type: feature
summary: centralized .locks/ directory isolation, POSIX path and CRLF normalization, cross-platform Git hooks, and local Windows/Linux simulation tests
status: shipped
version: 2.1.0
applies_to:
  - src/brain79/core/wiki.py
  - src/brain79/core/navigation.py
  - src/brain79/core/lint.py
  - src/brain79/core/bootstrap.py
  - src/brain79/core/drift.py
  - src/brain79/core/init_project.py
  - src/brain79/core/migration.py
  - src/brain79/core/session_commit.py
  - src/brain79/core/handoff.py
related:
  - architecture/roadmap-industrial-scale.md
last_updated: 2026-11-05
---

# Feature — Cross-platform portability and centralized lock isolation (Phase 6 specification)

## Overview

This specification defines **Phase 6 of the Industrial-Scale Roadmap**: eliminating adjacent `.md.lock` visual clutter via a centralized `.brain-79/.locks/` directory, hardening filesystem and path operations for Windows/Linux/macOS portability, and establishing a deterministic **Local Cross-Platform Simulation Suite** so all OS invariants are tested locally without relying on external CI runners.

---

## Problem statement

### 1. Visual pollution from adjacent `.lock` files
Currently, `wiki.py`, `navigation.py`, `lint.py`, and `bootstrap.py` create lock files directly adjacent to target files (`target.with_suffix(".md.lock")`, `.navigation_registry.json.lock`, `INDEX.md.lock`, `.bootstrap_state.json.lock`).
- Because `filelock` intentionally leaves empty lock files on disk to prevent POSIX inode unlink race conditions, every edited article leaves a companion `.md.lock` file in `architecture/`, `decisions/`, `features/`, `product/`, and `changelog/`.
- This duplicates visual entries in VS Code, Obsidian, Finder, and directory trees.

### 2. Hidden cross-platform bugs in core modules (Windows and Linux)
A static audit of `src/brain79/core/` reveals **9 concrete cross-platform bugs** across Windows and Linux (`ext4`/`xfs`):

1. **Linux Case-Sensitivity (`ext4`/`xfs` vs macOS `APFS` Case-Insensitive) in BOTH `lint.py` AND `_run_inline_checks` (`wiki.py`):**
   - On macOS default `APFS`, `Path("decisions/ADR-001.md").is_file()` and `.exists()` return `True` even if the file on disk is lowercase `decisions/adr-001.md`. On Linux (`ext4`/`xfs`), it returns `False`.
   - **Location A (`src/brain79/core/lint.py`, line 220):** When a link target does not match the exact-case dictionary `existing_rel_files`, the code falls back to `target_abs = (wiki_root / norm_rel).resolve()` and `target_abs.is_file()`. On macOS, a wrong-case `.md` link like `[ADR-001](ADR-001.md)` bypasses `existing_rel_files` and silently passes via the filesystem fallback! If `norm_rel.endswith(".md")`, it must **ONLY** check `norm_rel in existing_rel_files` (never falling back to case-insensitive `target_abs.is_file()`). For non-`.md` files, verify exact case via a recursive `has_exact_case_path(root, rel_path)` check walking each segment against `os.listdir(parent)`.
   - **Location B (`src/brain79/core/wiki.py`, `_run_inline_checks`, line 420):** Inline health checks on `write_article` use `if not target_file.exists():` to detect broken local links. On macOS, writing an article with `[ADR-001](ADR-001.md)` reports `lint OK` in `write_article` because `.exists()` is case-insensitive, and then fails in `lint_wiki`! `_run_inline_checks` must also use `has_exact_case_path(wiki_root, target_rel)` so inline checks and `lint_wiki` have 100% parity.
   - **Location C (`src/brain79/core/drift.py`, `find_matching_workspace_files`, line 129):** Direct path checks (`target.is_file()` / `target.is_dir()`) must also verify `has_exact_case_path(p_root, rel)` so mis-cased `applies_to` paths are caught on macOS.

2. **Path Resolution Bug on macOS/Windows When Writing a New Case-Renamed File (`_safe_resolve` in `wiki.py`, line 25):**
   - In Python on macOS (`APFS`), calling `(w_root / path).resolve()` on an **existing** file canonicalizes its case to the disk's existing casing, and on a **non-existent** file inside an existing differently-cased directory canonicalizes the parent directory's case. Worse, if a user passes backslashes `"decisions\\adr-001.md"` on macOS/Linux, `Path("decisions\\adr-001.md")` treats the entire string as a single filename with a literal backslash!
   - `_safe_resolve(path, wiki_root)` must first normalize `clean_path = path.replace("\\", "/").strip()` before constructing `w_root / clean_path`, and compute relative paths via normalized POSIX segments rather than letting `.resolve()` silently rewrite case or fail on backslashes.

3. **Linux Unordered Directory Traversal (`os.walk` / `Path.rglob` / `Path.glob`):**
   - On Linux `ext4`/`xfs` (htree hash indexing), `rglob("*.md")` and `glob("*")` return files in arbitrary inode/hash order. Every traversal in `drift.py` (lines 135, 141), `migration.py`, `lint_organizational.py`, and `context.py` must be explicitly wrapped in `sorted(...)`.

4. **Backslash Path Strings (`str(path.relative_to(...))` — 45+ occurrences across 12 files):**
   - Across `wiki.py` (including `register_article(w_root, str(rel_p), ...)` at line 339 and `_search_ripgrep` at line 630), `lint.py`, `drift.py`, `context.py`, `orient.py`, `session_commit.py`, `bootstrap.py`, `migration.py`, `lint_organizational.py`, and `handoff.py`, relative paths are converted via `str(p.relative_to(w_root))` instead of `.as_posix()`. On Windows, this yields `"decisions\\adr-001.md"`, corrupting `.navigation_registry.json`, `virtual_fs` keys in `session_commit.py`, and `.startswith("handoffs/")` checks.

5. **CRLF (`\r\n`) Line Endings on Read/Write/Edit & `session_commit.py` Pre-Flight:**
   - Files checked out on Windows with `git config core.autocrlf=true` contain `\r\n`.
   - In `edit_article` (`wiki.py:459`) AND in `session_commit.py` (`line 122`: `current_text = target.read_text(encoding="utf-8")`), reading raw `\r\n` content without normalizing `.replace("\r\n", "\n")` causes `old_text` (which arrives over MCP JSON with `\n`) to fail exact substring matching (`old_text not found`).
   - Similarly, `write_text()` on Windows converts `\n` to `os.linesep` (`\r\n`) unless `newline="\n"` is explicitly passed on all writes (`wiki.py`, `navigation.py`, `migration.py`, `bootstrap.py`, `init_project.py`).

6. **Ripgrep (`_search_ripgrep` in `wiki.py`, line 592) Exclusion Globs:**
   - `_search_ripgrep` passes `-g "!_raw/**"`, which does not exclude `.locks/**`, and converts paths via `str(rel)` instead of `rel.as_posix()`.

7. **`handoff.py` (`purge_handoffs`) and `test_handoff.py` Legacy Lock Coupling:**
   - When `purge_handoffs(wiki_root, apply=True)` deletes all handoff files in `handoffs/`, it must also delete any corresponding `handoffs__*.lock` files inside `.brain-79/.locks/` so stale handoff locks do not accumulate.

8. **NTFS Atomic Replace & Cross-Device (`/tmp` vs `/home`) Safety:**
   - On Windows NTFS, `tmp_path.replace(target)` can raise `PermissionError` (`WinError 5` / `WinError 32`) if an external indexer (Defender, VS Code, Obsidian) briefly holds a read handle on `target`.
   - Note that in `wiki.py` (`write_article`), `navigation.py` (`_save_registry_unlocked` and `regenerate_index_navigation`), `migration.py` (`migrate_wiki`), and `bootstrap.py` (`_save_state`), `tmp_path.replace(...)` is called in **5 distinct places**. All 5 must use the centralized `atomic_replace_with_retry(tmp_path, target)` helper!

9. **Pre-Commit Hook PATH & Non-Interactive Shell Resolution:**
   - `PRE_COMMIT_HOOK_SCRIPT` in `init_project.py` invokes bare `brain79` and is written without `newline="\n"`. On Windows, writing a `#!/usr/bin/env sh` script with `\r\n` causes `/usr/bin/env: 'sh\r': No such file or directory` in Git for Windows! `hook_path.write_text(..., newline="\n")` is mandatory.

---

## Architecture and design (4 pillars)

### Pillar 1: Centralized lock manager (`src/brain79/core/locks.py`)
Create a dedicated module `src/brain79/core/locks.py` as the single authority for all interprocess locks and cross-platform path/file helpers:

- **Lock Directory:** `.brain-79/.locks/` (added to `_EXCLUDED_DIRS = {"_raw", ".locks"}` in both `wiki.py` and `lint.py`, and ignored via `.locks/` in `.brain-79/.gitignore`).
- **Deterministic Lock Naming (`get_lock_path(wiki_root: Path, rel_posix_path: str) -> Path`):**
  Normalize `rel_posix_path = rel_posix_path.replace("\\", "/").strip("/")` and map into `.brain-79/.locks/`:
  - `.navigation_registry.json` $\rightarrow$ `.brain-79/.locks/_registry.lock`
  - `.bootstrap_state.json` $\rightarrow$ `.brain-79/.locks/_bootstrap.lock`
  - Any article or root file (replace `/` with `__`):
    - `decisions/adr-001.md` $\rightarrow$ `.brain-79/.locks/decisions__adr-001.md.lock`
    - `INDEX.md` $\rightarrow$ `.brain-79/.locks/INDEX.md.lock`
- **Unified Helper Functions in `locks.py`:**
  1. `rel_posix(path: Path, root: Path) -> str`: Returns `path.relative_to(root).as_posix()`.
  2. `normalize_posix_input(raw_path: str) -> str`: Converts `\\` to `/` and strips leading/trailing whitespace.
  3. `has_exact_case_path(root: Path, rel_posix_path: str) -> bool`: Verifies segment-by-segment via `os.listdir(current_dir)` that every directory and filename in `rel_posix_path` matches the exact character casing on disk (catching Linux `ext4` case errors even when running on macOS `APFS` or Windows `NTFS`).
  4. `get_lock_path(wiki_root: Path, rel_posix_path: str) -> Path`: Ensures `.brain-79/.locks/` exists (`mkdir(parents=True, exist_ok=True)`) and returns the canonical lock `Path`.
  5. `acquire_wiki_lock(wiki_root: Path, rel_posix_path: str, timeout: float = 10.0) -> filelock.FileLock`: Returns `filelock.FileLock(str(get_lock_path(wiki_root, rel_posix_path)), timeout=timeout)`.
  6. `atomic_replace_with_retry(tmp_path: Path, target: Path, retries: int = 3, delay: float = 0.02) -> None`: Calls `tmp_path.replace(target)` with a bounded retry loop on `PermissionError` (`time.sleep(delay * (attempt + 1))`), cleaning up `tmp_path` on unrecoverable failure.
  7. `cleanup_legacy_inline_locks(wiki_root: Path) -> int`: Scans `.brain-79/` (excluding `.locks/`) and removes any leftover `*.lock` files from older versions. Called automatically during `brain79 migrate --apply`, `brain79 navigate --regenerate`, and `brain79 init`.

### Pillar 2: Universal POSIX path, case-sensitivity and line-ending normalization
1. **Strict Case-Sensitive Link & Path Resolution (Linux `ext4` Parity on macOS):**
   - In `lint.py` (line 210):
     - If `norm_rel in existing_rel_files`, it is valid.
     - If `norm_rel.endswith(".md")` and `norm_rel not in existing_rel_files`, **immediately record `broken_links.append((rel_path, raw_target))` and `continue`** (never fall back to `target_abs.is_file()`, which is case-insensitive on macOS/Windows).
     - For non-`.md` targets, verify `target_abs.is_file() and has_exact_case_path(wiki_root, target_rel.as_posix())`.
   - In `wiki.py` (`_run_inline_checks`, line 420):
     - Check `if not target_file.is_file() or not has_exact_case_path(wiki_root, target_rel.as_posix()):` so `write_article` inline checks also flag case-mismatched local links on macOS!
   - In `drift.py` (`find_matching_workspace_files`, line 129):
     - Verify `has_exact_case_path(p_root, target.relative_to(p_root).as_posix())` on direct file/directory checks, and wrap `target.rglob("*")` and `p_root.glob(pat)` in `sorted(...)`.
2. **Canonical Relative Path Helper (`rel_posix` / `.as_posix()`):**
   - Replace every `str(p.relative_to(root))` and `f"{rel}"` across `wiki.py`, `lint.py`, `lint_organizational.py`, `drift.py`, `context.py`, `orient.py`, `session_commit.py`, `bootstrap.py`, `migration.py`, and `handoff.py` with `.relative_to(root).as_posix()`.
   - Normalize user-supplied `path` / `paths` arguments via `normalize_posix_input` at the entry boundary of `_safe_resolve` (`wiki.py`), `orient` (`orient.py`), `context` (`context.py`), and `drift` (`drift.py`).
3. **Strict LF (`\n`) Normalization on I/O Boundaries:**
   - When reading files in `read_article`, `edit_article`, `session_commit` (pre-flight disk read), `lint_wiki`, `parse_frontmatter`, and `navigation.py`, normalize `.replace("\r\n", "\n")`.
   - When writing files (`write_text`) in `wiki.py`, `navigation.py`, `migration.py`, `bootstrap.py`, and `init_project.py` (including `PRE_COMMIT_HOOK_SCRIPT`), **always pass `newline="\n"`**.

### Pillar 3: Resilient atomic replace and cross-platform pre-commit hook
1. **Use `atomic_replace_with_retry` Across All 5 Atomic Write Sites:**
   - `src/brain79/core/wiki.py` (`write_article`)
   - `src/brain79/core/navigation.py` (`_save_registry_unlocked` and `regenerate_index_navigation`)
   - `src/brain79/core/migration.py` (`migrate_wiki`)
   - `src/brain79/core/bootstrap.py` (`_save_state`)
2. **Cross-Platform Pre-Commit Hook (`init_project.py`):**
   - Write `.git/hooks/pre-commit` with `newline="\n"` so Git for Windows `sh.exe` never fails with `\r` errors.
   - Enhance `PRE_COMMIT_HOOK_SCRIPT` so it augments `PATH` with `$XDG_BIN_HOME`, `$HOME/.local/bin`, `$HOME/.cargo/bin`, and `$USERPROFILE/.local/bin` before resolving `brain79`.

### Pillar 4: How to test without CI (local cross-platform simulation suite)
Because there is no remote CI pipeline required in this workflow, we test Windows and Linux behaviors **deterministically on macOS** in `tests/test_cross_platform_and_locks.py` using 5 simulation techniques:
1. **Linux Case-Sensitivity Simulation on macOS APFS:** Create `decisions/adr-001.md` and an article linking to `decisions/ADR-001.md` (uppercase). Assert that **both** `lint_wiki()` AND `write_article()` inline health checks detect the case-mismatched link as broken even when running on a case-insensitive macOS filesystem, and that `drift.py` rejects mis-cased `applies_to` bindings.
2. **Linux `ext4` Inode Order Simulation:** Monkeypatch or shuffle directory iteration results in tests to verify `list_articles`, `lint`, `orient`, `drift`, and `context` produce 100% deterministic ordering regardless of OS filesystem indexing.
3. **CRLF Injection Tests (`read`, `edit`, `session_commit`, `lint`, `write`, `init`):** Write raw bytes containing `b"\r\n"` to `.brain-79/` files and verify `read_article`, `edit_article`, `commit_session` (editing a CRLF file on disk), `parse_frontmatter`, `lint_wiki`, and `write_article` process them cleanly and emit pure `\n` (`b"\r\n" not in target.read_bytes()`), including `.git/hooks/pre-commit`.
4. **Windows Backslash Input Tests:** Pass Windows-style paths (`"decisions\\adr-001.md"`, `paths=["src\\brain79\\server.py"]`) into `read_article`, `write_article`, `edit_article`, `commit_session`, `orient`, `get_context`, and `check_article_drift`, verifying they resolve identically to POSIX paths and store `"decisions/adr-001.md"` (with forward slashes) in `.navigation_registry.json`.
5. **NTFS `PermissionError` Retry & Zero Inline `.lock` Invariants:** Mock `Path.replace` to raise `PermissionError` on the first 2 attempts and succeed on the 3rd across `write_article` and `navigation.py`, and assert after a full session lifecycle (`init`, `write`, `edit`, `navigate`, `lint`, `bootstrap`, `handoff`) that **zero** `*.lock` files exist outside `.brain-79/.locks/`.

---

## Implementation checklist (developer agent)

1. **Create `src/brain79/core/locks.py`:** Implement `rel_posix`, `normalize_posix_input`, `has_exact_case_path`, `get_lock_path`, `acquire_wiki_lock`, `atomic_replace_with_retry`, and `cleanup_legacy_inline_locks`.
2. **Refactor All Lock Consumers & Atomic Writes:**
   - Update `wiki.py`, `navigation.py`, `lint.py`, `bootstrap.py`, `migration.py`, and `handoff.py` (`purge_handoffs`) to use `locks.py`.
   - Add `".locks"` to `_EXCLUDED_DIRS` in `wiki.py` and `lint.py`, add `-g "!.locks/**"` in `_search_ripgrep`, and add `.locks/` to `.brain-79/.gitignore` in `init_project.py`.
3. **Normalize Paths, Case-Sensitivity & Line Endings Across All 12 Core Modules:**
   - Replace all `str(x.relative_to(y))` with `.as_posix()`.
   - Normalize `\\` in `_safe_resolve`, `orient`, `context`, and `drift`.
   - Enforce `has_exact_case_path` in `lint.py`, `wiki.py` (`_run_inline_checks`), and `drift.py`.
   - Normalize `\r\n` $\rightarrow$ `\n` on reads (including `edit_article` and `session_commit.py`) and pass `newline="\n"` on all `write_text` calls.
4. **Harden Pre-Commit Hook:** Update `PRE_COMMIT_HOOK_SCRIPT` in `init_project.py` to include `~/.local/bin` in `PATH` and write with `newline="\n"`.
5. **Purge Existing `.lock` Clutter in Repo:** Run `cleanup_legacy_inline_locks` on the repository's own `.brain-79/` directory so all legacy `.md.lock` files are removed.
6. **Tests & Documentation:**
   - Update existing lock tests in `tests/test_wiki.py` (lines 122, 142), `tests/test_lint.py` (line 254), and `tests/test_handoff.py` (line 395) to use `get_lock_path(wiki_root, ...)`.
   - Create `tests/test_cross_platform_and_locks.py` covering all 5 simulation pillars.
   - Record `decisions/adr-014-centralized-locks-and-cross-platform-io.md` and update `features/cross-platform-and-lock-isolation.md` to `status: shipped` and `architecture/roadmap-industrial-scale.md` Phase 6 to `[x]`.

---

[← Volver al Índice](../INDEX.md)
