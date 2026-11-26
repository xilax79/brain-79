---
spec_id: SPEC-018
title: External drift lockfile and hash-free Markdown frontmatter
target_version: 0.19.0
status: approved
owner: xilax79
last_updated: 2026-11-26
related_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - features/transitive-drift-and-ripple-guards.md
  - features/team-collaboration-and-onboarding.md
  - features/cross-platform-and-lock-isolation.md
  - features/lifecycle-hooks-and-ci-gate.md
  - features/polyglot-ast-guards-and-stats.md
  - features/handoff-continuity.md
target_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - features/transitive-drift-and-ripple-guards.md
  - features/team-collaboration-and-onboarding.md
  - features/cross-platform-and-lock-isolation.md
  - features/lifecycle-hooks-and-ci-gate.md
  - features/polyglot-ast-guards-and-stats.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - changelog/v0-19-0.md
---

# SPEC-018 — External drift lockfile and hash-free Markdown frontmatter

## Problem statement and goal

Currently, `brain-79` stamps `applies_to_digest` and `applies_to_count` directly into the YAML frontmatter of every active governing Markdown article while storing per-file leaf hashes inside a git-ignored local cache (`.brain-79/.drift_manifest.json`). This creates two structural drawbacks for engineering teams:

1. **Hash-only commit noise and PR friction on living manuals**: when a developer performs an internal refactor or private bugfix in governed source code, `verified_articles` (validated by AST Guard C) must re-stamp `applies_to_digest` inside the governing `.md` file, polluting `git log`, `git blame`, and PR diffs with hash-only edits and increasing frontmatter merge conflicts across parallel branches.
2. **Degraded CI drift attribution on fresh clones**: because `.drift_manifest.json` is git-ignored, `brain79 ci-check` on a fresh CI runner cannot hydrate leaf `targets` for any article whose master digest changed (zero-masking invariant), forcing fallback to coarse master-digest messages instead of exact per-file `modified`/`deleted`/`added` attribution.

The goal of Phase 18 is to move all drift digest state out of Markdown frontmatter into a single deterministic, Git-tracked lockfile (`.brain-79/drift.lock`) protected by a 3-way Git merge driver (`brain79 merge-drift-lock`), eliminating hash-only diffs on `.md` articles while preserving Guard C AST baseline integrity, Hard Session Ripple Gate enforcement, read-only zero-mutation guarantees, and exact per-file drift attribution on fresh clones and in CI.

## Non-goals (out of scope)

- **No semantic / AST-only hashing in this phase**: `.brain-79/drift.lock` continues to hash normalized file bytes (CRLF/BOM-invariant SHA-256) so internal business-logic changes remain 100% detectable without loss of recall.
- **No changes to the 9-tool MCP surface**: `MCP_TOOLS` remains exactly 9 tools per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md); `merge-drift-lock` is an administrative CLI-only subcommand (mirroring `merge-index`).
- **No removal of `applies_to:` from Markdown frontmatter**: `applies_to:` remains a human-authored governance declaration in article frontmatter; only machine-generated digest state (`applies_to_digest`, `applies_to_count`) moves to `.brain-79/drift.lock`.
- **No mandatory breaking migration on read**: existing repositories with legacy `applies_to_digest` in frontmatter and no `.brain-79/drift.lock` MUST continue to work read-only via dual-read fallback until explicitly migrated or updated.
- **No changes to `.brain-79/.navigation_registry.json` git-ignore policy**: derived navigation cache stays git-ignored.

## Dependencies

