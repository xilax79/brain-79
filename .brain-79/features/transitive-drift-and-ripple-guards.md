---
type: feature
summary: specification for Phase 6.7 — Merkle leaf-manifest drift detection, multi-hop DAG propagation, hard session ripple gate, anti-sprawl guard, AST signature verification, and unbounded Signal 1 context
status: shipped
version: 0.8.0
applies_to:
  - src/brain79/core/drift.py
  - src/brain79/core/context.py
  - src/brain79/core/session_commit.py
  - src/brain79/core/orient.py
related:
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/session-triage-and-research-persistence.md
last_updated: 2026-11-12
applies_to_digest: "sha256:5f7d6addd2b97b97"
applies_to_count: 4
---

# Feature — Transitive drift detection, holistic ripple gates, anti-sprawl guards, and unbounded governing context (Phase 6.7)

## Overview

During multi-phase development, LLM coding agents exhibit four recurring behavioral failures that degrade persistent project memory:
1. **Partial / Append-Only Updates**: when implementing a feature or architectural change, agents create new leaf articles (`decisions/adr-016.md`, `features/new-feature.md`) or update 1 article while leaving other impacted governing and umbrella documents (`architecture/current-state.md`, `architecture/symmetry.md`, `features/cli.md`) stale.
2. **Uncontrolled Wiki Sprawl**: instead of updating an existing governing article (`features/handoff-continuity.md`), agents create fragmented duplicate articles (`features/handoff-v2.md`) governing the exact same `.py` modules.
3. **Partial Context Blindness at Cold Start (`max_articles=4` truncation)**: when 7 articles deterministically govern the files being touched via Signal 1 (`applies_to`), `rank_context_articles()` silently slices `candidates[:4]` and discards the other 3 governing articles.
4. **Incomplete End-of-Session Synchronization & Rubber-Stamping**: when asked to "update the wiki" at the end of a session, agents either forget some of the `.py` files modified in the working tree or attempt to silence drift alerts with generic excuses without documenting new public functions, classes, or CLI parameters.

This specification defines **Phase 6.7 of the Industrial-Scale Roadmap**, combining a **Merkle leaf-manifest and multi-hop DAG drift engine** with **four behavioral enforcement gates**:
- **Hard Session Ripple Gate (`unresolved_session_ripple`)**: rejects `session_commit` in pre-flight (Pass 2d) if any umbrella article impacted by the session's writes/edits or any digest-stamped governing article for modified workspace files remains drifted.
- **Anti-Sprawl & Target Overlap Guard (`duplicate_governance_target`)**: blocks creating a new redundant article in `features/`, `architecture/`, `product/`, `topics/`, or `context/` when its governed files or title/slug collide with an existing active article of the same type unless `supersedes` or `related` is declared.
- **Unbounded Signal 1 (`applies_to`) Context + Working-Tree Auto-Binding in `orient()`**: never truncates deterministic Signal 1 path matches by `top_n=4`, automatically binds `orient()` to dirty/modified git working-tree files when `paths` is omitted, and provides a Mandatory Reading Manifest if total inlined text exceeds the 64 KB buffer.
- **Guard C — AST Public API Signature Diff Check (`verified_article_public_signature_changed`)**: parses `git show HEAD:<file>` vs. disk using Python's standard `ast` module and forbids using `verified_articles` if public functions, classes, methods, or parameter signatures changed in a governed `.py` file.

---

## Problem statement (root-cause forensics)

An audit of `.brain-79/` at version `0.7.2` and an analysis of agent behavior revealed six mechanical gaps:

1. **Unanchored governance (`applies_to` omission)**: foundational articles written without `applies_to` are 100% invisible to both `drift.py` and Signal 1 (`applies_to` path matching) in `brain79_orient(paths=...)`.
2. **Intra-wiki synthesis & multi-hop blindness (umbrella articles)**: umbrella documents (`architecture/current-state.md`, `product/overview.md`) synthesize collections of other wiki articles (`.brain-79/decisions/adr-*.md`, `.brain-79/features/*.md`). Neither direct edits to child articles nor unresolved code drift in child articles propagated upward.
3. **Coarse `YYYY-MM-DD` date granularity and attribution blindness**: `file_date > last_updated` fails on same-day edits, git rebases/cherry-picks with older author dates, and deleted files. Furthermore, a single flat hash without a leaf manifest cannot tell which file in a 10-file glob actually changed.
4. **Passive warnings at session close**: emitting a non-blocking string in `receipt["warnings"]` after `commit_session()` has already returned `success: True` allows LLM agents to ignore remaining drift and terminate the session with a half-updated wiki.
5. **No anti-sprawl check on article creation**: `write_article()` allows creating unlimited overlapping `features/*.md` or `architecture/*.md` articles governing the exact same source files without requiring `supersedes` or `related`.
6. **Hard `top_n=4` truncation of Signal 1 matches in `context.py`**: `candidates[:top_n]` in `rank_context_articles()` truncates deterministic `applies_to` matches (`score >= 100.0`) whenever $\ge 5$ articles govern the target files.

---

## Architectural design (7 pillars)

### Pillar 1: Schema registration, strict type/regex validation, lifecycle state unification, and Anti-Sprawl Guard

1. **Formal schema registration (`frontmatter.py`, `templates/SCHEMA.md`, `templates/SCHEMA_GENERAL.md`, `.brain-79/SCHEMA.md`)**:
   - Register `"applies_to_digest"` and `"applies_to_count"` in `ALLOWED_UNKNOWN_KEYS` in `src/brain79/core/frontmatter.py`.
   - Register `"applies_to_digest"` and `"applies_to_count"` in the `"optional"` field lists of **all** types that support `applies_to`: `product`, `architecture`, `feature`, `decision`, `changelog`, `context`, and `topic` across `SOFTWARE_PROFILE_SCHEMA` and `GENERAL_PROFILE_SCHEMA`.
   - Add `"archived"` to the `stability` enum of `architecture` (`["experimental", "stable", "archived", "legacy"]`) and to the `status` enum of `feature` (`["planned", "in_progress", "shipped", "deprecated", "archived", "legacy"]`) in `SOFTWARE_PROFILE_SCHEMA`. This reserves `legacy` strictly for unreviewed auto-migrated articles (which trigger `legacy_needs_review` at `severity="info"` per ADR-003), while reviewed historical documents use `archived` (in `INACTIVE_STATUSES`, emitting `0 info`).
