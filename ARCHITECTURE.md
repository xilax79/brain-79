# Architecture and technical specifications

Technical design, component architecture, and mechanical invariants of `brain-79`.

---

## 1. Document ontology and authority model

`brain-79` partitions workspace memory into three distinct document classes with deterministic authority rules:

```
+-----------------------------------------------------------------------------+
| Class 1: Immutable audit trail                                              |
| (decisions/, changelog/, _raw/sessions/)                                    |
| - Append-only records. Never modified or purged.                            |
| - Chesterton's Fence: superseded ADRs remain permanent rationale.           |
| - Cost 0 tokens in orient() once superseded.                                |
+--------------------------------------^--------------------------------------+
                                       |
+--------------------------------------|--------------------------------------+
| Class 2: Evergreen living manuals                                           |
| (features/, architecture/, product/)                                        |
| - Canonical truth of active repository capabilities in the present tense.   |
| - Strict size limits: <= 400 lines and <= 20,480 bytes (20 KB).             |
| - Temporal markers (Phase X, Sprint Y, WIP) prohibited by write validation. |
+--------------------------------------^--------------------------------------+
                                       |
+--------------------------------------|--------------------------------------+
| Class 3: Ephemeral transition notes                                         |
| (handoffs/)                                                                 |
| - Short-term operational bridges between working turns.                     |
| - Provenance stamping: wiki_digest, code_digest, git_head, git_branch.      |
| - Authority decay states: fresh, stale, foreign_branch, unverified.         |
| - Purged on demand via brain79 handoff-purge.                               |
+-----------------------------------------------------------------------------+
```

### Authority hierarchy

1. **`code and git > wiki > handoff`**: source code is physical reality. The wiki is governed project truth. Handoffs are perishable transition notes.
2. **Authority decay**: when governed code or wiki files mutate, subsequent handoff evaluations decay from `fresh` to `stale`. In `orient()`, stale handoffs are demoted to historical context, instructing incoming agents to verify current code before executing instructions.
3. **Chesterton's Fence for ADRs**: architectural decisions are immutable. When replaced, older ADRs receive `status: superseded` pointing to the successor ADR (`supersedes:` / `superseded_by:`), preserving rationale at zero token cost during orientation.
4. **Living manual timelessness**: manuals in `features/`, `architecture/`, and `product/` describe current state. Transient project management markers are rejected synchronously at write time.

---

## 2. Interface symmetry (MCP subset and CLI superset)

`brain-79` exposes **9 focused FastMCP server tools** as a strict subset of the **26 CLI subcommands**. Automated test suites (`tests/test_symmetry.py`) enforce `MCP_TOOLS` ⊂ `WHITELIST` and parameter parity across retained interfaces.

| Category | CLI subcommands (26) | FastMCP server tools (9) |
|:---|:---|:---|
| **Session & workflow** | `orient`, `session-commit`, `context`, `index`, `ingest` | `brain79_orient`, `brain79_session_commit`, `brain79_context` |
| **Handoff continuity** | `handoff-write`, `handoff-read`, `handoff-purge` | *Use `brain79_session_commit` / `brain79_orient` or CLI* |
| **Reading & writing** | `read`, `read-batch`, `write`, `write-many`, `edit`, `list`, `search` | `brain79_read`, `brain79_read_batch`, `brain79_edit`, `brain79_search` |
| **Governance & health** | `lint`, `ci-check`, `stats`, `schema`, `navigate`, `migrate`, `bootstrap`, `doctor`, `update-project` | `brain79_lint`, `brain79_bootstrap` |
| **Host CLI only** | `init`, `update` | *N/A (Host setup & self-update operations)* |

---

## 3. Directory layout and storage roles

```
.brain-79/
├── SCHEMA.md                 <- Authoritative schema rules and frontmatter definitions
├── INDEX.md                  <- Central automated routing table (read first by agents)
├── .drift_manifest.json      <- Merkle leaf manifest tracking SHA-256 target digests
├── .navigation_registry.json <- Thread-safe navigation registry for O(1) lookups
├── .locks/                   <- Centralized mutex directory (excluded from git and search)
├── handoffs/                 <- Cryptographically stamped session handoffs
├── product/                  <- Product vision, domain models, and personas
├── architecture/             <- Subsystem topologies, current state, and roadmaps
├── features/                 <- Detailed functional living manuals
├── decisions/                <- Architectural Decision Records (ADRs)
├── changelog/                <- Versioned release records and consolidated logs
├── topics/                   <- Research findings, market data, and domain analyses
└── _raw/                     <- Append-only raw logs (excluded from search and index)
    ├── sessions/             <- Ingested session summaries
    └── commits/              <- Raw commit metadata
```

---

## 4. Source code map (`src/brain79/`)

The implementation is organized across root, CLI, templates, and core layers (including modular `ast_guards/` and `harnesses/` subpackages):