- **Internal seams**:
  - `src/brain79/core/drift.py` (`WorkspaceIndex`, `compute_applies_to_manifest`, `check_article_drift`, `detect_all_drift`, `VOLATILE_FRONTMATTER_FIELDS`).
  - `src/brain79/core/ast_guards/orchestrator.py` and `src/brain79/core/ast_guards/python_inspector.py` (Guard C baseline commit resolution).
  - `src/brain79/core/locks.py` (`LOCK_HIERARCHY`, `get_lock_path`, `acquire_wiki_lock`, `OrderedFileLock`, `atomic_replace_with_retry`).
  - `src/brain79/core/session_commit.py` (Pass 2b/2c/2d ripple gate and Pass 3 rollback) and `src/brain79/core/wiki.py` (`write_article`, `write_many_articles`, `edit_article`).
  - `src/brain79/core/navigation.py` (`regenerate_index_navigation`, `merge_index_files`), `src/brain79/core/ci_check.py`, `src/brain79/core/handoff_freshness.py`, `src/brain79/core/stats.py`, and `src/brain79/core/frontmatter.py`.
  - `src/brain79/core/init_project.py` (`.gitignore` negation, `.gitattributes`, and Git merge driver setup), `src/brain79/core/doctor.py`, `src/brain79/core/migration.py`, and `src/brain79/core/update.py`.
  - `src/brain79/cli/dispatch.py` (`WHITELIST` expansion from 26 to 27 commands for `merge-drift-lock`, and `ci-check` exit code ordering).
- **External / optional**: none (zero new dependencies).

## Constraints and invariants

All requirements must preserve the repository's canonical invariants:

- **Versioning**: pre-GA minor versioning per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md).
- **Concurrency and cross-platform I/O**: centralized lock hierarchy (`_transaction.lock -> _registry.lock -> _drift_lock.lock -> INDEX.md.lock`) and atomic LF writes per [ADR-014](../.brain-79/decisions/adr-014-centralized-locks-and-cross-platform-io.md).
- **CLI and MCP symmetry**: `MCP_TOOLS ⊂ WHITELIST` (`9 ⊂ 27`) per [ADR-001](../.brain-79/decisions/adr-001-hybrid-cli.md), [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md), and [symmetry.md](../.brain-79/architecture/symmetry.md).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Documentation style**: sentence case and living manual rules per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **Zero-masking drift invariant**: no automatic rebuild, merge-driver resolution, or migration may ever stamp a new digest onto an article whose underlying governed files have drifted without explicit write/edit or Guard-C-verified `verified_articles` approval.
- **Read-only zero-mutation invariant**: read-only commands (`orient`, `stats`, `ci-check`, `lint`) MUST perform zero disk mutations (never creating `.brain-79/drift.lock` or `.brain-79/.locks/_drift_lock.lock` on read).
- **Deterministic serialization**: `.brain-79/drift.lock` MUST be formatted deterministically (UTF-8, LF-only, sorted article keys, sorted target keys, 2-space indentation, trailing newline) so identical states always produce byte-identical files across macOS, Linux, and Windows.

## Open questions

All open questions MUST be resolved (`[x]`) before the `owner` transitions this specification from `draft` to `approved`. Agents MUST NOT implement a `draft` specification.

- [x] **Q-1**: Should `.brain-79/drift.lock` store the full per-file leaf `targets` map (`{"digest", "count", "targets": {"src/a.py": "sha256:..."}}`) per article — replacing `.drift_manifest.json` as primary storage and restoring exact per-file attribution in CI on fresh clones — while retaining `.drift_manifest.json` strictly as read-only fallback for un-migrated legacy wikis? **Decision (`xilax79`)**: yes.
- [x] **Q-2**: When `brain79 merge-drift-lock` encounters a true same-article conflict (`ours[k] != base[k]`, `theirs[k] != base[k]`, and `ours[k] != theirs[k]`):
  - If `base[k]` existed (modify/modify or delete/modify conflict): revert `k` to `base[k]` (or prune if `wiki_root / k` does not exist when `--wiki-root` is provided) and exit `0` so real drift surfaces cleanly on the next `ci-check` / `session_commit`.
  - If `base[k]` did NOT exist (conflicting add/add of the same article key `k`): write a deterministic conflict sentinel entry (`{"digest": "sha256:0000000000000000", "count": 0, "targets": {}, "conflict": true}`) and exit `0` so `check_article_drift` ALWAYS reports explicit merge-conflict drift (NEVER omitting `k` and NEVER falling back to `last_updated`).
  **Decision (`xilax79`)**: Option B+sentinel.