2. **Strict frontmatter type and format validation (`validate_frontmatter`)**:
   - **Digest format (`frontmatter_invalid_digest`)**: if `applies_to_digest` is present in frontmatter, `validate_frontmatter()` verifies `isinstance(val, str)` and `re.fullmatch(r"^sha256:[0-9a-f]{16}$", val)`. Because the string starts with `"sha256:"`, YAML 1.1/1.2 parsers never coerce it to `int`, `float`, or octal, and `dump_frontmatter()` always quotes `"sha256:..."` strings.
   - **Count format (`frontmatter_invalid_count`)**: if `applies_to_count` is present in frontmatter, `validate_frontmatter()` verifies `isinstance(val, int) and not isinstance(val, bool) and val >= 0`.
3. **Canonical lifecycle status sets (`frontmatter.py`)**:
   ```python
   PRE_IMPLEMENTATION_STATUSES: frozenset[str] = frozenset({
       "planned", "draft", "experimental", "in_progress", "proposed"
   })
   INACTIVE_STATUSES: frozenset[str] = frozenset({
       "legacy", "superseded", "deprecated", "rejected", "archived"
   })
   ```
   - An article is **strictly active** when neither its `status` nor its `stability` is in `PRE_IMPLEMENTATION_STATUSES | INACTIVE_STATUSES` (e.g., `architecture` with `stability: stable`, `feature` with `status: shipped`, `decision` with `status: accepted`, and `product`/`changelog`/`context`/`topic` without an inactive status).
4. **Write-time vs. lint-time target enforcement (preventing both batch ordering bugs and CI refactoring deadlocks)**:
   - **`unanchored_governance_article` (`severity="warning"` in `lint_organizational`)**: triggers in the `software` profile when a strictly active `architecture` (`stability: stable`) or `feature` (`status: shipped`) article lacks a non-empty `applies_to` list in YAML frontmatter. `in_progress` features are exempt (`PRE_IMPLEMENTATION_STATUSES`).
   - **`applies_to_target_missing` (Post-Staging Write Validation vs. Lint-Time Info)**:
     - **In single-file `write_article` / `edit_article`**: after validating frontmatter and markdown structure, build `WorkspaceIndex(project_root, wiki_root, overlay_fs={rel_str: content})`. If the article is strictly active (`stable` / `shipped` / `accepted`), every pattern in `applies_to` must resolve to $\ge 1$ file in `WorkspaceIndex`, or `ValidationError(rule="applies_to_target_missing")` is raised immediately.
     - **In batch `write_many_articles` and `commit_session`**: during Pass 1, `validate_article_content()` validates frontmatter schema and markdown structure while populating `virtual_fs` **without** checking target existence yet (because `writes[0]` may reference `decisions/adr-018.md` which is created in `writes[1]`). Once `virtual_fs` is 100% populated with all `writes` and `edits`, Pass 2a builds `WorkspaceIndex(project_root, wiki_root, overlay_fs=virtual_fs)` and validates `applies_to_target_missing` across all written/edited strictly active articles in `virtual_fs` before any file touches disk.
     - **At `brain79 lint` time (`lint_organizational`)**: if an existing active article has a pattern that now resolves to 0 files (because a developer deleted or renamed a `.py` file during a code refactoring commit), `lint_organizational` emits `applies_to_target_missing` with **`severity="info"`** so tactical code commits never deadlock `.git/hooks/pre-commit`.
5. **Anti-Sprawl & Target Subsumption Guard on New Article Creation (`duplicate_governance_target`)**:
   - When creating a **new** article (path does not yet exist on disk) of `type in {"feature", "architecture", "product", "topic", "context"}` (excluding `decision`, `changelog`, `handoff`, and `navigation`, where chronological entries are expected):
   - Compare the new article against all existing strictly active articles $E$ on disk of the **exact same `type`**:
     - Let $T_{\text{new}}$ be the resolved non-intra-wiki workspace target files of the new article, and $T_E$ be the resolved non-intra-wiki workspace target files of existing active article $E$.
     - **Case 1 — Full Target Subsumption ($T_{\text{new}} \subseteq T_E$ with $|T_{\text{new}}| > 0$)**: 100% of the new article's code targets are already governed by existing active article $E$ of the same `type`.
       - **Strict exemption**: `related` does **not** exempt full subsumption (otherwise an agent could bypass the guard by adding `related: [E]`). Only declaring `supersedes: <E>` (or an explicit `allow_overlapping_governance: true` override) exempts full target subsumption.
     - **Case 2 — Partial Target Overlap ($T_{\text{new}} \not\subseteq T_E$ with Jaccard $\frac{|T_{\text{new}} \cap T_E|}{|T_{\text{new}} \cup T_E|} \ge 0.65$)**:
       - Exempt if the new article declares `supersedes: <E>` or explicitly links `<E>` in `related` (confirming it is an intentional companion/sub-feature that also introduces its own distinct target files).
     - Otherwise, raise `ValidationError(rule="duplicate_governance_target")` instructing the agent:
       `"Anti-sprawl guard: existing active article '{E}' of type '{type}' already governs {overlapping_files}. Use brain79_edit to update '{E}' organically instead of creating a duplicate article, or declare 'supersedes: {E}'."`

---

### Pillar 2: Operation-scoped `WorkspaceIndex` and unified glob/directory matching (`context.py` & `drift.py`)

1. **Canonical path coordinate system (`project_root`-relative POSIX paths)**:
   - Every target file path in `WorkspaceIndex`, `.drift_manifest.json`, and digest calculation is strictly a **POSIX path relative to `project_root`** (e.g., `"src/brain79/core/drift.py"`, `".brain-79/decisions/adr-001-dual-interface.md"`).
   - Wiki article identifiers (`article_path`) are POSIX paths relative to `wiki_root` (e.g., `"architecture/current-state.md"`).