```
src/brain79/
├── __init__.py                 <- Package metadata and single-source __version__ declaration
├── __main__.py                 <- CLI entrypoint, global flag parser, and FastMCP fallback
├── config.py                   <- Dynamic ancestor root discovery and path resolution
├── server.py                   <- FastMCP stdio server registering 9 focused JSON-RPC tools
├── cli/
│   ├── __init__.py             <- Whitelist registration and CLI runner entrypoint
│   ├── dispatch.py             <- Subcommand argument parsing, POSIX exit codes, and routing
│   └── io.py                   <- Stdio streaming, stdin ingest, and JSON formatting
├── templates/
│   └── __init__.py             <- Package resource loader for protocol and skill templates
└── core/
    ├── __init__.py             <- Core package marker
    ├── ast_guards/             <- Language-agnostic Guard C orchestrator, Python + polyglot parsers
    │   ├── __init__.py         <- Inspector registry, lazy find_spec discovery, thread-safe init
    │   ├── base.py             <- LanguageInspector protocol and SignatureDiff dataclass
    │   ├── orchestrator.py     <- Generalized has_public_api_changes() with 2 MB size guard
    │   ├── python_inspector.py <- Built-in Python AST public signature extractor
    │   ├── treesitter_inspector.py <- Optional Tree-sitter AST engine and comment-node stripper
    │   └── polyglot.py         <- Qualified signature extractors for 10 polyglot parsers
    ├── bootstrap.py            <- Scan manifest generator and initial wiki scaffolding
    ├── ci_check.py             <- Read-only CI governance gate and lifecycle hook runtime
    ├── context.py              <- 3-Signal context search (applies_to, BM25, 1-hop ADR)
    ├── curate.py               <- Amnesia Test triage and zero-code research persistence
    ├── doctor.py               <- 9-Check operational diagnostics with AST guard reporting
    ├── drift.py                <- Merkle leaf manifest, SHA-256 streaming, and DAG ripple
    ├── frontmatter.py          <- YAML frontmatter parsing, validation, and serialization
    ├── handoff_freshness.py    <- Cryptographic provenance and handoff decay evaluation
    ├── handoff.py              <- Immutable handoff creation, retrieval, and purging
    ├── init_project.py         <- Project initialization, AGENTS.md blocks, and MCP harnesses
    ├── lint_organizational.py  <- Code-fence masked regex linter for decisions and debt
    ├── lint.py                 <- Structural wiki linter (schemas, links, sections, drift)
    ├── locks.py                <- Centralized .brain-79/.locks/ file mutexes
    ├── migration.py            <- Schema v2 transformation and legacy wiki reconditioning
    ├── navigation.py           <- Thread-safe navigation registry and pure INDEX.md routing
    ├── orient.py               <- 1-Call cold-start engine (budgeted context assembly)
    ├── session_commit.py       <- 4-Phase transactional commit pipeline with ripple gates
    ├── stats.py                <- Read-only context budget telemetry and governance coverage
    ├── update.py               <- Self-update engine (zero-clone Git and editable dev checkouts)
    ├── validation.py           <- Synchronous write validation, size caps, and anti-sprawl
    └── wiki.py                 <- Atomic article I/O (read, write, edit, search) with retry
```

---

## 5. Verified trace of `orient()` (`src/brain79/core/orient.py`)

When an agent executes `brain79_orient(task, paths)` during cold start, execution proceeds through these sequential steps:

1. **Passive protocol skew detection**:
   - Inspects `AGENTS.md` for `<!-- brain79:start v{version} -->` and `SCHEMA.md` for `schema_version >= 2`.
   - Emits non-blocking advisory warnings if repository files lag behind the running binary.
2. **Table of contents and schema ingest**:
   - Reads pure routing table from `INDEX.md`.
   - Appends Active Schema Summary (profile, allowed types, required frontmatter keys) and ADR deficit alerts if decisions lack governing links.
3. **Filesystem caching (`WorkspaceIndex.build`)**:
   - Executes a single-pass filesystem crawl caching workspace file paths and SHA-256 digests.
4. **Handoff retrieval and freshness evaluation**:
   - Resolves latest handoff via `_resolve_handoff_path("latest")`.
   - Evaluates cryptographic freshness via `compute_handoff_freshness(wiki_digest, code_digest, git_head, git_branch)`.
   - Marks handoff as `fresh`, `stale` (workspace drift detected), `foreign_branch` (handoff recorded on another branch), or `unverified` (gitless).
5. **Git path discovery**:
   - Runs `git status --porcelain=v1 -z` to discover modified or untracked repository files.
6. **Code-to-wiki drift detection**:
   - Invokes `detect_all_drift()` to compute `[DIRECT]` code-level drift (via `applies_to` globs in leaf feature articles) and `[TRANSITIVE]` multi-hop drift (propagated up the DAG to architecture and product umbrella articles).
7. **3-signal context ranking (`rank_context_articles`)**:
   - **Signal 1 (Code target binding)**: matches target file paths against `applies_to` frontmatter globs without artificial length truncation.
   - **Signal 2 (Field-weighted BM25)**: ranks title, summary, and article body against the task description using multi-language stop-word filtering.
   - **Signal 3 (1-Hop ADR graph expansion)**: expands matched feature articles to include directly linked Architecture Decision Records via `related` and `supersedes` edges.