- [x] **Q-3**: Should `brain79 lint` emit an `INFO`-level advisory pointing to `brain79 migrate --apply` when `.brain-79/drift.lock` exists alongside `.md` articles still containing legacy `applies_to_digest` / `applies_to_count` keys (never failing `lint --strict`, `lint --fail-on-warnings`, or `ci-check`)? **Decision (`xilax79`)**: yes.
- [x] **Q-4**: Should `brain79 update-project` and `brain79 doctor --fix` (which already invoke `migrate_wiki(dry_run=False)`) migrate legacy frontmatter digests into `.brain-79/drift.lock` automatically, or require explicit `brain79 migrate --apply`? **Decision (`xilax79`)**: trigger automatically via `migrate_wiki(dry_run=False)` in `update-project` / `doctor --fix` and explicitly via `brain79 migrate --apply`.

## Requirements (EARS)

### Capability 1 — Deterministic `.brain-79/drift.lock` schema, locking, and fail-closed validation

- **R-1.1**: THE drift storage subsystem (`src/brain79/core/drift.py`) SHALL persist versioned drift state in `.brain-79/drift.lock` using a deterministic JSON schema:
  - Top-level object: `{"version": "2.0", "articles": { ... }}`.
  - Each article entry keyed by normalized relative wiki POSIX path (`<rel_wiki_posix>`): `{"digest": "sha256:<16-hex>", "count": <int >= 0>, "targets": {"<project_rel_posix>": "sha256:<16-hex>"}, ...}` with optional boolean `"conflict": true` (used exclusively by `merge-drift-lock` add/add conflict sentinels). Schema validation SHALL permit `"targets": {}` even when `"count" >= 0` (required for migrated drifted articles without legacy `.drift_manifest.json`).
  - Serialized with UTF-8 encoding, LF line endings, `indent=2`, `sort_keys=True`, and a single trailing newline.
  - `.brain-79/drift.lock` SHALL be created or written ONLY when `articles` is non-empty OR `.brain-79/drift.lock` already exists on disk (pure handoff/topic sessions with zero governed articles MUST NOT emit an empty `drift.lock`).
- **R-1.2**: THE lock subsystem (`src/brain79/core/locks.py`) SHALL register `_drift_lock.lock` in `LOCK_HIERARCHY` between `_registry.lock` and `INDEX.md.lock` (`_transaction.lock -> _registry.lock -> _drift_lock.lock -> INDEX.md.lock`), map `get_lock_path(wiki_root, "drift.lock")` to `.brain-79/.locks/_drift_lock.lock`, and guard all `.brain-79/drift.lock` read-modify-write mutations via `_drift_lock.lock` with atomic temporary-file replacement (`atomic_replace_with_retry`).
- **R-1.3**: WHEN any active wiki article is deleted on disk (e.g., via `rm` / `git rm`), archived, transitioned to `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES`, or has its `applies_to` removed, ALL mutation and sync paths (`commit_session`, `write_article`, `write_many_articles`, `regenerate_index_navigation`, and `migrate_wiki`) SHALL prune its stale entry from `.brain-79/drift.lock` and Pass 2b of `commit_session` SHALL NEVER insert inactive or pre-implementation articles into `drift.lock`.
- **R-1.4**: IF `.brain-79/drift.lock` exists on disk and is corrupted (unparseable JSON, invalid `version`, non-dict `articles`, or malformed entry schema), THEN `brain79 ci-check`, `brain79 lint`, `brain79_session_commit`, `write_article`, and `regenerate_index_navigation` SHALL fail closed with `ValidationError(rule="corrupt_drift_lock")` (CLI Exit `1`) without overwriting the file or silently masking drift. `dispatch.py` `ci-check` SHALL catch `ValidationError` and `json.JSONDecodeError` before `ValueError` so corrupt lockfiles return Exit `1` rather than Exit `2`.

### Capability 2 — Hash-free Markdown writes, zero-diff `verified_articles`, Guard C baseline integrity, and ripple parity