2. **Operation-scoped `WorkspaceIndex` (zero cross-request stale state in `brain79 serve`)**:
   - `WorkspaceIndex.build(project_root, wiki_root, overlay_fs=None)` is instantiated **once per top-level operation** (`orient()`, `lint_organizational()`, `detect_all_drift()`, `commit_session()`, `write_article()`, `edit_article()`, `write_many_articles()`, `migrate_wiki()`), passed explicitly via `workspace_index: WorkspaceIndex | None = None`, and discarded when the operation finishes.
   - Within that operation, `WorkspaceIndex.build()` executes **at most one** `git -c core.quotepath=false ls-files -z --cached --others --exclude-standard` call (timeout 2s), reducing complexity from $O(A \times W)$ to $O(W + A)$ ($<10\text{ ms}$ total) while always seeing fresh untracked files on every new MCP call.
   - **Git submodule & non-git contingency**: if `.git` is absent, if `git ls-files` exits non-zero, or for submodule paths where `git` only reports a directory entry (`p_root / entry` is a directory on disk), `WorkspaceIndex` seamlessly traverses those directories on the filesystem while excluding `_IGNORED_DIRS`.
   - **Dynamic intra-wiki prefix set**: `WorkspaceIndex` loads the active schema (`load_active_schema(wiki_root)`) and inspects existing subdirectories of `wiki_root` (plus paths in `overlay_fs`) to build `known_wiki_prefixes` dynamically (supporting built-in folders as well as any user-defined `custom_types` directories such as `rfcs/` or `specs/`).
   - **Ephemeral exclusions**: `.brain-79/INDEX.md`, `.brain-79/.navigation_registry.json`, `.brain-79/.drift_manifest.json`, `.brain-79/_raw/**`, `.brain-79/.locks/**`, and `.brain-79/handoffs/**` are always excluded from target matching.
3. **Unified pattern matcher (`match_applies_to_pattern`) shared by `context.py` and `drift.py`**:
   - Both `context.py` (`_match_applies_to`) and `drift.py` (`find_matching_workspace_files`) call the **exact same function** `match_applies_to_pattern(pattern, candidate_project_rel_posix, known_dirs, known_wiki_prefixes, wiki_rel_posix)`:
     - **Bidirectional `.brain-79/` normalization**: if `pattern` starts with a prefix in `known_wiki_prefixes` (e.g., `"decisions/adr-*.md"` or `"rfcs/*.md"`) and that top-level prefix does not exist at `project_root`, it is normalized to `f"{wiki_rel_posix}/{pattern}"` (e.g., `".brain-79/decisions/adr-*.md"`).
     - **Directory prefix parity**: if `pat_clean` (stripped of trailing `/`) is a directory in `WorkspaceIndex.known_dirs` or ends with `/`, it matches any `candidate` where `candidate == pat_clean` or `candidate.startswith(pat_clean + "/")`.
     - **Segment-aware globbing (`*` vs. `**`)**: patterns containing `*`, `?`, or `[` are compiled via a segment-aware glob-to-regex translator where `*` matches within a single path segment (`[^/]*`), `**/` matches zero or more directory levels (`(?:.+/)?`), and `**` matches across directories (`.*`).

---

### Pillar 3: 64 KB byte-streaming hashing, Merkle leaf manifest (`.drift_manifest.json`), and multi-hop DAG transitivity

1. **Constant-memory 64 KB byte-streaming for workspace files (CRLF & BOM invariant)**:
   - Files exceeding `MAX_DRIFT_FILE_SIZE = 10 * 1024 * 1024` (10 MB) are skipped.
   - Open file in binary mode (`"rb"`) and read in `65536`-byte (64 KB) chunks:
     - **Binary detection on chunk 0**: if `b"\x00" in chunk0[:8192]`, feed `chunk0` and all subsequent 64 KB chunks directly into `hashlib.sha256()`.
     - **Byte-stream text normalization (encoding-agnostic)**: if no null byte is in `chunk0[:8192]`:
       - Strip leading UTF-8 BOM (`if chunk0.startswith(b"\xef\xbb\xbf"): chunk0 = chunk0[3:]`).
       - Stream each 64 KB chunk through a stateful byte-level `b"\r\n"` $\rightarrow$ `b"\n"` normalizer.
   - Return `"sha256:" + hasher.hexdigest()[:16]`, cached in `_FILE_HASH_CACHE` keyed by `(abs_posix_path, st_mtime_ns, st_size)`.

2. **Canonical non-volatile hashing for intra-wiki targets (`.brain-79/*.md`)**:
   - Read content from `overlay_fs[wiki_rel_path]` if present, else from disk.
   - Strip only `VOLATILE_FRONTMATTER_FIELDS = frozenset({"applies_to_digest", "applies_to_count", "last_updated"})`.
   - Serialize remaining `stable_meta` via `json.dumps(stable_meta, sort_keys=True, ensure_ascii=False, default=str)` + `norm_body`.

3. **Master digest + Per-Target Leaf Manifest (`.brain-79/.drift_manifest.json`) & System Integration**:
   - `compute_applies_to_manifest(patterns, project_root, wiki_root, exclude_self_path, overlay_fs=None, workspace_index=None)` returns `(master_digest: str | None, count: int, targets: dict[str, str])`.
   - **Protection against 0-match erasure**: if an article already had a recorded `applies_to_digest` on disk, automatic migration or background reads **never** strip or overwrite `applies_to_digest` with `None` when `len(targets) == 0`.
   - **Git tracking, lock mapping, registry self-healing, and `handoff_freshness.py` exclusion**:
     - `.brain-79/.drift_manifest.json` is versioned in Git (`indent=2, sort_keys=True`).
     - **Self-healing orphan purge on file deletion**: both `regenerate_index_navigation(wiki_root)` (`navigation.py`) and `migrate_wiki(wiki_root)` (`migration.py`) automatically purge any entry from `.navigation_registry.json` and `.drift_manifest.json` whose `.md` file no longer exists on disk (`not (wiki_root / path).is_file()`).
     - In `src/brain79/core/handoff_freshness.py`, add `".drift_manifest.json"` to `_EXCLUDED_WIKI_FILES`.
     - In `src/brain79/core/locks.py`, map `".drift_manifest.json"` $\rightarrow$ `locks_dir / "_drift_manifest.lock"` and `"_transaction.lock"` $\rightarrow$ `locks_dir / "_transaction.lock"`.