8. **Context budget enforcement (`MAX_ORIENT_INLINE_CHARS = 64_000`)**:
   - Inlines top-ranked governing articles up to the 64 KB inline character ceiling.
   - If governing articles exceed the budget, renders a structured Mandatory Reading Manifest directing the agent to ingest remaining files via `brain79_read_batch`.

---

## 6. Verified trace of `commit_session()` (`src/brain79/core/session_commit.py`)

Session finalization runs under a centralized process lock (`.brain-79/.locks/_transaction.lock`) via a 4-phase transactional pipeline:

1. **Pass 1 — Pre-flight validation (in-memory)**:
   - Sets up an in-memory `virtual_fs` overlay.
   - Validates frontmatter, schemas, required H2 sections, and size limits (<= 20 KB) for all proposed writes and edits.
   - Rejects missing handoff fields or empty `boot_instruction`.
   - Requires justification (>= 20 characters) for any article marked in `verified_articles`.
2. **Lock acquisition**:
   - Acquires inter-process mutex `.brain-79/.locks/_transaction.lock`.
3. **Pass 2a — Target integrity and anti-sprawl**:
   - Verifies all files in `applies_to` exist in the workspace (`applies_to_target_missing`).
   - Performs Jaccard overlap and containment analysis (`check_anti_sprawl_overlap`), blocking duplicate or overlapping documentation.
4. **Pass 2b — Merkle convergence**:
   - Computes SHA-256 digests of virtual file states across two fixed-point iterations until digests stabilize.
5. **Pass 2c — AST verification & bottom-up verification guards**:
   - Evaluates `verified_articles` in leaf-then-umbrella order.
   - **Guard A**: rejects articles not currently in a drifted state.
   - **Guard B**: rejects verification if the article's own `applies_to` code targets were modified in this turn.
   - **Guard C (AST signature guard)**: dispatches modified governed files through `core/ast_guards/` (`PythonInspector` by default, optional `brain79[polyglot]` Tree-sitter parsers, or custom `LanguageInspector` implementations). If public functions, classes, types, or parameter signatures mutated, blocks verification without documentation updates while permitting internal body/private refactors.
6. **Pass 2d — Hard Session Ripple Gate (`unresolved_session_ripple`)**:
   - Evaluates the transitive documentation DAG.
   - If any child leaf or composite umbrella article remains in a drifted state without simultaneous update or verification, halts the transaction with an actionable list of unresolved articles.
7. **Pass 3 — Atomic persistence**:
   - Writes updated `.drift_manifest.json`.
   - Records session transcript under `_raw/sessions/`.
   - Writes all validated articles to disk with `_skip_nav_regen=True`.
   - Rebuilds `.navigation_registry.json` and `INDEX.md` once in a single thread-safe pass.
8. **Pass 4 — Handoff persistence and release**:
   - Writes immutable, timestamped handoff record under `handoffs/`.
   - Releases transaction lock and returns structured commit receipt.

---

## 7. Storage, concurrency, and cross-platform I/O

- **Plain Markdown storage**: all knowledge persists as human-readable Markdown in Git without external databases.
- **Centralized lock isolation (`.brain-79/.locks/`)**: file locks live in `.brain-79/.locks/`, preventing `.lock` clutter inside wiki folders.
- **Windows NTFS retry**: file replacements use `atomic_replace_with_retry()` with exponential backoff to handle transient `PermissionError` file-locking on Windows.
- **Cross-platform path and text normalization**:
  - Paths strictly use POSIX format (`.as_posix()`).
  - Text files use pure LF (`\n`) line endings.
  - Case-insensitive APFS parity checks on macOS prevent duplicate case collisions.
  - 64 KB chunked SHA-256 streaming normalizes CRLF and UTF-8 BOM before hashing.

---

## 8. Runtime invariants summary

| Invariant | Scope | Enforcement mechanism |
|:---|:---|:---|
| **Handoff immutability** | `handoffs/` | Timestamped filenames (`handoff-%Y-%m-%d-%H%M%S-%f.md`). Never overwritten. |
| **Anti-hallucination work tracking** | `handoffs/` | If `pending_work` is empty, `boot_instruction` must explicitly declare no pending work remains. |
| **Living manual size cap** | `features/`, `architecture/`, `product/` | Synchronously rejected if exceeding 400 lines or 20,480 bytes. |
| **Temporal decontamination** | `features/`, `architecture/`, `product/` | Milestone labels (`Phase X`, `Sprint Y`) rejected by write validator and strict linter. |
| **Hard Session Ripple Gate** | Session finalization | Commits halted if governed code changes leave child or umbrella articles drifted. |
| **AST Guard C** | Verification bypass | Public signature changes block rubber-stamp verification without documentation updates. |
| **Anti-sprawl subsumption** | Article creation | Rejects articles whose target scopes are completely contained in existing sibling docs. |
| **Path traversal containment** | File I/O | All paths validated via `is_relative_to(project_root)` before filesystem access. |
| **Atomic state replacement** | File mutations | Writes staged to `.tmp` files and committed via atomic rename with retry. |
| **Strict backlink invariant** | Wiki articles | Every article must terminate with `[← Volver al Índice](../INDEX.md)`. |
