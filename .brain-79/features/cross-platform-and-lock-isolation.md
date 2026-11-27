---
type: feature
summary: centralized .locks/ directory isolation, _drift_lock.lock hierarchy, POSIX path and CRLF normalization, cross-platform Git hooks, and local Windows/Linux simulation tests
status: shipped
version: 0.18.0
applies_to:
  - src/brain79/core/locks.py
  - src/brain79/config.py
related:
  - architecture/roadmap-industrial-scale.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-023-external-drift-lockfile.md
last_updated: 2026-11-27
---

# Feature — Cross-platform portability and centralized lock isolation

## Overview

The Cross-Platform Portability and Centralized Lock Isolation system eliminates adjacent `.md.lock` visual clutter, isolates concurrency mutexes into `.brain-79/.locks/`, normalizes paths and line endings across operating systems, and enforces case-sensitivity consistency between macOS APFS, Windows NTFS, and Linux ext4.

## Subsystem architecture (4 pillars)

### 1. Centralized lock manager (`src/brain79/core/locks.py`)
All inter-process file locks are isolated in `.brain-79/.locks/` (excluded from git tracking and wiki searches):
- **Singleton registry lock**: `.brain-79/.locks/_registry.lock` guards `.navigation_registry.json`.
- **Bootstrap state lock**: `.brain-79/.locks/_bootstrap.lock` guards `.bootstrap_state.json`.
- **Drift lockfile mutex**: `.brain-79/.locks/_drift_lock.lock` (`get_lock_path(wiki_root, "drift.lock")`) guards `.brain-79/drift.lock` writes via atomic temporary-file replacement (`create_temp_path` + `atomic_replace_with_retry`).
- **Legacy manifest lock**: `.brain-79/.locks/_drift_manifest.lock` guards `.drift_manifest.json` for backward-compatible legacy callers.
- **Transaction commit lock**: `.brain-79/.locks/_transaction.lock` guards multi-file writes and session commits.
- **Article content locks**: mapped deterministically by replacing `/` with `__` (e.g. `features/cli.md` -> `.brain-79/.locks/features__cli.md.lock`).
- **Global lock hierarchy (`LOCK_HIERARCHY` / `OrderedFileLock`)**: enforces strict acquisition order `_transaction.lock` -> `_registry.lock` -> `_drift_lock.lock` -> `_drift_manifest.lock` -> `INDEX.md.lock` per thread, raising `RuntimeError` on reverse-order acquisition.
- **Legacy inline lock cleanup (`cleanup_legacy_inline_locks`)**: purges stray legacy `*.lock` files outside `.brain-79/.locks/` while explicitly preserving top-level `wiki_root / "drift.lock"`.
- **Transaction-scoped temp tracking (`transaction_temp_scope`, `create_temp_path`, `register_tx_temp_file`)**: tracks transaction-owned `.tmp` files via `ContextVar` for scoped rollback cleanup without touching unrelated worker files.

### 2. Universal POSIX path, case-sensitivity, and line-ending normalization
- **Case-sensitive path verification (`has_exact_case_path`)**: walks directory segments against `os.listdir()` to enforce exact character casing on macOS and Windows, preventing links that would break on case-sensitive Linux filesystems.
- **Canonical POSIX serialization (`rel_posix`)**: converts all filesystem paths to forward-slash POSIX strings (`.as_posix()`), preventing Windows backslash corruption in registries, lockfiles, and manifests.
- **Strict LF (`\n`) normalization**: strips Windows CRLF (`\r\n`) on input reads and guarantees pure `\n` line endings on all write operations.

### 3. Resilient atomic replace and cross-platform pre-commit hook
- **NTFS retry resilience (`atomic_replace_with_retry`)**: executes atomic file replacement with exponential backoff retries when external indexers hold temporary locks.
- **Portable pre-commit hook**: installs POSIX-compliant `.git/hooks/pre-commit` scripts with LF line endings and comprehensive `$PATH` discovery for non-interactive Git GUI environments.

### 4. Local cross-platform simulation suite (`tests/test_cross_platform_and_locks.py`)
Deterministic unit tests simulate foreign OS behaviors without requiring remote CI runners:
- **Case-sensitivity simulation**: verifies that casing mismatches are rejected on case-insensitive filesystems.
- **CRLF injection simulation**: verifies that Windows CRLF byte sequences are stripped cleanly without corrupting content hashes.
- **PermissionError simulation**: verifies that atomic file replacements recover from transient filesystem contention.

---

[← Back to Index](../INDEX.md)