4. **Multi-hop DAG transitive drift propagation & Missing-Manifest Contingency**:
   - **Formal Governance Dependency Graph definition ($G = (V, E)$)**:
     $$\text{Drift}(A) = \text{DirectDrift}(A) \lor \bigvee_{B \in \text{Children}(A)} \text{Drift}(B)$$
   - **Step A (`DirectDrift(A)`)**: compares `current_targets` against `manifest_targets` to emit exact `modified`, `deleted`, `added`, or `missing` (`"governed files missing: pattern matched 0 files in active article"`) records, with Case A2 contingency fallback when `manifest_targets` is absent.
   - **Step B (Recursive & memoized multi-hop transitive closure)**: both `check_article_drift(A, ..., _visited=frozenset())` and `detect_all_drift()` evaluate child wiki targets `.brain-79/<B>` recursively (memoized in `WorkspaceIndex.drift_cache`) and emit `drift_kind="transitive"` records.

---

### Pillar 4: Dedicated `_transaction.lock`, 4-Phase `session_commit` pipeline, and Hard Session Ripple Gate (`unresolved_session_ripple`)

1. **Dedicated non-reentrant transaction lock (`_transaction.lock`)**:
   - `write_many_articles()` and `commit_session()` acquire `acquire_wiki_lock(w_root, "_transaction.lock", timeout=timeout)` so inner calls to `write_article("INDEX.md")` or `regenerate_index_navigation()` never self-deadlock on `INDEX.md.lock`.
2. **Strict 4-phase execution order in `commit_session()` with Hard Session Ripple Gate (Pass 2d)**:
   - **Pass 1 (In-memory syntax/schema validation & staging in `virtual_fs`)**:
     - Validate frontmatter schema and markdown structure for all `writes` and `edits`, populating `virtual_fs`. Validate `verified_articles` format (`path` exists, `reason` $\ge 20$ chars).
   - **Pass 2 (Post-staging target check, anti-sprawl check, bottom-up verification, digest convergence & Hard Ripple Gate)**:
     - Acquire `_transaction.lock` and build `ws_index = WorkspaceIndex.build(project_root, w_root, overlay_fs=virtual_fs)`.
     - **2a. Validate `applies_to_target_missing` and `duplicate_governance_target` (Anti-Sprawl Guard)** across written/edited articles in `virtual_fs`.
     - **2b. Stamp digests for `written_article_keys + edited_article_keys` in memory** (`virtual_fs` and `manifest_staging`).
     - **2c. Bottom-up evaluation of `verified_articles`**: evaluate Guards A, B, and C (AST Public API check) on leaf articles first, update their digests in `virtual_fs` and `manifest_staging`, clear `ws_index.drift_cache`, and then evaluate umbrella articles in `verified_articles`.
     - **2d. Hard Session Ripple Gate (`unresolved_session_ripple` — Objective 1 & 4 enforcement)**:
       - Runs whenever `writes`, `edits`, `verified_articles`, **or `handoff`** is committed.
       - Compute remaining drift across the wiki over `overlay_fs=virtual_fs` and `manifest_staging`.
       - Identify the **Session Ripple Set (`session_ripple_articles`)**:
         1. **Intra-wiki umbrella ripple**: any strictly active umbrella article whose `applies_to` matches an article modified or created in this commit (`written_article_keys` or `edited_article_keys`) and which still has unresolved drift against `virtual_fs`.
         2. **Modified working-tree code ripple**: any strictly active article that already has a stamped `applies_to_digest` and governs a workspace file currently modified/added/deleted in the Git working tree (`git status --porcelain=v1 -z`) and still has unresolved drift—**except** when committing a pure zero-code research/knowledge session (`handoff.session_type in {"research", "brainstorming", "analysis", "writing"}` where all `writes`/`edits` target `topics/` or `context/`), so unrelated dirty `.py` files never block domain research commits.
       - If `session_ripple_articles` is non-empty (and `allow_partial_ripple` is not set), **reject the commit in Pass 2d** with `ValidationError(rule="unresolved_session_ripple")`:
         `"Holistic update required: your session changes impacted governing/umbrella article(s) {session_ripple_articles}, which remain drifted. Update their prose in 'edits' (or include eligible internal code refactors in 'verified_articles') within this same session_commit."`
   - **Pass 3 (Single atomic disk persistence of articles, `.drift_manifest.json`, and `INDEX.md`)**.
   - **Pass 4 (Post-persistence `write_handoff()` so `wiki_digest` is 100% `fresh`)**.

---

### Pillar 5: Anti-rubber-stamping guards + Guard C (AST Public API Signature Verification)

1. **Structured `verified_articles` contract (`{"path": str, "reason": str}` with `len(reason) >= 20`)**.
2. **Three mechanical prohibitions on `verified_articles`**:
   - **Guard A (`verified_article_structural_change_forbidden`)**: rejects `verified_articles` if the article has any drift record with `drift_kind in {"added", "deleted", "missing"}`.
   - **Guard B (`verified_article_umbrella_bypass_forbidden`)**: rejects `verified_articles` if (after resolving leaf verifications in Pass 2c) the article still has any drift record targeting an intra-wiki `.brain-79/*.md` article.
   - **Guard C (`verified_article_public_signature_changed` — AST Public API Diff Check)**:
     - For every modified `.py` target file (`drift_kind == "modified"`) of an article in `verified_articles`, if the workspace is a Git repository with a valid `HEAD`:
       - Determine the baseline commit `base_rev` at which the governing article `.brain-79/<article_path>` was last committed (`git log -1 --format=%H -- .brain-79/<article_path>`, falling back to `HEAD` if the article has no prior commit history). This ensures Guard C detects public API changes even if the developer/agent already ran `git commit` on the `.py` file earlier in the session before calling `brain79_session_commit`.
       - Read baseline content via `git show <base_rev>:<project_rel_posix_path>` (timeout 2s) and current disk content, and parse both using Python's standard `ast.parse()`.
       - Extract the **Public Symbol Signature Map** for each module:
         - Top-level public functions (`ast.FunctionDef` / `ast.AsyncFunctionDef` where `not name.startswith("_")`): tuple of `(arg_names, kwonly_names, vararg, kwarg, num_defaults)`.
         - Top-level public classes (`ast.ClassDef` where `not name.startswith("_")`): tuple of public method names and their argument signatures.
       - If the public signature map of disk differs from `base_rev` (a public function, class, method, or parameter was added, removed, or renamed), raise `ValidationError(rule="verified_article_public_signature_changed")` naming the exact changed symbol(s) (`e.g., def commit_session, class WorkspaceIndex`) and requiring a real documentation update via `writes` or `edits` instead of `verified_articles`!

