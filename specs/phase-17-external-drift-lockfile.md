---
spec_id: SPEC-017
title: External drift lockfile and hash-free Markdown frontmatter
target_version: 0.18.0
status: approved
owner: xilax79
last_updated: 2026-11-27
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
  - features/project-upgrade-and-multi-harness-doctor.md
target_wiki:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - architecture/dispatcher.md
  - architecture/symmetry.md
  - features/transitive-drift-and-ripple-guards.md
  - features/team-collaboration-and-onboarding.md
  - features/cross-platform-and-lock-isolation.md
  - features/lifecycle-hooks-and-ci-gate.md
  - features/polyglot-ast-guards-and-stats.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - decisions/adr-023-external-drift-lockfile.md
  - changelog/v0-18-0.md
---

# SPEC-017 — External drift lockfile and hash-free Markdown frontmatter

## Problem statement and goal

Currently, `brain-79` stamps `applies_to_digest` and `applies_to_count` directly into the YAML frontmatter of every active governing Markdown article while storing per-file leaf hashes inside a git-ignored local cache (`.brain-79/.drift_manifest.json`). This creates two structural drawbacks for engineering teams:

1. **Hash-only commit noise and PR friction on living manuals**: when a developer performs an internal refactor or private bugfix in governed source code, `verified_articles` (validated by AST Guard C) must re-stamp `applies_to_digest` inside the governing `.md` file, polluting `git log`, `git blame`, and PR diffs with hash-only edits and increasing frontmatter merge conflicts across parallel branches.
2. **Degraded CI drift attribution on fresh clones**: because `.drift_manifest.json` is git-ignored, `brain79 ci-check` on a fresh CI runner cannot hydrate leaf `targets` for any article whose master digest changed (zero-masking invariant), forcing fallback to coarse master-digest messages instead of exact per-file `modified`/`deleted`/`added` attribution.

The goal of Phase 17 (prioritized ahead of PyPI distribution, now Phase 18) is to move all machine-managed drift digest state out of Markdown frontmatter into a single deterministic, Git-tracked lockfile (`.brain-79/drift.lock`) protected by a 3-way Git merge driver (`brain79 merge-drift-lock`). This eliminates hash-only diffs on `.md` articles while preserving Guard C AST baseline integrity, Hard Session Ripple Gate enforcement, read-only zero-mutation guarantees, backward-compatible dual-read for legacy wikis, and exact per-file drift attribution on fresh clones and in CI.

## Non-goals (out of scope)

- **No semantic / AST-only hashing in this phase**: `.brain-79/drift.lock` continues to hash normalized file bytes (CRLF/BOM-invariant SHA-256 via 64 KB byte-streaming) so internal business-logic changes remain 100% detectable without loss of recall.
- **No changes to the 9-tool MCP surface**: `MCP_TOOLS` remains exactly 9 tools per [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md); `merge-drift-lock` is an administrative CLI-only subcommand (mirroring `navigate --merge-driver`).
- **No removal of `applies_to:` from Markdown frontmatter**: `applies_to:` remains a human-authored governance declaration in article frontmatter; only machine-generated digest state (`applies_to_digest`, `applies_to_count`) moves to `.brain-79/drift.lock`.
- **No mandatory breaking migration on read**: existing repositories with legacy `applies_to_digest` in frontmatter and no `.brain-79/drift.lock` MUST continue to work read-only via dual-read fallback until explicitly migrated or updated.
- **No changes to `.brain-79/.navigation_registry.json` git-ignore policy**: derived navigation cache stays git-ignored and locally rebuilt on demand.
- **No PyPI publication automation in this phase**: automated PyPI Trusted Publishers release workflows are scheduled in Phase 18 (`v0.19.0`).

## Dependencies

- **Internal seams**:
  - `src/brain79/core/drift.py` (`WorkspaceIndex`, `compute_applies_to_manifest`, `compute_wiki_article_digest`, `check_article_drift`, `detect_all_drift`, `VOLATILE_FRONTMATTER_FIELDS`, `load_drift_manifest`).
  - `src/brain79/core/ast_guards/orchestrator.py` and `src/brain79/core/ast_guards/python_inspector.py` (Guard C baseline commit resolution).
  - `src/brain79/core/git_ops.py` (bounded history lookup and `git_check_ignore`).
  - `src/brain79/core/locks.py` (`LOCK_HIERARCHY`, `get_lock_path`, `acquire_wiki_lock`, `OrderedFileLock`, `atomic_replace_with_retry`, `cleanup_legacy_inline_locks`).
  - `src/brain79/core/session_commit.py` (Pass 1 stripping, Pass 2b/2c/2d ripple and conflict guards, Pass 3 rollback) and `src/brain79/core/wiki.py` (`write_article`, `write_many_articles`, `edit_article`).
  - `src/brain79/core/validation.py` (`validate_article_content`) and `src/brain79/core/frontmatter.py` (legacy read-tolerance).
  - `src/brain79/core/navigation.py` (`regenerate_index_navigation`), `src/brain79/core/ci_check.py` (`_EPHEMERAL_WIKI_FILES`, `run_ci_check`, `run_lifecycle_hook`), `src/brain79/core/handoff_freshness.py` (`_EXCLUDED_WIKI_FILES`), `src/brain79/core/orient.py`, `src/brain79/core/stats.py`, `src/brain79/core/lint_organizational.py`.
  - `src/brain79/core/init_project.py` (`DERIVED_STATE_GITIGNORE_ENTRIES`, `sync_wiki_gitignore`, `sync_git_merge_driver`, `PRE_COMMIT_HOOK_SCRIPT`, `update_project`), `src/brain79/core/doctor.py`, `src/brain79/core/migration.py`, `src/brain79/templates/SCHEMA.md`, `src/brain79/templates/SCHEMA_GENERAL.md`.
  - `src/brain79/cli/dispatch.py` (`WHITELIST` expansion from 26 to 27 commands for `merge-drift-lock`, and `ci-check` exception ordering).
  - `.github/workflows/ci.yml`, `tests/test_ci_workflow.py`, `tests/test_phase16_fixture_and_isolation.py`, and `tests/test_transitive_drift_and_ripple.py` (CI matrix reliability, polyglot test gating, hidden-dir artifact upload, and Windows SLA-1 cold-start latency).
- **External / optional**: none (zero new core dependencies).

## Constraints and invariants

All requirements must preserve the repository's canonical invariants:

- **Versioning**: pre-GA minor versioning per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md).
- **Concurrency and cross-platform I/O**: centralized lock hierarchy (`_transaction.lock -> _registry.lock -> _drift_lock.lock -> _drift_manifest.lock -> INDEX.md.lock`), POSIX forward-slash keys, and atomic LF writes per [ADR-014](../.brain-79/decisions/adr-014-centralized-locks-and-cross-platform-io.md).
- **CLI and MCP symmetry**: `MCP_TOOLS ⊂ WHITELIST` (`9 ⊂ 27`) per [ADR-001](../.brain-79/decisions/adr-001-hybrid-cli.md), [ADR-020](../.brain-79/decisions/adr-020-focused-mcp-surface-and-cli-superset.md), and [symmetry.md](../.brain-79/architecture/symmetry.md).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Passive lifecycle hook fail-open**: `--lifecycle-hook session-start|stop` MUST continue exiting `0` and returning `{}` on unexpected errors per [ADR-021](../.brain-79/decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md).
- **Documentation style**: sentence case and living manual rules per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **Zero-masking drift invariant**: no automatic rebuild, merge-driver resolution, `verified_articles` pass, or migration may ever stamp a new digest onto an article whose underlying governed files have drifted or carry an unresolved merge conflict without explicit write/edit or passing all applicable guards.
- **Read-only zero-mutation invariant**: read-only commands (`orient`, `stats`, `ci-check`, `lint`, `read`, `read-batch`, `context`, `list`, `search`, `migrate --dry-run`) MUST perform zero disk mutations under `.brain-79/` or `.brain-79/.locks/` (never creating `.brain-79/drift.lock`, `.drift_manifest.json`, `.locks/_drift_lock.lock`, or `.locks/_drift_manifest.lock`).
- **Deterministic serialization**: `.brain-79/drift.lock` MUST be formatted deterministically (UTF-8, LF-only, `indent=2`, `sort_keys=True`, single trailing newline) so identical logical states always produce byte-identical files across macOS, Linux, and Windows.

## Open questions

All open questions MUST be resolved (`[x]`) before the `owner` transitions this specification from `draft` to `approved`. Agents MUST NOT implement a `draft` specification.

- [x] **Q-1**: Should `.brain-79/drift.lock` store the full per-file leaf `targets` map (`{"digest", "count", "targets": {"src/a.py": "sha256:..."}}`) per article — replacing `.drift_manifest.json` as primary storage and restoring exact per-file attribution in CI on fresh clones — while retaining `.drift_manifest.json` strictly as read-only fallback for un-migrated legacy wikis? **Decision (`xilax79`)**: yes.
- [x] **Q-2**: When `brain79 merge-drift-lock` encounters a true same-article conflict (`ours[k] != base[k]`, `theirs[k] != base[k]`, and `ours[k] != theirs[k]`):
  - If `base[k]` existed (modify/modify or delete/modify conflict): revert `k` to `base[k]` (pruning `k` ONLY if `--wiki-root` is explicitly provided and `wiki_root / k` does not exist on disk) and exit `0` so real drift surfaces cleanly on the next `ci-check` / `session_commit`.
  - If `base[k]` did NOT exist (conflicting add/add of the same article key `k`): write a deterministic conflict sentinel entry (`{"conflict": true, "count": 0, "digest": "sha256:0000000000000000", "targets": {}}`) and exit `0` so `check_article_drift` ALWAYS reports explicit merge-conflict drift (NEVER omitting `k` and NEVER falling back to `last_updated`).
  **Decision (`xilax79`)**: Option B+sentinel.
- [x] **Q-3**: Should `brain79 lint` emit an `INFO`-level advisory pointing to `brain79 migrate --apply` when `.brain-79/drift.lock` exists alongside `.md` articles still containing legacy `applies_to_digest` / `applies_to_count` keys (never failing `lint --strict`, `lint --fail-on-warnings`, or `ci-check`)? **Decision (`xilax79`)**: yes.
- [x] **Q-4**: Should `brain79 update-project` and `brain79 doctor --fix` (which already invoke `migrate_wiki(dry_run=False)`) migrate legacy frontmatter digests into `.brain-79/drift.lock` automatically, or require explicit `brain79 migrate --apply`? **Decision (`xilax79`)**: trigger automatically via `migrate_wiki(dry_run=False)` in `update-project` / `doctor --fix` and explicitly via `brain79 migrate --apply`.

## Requirements (EARS)

### Capability 1 — Deterministic `.brain-79/drift.lock` schema, strict validation, locking, and pruning