- **R-2.1**: WHEN `commit_session`, `write_article`, `edit_article`, or `write_many_articles` persists an article, THE write engine SHALL strip any legacy `applies_to_digest` and `applies_to_count` keys from the article's YAML frontmatter (even when `force_validation_skip=True` or `applies_to` is removed) and—for active governing articles—record its computed digest, count, and leaf `targets` in `.brain-79/drift.lock`. Standalone `write_article()` SHALL perform an atomic locked read-modify-write under `_drift_lock.lock` coordinated with the `.md` write so concurrent calls cannot clobber entries and `.md` write failures cannot leave `drift.lock` diverged.
- **R-2.2**: WHEN `brain79_session_commit` processes `verified_articles` (after passing Guard A structural checks, Guard B umbrella checks, and Guard C AST public-signature checks), THE transaction engine SHALL update ONLY `.brain-79/drift.lock` for those verified articles and SHALL NOT modify the corresponding `.md` article files on disk (`git diff` on those `.md` files MUST be empty).
- **R-2.3**: WHEN `commit_session` rolls back on a Pass 3 write failure, THE rollback mechanism SHALL restore `.brain-79/drift.lock` atomically to its exact pre-transaction state (unlinking it if it did not exist pre-transaction) alongside all touched `.md` files.
- **R-2.4**: WHEN Guard C (`src/brain79/core/ast_guards/orchestrator.py` and `python_inspector.py`) resolves the baseline Git commit for an article `rel_wiki_path` to compare public API signatures, THE baseline resolver SHALL NOT rely solely on `git_last_commit_for_path(rel_wiki_path)` (which breaks after `migrate` strips digests from drifted `.md` files or after `balanced`-tier `verified_articles` updates only `drift.lock`):
  - It SHALL resolve the most recent commit where `.brain-79/drift.lock` added or modified `articles[rel_article].digest` OR where `rel_wiki_path` had a substantive (non-volatile-only) change (ignoring commits whose `.md` diff only stripped `VOLATILE_FRONTMATTER_FIELDS` without changing `drift.lock`'s `digest`).
  - When no `drift.lock` history exists for a legacy un-migrated article, it SHALL fall back to `git_last_commit_for_path(rel_wiki_path)`.
- **R-2.5**: WHEN `commit_session` executes Pass 2d (Hard Session Ripple Gate, `src/brain79/core/session_commit.py`), THE working-tree dirty check SHALL consider an article digest-tracked when `(art_path in lock_staging["articles"]) or bool(meta_art.get("applies_to_digest"))` so stripping frontmatter digests never disables `unresolved_session_ripple`.

### Capability 3 — Dual-read backward compatibility, metadata exclusion, and read-only zero-mutation

- **R-3.1**: WHEN `check_article_drift` or `detect_all_drift` evaluates an active article with `applies_to:`, THE drift detector SHALL resolve stored baseline state in strict precedence order:
  1. `.brain-79/drift.lock` entry for `rel_article`: if `"conflict": true` is present, emit an explicit `drift_kind: "conflict"` item immediately; if `targets` is non-empty, compute exact per-file `modified`/`deleted`/`added`/`missing` attribution (even on fresh Git clones and CI runners); if `targets` is empty (migrated drifted article without legacy manifest), compare `curr_digest != stored_digest` using count-based fallback attribution.
  2. Legacy frontmatter `applies_to_digest` (+ optional read-only `.drift_manifest.json` leaf cache) when the article has no entry in `.brain-79/drift.lock`.
  3. Legacy `last_updated` timestamp fallback when neither `drift.lock` nor frontmatter digest exists.
- **R-3.2**: WHEN `compute_wiki_article_digest` hashes an intra-wiki Markdown article governed by an umbrella article, THE digest calculation SHALL continue ignoring `VOLATILE_FRONTMATTER_FIELDS` (`applies_to_digest`, `applies_to_count`, `last_updated`) so stripping legacy frontmatter digests produces zero spurious transitive drift. `frontmatter.py` SHALL continue accepting legacy `applies_to_digest` and `applies_to_count` keys during read validation for dual-read compatibility.
- **R-3.3**: THE workspace and diagnostic layers SHALL exclude `.brain-79/drift.lock` from `WorkspaceIndex.all_paths` (`drift.py`), `ci_check._EPHEMERAL_WIKI_FILES` (`ci_check.py`), and `handoff_freshness._EXCLUDED_WIKI_FILES` (`handoff_freshness.py`) so `drift.lock` never triggers self-referential drift loops, false `impacted_articles`, or false handoff staleness; AND read-only operations (`orient`, `stats`, `ci-check`, `lint`) SHALL perform zero disk writes (neither `drift.lock` nor `.locks/_drift_lock.lock`).

### Capability 4 — 3-way Git merge driver (`brain79 merge-drift-lock`), `.gitignore` negation, and `doctor` checks

- **R-4.1**: THE CLI dispatcher (`src/brain79/cli/dispatch.py`) SHALL expose `brain79 merge-drift-lock <base> <ours> <theirs>` (expanding `WHITELIST` from 26 to 27 commands; `MCP_TOOLS` remains 9) implementing a deterministic 3-way per-article JSON merge over `.brain-79/drift.lock`:
  - A 0-byte or whitespace-only `<base>` file (Git `add/add` merge with no common ancestor) SHALL be treated as `{"version": "2.0", "articles": {}}`.
  - Empty `<ours>` or `<theirs>`, or non-empty invalid JSON / schema in any of `<base>`, `<ours>`, `<theirs>` SHALL fail closed with Exit `1` without modifying `<ours>`.
  - Entries modified on only one branch (`ours != base == theirs` or `theirs != base == ours`) SHALL take the modified branch's entry (or deletion if deleted on that branch).
  - Entries added on only one branch SHALL be included; entries identical on `ours` and `theirs` SHALL be kept as-is.
  - Entries with true same-article conflicts (`ours[k] != base[k]`, `theirs[k] != base[k]`, `ours[k] != theirs[k]`) SHALL obey `Q-2`: revert to `base[k]` when `k` existed in `base` (including delete-vs-modify, pruning only if `--wiki-root` confirms the `.md` file no longer exists on disk), or write the conflict sentinel `{"digest": "sha256:0000000000000000", "count": 0, "targets": {}, "conflict": true}` when `k` did not exist in `base` (NEVER omitting `k`).
  - The merged result SHALL be written atomically back to `<ours>` in deterministic LF JSON format (`Exit 0`).
- **R-4.2**: WHEN `brain79 init`, `brain79 update-project`, or `brain79 doctor --fix` configures Git integration (`src/brain79/core/init_project.py`), THE initializer SHALL:
  1. Append `"!drift.lock"` **after** `"*.lock"` in `DERIVED_STATE_GITIGNORE_ENTRIES` so `sync_wiki_gitignore()` ensures `.brain-79/drift.lock` is explicitly un-ignored by Git while retaining `.locks/` and legacy `.drift_manifest.json` ignored.
  2. Idempotently add `drift.lock merge=brain79-drift-lock` to `.brain-79/.gitattributes` and configure `merge.brain79-drift-lock.name` and `merge.brain79-drift-lock.driver` in `.git/config` alongside `brain79-index`.
- **R-4.3**: WHEN `brain79 doctor` runs diagnostics (`src/brain79/core/doctor.py`), THE doctor engine SHALL verify both `INDEX.md` and `drift.lock` merge driver entries in `.brain-79/.gitattributes` and `.git/config`, and SHALL verify via `git check-ignore` (with `.gitignore` rule-ordering fallback outside Git repos) that `.brain-79/drift.lock` is **not** git-ignored (while keeping `.navigation_registry.json` and legacy `.drift_manifest.json` git-ignored).

### Capability 5 — Zero-masking idempotent migration and `lint` advisory

- **R-5.1**: WHEN a user runs `brain79 migrate --apply` (or `brain79 update-project` / `brain79 doctor --fix` per `Q-4`) on an existing pre-Phase-18 wiki, THE migration engine (`src/brain79/core/migration.py`) SHALL:
  1. For each active article with frontmatter `applies_to_digest` NOT already present in `.brain-79/drift.lock`: compute current targets; ONLY if `curr_digest == stored_digest`, populate its full leaf `targets` in `.brain-79/drift.lock`; if `curr_digest != stored_digest` and legacy `.drift_manifest.json` has matching `digest == stored_digest`, copy those leaf `targets`; otherwise store `{"digest": stored_digest, "count": stored_count, "targets": {}}` (zero-masking invariant).
  2. For any article already present in `.brain-79/drift.lock`, preserve the existing `drift.lock` entry (never overwriting newer `drift.lock` state with stale frontmatter).
  3. For inactive or pre-implementation articles carrying legacy `applies_to_digest`/`applies_to_count`, strip those keys without inserting the article into `drift.lock`.
  4. For active articles carrying `applies_to:` without `applies_to_digest` and without a `drift.lock` entry, stamp current digests into `drift.lock` ONLY if `last_updated` timestamp comparison shows zero drift (zero-masking: do not mask pre-existing timestamp drift).
  5. Strip legacy `applies_to_digest` and `applies_to_count` from migrated `.md` frontmatter atomically, configure `!drift.lock` in `.brain-79/.gitignore`, and configure the `drift.lock` Git merge driver idempotently.
  6. Re-running `brain79 migrate --apply` on an already migrated wiki SHALL be a clean no-op (`0` files modified); `brain79 migrate` without `--apply` SHALL remain dry-run.
- **R-5.2**: WHEN `brain79 lint` inspects an active wiki where `.brain-79/drift.lock` exists and one or more `.md` articles still carry legacy `applies_to_digest` or `applies_to_count` frontmatter keys, THE linter SHALL report an `INFO`-level advisory pointing to `brain79 migrate --apply` (per `Q-3`, never failing `lint --strict`, `lint --fail-on-warnings`, or `ci-check`).

## Interface and error contract

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `brain79 merge-drift-lock <base> <ours> <theirs>` | Missing file argument or `FileNotFoundError` | Emit actionable error to stderr; leave `<ours>` untouched | Exit `2` |
| `brain79 merge-drift-lock <base> <ours> <theirs>` | `PermissionError` or `OSError` writing `<ours>` | Emit structured OS error; leave `<ours>` intact | Exit `3` |
| `brain79 merge-drift-lock <base> <ours> <theirs>` | 0-byte `<base>` (`add/add` merge) | Treat `<base>` as empty `drift.lock` (`version: "2.0", articles: {}`) and merge | Exit `0` |
| `brain79 merge-drift-lock <base> <ours> <theirs>` | Empty `<ours>`/`<theirs>` or invalid JSON/schema in any input | Fail closed without overwriting `<ours>` so Git aborts merge cleanly | Exit `1` |
| `.brain-79/drift.lock` load during `ci-check` / `lint` / `session_commit` / `write_article` | Corrupt JSON or invalid schema in tracked `drift.lock` | Fail closed with `ValidationError(rule="corrupt_drift_lock")`; zero silent overwrite | `ValidationError` / Exit `1` |
| `.brain-79/drift.lock` write | Lock timeout or OS error (`TimeoutError`/`PermissionError`/`OSError`) | Preserve pre-existing `drift.lock` atomically; roll back transaction | Exit `3` |
| `brain79 migrate --apply` on pre-Phase-18 wiki with active drift | Article has `curr_digest != stored_digest` or timestamp drift | Preserve stale baseline without masking drift; Guard C still catches breaking API changes | Exit `0` (drift remains visible) |

## Migration and rollout

- **Default behavior**:
  - New repositories initialized with `brain79 init` add `!drift.lock` to `.brain-79/.gitignore`, pre-configure `drift.lock merge=brain79-drift-lock` in `.brain-79/.gitattributes`, and create `.brain-79/drift.lock` on the first governing article write.
  - Existing repositories remain 100% readable without running `brain79 migrate --apply` via dual-read fallback (`R-3.1`); articles progressively shed frontmatter digests as they are updated, or all at once via `brain79 migrate --apply`.
- **Intentional existing test updates (disclosed upfront)**:
  - `WHITELIST` count (`26 -> 27`): `tests/test_symmetry.py`, `tests/test_phase14_ci_check_and_hooks.py`.
  - `LOCK_HIERARCHY` tuple (`_drift_lock.lock` slot): `tests/test_navigation.py`, `tests/test_transitive_drift_and_ripple.py`.
  - Legacy assertions expecting frontmatter `applies_to_digest` / `.drift_manifest.json` writes: `tests/test_transitive_drift_and_ripple.py`, `tests/test_phase12_derived_state.py`, `tests/test_session_commit.py`, `tests/test_phase14_ci_check_and_hooks.py`, `tests/test_phase15_stats.py`, `tests/test_chaos_and_fuzzing.py`, `tests/test_phase12_enforcement_tiers.py`.
- **Upgrade path**: run `brain79 update-project` or `brain79 migrate --apply` to extract digests into `.brain-79/drift.lock`, strip frontmatter digests, update `.gitignore` with `!drift.lock`, and register the `brain79-drift-lock` merge driver.
- **Rollback safety**: reverting to `v0.16.0`–`v0.18.0` keeps all `.md` articles readable; articles without frontmatter `applies_to_digest` gracefully fall back to `last_updated` timestamp drift checks on older binaries.

## Acceptance criteria (Given / When / Then)

### AC-1 — Deterministic `.brain-79/drift.lock` serialization, lock ordering, pruning, and corrupt fail-closed
- **Verifies**: `R-1.1`, `R-1.2`, `R-1.3`, `R-1.4`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: a software wiki with governed articles, a pure handoff-only commit (zero governed articles), an article archived/deleted on disk, and a separate corrupted `drift.lock` fixture.
- **When**: articles are written, archived, deleted via `rm` + `commit_session`/`regenerate_index_navigation`, and `ci-check`/`lint`/`session_commit` run against valid and corrupted `drift.lock`.
- **Then**: `.brain-79/drift.lock` is deterministic LF JSON (`version: "2.0"`, sorted keys, allowing `targets: {}` when `count >= 0`), is not created on pure non-governed commits, locks via `_drift_lock.lock` in `LOCK_HIERARCHY`, prunes deleted/inactive/unanchored articles, and fails closed with `ValidationError(rule="corrupt_drift_lock")` / CLI Exit `1` (including `ci-check`) on corrupt JSON.

### AC-2 — Hash-free writes, zero-diff `verified_articles`, Guard C baseline integrity, ripple gate, and rollback
- **Verifies**: `R-2.1`, `R-2.2`, `R-2.3`, `R-2.4`, `R-2.5`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: a Git repository with governed article `features/billing.md` and: (a) an internal non-API refactor in `src/billing.py`, (b) a dirty working-tree edit without `writes`/`verified_articles`, (c) a `balanced`-tier `verified_articles` commit followed by a `strict`-tier follow-up, (d) a `migrate --apply` commit on a drifted article with breaking API changes, (e) concurrent `write_article` calls, and (f) a simulated Pass 3 failure.
- **When**: `write_article` (including `force_validation_skip=True`) and `commit_session` run across scenarios (a)–(f).
- **Then**: `.md` files contain zero `applies_to_digest`/`applies_to_count`; `verified_articles` leaves `git diff .brain-79/features/billing.md` empty; Pass 2d ripple gate still triggers on dirty working-tree code; Guard C still blocks breaking API changes after `migrate` and does not re-flag already-verified `balanced` changes; concurrent `write_article` preserves both entries; Pass 3 rollback restores/unlinks `.brain-79/drift.lock` byte-for-byte.

### AC-3 — Exact per-file CI drift attribution on fresh clone, dual-read fallback, exclusion, and zero-mutation reads
- **Verifies**: `R-3.1`, `R-3.2`, `R-3.3`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: (a) a fresh clone with `.brain-79/drift.lock` committed and zero `.drift_manifest.json` where 1 of 3 governed files is modified and 1 is deleted, (b) a legacy pre-Phase-18 wiki with only frontmatter `applies_to_digest`, and (c) an article with `applies_to: [".brain-79/**"]` plus an active handoff.
- **When**: `brain79 ci-check --format json --enforcement strict`, `brain79 orient`, `brain79 stats`, and `brain79 lint --strict` run.
- **Then**: (a) reports exact per-file `modified` and `deleted` attribution; (b) detects drift via legacy frontmatter fallback; (c) `.brain-79/drift.lock` never appears in `WorkspaceIndex.all_paths`, `impacted_articles`, or handoff staleness; read-only commands create zero files under `.brain-79/` or `.brain-79/.locks/`.

### AC-4 — 3-way `brain79 merge-drift-lock` driver, `!drift.lock` `.gitignore` negation, and `doctor` verification
- **Verifies**: `R-4.1`, `R-4.2`, `R-4.3`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: Git merge scenarios covering (a) disjoint article edits (`features/a.md` vs `features/b.md`), (b) `add/add` with 0-byte `<base>` and disjoint vs same-key conflicting articles, (c) modify/modify and delete/modify conflicts on the same article key, (d) corrupt JSON / missing file / permission error, and (e) `brain79 init` + `brain79 doctor` + `brain79 doctor --fix`.
- **Then**: disjoint and 0-byte-`<base>` disjoint `add/add` auto-merge cleanly (`Exit 0`); same-key `add/add` writes the conflict sentinel (`"conflict": true`) detected by `check_article_drift` without `last_updated` masking; corrupt JSON exits `1`, missing file exits `2`, permission error exits `3`; `.brain-79/.gitignore` has `!drift.lock` after `*.lock` verified via `git check-ignore` in `doctor`; `WHITELIST` is 27 and `MCP_TOOLS` remains 9.

### AC-5 — Idempotent zero-masking migration (`--apply`) and `lint` legacy advisory
- **Verifies**: `R-5.1`, `R-5.2`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: a pre-Phase-18 wiki containing 1 clean governed article, 1 genuinely drifted governed article (with legacy `applies_to_digest`), 1 inactive article with legacy `applies_to_digest`, and 1 unhashed legacy article with timestamp drift.
- **When**: `brain79 migrate` (dry-run) runs, then `brain79 migrate --apply` runs twice, followed by `brain79 ci-check --enforcement strict` and `brain79 lint --strict`.
- **Then**: dry-run makes zero mutations; first `--apply` populates `.brain-79/drift.lock` (preserving stale baselines without masking either drifted article, omitting the inactive article), strips frontmatter digests, and configures `.gitignore`/merge driver; second `--apply` is a 0-file no-op; `lint --strict` emits `INFO` (exit `0`) when a legacy frontmatter digest remains alongside `drift.lock`.

## Wiki impact map

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/core/drift.py`, `src/brain79/core/session_commit.py`, `src/brain79/core/wiki.py`, `src/brain79/core/frontmatter.py` | `features/transitive-drift-and-ripple-guards.md` | `update` |
| `src/brain79/core/ast_guards/orchestrator.py`, `src/brain79/core/ast_guards/python_inspector.py` | `features/polyglot-ast-guards-and-stats.md` | `update` |
| `src/brain79/core/init_project.py`, `src/brain79/core/migration.py`, `src/brain79/core/navigation.py` | `features/team-collaboration-and-onboarding.md` | `update` |
| `src/brain79/core/locks.py` | `features/cross-platform-and-lock-isolation.md` | `update` |
| `src/brain79/core/ci_check.py`, `src/brain79/core/handoff_freshness.py` | `features/lifecycle-hooks-and-ci-gate.md` | `update` |
| `src/brain79/core/doctor.py`, `src/brain79/core/update.py` | `features/project-upgrade-and-multi-harness-doctor.md` | `update` |
| `src/brain79/cli/dispatch.py` | `architecture/dispatcher.md` | `update` |
| `src/brain79/cli/dispatch.py` | `architecture/symmetry.md` | `update` |
| `src/brain79/core/drift.py` (Phase 18 roadmap tracking) | `architecture/roadmap-industrial-scale.md` | `update` |
| `CHANGELOG.md` | `changelog/v0-19-0.md` | `create` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
uv run pytest
uv run mypy src tests
uv run brain79 lint --strict
uv run brain79 ci-check --enforcement strict
uv run brain79 doctor
```

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| — | — | No amendments recorded yet. | — |

## Wiki distillation checklist (post-implementation)

- [ ] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [ ] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [ ] Record any new architectural decision in `.brain-79/decisions/adr-XXX.md` (external `drift.lock` ADR).
- [ ] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-19-0.md`.
- [ ] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [ ] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