---

### Pillar 6: Unbounded Signal 1 (`applies_to`) Context + Working-Tree Auto-Binding in `orient()` (Objective 3 fix)

To guarantee that an agent calling `brain79_orient()` reads **all** governing articles (e.g., all 7 articles governing the touched files, never truncated to 3 or 4):

1. **Unconditional Git working-tree path discovery in `orient()` (even when `task=None` and `paths=None`)**:
   - In `src/brain79/core/orient.py`, working-tree path discovery (`git status --porcelain=v1 -z` modified, staged, and untracked code files, capped at 50 paths) executes **before** checking `if task or paths:` and merges discovered paths into `effective_paths`.
   - Even if an agent calls `brain79_orient()` with zero arguments (`task=None, paths=None`) or `brain79_orient(task="update the wiki")`, Signal 1 automatically matches every article governing the files modified in the current session, and `## ⚠️ Documentation Drift Alerts` is always rendered whenever any active drift exists!
2. **Unbounded Signal 1 + Signal 3 in `rank_context_articles()` (`src/brain79/core/context.py`)**:
   - Partition `candidates` into:
     - `signal1_candidates`: all candidates with a deterministic Signal 1 `applies_to` match (`any(r.startswith("path:") for r in reasons)`).
     - `signal2_only_candidates`: candidates matched only via Signal 2 keyword TF-IDF.
   - **Zero truncation on Signal 1**: `signal1_candidates` is **never** sliced by `top_n`! If 7 articles match `paths` via `applies_to`, all 7 are kept in `top_candidates`, plus up to `max(0, top_n - len(signal1_candidates))` additional Signal 2 keyword matches (or `top_n` Signal 2 matches when `signal1_candidates` is empty), followed by all Signal 3 1-hop active ADRs.
3. **Token-budgeted full inlining (`64,000` chars) + Mandatory Reading Manifest fallback**:
   - `orient()` inlines the full markdown body of all ranked articles up to `MAX_ORIENT_INLINE_CHARS = 64_000` (~16,000 tokens, sufficient for 8–12 full articles).
   - If an unusually broad query exceeds `64,000` characters after inlining the first $K$ articles, `orient()` **never drops the remaining governing articles**: it lists every remaining article with its `summary`, `applies_to`, and H2 section headers inside a **`## 🚨 Mandatory Reading Manifest (Must Read Before Editing)`** section with an explicit `brain79_read_batch` instruction.

---

### Pillar 7: Direct vs. Transitive drift visibility in `orient()` and `prepare_curation_guide()`

1. **Actionable Direct vs. Transitive drift alerts in `brain79_orient()`**:
   - `orient()` labels each drift alert as `[DIRECT]` or `[TRANSITIVE]` and includes the actionable instruction:
     `Update drifted articles via brain79_edit/brain79_write, or pass eligible internal leaf code refactors in verified_articles=[{"path": "...", "reason": "..."}] during brain79_session_commit.`
2. **Full Session Impact Map in `prepare_curation_guide()` (`brain79_ingest`)**:
   - Lists all currently drifted articles (direct and transitive) plus all governing articles for files modified in `git status`, giving the agent a complete checklist before calling `brain79_session_commit`.

---

## Self-wiki reconditioning specification: As-Is Baseline vs. To-Be Golden Blueprint