- **R-1.1**: THE drift storage subsystem (`src/brain79/core/drift.py`) SHALL persist versioned drift state in `.brain-79/drift.lock` using a strict, deterministic JSON schema:
  - Top-level JSON object MUST contain exact keys `{"version", "articles"}` where `"version"` is the literal string `"2.0"` and `"articles"` is a JSON object mapping normalized wiki-relative POSIX article paths (`<rel_wiki_posix>`) to entry objects.
  - Each article key `<rel_wiki_posix>` MUST be a non-empty string with no backslashes (`\`), no leading `/`, no `.brain-79/` prefix, and no `..` path segments.
  - Each article entry MUST be a JSON object whose keys are a subset of `{"digest", "count", "targets", "conflict"}` containing:
    - `"digest"`: string matching `^sha256:[0-9a-f]{16}$`.
    - `"count"`: non-negative integer (`isinstance(v, int)` and not `bool`, `>= 0`).
    - `"targets"`: JSON object mapping non-empty normalized POSIX paths (no `\`, no leading `/`, no `..` segments) to strings matching `^sha256:[0-9a-f]{16}$`. Schema validation SHALL permit `"targets": {}` for any `"count" >= 0` (required for migrated drifted articles without legacy `.drift_manifest.json` and for conflict sentinels).
    - `"conflict"` (optional): MUST equal `True` (`v is True`) whenever present; `"conflict": false` or non-boolean values SHALL be rejected as `corrupt_drift_lock` (used exclusively by `merge-drift-lock` add/add conflict sentinels).
  - Serialized via `json.dumps(data, indent=2, sort_keys=True) + "\n"`, UTF-8 encoding, and pure LF line endings (`newline="\n"`).
  - `.brain-79/drift.lock` SHALL be created or written ONLY when `articles` is non-empty OR `.brain-79/drift.lock` already exists on disk (pure handoff/topic sessions with zero governed articles MUST NOT create an empty `drift.lock`).
- **R-1.2**: THE lock subsystem (`src/brain79/core/locks.py`) SHALL:
  - Register `_drift_lock.lock` in `LOCK_HIERARCHY` between `_registry.lock` and `_drift_manifest.lock` (`_transaction.lock -> _registry.lock -> _drift_lock.lock -> _drift_manifest.lock -> INDEX.md.lock`), preserving `_drift_manifest.lock` ordering for backward-compatible legacy callers.
  - Map `get_lock_path(wiki_root, "drift.lock")` to `.brain-79/.locks/_drift_lock.lock` (while retaining `.drift_manifest.json` -> `_drift_manifest.lock`).
  - Guard all `.brain-79/drift.lock` writes via `_drift_lock.lock` with atomic temporary-file replacement (`create_temp_path` + `atomic_replace_with_retry`).
  - Explicitly preserve top-level `wiki_root / "drift.lock"` inside `cleanup_legacy_inline_locks(wiki_root)` so cleanup NEVER deletes the tracked drift lockfile while continuing to purge stray legacy inline `*.lock` files outside `.brain-79/.locks/`.
- **R-1.3**: WHEN any active wiki article is deleted on disk (e.g., via `rm` / `git rm`), archived, transitioned to `INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES`, or has its `applies_to` removed or emptied, ALL mutation and sync paths (`commit_session`, `write_article` including `force_validation_skip=True`, `write_many_articles`, `regenerate_index_navigation`, and `migrate_wiki` including articles demoted to `legacy` by Paso B) SHALL prune its stale entry from `.brain-79/drift.lock` under `_drift_lock.lock` (without creating `drift.lock` if it does not exist), and NO write or migration path SHALL insert inactive or pre-implementation articles into `drift.lock`.
- **R-1.4**: IF `.brain-79/drift.lock` exists on disk and is corrupted (invalid UTF-8, unparseable JSON, duplicate JSON keys via `object_pairs_hook`, non-standard `NaN`/`Infinity` constants via `parse_constant`, invalid `version`, unknown top-level/entry keys, `"conflict": false`, or malformed entry schema), THEN `load_drift_lock`, `check_article_drift`, `detect_all_drift`, `brain79 ci-check`, `brain79 lint`, `brain79 orient`, `brain79 stats`, `brain79 migrate`, `brain79_session_commit` (including `allow_partial_ripple=True` and handoff-only commits via an unconditional Pass 2 `load_drift_lock` check), `write_article` (including `force_validation_skip=True`, `is_special`, and articles without `applies_to`), `write_many_articles`, and `regenerate_index_navigation` SHALL fail closed with `ValidationError(rule="corrupt_drift_lock")` (CLI Exit `1`) without overwriting the file or silently masking drift. `navigation.py` and its callers (`wiki.py`, `migration.py`, `session_commit.py`) MUST NOT swallow `ValidationError(rule="corrupt_drift_lock")`. `dispatch.py` `ci-check` SHALL catch `ValidationError` and `json.JSONDecodeError` before `ValueError` so corrupt lockfiles return Exit `1` rather than Exit `2`. Passive lifecycle hooks (`run_lifecycle_hook` via `--lifecycle-hook`) SHALL preserve ADR-021 fail-open behavior (returning `{}` and Exit `0`).

### Capability 2 — Hash-free Markdown writes, zero-diff `verified_articles`, conflict blocking, Guard C baseline integrity, and ripple parity

- **R-2.1**: WHEN `commit_session`, `write_article`, `edit_article`, or `write_many_articles` persists an article, THE write engine SHALL strip any legacy `applies_to_digest` and `applies_to_count` keys from the article's YAML frontmatter before writing `.md` to disk (including when `applies_to` is removed and when `force_validation_skip=True` on valid YAML frontmatter—explicitly handling frontmatter stripping prior to or alongside the `force_skip` early return in `validation.py` without crashing on intentionally malformed YAML under `force_validation_skip=True`) and—for active governing articles with non-empty computed targets—record its computed `digest`, `count`, and leaf `targets` in `.brain-79/drift.lock`.
  - Standalone `write_article()` (outside batch transactions) SHALL unconditionally validate existing `.brain-79/drift.lock` upfront (`R-1.4`), hold the article lock, write the `.md` atomically, and then execute a locked read-modify-write under `_drift_lock.lock` (updating the entry for active governing articles or pruning any stale entry when inactive, pre-implementation, `force_validation_skip=True`, or `applies_to` is absent/removed, so concurrent `write_article` calls on distinct articles cannot clobber each other); if the `drift.lock` update fails, `write_article()` SHALL atomically restore (or unlink) the `.md` file.
  - `write_many_articles()` SHALL snapshot pre-transaction `.brain-79/drift.lock` and atomically restore (or unlink) it alongside touched `.md` files if any write fails.
- **R-2.2**: WHEN `brain79_session_commit` processes `verified_articles`:
  - IF an article in `verified_articles` carries `drift_kind == "conflict"` (from a `merge-drift-lock` conflict sentinel), THEN Pass 2c SHALL reject verification with `ValidationError(rule="verified_article_conflict_forbidden")` under `strict` and `balanced` enforcement (and emit a downgraded warning under `advisory`), preventing agents from silently clearing merge conflicts without editing the article.
  - AFTER passing Guard A (structural), Guard B (umbrella), conflict guard, and Guard C (AST public signatures), THE transaction engine SHALL update ONLY `lock_staging["articles"][v_path]` (`.brain-79/drift.lock`) and SHALL NOT add `v_path` to `virtual_fs` or modify the corresponding `.md` article file on disk (`git diff` on those `.md` files MUST remain empty, even if the `.md` still contains legacy frontmatter digest keys prior to migration).
  - IF an article appears in both `writes`/`edits` AND `verified_articles` in the same `commit_session`, THE `writes`/`edits` update SHALL take precedence (hash-free `.md` written, `drift.lock` updated).
- **R-2.3**: WHEN `commit_session` rolls back on any Pass 3 failure (`BaseException`), THE rollback mechanism SHALL restore `.brain-79/drift.lock` atomically to its exact pre-transaction bytes (unlinking it if it did not exist pre-transaction) alongside all touched `.md` files, `.navigation_registry.json`, `INDEX.md`, raw session logs, and transaction-owned temp files.
- **R-2.4**: WHEN Guard C (`src/brain79/core/ast_guards/orchestrator.py` and `src/brain79/core/ast_guards/python_inspector.py`) resolves the baseline Git commit for an article `rel_article` to compare public API signatures, BOTH entry points (`has_public_api_changes` and `has_public_python_api_changes`) SHALL delegate to a single shared baseline resolver (`resolve_article_baseline_commit`) using bounded first-parent history walks (`max_commits = 50`, cached in `GitSessionCache`):
  - **Pass 1 (combined walk)**: inspect commits `C` newest-first via `git log -n 50 --first-parent --format=%H %P -- <wiki_rel>/drift.lock <wiki_rel>/<rel_article>`. For each commit `C`, resolve its true Git first parent `P` strictly from `%P` (`P = None` ONLY when `%P` is empty at a root commit or shallow boundary; NEVER infer `P` from `commits[i+1]`). Select `C` as the baseline commit if ANY of the following holds:
    1. **Substantive `.md` change**: `<rel_wiki_path>` exists at `C` and either did not exist at `P` (or `P is None`) OR `compute_wiki_article_digest(blob(C, rel_wiki_path)) != compute_wiki_article_digest(blob(P, rel_wiki_path))`.
    2. **Non-migration `drift.lock` digest change**: `C:drift.lock["articles"][rel_article]` exists, has `conflict != True`, and its `digest` differs from the previous effective digest at `P` (defined as `P:drift.lock["articles"][rel_article]["digest"]` when `P` exists and the entry is present and non-conflict, otherwise `P:article_frontmatter.get("applies_to_digest")` when `P` exists, else `None`). This explicitly skips pure `brain79 migrate --apply` commits that transfer an unchanged legacy digest from frontmatter into `drift.lock` while stripping only `VOLATILE_FRONTMATTER_FIELDS` from the `.md` file.
    3. **Legacy frontmatter digest update**: `rel_article` is absent from `C:drift.lock`, `C:article_frontmatter.get("applies_to_digest")` is non-empty, and differs from `P:article_frontmatter.get("applies_to_digest")` (or `P is None`).
  - **Pass 2 (article-only fallback walk)**: IF Pass 1 finds no qualifying commit (for example, when >50 unrelated commits to shared `drift.lock` pushed `rel_article`'s history past the 50-commit window), THE resolver SHALL run a second bounded walk exclusive to `<wiki_rel>/<rel_article>` (`git log -n 50 --first-parent --format=%H %P -- <wiki_rel>/<rel_article>`) applying Rules 1 and 3 (using `%P` so pure migration commits are still skipped) before falling back to the oldest commit reached in Pass 2 (if any), else the oldest commit reached in Pass 1 (if any), else `git_rev_parse_head()`.
  - Outside a Git repository (`NotAGitRepoError`), Guard C SHALL return `(False, "")`; on operational Git errors (`GitTimeoutError`, `GitError`, `OSError`), Guard C SHALL fail closed with `ValidationError(rule="ast_verification_failed")`.
- **R-2.5**: WHEN `commit_session` executes Pass 2d (Hard Session Ripple Gate, `src/brain79/core/session_commit.py`), THE working-tree dirty check SHALL consider an article digest-tracked when `(art_path in lock_staging["articles"]) or bool(meta_art.get("applies_to_digest"))` (and SHALL also flag any article carrying `drift_kind == "conflict"` that governs dirty working-tree code or touched intra-wiki articles) so stripping frontmatter digests never disables `unresolved_session_ripple`.

### Capability 3 — Dual-read backward compatibility, metadata exclusion, and read-only zero-mutation

- **R-3.1**: WHEN `check_article_drift` or `detect_all_drift` evaluates an active article with `applies_to:` (retaining backward-compatible `manifest_data` parameter and accepting optional `lock_data` parameter), THE drift detector SHALL resolve stored baseline state in strict precedence order:
  1. `.brain-79/drift.lock` entry for `rel_article`:
     - If `"conflict": true` is present, emit an explicit `drift_kind: "conflict"` item immediately (`target_file = workspace_file = patterns[0]`, message explaining `.brain-79/drift.lock` merge conflict requiring review and `brain79_session_commit`), NEVER falling back to frontmatter or `last_updated`.
     - Else if `targets` is non-empty, compute exact per-file `deleted`/`modified`/`added`/`missing` attribution against `curr_targets` (even on fresh Git clones and CI runners); if per-file comparison finds 0 diffs yet `curr_digest != stored_digest` (inconsistent manual edit), emit a fallback `modified` drift item with `target_file = workspace_file = sorted(curr_targets)[0] if curr_targets else patterns[0]` and `fallback_targets = sorted(curr_targets.keys())` so Guard C dispatches inspectors cleanly (zero-masking).
     - Else (`targets` is empty `{}`), compare `curr_digest != stored_digest` (or `curr_count == 0` when `stored_count > 0`) using count-based fallback attribution (`missing`/`added`/`deleted`/`modified` with `fallback_targets: sorted(curr_targets.keys())`).
  2. Legacy frontmatter `applies_to_digest` (when `rel_article` has no entry in `.brain-79/drift.lock`): load legacy `.drift_manifest.json` lazily in read-only mode (`auto_rebuild=True, persist=False`) only when needed for that legacy article, falling back to count-based master-digest comparison when leaf targets are absent.
  3. Legacy `last_updated` timestamp fallback when neither `drift.lock` nor frontmatter `applies_to_digest` exists.
  - Step B (multi-hop transitive closure) SHALL propagate `lock_data` and `manifest_data` across recursive hops and emit `drift_kind: "transitive"` whenever any governed intra-wiki child has direct or conflict drift.
- **R-3.2**: WHEN `compute_wiki_article_digest` hashes an intra-wiki Markdown article governed by an umbrella article, THE digest calculation SHALL continue ignoring `VOLATILE_FRONTMATTER_FIELDS` (`applies_to_digest`, `applies_to_count`, `last_updated`) so stripping legacy frontmatter digests produces zero spurious transitive drift. `frontmatter.py` SHALL continue accepting legacy `applies_to_digest` and `applies_to_count` keys during read/lint validation for dual-read compatibility, while `src/brain79/templates/SCHEMA.md` and `SCHEMA_GENERAL.md` document `.brain-79/drift.lock` as primary drift digest storage.
- **R-3.3**: THE workspace and diagnostic layers SHALL exclude `.brain-79/drift.lock` from `WorkspaceIndex.all_paths` (`ephemeral_files` in `src/brain79/core/drift.py`), `ci_check._EPHEMERAL_WIKI_FILES` (`src/brain79/core/ci_check.py`), and `handoff_freshness._EXCLUDED_WIKI_FILES` (`src/brain79/core/handoff_freshness.py`) so `drift.lock` never triggers self-referential drift loops, false `impacted_articles`, or false handoff staleness; AND read-only operations (`orient`, `stats`, `ci-check`, `lint`, `read`, `read-batch`, `context`, `list`, `search`, `migrate --dry-run`) SHALL perform zero disk writes under `.brain-79/` or `.brain-79/.locks/` (never creating `drift.lock`, `.drift_manifest.json`, `.locks/_drift_lock.lock`, or `.locks/_drift_manifest.lock`).

### Capability 4 — 3-way Git merge driver (`brain79 merge-drift-lock`), `.gitignore` negation, pre-commit hook, and `doctor` diagnostics

- **R-4.1**: THE CLI dispatcher (`src/brain79/cli/dispatch.py`) SHALL expose `brain79 merge-drift-lock <base> <ours> <theirs> [--wiki-root PATH]` (expanding `WHITELIST` from 26 to 27 commands; `MCP_TOOLS` remains 9) implementing a deterministic 3-way per-article JSON merge over `.brain-79/drift.lock`:
  - Missing positional arguments, non-existent input files, or a `--wiki-root PATH` argument that does not point to an existing directory SHALL emit an actionable error to stderr and exit `2` without modifying `<ours>`.
  - A 0-byte or whitespace-only `<base>` file (Git `add/add` merge with no common ancestor) SHALL be treated as `{"version": "2.0", "articles": {}}`.
  - Empty `<ours>` or `<theirs>`, or invalid UTF-8, invalid JSON, duplicate keys, `NaN`/`Infinity`, unsupported `version != "2.0"`, or invalid schema in any non-empty input SHALL fail closed with Exit `1` without modifying `<ours>`.
  - Entries identical on `ours` and `theirs` (`ours[k] == theirs[k]`) SHALL be kept as-is (including preserving an identical conflict sentinel, or omitting if both deleted).
  - Entries modified or deleted on only one branch (`ours[k] == base[k]` or `theirs[k] == base[k]`) SHALL take the changed branch's entry (or deletion if `None`).
  - Entries added on only one branch SHALL be included.
  - Entries with true same-article conflicts (`ours[k] != base[k]`, `theirs[k] != base[k]`, `ours[k] != theirs[k]`) SHALL obey `Q-2`:
    - When `k` existed in `base` (modify/modify or delete/modify): revert to `base[k]`. Prune `k` ONLY if `--wiki-root` was explicitly provided AND `(wiki_root / k)` does not exist on disk (default Git merge-driver invocation without `--wiki-root` MUST NOT inspect the mid-merge working tree to prune).
    - When `k` did NOT exist in `base` (conflicting `add/add` of the same key): write the conflict sentinel `{"conflict": true, "count": 0, "digest": "sha256:0000000000000000", "targets": {}}` (NEVER omitting `k`).
  - The merged result SHALL be written atomically back to `<ours>` (`create_temp_path` + `atomic_replace_with_retry`) in deterministic LF JSON format (`Exit 0`); `PermissionError` or `OSError` writing `<ours>` SHALL leave `<ours>` intact and exit `3`.
- **R-4.2**: WHEN `brain79 init`, `brain79 update-project`, or `brain79 doctor --fix` configures Git integration (`src/brain79/core/init_project.py`), THE initializer SHALL:
  1. Place `"!drift.lock"` strictly **after** `"*.lock"` in `DERIVED_STATE_GITIGNORE_ENTRIES`. `sync_wiki_gitignore()` SHALL ensure `.brain-79/drift.lock` is un-ignored even on existing `.gitignore` files where `"!drift.lock"` previously appeared before `"*.lock"` (re-appending `"!drift.lock"` after the last `"*.lock"` rule while preserving user lines and retaining `.locks/` and `.drift_manifest.json` ignored).
  2. Idempotently ensure `.brain-79/.gitattributes` contains both `INDEX.md merge=brain79-index` and `drift.lock merge=brain79-drift-lock`, and—when `install=True` inside a Git repository—configure both `merge.brain79-index.{name,driver}` and `merge.brain79-drift-lock.name = "Brain-79 deterministic drift.lock merge driver"` / `merge.brain79-drift-lock.driver = "brain79 merge-drift-lock %O %A %B"` in local `.git/config`.
  3. Update `PRE_COMMIT_HOOK_SCRIPT` staged-file filter regex to `^\.brain-79/(.*\.md|drift\.lock)$` so commits staging `.brain-79/drift.lock` alone are validated by `brain79 lint --strict`.
- **R-4.3**: WHEN `brain79 doctor` runs diagnostics (`src/brain79/core/doctor.py`), THE doctor engine SHALL:
  1. Exclude top-level `w_root / "drift.lock"` from `legacy_locks` in check `locks_and_filesystem` so a tracked `.brain-79/drift.lock` never produces a false legacy inline lock warning.
  2. Verify in check `derived_state_tracking` (via a centralized `git_check_ignore()` helper in `src/brain79/core/git_ops.py` running `git check-ignore --no-index`, with `.brain-79/.gitignore` rule-ordering fallback outside Git repos when `.brain-79/.gitignore` exists) that `.brain-79/drift.lock` is **not** git-ignored while `.navigation_registry.json`, `.drift_manifest.json`, and `.bootstrap_state.json` remain untracked.
  3. Verify in check `git_merge_driver` that BOTH `INDEX.md` (`brain79-index`) and `drift.lock` (`brain79-drift-lock`) are configured in `.brain-79/.gitattributes` and local `.git/config`.
  4. During `doctor --fix`, surface `gitignore_updated` and `migration_report` changes directly from `update_project()` into `DoctorReport.fixed` without running a redundant second `migrate_wiki(dry_run=False)` pass.

### Capability 5 — Zero-masking idempotent migration and `lint` advisory

- **R-5.1**: WHEN a user runs `brain79 migrate --apply` (or `brain79 update-project` / `brain79 doctor --fix` per `Q-4`) on a wiki, THE migration engine (`src/brain79/core/migration.py`) SHALL:
  1. Load existing `.brain-79/drift.lock` fail-closed (`R-1.4`) and prune entries for deleted, inactive/pre-implementation, or unanchored articles.
  2. Evaluate Paso D strictly **after** Paso B (so articles demoted to `status: legacy` or `stability: legacy` by Paso B are treated as inactive):
     - For inactive or pre-implementation articles (including articles newly demoted to `legacy` by Paso B), strip any legacy `applies_to_digest`/`applies_to_count` keys AND explicitly prune any pre-existing entry for `rel_str` from `drift.lock` without inserting the article into `drift.lock`.
     - For active articles with `applies_to` and legacy frontmatter `applies_to_digest`:
       - If already present in `.brain-79/drift.lock`, preserve the existing `drift.lock` entry (never overwriting newer `drift.lock` state with stale frontmatter).
       - Else validate `stored_digest` against `^sha256:[0-9a-f]{16}$`; if `stored_digest` is malformed, strip the invalid frontmatter keys and fall through to the unhashed `last_updated` check below so malformed legacy metadata can NEVER poison `drift.lock`.
       - For valid `stored_digest`: compute current targets; ONLY if `curr_digest == stored_digest`, populate full leaf `targets`; else if legacy `.drift_manifest.json` has `digest == stored_digest` with valid `targets`, copy those leaf `targets`; else store `{"digest": stored_digest, "count": stored_count, "targets": {}}` (zero-masking invariant, parsing `stored_count` as non-negative int defaulting to `0`).
     - For active articles with `applies_to` without a valid `applies_to_digest` and without a `drift.lock` entry: check `last_updated` timestamp drift against current targets; stamp current digests into `drift.lock` ONLY if `last_updated` is a valid ISO date (`YYYY-MM-DD`), zero targets exhibit timestamp drift, and `curr_digest is not None` (zero-masking: do not mask pre-existing timestamp drift).
  3. Strip legacy `applies_to_digest` and `applies_to_count` from migrated `.md` frontmatter atomically, sync `!drift.lock` in `.brain-79/.gitignore`, and configure the `drift.lock` Git merge driver idempotently when `dry_run=False`. Invoke `regenerate_index_navigation(wiki_root)` ONLY when at least one article was modified or `drift.lock` was pruned/updated (never rewriting `INDEX.md` when `## Changes (0)` and `drift.lock` is unchanged).
  4. Leave all files and Git config completely untouched when `dry_run=True` (`brain79 migrate` without `--apply`).
  5. Be strictly idempotent: re-running `brain79 migrate --apply` on an already migrated wiki SHALL modify `0` files on disk (including `INDEX.md` and `drift.lock`) and report `## Changes (0)`.
- **R-5.2**: WHEN `brain79 lint` inspects a wiki where `.brain-79/drift.lock` exists and one or more non-excluded `.md` articles still carry legacy `applies_to_digest` or `applies_to_count` frontmatter keys, THE organizational linter (`src/brain79/core/lint_organizational.py`) SHALL emit an `OrganizationalIssue` with `rule="legacy_frontmatter_digest"` and `severity="info"` pointing to `brain79 migrate --apply` (per `Q-3`, NEVER causing `WARNING`/`CRITICAL` or failing `lint --strict`, `lint --fail-on-warnings`, or `ci-check`).

### Capability 6 — CI matrix reliability, polyglot test gating, and artifact upload hygiene

- **R-6.1**: WHEN `tests/test_phase16_fixture_and_isolation.py::test_fixture_sources_supported_by_ast_guard_c` runs on base zero-dependency environments (without `brain79[polyglot]`, such as the CI `test` matrix jobs), THE test SHALL unconditionally assert Guard C coverage for all `.py` canonical fixture files and SHALL assert Guard C coverage for `.mjs` fixture files whenever `BRAIN79_REQUIRE_POLYGLOT=1` or the JavaScript polyglot grammar is installed (skipping only uninstalled optional polyglot extensions cleanly instead of failing the base matrix).
- **R-6.2**: THE GitHub Actions CI workflow (`.github/workflows/ci.yml`) SHALL configure both `Upload pytest artifacts on failure` steps (`test` and `test-polyglot` jobs) with `include-hidden-files: true` and `if-no-files-found: ignore` alongside `path: ${{ runner.temp }}/.pytest_tmp` so dot-prefixed `.pytest_tmp` directories are uploaded reliably on pytest failure without emitting spurious `No files were found with the provided path` warnings when non-pytest steps fail (enforced by `tests/test_ci_workflow.py`).
- **R-6.3**: WHEN `orient()` executes on a repository whose active articles are tracked in `.brain-79/drift.lock` (including fresh CI checkouts without `.drift_manifest.json`), THE drift detector SHALL resolve baselines directly from `.brain-79/drift.lock` without invoking `rebuild_drift_manifest()`, keeping cold-start latency reliably under the SLA-1 CI budget across Ubuntu, macOS, and Windows (including `test-polyglot (windows-latest, py3.12)`).

## Interface and error contract

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `brain79 merge-drift-lock <base> <ours> <theirs> [--wiki-root PATH]` | Missing argument, missing input file (`FileNotFoundError`), or non-existent `--wiki-root` directory | Emit actionable error to stderr; leave `<ours>` untouched | Exit `2` |
| `brain79 merge-drift-lock <base> <ours> <theirs>` | `PermissionError` or `OSError` writing `<ours>` | Emit structured OS error; leave `<ours>` intact | Exit `3` |
| `brain79 merge-drift-lock <base> <ours> <theirs>` | 0-byte or whitespace-only `<base>` (`add/add` merge) | Treat `<base>` as `{"version": "2.0", "articles": {}}` and merge | Exit `0` |
| `brain79 merge-drift-lock <base> <ours> <theirs>` | Empty `<ours>`/`<theirs>`, duplicate JSON keys, `NaN`/`Infinity`, unsupported `version`, or invalid schema | Fail closed without modifying `<ours>` so Git aborts merge cleanly | Exit `1` |
| `.brain-79/drift.lock` load during `ci-check` / `lint` / `orient` / `stats` / `migrate` / `session_commit` / `write` / `navigate` | Corrupt JSON, duplicate keys, `NaN`, invalid `version`, or malformed schema | Fail closed with `ValidationError(rule="corrupt_drift_lock")`; zero silent overwrite | `ValidationError` / Exit `1` |
| `brain79 ci-check --lifecycle-hook session-start\|stop` | Corrupt `.brain-79/drift.lock` | Preserve ADR-021 fail-open contract; emit `{}` to stdout | Exit `0` |
| `brain79_session_commit(verified_articles=[...])` | Article entry has `"conflict": true` (`drift_kind == "conflict"`) | Reject under `strict`/`balanced` with `verified_article_conflict_forbidden`; warn under `advisory` | `ValidationError` / Exit `1` |
| `.brain-79/drift.lock` write | Lock timeout or OS error (`TimeoutError`/`PermissionError`/`OSError`) | Preserve pre-existing `drift.lock` and touched `.md` files atomically via rollback | Exit `3` |
| `brain79 migrate --apply` on pre-Phase-17 wiki with active drift | Article has `curr_digest != stored_digest` or timestamp drift | Preserve stale baseline without masking drift; Guard C still catches breaking API changes | Exit `0` (drift remains visible) |

## Migration and rollout

- **Default behavior**:
  - New repositories initialized with `brain79 init` add `!drift.lock` after `*.lock` in `.brain-79/.gitignore`, pre-configure `drift.lock merge=brain79-drift-lock` in `.brain-79/.gitattributes` and local `.git/config`, update `.git/hooks/pre-commit`, and create `.brain-79/drift.lock` on the first governing article write.
  - Existing repositories remain 100% readable without running `brain79 migrate --apply` via dual-read fallback (`R-3.1`); articles progressively shed frontmatter digests as they are edited, or all at once via `brain79 migrate --apply`.
- **Intentional existing test updates (disclosed upfront)**:
  - `WHITELIST` count (`26 -> 27`): `tests/test_symmetry.py`, `tests/test_phase14_ci_check_and_hooks.py`, `tests/test_phase17_read_batch_parity.py`.
  - `LOCK_HIERARCHY` tuple (`_drift_lock.lock` inserted before `_drift_manifest.lock`): `tests/test_navigation.py`.
  - Legacy assertions expecting frontmatter `applies_to_digest` / `.drift_manifest.json` writes: `tests/test_transitive_drift_and_ripple.py`, `tests/test_phase12_derived_state.py`, `tests/test_session_commit.py`, `tests/test_phase14_ci_check_and_hooks.py`, `tests/test_phase15_stats.py`, `tests/test_chaos_and_fuzzing.py`, `tests/test_phase12_enforcement_tiers.py`.
- **Upgrade path**: run `brain79 update-project` or `brain79 migrate --apply` to extract digests into `.brain-79/drift.lock`, strip frontmatter digests, update `.gitignore` with `!drift.lock`, update `.git/hooks/pre-commit`, and register the `brain79-drift-lock` merge driver.
- **Rollback safety**: reverting to `v0.16.0`–`v0.17.0` keeps all `.md` articles readable; articles without frontmatter `applies_to_digest` gracefully fall back to `last_updated` timestamp drift checks on older binaries.

## Acceptance criteria (Given / When / Then)

### AC-1 — Deterministic `.brain-79/drift.lock` schema, lock ordering, inline-lock preservation, pruning, and corrupt fail-closed
- **Verifies**: `R-1.1`, `R-1.2`, `R-1.3`, `R-1.4`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: a software wiki with governed articles, a pure handoff-only commit (zero governed articles), an article archived/deleted on disk or having `applies_to` removed (including via `write_article(..., force_validation_skip=True)`), a legacy inline `INDEX.md.lock` file alongside `.brain-79/drift.lock`, and separate corrupted `drift.lock` fixtures (bad JSON, duplicate keys, `NaN`, wrong `version`, unknown entry key, `"conflict": false`).
- **When**: articles are written, archived, deleted via `rm` + `commit_session`/`regenerate_index_navigation`, `cleanup_legacy_inline_locks` runs, and `ci-check`, `lint`, `orient`, `stats`, `migrate`, `session_commit` (including `allow_partial_ripple=True` + handoff-only), `write_article` (including `force_validation_skip=True` and `is_special`), `regenerate_index_navigation`, and `--lifecycle-hook` run against valid and corrupted `drift.lock`.
- **Then**: `.brain-79/drift.lock` is deterministic LF JSON (`version: "2.0"`, sorted keys, allowing `targets: {}` when `count >= 0`), is not created on pure non-governed commits, locks via `_drift_lock.lock` in `LOCK_HIERARCHY`, survives `cleanup_legacy_inline_locks` while legacy inline locks are deleted, prunes deleted/inactive/unanchored articles across all mutation paths, fails closed with `ValidationError(rule="corrupt_drift_lock")` / CLI Exit `1` (including `ci-check` and never swallowed by `navigation.py` callers) across all corrupt fixtures, and leaves `--lifecycle-hook` fail-open (Exit `0`, `{}`).

### AC-2 — Hash-free writes, concurrent safety, zero-diff `verified_articles`, conflict blocking, and rollback
- **Verifies**: `R-2.1`, `R-2.2`, `R-2.3`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: a Git repository with governed articles and scenarios covering: (a) `write_article` (normal, `force_validation_skip=True` with valid and malformed frontmatter, and concurrent writes to distinct articles), (b) `write_many_articles` with simulated mid-batch failure, (c) `verified_articles` on an internal non-API refactor (including an article still holding legacy frontmatter digest), (d) `verified_articles` on an article whose `drift.lock` entry has `"conflict": true` under `strict`, `balanced`, and `advisory`, (e) an article present in both `edits` and `verified_articles`, and (f) a simulated Pass 3 failure during `commit_session`.
- **When**: `write_article`, `write_many_articles`, and `commit_session` execute across scenarios (a)–(f).
- **Then**: written/edited `.md` files contain zero `applies_to_digest`/`applies_to_count`; concurrent `write_article` calls preserve both entries without clobbering; `verified_articles` leaves `git diff` on the verified `.md` empty and updates only `drift.lock`; `verified_articles` rejects `"conflict": true` with `verified_article_conflict_forbidden` under `strict`/`balanced` (downgraded warning under `advisory`); `writes`/`edits` wins over `verified_articles` when both name the same article; simulated write/Pass-3 failures restore or unlink `.brain-79/drift.lock` and `.md` files byte-for-byte.

### AC-3 — Guard C baseline resolution across migration, busy lockfile history, and `balanced` verification, plus Hard Session Ripple Gate parity
- **Verifies**: `R-2.4`, `R-2.5`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: a Git repository with governed article `features/billing.md` and `src/billing.py` exercising: (a) a breaking public API change committed before `brain79 migrate --apply` (which strips frontmatter digests and copies the stale digest into `drift.lock`), (b) a `balanced`-tier `verified_articles` commit updating only `drift.lock` followed by a `strict`-tier internal non-API refactor, (c) >50 intervening commits touching `drift.lock` for unrelated articles after `billing.md`'s last baseline commit (testing Pass 2 article-only fallback and true `%P` first-parent resolution), (d) a substantive `.md` edit vs a volatile-only `.md` edit, (e) both `has_public_api_changes` and `has_public_python_api_changes` invocations, and (f) a dirty working-tree code edit or `"conflict": true` article with zero frontmatter digests.
- **When**: Guard C and Pass 2d (`commit_session`) execute across scenarios (a)–(f).
- **Then**: (a) skips the pure migration commit and STILL blocks the pre-existing breaking API change; (b) anchors at the `balanced` `drift.lock` commit and allows the subsequent `strict` non-API refactor; (c) falls back to the article-only walk without advancing the baseline past unverified breaking API changes; (d) distinguishes substantive vs volatile-only `.md` commits; (e) both orchestrator and Python inspector produce identical baseline decisions; (f) Pass 2d still raises `unresolved_session_ripple` without frontmatter digests.

### AC-4 — Exact per-file CI drift attribution on fresh clone, conflict reporting, dual-read fallback, exclusion, and read-only zero-mutation
- **Verifies**: `R-3.1`, `R-3.2`, `R-3.3`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: (a) a fresh clone with `.brain-79/drift.lock` committed and zero `.drift_manifest.json` where 1 governed file is modified, 1 is deleted, and 1 is added, (b) an article with `"conflict": true` in `drift.lock` (including transitive parent propagation), (c) an entry where `targets` match disk but `digest` was manually altered, (d) a legacy pre-Phase-17 wiki with only frontmatter `applies_to_digest`, and (e) an article with `applies_to: [".brain-79/**"]` plus an active handoff.
- **When**: `brain79 ci-check --format json --enforcement strict`, `brain79 orient`, `brain79 stats`, `brain79 lint --strict`, and `brain79 migrate` (dry-run) run.
- **Then**: (a) reports exact per-file `modified`, `deleted`, and `added` attribution; (b) emits `drift_kind: "conflict"` (and `"transitive"` on parent) without `last_updated` masking; (c) detects the mismatched master digest (zero-masking); (d) detects drift via legacy frontmatter fallback; (e) `.brain-79/drift.lock` never appears in `WorkspaceIndex.all_paths`, `impacted_articles`, or handoff staleness; all read-only commands create zero files under `.brain-79/` or `.brain-79/.locks/`.

### AC-5 — 3-way `brain79 merge-drift-lock` driver and `WHITELIST` / `MCP_TOOLS` parity
- **Verifies**: `R-4.1`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: Git and CLI merge fixtures covering (a) disjoint article edits (`features/a.md` vs `features/b.md`), (b) identical edits and delete/delete, (c) 0-byte `<base>` disjoint `add/add` vs same-key conflicting `add/add`, (d) modify/modify and delete/modify conflicts with and without explicit `--wiki-root`, (e) corrupt JSON / duplicate keys / `NaN` / unsupported version / `"conflict": false` / empty `<ours>`, (f) missing file argument or non-existent `--wiki-root` directory, and (g) read-only `<ours>` directory permission error.
- **When**: `brain79 merge-drift-lock` runs on each fixture and `test_mcp_cli_symmetry` checks dispatcher and MCP tool inventories.
- **Then**: disjoint, identical, delete/delete, and 0-byte-`<base>` disjoint `add/add` merge cleanly (`Exit 0`); same-key `add/add` writes the conflict sentinel (`"conflict": true`) detected by `check_article_drift`; modify/modify and delete/modify revert to `base[k]` by default (pruning delete/modify ONLY when explicit existing `--wiki-root` confirms `.md` is absent); corrupt/invalid inputs exit `1` without touching `<ours>`, missing files or invalid `--wiki-root` exit `2`, permission errors exit `3`; `WHITELIST` has 27 commands and `MCP_TOOLS` remains 9.

### AC-6 — `.gitignore` negation ordering, Git merge driver & pre-commit setup, and `doctor` diagnostics
- **Verifies**: `R-4.2`, `R-4.3`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: (a) a freshly initialized repo via `brain79 init`, (b) an existing repo whose `.brain-79/.gitignore` has inverted ordering (`!drift.lock` before `*.lock`) or omits `!drift.lock`, (c) a repo with tracked `.brain-79/drift.lock` and missing `brain79-drift-lock` config, and (d) a Git commit staging only a corrupted `.brain-79/drift.lock`.
- **When**: `brain79 init`, `brain79 update-project`, `brain79 doctor`, `brain79 doctor --fix`, and `.git/hooks/pre-commit` execute.
- **Then**: `.brain-79/.gitignore` ends with `!drift.lock` strictly after `*.lock` (verified via `git check-ignore --no-index` in `doctor` and `.gitignore` fallback outside Git); `.brain-79/.gitattributes` and `.git/config` contain both `brain79-index` and `brain79-drift-lock`; `doctor` check `locks_and_filesystem` reports `ok` when `.brain-79/drift.lock` exists; `doctor` flags ignored `drift.lock` or missing merge driver as `warning` and `--fix` repairs both; pre-commit hook runs `brain79 lint --strict` when only `.brain-79/drift.lock` is staged.

### AC-7 — Idempotent zero-masking migration (`--apply`) and `lint` legacy advisory
- **Verifies**: `R-5.1`, `R-5.2`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: a pre-Phase-17 wiki containing: (1) a clean governed article with legacy `applies_to_digest`, (2) a genuinely drifted governed article with legacy `applies_to_digest` (tested both with and without matching legacy `.drift_manifest.json`), (3) an article with a malformed legacy frontmatter `applies_to_digest` (e.g. `"not-a-sha"`), (4) an article already present in `.brain-79/drift.lock` with a newer digest than its legacy frontmatter, (5) an oversized/incomplete article demoted to `legacy` by Paso B (that previously had a `drift.lock` entry), (6) an inactive article with legacy `applies_to_digest`, and (7) two unhashed legacy articles (one clean, one with `last_updated` timestamp drift).
- **When**: `brain79 migrate` (dry-run) runs, then `brain79 migrate --apply` runs twice (with an older `INDEX.md` `last_updated` date prior to the second run), followed by `brain79 ci-check --enforcement strict` and `brain79 lint --strict` (plus a separate fixture where `.brain-79/drift.lock` coexists with one article retaining legacy `applies_to_digest`).
- **Then**: dry-run makes zero disk/Git mutations; first `--apply` populates `.brain-79/drift.lock` preserving stale baselines without masking either drifted article, strips malformed legacy digests without poisoning `drift.lock`, keeps newer `drift.lock` entries intact, prunes/omits inactive and Paso-B-demoted articles, strips frontmatter digests, and configures `.gitignore`/merge driver; second `--apply` reports `## Changes (0)` and modifies 0 files on disk (including `INDEX.md` and `drift.lock`); `lint --strict` emits `legacy_frontmatter_digest` at `INFO` severity (`Exit 0`) without failing `lint --strict`, `lint --fail-on-warnings`, or `ci-check`.

### AC-8 — CI matrix polyglot gating, hidden-directory artifact upload, and Windows SLA-1 cold-start reliability
- **Verifies**: `R-6.1`, `R-6.2`, `R-6.3`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: (a) `test_fixture_sources_supported_by_ast_guard_c` executed both with and without `tree-sitter-javascript` / `BRAIN79_REQUIRE_POLYGLOT=1`, (b) `.github/workflows/ci.yml` validated by `tests/test_ci_workflow.py`, and (c) a fresh checkout with `.brain-79/drift.lock` committed and zero `.drift_manifest.json` running `orient()` / `test_sla1_cold_start_latency_and_subprocess_bound`.
- **When**: `pytest` runs on base (`uv sync --group dev`) and polyglot (`uv sync --group dev --extra polyglot`) environments, and GitHub Actions CI runs after push.
- **Then**: (a) base matrix passes `.py` checks without false failure on uninstalled `.mjs` grammar while polyglot matrix enforces both `.py` and `.mjs`; (b) both failure upload steps in `.github/workflows/ci.yml` set `include-hidden-files: true` and `if-no-files-found: ignore` (verified in `tests/test_ci_workflow.py`); (c) `orient()` never calls `rebuild_drift_manifest()` when all active articles are in `drift.lock`, and all 8 GitHub Actions CI jobs pass green post-push.

## Wiki impact map

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/core/drift.py`, `src/brain79/core/session_commit.py`, `src/brain79/core/wiki.py`, `src/brain79/core/frontmatter.py`, `src/brain79/core/validation.py` | `features/transitive-drift-and-ripple-guards.md` | `update` |
| `src/brain79/core/ast_guards/orchestrator.py`, `src/brain79/core/ast_guards/python_inspector.py`, `src/brain79/core/git_ops.py` | `features/polyglot-ast-guards-and-stats.md` | `update` |
| `src/brain79/core/init_project.py`, `src/brain79/core/migration.py`, `src/brain79/core/navigation.py` | `features/team-collaboration-and-onboarding.md` | `update` |
| `src/brain79/core/locks.py` | `features/cross-platform-and-lock-isolation.md` | `update` |
| `src/brain79/core/ci_check.py`, `src/brain79/core/handoff_freshness.py`, `src/brain79/core/lint_organizational.py` | `features/lifecycle-hooks-and-ci-gate.md` | `update` |
| `src/brain79/core/doctor.py` | `features/project-upgrade-and-multi-harness-doctor.md` | `update` |
| `src/brain79/cli/dispatch.py` | `architecture/dispatcher.md` | `update` |
| `src/brain79/cli/dispatch.py` | `architecture/symmetry.md` | `update` |
| `src/brain79/core/drift.py` (Phase 17 architectural decision) | `decisions/adr-023-external-drift-lockfile.md` | `create` |
| `src/brain79/core/drift.py` (Phase 17 roadmap tracking) | `architecture/roadmap-industrial-scale.md` | `update` |
| `src/brain79/core/drift.py` (current architecture summary) | `architecture/current-state.md` | `update` |
| `CHANGELOG.md` | `changelog/v0-18-0.md` | `create` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
uv run pytest
uv run mypy src tests
uv run brain79 lint --strict
uv run brain79 ci-check --enforcement strict
uv run brain79 doctor
```

**Post-push CI gate**: after any push to remote, wait for the GitHub Actions CI workflow (all 8 matrix jobs across `test` and `test-polyglot`) to complete with `conclusion: success` before declaring the release or merge complete.

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| 2026-11-27 | xilax79 | Renumbered external drift lockfile from Phase 18 (`SPEC-018`, `v0.19.0`) to Phase 17 (`SPEC-017`, `v0.18.0`) ahead of PyPI distribution (now Phase 18, `v0.19.0`); hardened specification against codebase and adversarial Opus 5.5 Medium audit (`S-1`–`S-7`): `cleanup_legacy_inline_locks` / `doctor` lock exclusion, Guard C Pass 2 article-only fallback + `%P` parent resolution + migration-commit skipping, `verified_articles` conflict blocking, strict JSON validation (`"conflict": false` rejected), upfront `load_drift_lock` and non-swallowing `corrupt_drift_lock`, `migrate_wiki` malformed-digest sanitization + Paso-B pruning + zero-touch `INDEX.md` idempotency, `--wiki-root` directory check, `.gitignore` precedence repair, pre-commit hook coverage, and `tests/test_phase17_read_batch_parity.py` disclosure. | `R-1.1`–`R-5.2`, `AC-1`–`AC-7` |
| 2026-11-27 | xilax79 | Added Capability 6 (`R-6.1`–`R-6.3`, `AC-8`) and post-push CI gate to resolve the `v0.17.0` GitHub Actions failures: base-vs-polyglot gating in `test_fixture_sources_supported_by_ast_guard_c`, `include-hidden-files: true` + `if-no-files-found: ignore` for `.pytest_tmp` artifact upload in `.github/workflows/ci.yml`, and zero-rebuild `drift.lock` fast path for Windows SLA-1 `orient()` latency. | `R-6.1`–`R-6.3`, `AC-8` |

## Wiki distillation checklist (post-implementation)

- [ ] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [ ] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [ ] Record the external `drift.lock` architectural decision in `.brain-79/decisions/adr-023-external-drift-lockfile.md`.
- [ ] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-18-0.md`.
- [ ] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [ ] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