To validate Phase 6.7 against a real, organically evolved 42-article engineering wiki (and turn this repository's `.brain-79/` into the canonical reference implementation), Phase 6.7 defines a formal **Before vs. After Golden Blueprint Integration Test**.

### 1. Immutable pre-reconditioning snapshot (`tests/fixtures/wiki_pre_6_7_snapshot/`)

Before modifying any existing article in `.brain-79/` during Phase 6.7 implementation:
1. Copy the entire pre-reconditioning `.brain-79/` directory (excluding `.locks/`) to `tests/fixtures/wiki_pre_6_7_snapshot/.brain-79/`.
2. Generate `tests/fixtures/wiki_pre_6_7_snapshot/SNAPSHOT_MANIFEST.json` recording:
   - `file_count`: exact number of files in the snapshot.
   - `files`: dictionary mapping each relative POSIX path inside `.brain-79/` to its `sha256` hex digest.
3. **Immutability invariant**: every test run verifies that all files in `tests/fixtures/wiki_pre_6_7_snapshot/.brain-79/` match `SNAPSHOT_MANIFEST.json` byte-for-byte, copying the snapshot into an isolated `tmp_path` before executing diagnostic or migration tests.

### 2. Quantitative comparison: As-Is Baseline (Before) vs. To-Be Golden Blueprint (After)

| Dimension | As-Is Baseline (`wiki_pre_6_7_snapshot`) | To-Be Golden Blueprint (Live `.brain-79/` after Phase 6.7) |
|---|---|---|
| **Active articles missing `applies_to` (`unanchored_governance_article`)** | **7 articles** (`architecture/dispatcher.md`, `architecture/mcp-server.md`, `architecture/symmetry.md`, `features/cli.md`, `features/mcp-server.md`, `features/handoff-continuity.md`, `features/handoff-purge.md`) | **0 articles** (100% of active `architecture` and `feature` articles declare verified `applies_to` patterns) |
| **Articles with `applies_to_digest` & `.drift_manifest.json` leaf entries** | **0 articles** | **100%** of active articles with `applies_to` |
| **Handoff feature fragmentation (Wiki Sprawl)** | **3 overlapping articles** (`features/handoff-continuity.md`, `features/handoff-freshness.md`, `features/handoff-purge.md`) governing `handoff.py` / `handoff_freshness.py` | **1 consolidated canonical article** (`features/handoff-continuity.md`, `status: shipped`) covering creation, freshness/authority decay, research guard, and purge, with all incoming links in `decisions/` and `changelog/` updated |
| **Closed historical defect backlog status** | `architecture/defect-backlog.md` marked `stability: stable` (polluting active architecture context) | `architecture/defect-backlog.md` transitioned to `stability: archived` (in `INACTIVE_STATUSES`, emitting `0 info` in `lint --strict`) |
| **Source code coverage (`src/brain79/**/*.py`)** | Partial (`__main__.py`, `cli/io.py`, `config.py` unanchored) | **100%** of `.py` files under `src/brain79/` governed by $\ge 1$ active article |
| **Semantic version & command/tool counts in prose** | Stale (`v1.1` / `v2.0.2`, 16 CLI commands, 14 MCP tools) | Synchronized to **`v0.8.0`**, **22 CLI subcommands**, and **20 MCP tools** |
| **Active drift (`detect_all_drift()`)** | Undetected semantic drift across 7 core articles | **`[]` (0 drifted articles — direct or transitive)** |
| **Organizational lint (`brain79 lint --strict`)** | Passes only because anchoring & digest rules did not exist | **`[Status: OK]` (`0 critical, 0 warning, 0 orphan, 0 info`)** under full Phase 6.7 rules |
| **Handoffs directory (`handoffs/`)** | 5 historical handoffs accumulated across prior phases | Purged via `handoff-purge` and replaced with **1 `fresh` handoff** at Phase 6.7 completion |

### 3. Target article-by-article Golden Blueprint matrix

| Wiki article | Target status / stability | Required `applies_to` anchoring | Required reconditioning action |
|---|---|---|---|
| `product/overview.md` | active | `.brain-79/SCHEMA.md`, `.brain-79/features/*.md`, `src/brain79/__init__.py` | Update Cold Start step 1 to `brain79_orient()` and document the Two-Call Session Protocol (`v0.8.0`). |
| `architecture/current-state.md` | `stable` | `.brain-79/decisions/adr-*.md`, `.brain-79/features/*.md`, `src/brain79/__init__.py` | Update to `v0.8.0`, synthesize Phases 6, 6.5, 6.6, 6.7, and link ADRs 001–017. |
| `architecture/symmetry.md` | `stable` | `src/brain79/cli/dispatch.py`, `src/brain79/server.py`, `tests/test_symmetry.py` | Update mapping table to all 22 CLI subcommands and 20 MCP tools (`orient`, `session-commit`, `read-batch`, `verified_articles`). |
| `architecture/dispatcher.md` | `stable` | `src/brain79/__main__.py`, `src/brain79/cli/dispatch.py`, `src/brain79/cli/io.py` | Anchor and document all 22 whitelisted subcommands, I/O helpers, and exit codes. |
| `architecture/mcp-server.md` | `stable` | `src/brain79/server.py`, `src/brain79/__main__.py` | Anchor and document all 20 MCP tools, `_unpack_nested_args` proxy unpacking, and stdio server lifecycle. |
| `architecture/roadmap-industrial-scale.md` | `stable` | `.brain-79/features/*.md` | Mark Phase 6.7 completed (`v0.8.0`) upon implementation close. |
| `architecture/defect-backlog.md` | `archived` | `src/brain79/core/wiki.py`, `src/brain79/core/session_commit.py` | Transition `stability` from `stable` to `archived` (all defects remediated in Phases 5.5–6; exempt from `legacy_needs_review`). |
| `features/cli.md` | `shipped` | `src/brain79/cli/dispatch.py`, `src/brain79/cli/io.py` | Update from 16 to 22 subcommands (`orient`, `session-commit`, `read-batch`, `context`, `handoff-purge`). |
| `features/mcp-server.md` | `shipped` | `src/brain79/server.py` | Update to `v0.8.0`, document all 20 MCP tools, section projection, and `verified_articles`. |
| `features/handoff-continuity.md` | `shipped` | `src/brain79/core/handoff.py`, `src/brain79/core/handoff_freshness.py` | **Consolidate** `handoff-continuity.md`, `handoff-freshness.md`, and `handoff-purge.md` into this single canonical article (11 `session_type` values, ADR-016 freshness/authority decay, research guard, and `handoff-purge`); remove the 2 redundant files, purge their entries from `.navigation_registry.json` and `.drift_manifest.json`, and update all incoming links across `.brain-79/` (`architecture/roadmap-industrial-scale.md`, `architecture/current-state.md`, `decisions/adr-012-*.md`, `decisions/adr-016-*.md`, and `changelog/*.md`). |
| `features/organizational-enforcement.md` | `shipped` | `src/brain79/core/lint.py`, `src/brain79/core/lint_organizational.py`, `src/brain79/core/validation.py`, `src/brain79/core/frontmatter.py`, `src/brain79/core/navigation.py`, `src/brain79/core/migration.py` | Document `unanchored_governance_article`, `applies_to_target_missing`, `duplicate_governance_target`, and `.drift_manifest.json`. |
| `features/cross-platform-and-lock-isolation.md` | `shipped` | `src/brain79/core/locks.py`, `src/brain79/config.py` | Add `src/brain79/config.py` and document `_drift_manifest.lock` and `_transaction.lock`. |
| `features/session-triage-and-research-persistence.md` | `shipped` | `src/brain79/core/session_commit.py`, `src/brain79/core/curate.py`, `src/brain79/core/orient.py`, `src/brain79/core/context.py`, `src/brain79/core/wiki.py`, `src/brain79/core/bootstrap.py`, `src/brain79/core/init_project.py` | Ensure full coverage of core workflow modules and link to Phase 6.7 ripple gates. |
| `features/transitive-drift-and-ripple-guards.md` | `shipped` (at close) | `src/brain79/core/drift.py`, `src/brain79/core/context.py`, `src/brain79/core/session_commit.py`, `src/brain79/core/orient.py` | Transition `status` from `planned` to `shipped` upon Phase 6.7 completion. |
| `features/version-governance.md` | `shipped` | `src/brain79/__init__.py`, `pyproject.toml` | Verify `v0.8.0` alignment under ADR-017. |
| `features/project-upgrade-and-multi-harness-doctor.md` | `planned` | `src/brain79/core/init_project.py`, `src/brain79/core/migration.py` | Keep `status: planned` (`version: 0.8.0`) as the next roadmap milestone (Phase 7). |

---

## Acceptance criteria and verification design (Gate 0)

Before declaring Phase 6.7 complete, the implementation must pass all three verification tiers below: **Tier 1 (Behavioral Acceptance Criteria mapped to the 4 core user goals)**, **Tier 2 (Deterministic Engine & Concurrency Invariants)**, and **Tier 3 (Quantitative SLAs, Self-Hosting Zero-Drift Gate, and Real-Agent E2E Smoke Testing)**.

### Tier 1: Behavioral acceptance criteria (the 4 user goals)

| ID | User goal | Given / When / Then acceptance test | Verification method |
|---|---|---|---|
| **AC-B1** | **Holistic & organic updates** (never update some articles while leaving others stale) | **Given** an active umbrella article (`architecture/current-state.md`) governing `.brain-79/decisions/adr-*.md` and `.brain-79/features/*.md`, or two active articles (`features/cli.md`, `architecture/symmetry.md`) governing `src/brain79/cli/dispatch.py`.<br>**When** `commit_session()` is called creating `decisions/adr-018.md` (or after modifying `dispatch.py` in the git working tree) while omitting `architecture/current-state.md` (or `architecture/symmetry.md`) from `writes`/`edits`/`verified_articles`.<br>**Then** Pass 2d **must abort the commit** with `ValidationError(rule="unresolved_session_ripple")`, writing 0 bytes to disk and naming the exact omitted article(s); and **must succeed** once all impacted articles are included in the same `session_commit`. | `test_ac_b1_holistic_ripple_gate_blocks_partial_commit` |
| **AC-B2** | **No uncontrolled wiki sprawl** (edit existing article instead of creating redundant duplicates) | **Given** an existing strictly active article `features/handoff-continuity.md` (`status: shipped`) governing `src/brain79/core/handoff.py`.<br>**When** `write_article()` or `commit_session()` attempts to create a new article `features/handoff-v2.md` whose code targets are 100% subsumed ($T_{\text{new}} \subseteq T_E$) by `features/handoff-continuity.md` without declaring `supersedes: features/handoff-continuity.md` (even if `related` is present).<br>**Then** pre-flight validation **must reject the creation** with `ValidationError(rule="duplicate_governance_target")` and instruct the agent to update `features/handoff-continuity.md` via `brain79_edit`. | `test_ac_b2_anti_sprawl_blocks_duplicate_feature_creation` |
| **AC-B3** | **Complete governing context reading** (read all 7 governing articles, never truncated to 3 or 4) | **Given** a workspace where **7 active articles** govern the target files via Signal 1 (`applies_to`) plus **2 linked ADRs** via Signal 3.<br>**When** `orient(task=..., paths=...)` is called with default `max_articles=4` (or `orient()` is called with `task=None, paths=None` while those files are modified in `git status`).<br>**Then** `orient()` **must return and inline all 7 Signal 1 articles + all 2 Signal 3 ADRs (9 total, 0 dropped by `max_articles=4`)**; and if total content exceeds `64,000` chars, every overflow article must appear in `## 🚨 Mandatory Reading Manifest (Must Read Before Editing)` with its summary, `applies_to`, and H2 headings. | `test_ac_b3_orient_returns_all_seven_signal1_articles_untruncated` |
| **AC-B4** | **Total trust on "update the wiki" at session end** (no fake rubber-stamping when public code APIs change) | **Given** a modified `.py` file (`src/brain79/server.py`) where a public function (`def new_tool(...)`) or public class/parameter signature was added, removed, or altered compared to the commit where `features/mcp-server.md` was last updated (`git log -1 --format=%H -- .brain-79/features/mcp-server.md` or `HEAD`).<br>**When** `commit_session()` is called attempting to silence drift on `features/mcp-server.md` via `verified_articles=[{"path": "features/mcp-server.md", "reason": "Internal refactor only without public API changes"}]`.<br>**Then** Guard C **must reject the commit** with `ValidationError(rule="verified_article_public_signature_changed")` naming the changed public symbol; whereas if only private helpers (`_helper`) or function body statements changed, `verified_articles` succeeds. | `test_ac_b4_ast_guard_blocks_verified_articles_on_public_api_change` |

---

### Tier 2: Deterministic engine & concurrency invariants

| ID | Invariant | Acceptance criteria | Verification method |
|---|---|---|---|
| **AC-E1** | **Multi-hop DAG transitivity & cycle immunity** | Modifying `src/brain79/server.py` immediately marks `features/mcp-server.md` as `[DIRECT]` drifted (`drift_kind="modified"`) and `architecture/current-state.md` as `[TRANSITIVE]` drifted (`drift_kind="transitive"`) in both standalone `check_article_drift("architecture/current-state.md")` and `detect_all_drift()`. Bidirectional cycles (`Article A ↔ Article B`) converge in 1 pass and terminate in $O(V + E)$ time with zero hash oscillation. | `test_ac_e1_two_hop_transitive_drift_and_cycle_immunity` |
| **AC-E2** | **Exact leaf attribution (`.drift_manifest.json`) & 0-match safety** | In a 10-file glob `src/core/*.py`, modifying `b.py` (even with an older git rebase timestamp), deleting `c.py`, and adding `k.py` reports drift **only** on `b.py` (`modified`), `c.py` (`deleted`), and `k.py` (`added`)—never blaming untouched files or `patterns[0]`. Deleting all governed files of an active article (`0` matches) preserves `applies_to_digest` and emits `deleted` + `missing` records. | `test_ac_e2_merkle_leaf_attribution_and_zero_match_safety` |
| **AC-E3** | **Batch ordering, `_transaction.lock` & post-persistence `fresh` handoff** | Calling `commit_session(writes=[umbrella_doc, child_adr], handoff={...})` where `writes[0]` references `writes[1]` in `applies_to` succeeds without false `applies_to_target_missing` (Pass 2a), does not self-deadlock on `INDEX.md.lock` (`_transaction.lock`), and produces a handoff whose `compute_handoff_freshness()` state is immediately **`fresh`** (Pass 4). | `test_ac_e3_batch_order_transaction_lock_and_fresh_handoff` |
| **AC-E4** | **Bottom-up leaf-first `verified_articles` resolution** | When an internal code refactor causes direct drift on leaf `features/mcp-server.md` and transitive drift on umbrella `architecture/current-state.md`, passing `verified_articles` for `features/mcp-server.md` (or both) resolves the transitive drift in Pass 2c without raising `verified_article_umbrella_bypass_forbidden`. If `features/mcp-server.md` had its prose/summary edited, passing `current-state.md` in `verified_articles` is rejected with `verified_article_umbrella_bypass_forbidden`. | `test_ac_e4_bottom_up_verified_articles_resolution` |
| **AC-E5** | **64 KB CRLF/BOM/Latin-1 byte-streaming & glob symmetry** | A file with Windows `\r\n`, UTF-8 BOM (`\xef\xbb\xbf`), and Latin-1 (`0xe9`) bytes produces the exact same `sha256:<16-hex>` digest as its LF (`\n`) BOM-free counterpart via 64 KB chunk streaming. `context.py` and `drift.py` return 100% identical match sets across `*` (single-segment), `**` (multi-segment), directory prefixes (`src/core` vs `src/core/`), and custom schema directories (`rfcs/*.md`). | `test_ac_e5_byte_streaming_crlf_bom_and_glob_symmetry` |
| **AC-E6** | **Non-blocking tactical code commits vs. strict write-time validation** | Editing or deleting a `.py` file in a dirty working tree emits `documentation_drift_suspected` / `applies_to_target_missing` at `severity="info"` so `brain79 lint --strict` exits `0` during tactical code commits, whereas authoring an active `architecture`/`feature` without `applies_to` fails `brain79 lint --strict` (`unanchored_governance_article`, `severity="warning"`) and authoring an active article with a non-existent `applies_to` pattern raises `ValidationError(rule="applies_to_target_missing")` on write. | `test_ac_e6_lint_strict_non_blocking_on_dirty_code_tree` |

---

### Tier 3: Quantitative SLAs, self-hosting gate & real-agent E2E smoke test

1. **SLA-1 — Cold Start Latency & Subprocess Bound**:
   - `brain79_orient()` on the Brain-79 repository ($\ge 35$ articles, $\ge 100$ tracked workspace files) must complete in **$< 100\text{ ms}$** wall-clock time and spawn at most **1** `git ls-files` subprocess call per invocation.
2. **SLA-2 — 1:1 CLI/MCP Symmetry (`tests/test_symmetry.py`)**:
   - `verified_articles` and `allow_partial_ripple` must maintain 100% parity between `brain79_session_commit` (MCP) and `brain79 session-commit` JSON payload (CLI).
3. **SLA-3 — Self-Hosting Golden Blueprint Gate on `.brain-79/` (Before vs. After Integration Proof)**:
   - **Immutable Pre-6.7 Baseline Fixture (`tests/fixtures/wiki_pre_6_7_snapshot/`)**:
     - An immutable copy of `.brain-79/` prior to Phase 6.7 reconditioning is stored in `tests/fixtures/wiki_pre_6_7_snapshot/.brain-79/` alongside `SNAPSHOT_MANIFEST.json` (recording SHA-256 digests of every pre-reconditioning file so tests can verify the fixture is never mutated).
     - **Diagnostic "Before" Proof (`test_pre_6_7_snapshot_diagnostic_baseline`)**: copying `wiki_pre_6_7_snapshot` into an isolated `tmp_path` and running the Phase 6.7 engine must deterministically detect:
       1. The 7 unanchored active articles (`architecture/dispatcher.md`, `architecture/mcp-server.md`, `architecture/symmetry.md`, `features/cli.md`, `features/mcp-server.md`, `features/handoff-continuity.md`, `features/handoff-purge.md`) via `unanchored_governance_article`.
       2. Overlapping target sprawl across the 3 handoff feature articles (`handoff-continuity.md`, `handoff-freshness.md`, `handoff-purge.md`).
       3. `0` articles with `applies_to_digest` prior to migration, and 100% automatic digest + `.drift_manifest.json` seeding upon running `migrate_wiki(apply=True)`.
   - **Reconditioned "After" Golden Blueprint (`test_golden_wiki_blueprint_verification`)**:
     - After reconditioning the live `.brain-79/` repository wiki:
       1. **Sprawl consolidation & registry orphan purge**: `handoff-continuity.md`, `handoff-freshness.md`, and `handoff-purge.md` are consolidated into a single canonical `features/handoff-continuity.md` (`status: shipped`, governing `src/brain79/core/handoff.py` and `src/brain79/core/handoff_freshness.py`), deleted files are automatically purged from `.navigation_registry.json` and `.drift_manifest.json`, and all incoming references across `.brain-79/` (`architecture/`, `decisions/`, `changelog/`) are updated (`0` broken links).
       2. **Historical lifecycle accuracy**: `architecture/defect-backlog.md` is transitioned to `stability: archived` (exempt from `legacy_needs_review`, emitting `0 info`).
       3. **100% source code governance coverage**: every `.py` module under `src/brain79/` is matched by the `applies_to` of at least 1 strictly active article in `.brain-79/`.
       4. **100% digest & manifest synchronization**: `detect_all_drift()` returns `[]` (0 drifted articles), `.brain-79/.drift_manifest.json` contains valid leaf maps for all active anchored articles, and `brain79 lint --strict` reports `0 critical, 0 warning, 0 orphan, 0 info`.
4. **SLA-4 — Real-Agent E2E Behavioral Smoke Test (`scripts/run_e2e_smoke.py` — Scenario 4)**:
   - Extend `scripts/run_e2e_smoke.py` with **Scenario 4 (Holistic Ripple & Unbounded Context Verification)**: in a Git software project with 6 governing articles and an umbrella `architecture/overview.md`, a real `pi` agent modifies a governed `.py` module, runs `brain79_orient`, and is asked to "update the wiki and wrap up". The test verifies that the agent updates both the leaf feature article and the umbrella `architecture/overview.md` in `brain79_session_commit` leaving `0` drifted articles.

---

[← Volver al Índice](../INDEX.md)
