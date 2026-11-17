# Brain-79 Architecture and Technical Specifications

> **System architecture, design principles, and mechanical runtime invariants.**

---

## 1. System overview and the three-class document ontology

`brain-79` separates memory into three distinct document lifecycles governed by an explicit authority decay model (ADR-016, ADR-018):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CLASS 1: IMMUTABLE AUDIT TRAIL                        │
│                   (decisions/, changelog/, _raw/sessions/)                  │
│                                                                             │
│  • Append-only historical truth. Never deleted or compacted.                │
│  • Chesterton's Fence: past decisions remain permanent rationale.           │
│  • Decay mechanism: superseded ADRs decay in authority and cost 0 tokens.    │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────┴──────────────────────────────────────┐
│                       CLASS 2: EVERGREEN LIVING MANUALS                     │
│                       (features/, architecture/, product/)                  │
│                                                                             │
│  • Active truth of the codebase. Timeless capabilities in present tense.    │
│  • Strict Write-Time size limits: <= 400 lines and <= 20,480 bytes (20 KB). │
│  • Prohibition of temporal markers (Phase X, Sprint Y, Milestone Z, WIP).   │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────┴──────────────────────────────────────┐
│                    CLASS 3: EPHEMERAL TRANSITION NOTES                      │
│                                (handoffs/)                                  │
│                                                                             │
│  • Short-term operational bridges between sessions. Perishable by design.   │
│  • Cryptographic provenance: wiki_digest, code_digest, git_head, git_branch.│
│  • Authority decay states: fresh, stale, foreign_branch, unverified.        │
│  • Operational lifecycle: purged on-demand via brain79 handoff-purge.       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Authority hierarchy and conflict resolution rules

1. **Authority order:** `code and git > wiki > handoff`. Code is physical reality. The wiki is governed system truth. Handoffs are perishable transition notes.
2. **Authority decay (ADR-016):** when workspace code or wiki content mutates, subsequent handoff evaluations decay from `fresh` to `stale`. In `orient()`, stale handoffs are demoted to historical context, instructing incoming agents to verify current code before executing instructions.
3. **Chesterton's Fence for ADRs (ADR-018):** Architecture Decision Records are immutable audit artifacts. They are never purged, compacted, or mutated when replaced; they transition to `status: superseded` pointing to the successor ADR (`supersedes:` / `superseded_by:`), retaining past rationale at zero cost in `orient()` ranking.
4. **Living manual timelessness (ADR-018):** living manuals under `features/`, `architecture/`, and `product/` describe software capabilities evergreenly. Ephemeral project management labels (`(Phase X)`, `Sprint Y`) are mechanically rejected by both synchronous write validation and CI linter checks.

---

## 2. Core architectural layers and engines

The system is organized into six isolated layers:

```
                      [ AI agents ]            [ Developers & CI ]
               (Pi, Claude, Cursor, agy)         (Terminal CLI)
                             │                         │
                             ▼                         ▼
  LAYER 1: INTERFACE   FastMCP stdio server      CLI dispatcher
                             (server.py)       (cli/dispatch.py)
                             └──────────┬──────────────┘
                                        ▼ (1:1 symmetry: 24 CLI, 22 FastMCP)
  LAYER 2: CONTEXT     3-Signal context ranker & 1-call orientation
                       (core/orient.py, core/context.py)
                                        │
                                        ▼
  LAYER 3: DRIFT       Merkle leaf manifest & multi-hop DAG engine
                       (core/drift.py, .drift_manifest.json)
                                        │
                                        ▼
  LAYER 4: COMMIT      4-Phase transactional session commit pipeline
                       (core/session_commit.py, _transaction.lock)
                                        │
                                        ▼
  LAYER 5: PROTOCOL    Non-destructive upgrader & diagnostic doctor
                       (core/init_project.py, migration.py, doctor.py)
                                        │
                                        ▼
  LAYER 6: STORAGE     Centralized .locks/ isolation & cross-platform I/O
                       (core/locks.py, atomic retry, POSIX normalization)
```

### 1. Interface layer (1:1 symmetry)
- **FastMCP stdio server (`server.py`):** exposes 22 structured tools via JSON-RPC over stdio. Configures `output_schema=None` to prevent token duplication and suppresses stderr banner noise during initialization.
- **CLI dispatcher (`cli/dispatch.py`):** provides 24 deterministic subcommands with colored terminal output, machine-readable JSON flags, and POSIX exit codes (`0`, `1`, `2`).
- **Guaranteed parity (`tests/test_symmetry.py`):** automated tests assert that every CLI command (except setup-only `init` and `update`) maps to an identical MCP tool counterpart with parameter-level signature parity.

### 2. 3-signal context and orientation engine (`orient.py`, `context.py`)
- **Signal 1 (Target binding):** matches exact files and glob patterns declared in `applies_to` frontmatter against active workspace targets. Returns all governing articles without artificial truncation.
- **Signal 2 (Field-weighted BM25):** scores title, summary, and body text using BM25 with multi-language stop-word filtering.
- **Signal 3 (1-Hop ADR graph expansion):** follows `related` and `supersedes` graph edges to include governing decisions connected to matched features.
- **Orientation budget (64 KB ceiling):** `orient()` inlines `INDEX.md`, active handoff state with authority decay evaluation, and top governing articles up to a 64 KB token budget, rendering a Mandatory Reading Manifest if articles exceed the budget.
- **Passive protocol skew detection:** inspects `AGENTS.md` delimiters and `SCHEMA.md` `schema_version`, alerting when repository templates lag behind the installed binary.

### 3. Merkle drift and multi-hop DAG engine (`drift.py`)
- **Merkle leaf manifest (`.drift_manifest.json`):** records deterministic SHA-256 digests of all source files governed by `applies_to`. Employs 64 KB streaming chunks with CRLF and UTF-8 BOM normalization.
- **Single-pass `WorkspaceIndex`:** caches workspace file paths and digests in a single filesystem traversal, eliminating redundant I/O.
- **Multi-hop transitive propagation:** recursively propagates code mutations up the documentation DAG from leaf feature articles to composite architecture and product umbrella articles.

### 4. 4-phase transactional session commit engine (`session_commit.py`)
All session finalization executes under `.brain-79/.locks/_transaction.lock`:
- **Pass 1 (Pre-flight validation):** validates frontmatter, schemas, required sections, and size limits in-memory before mutating disk.
- **Pass 2a (Anti-sprawl guard):** verifies Jaccard overlap and target subsumption to prevent duplicate article creation.
- **Pass 2b (Merkle convergence):** computes updated digests for all written and edited articles.
- **Pass 2c (AST Guard C):** parses Python source code using `ast` to detect public signature changes (functions, classes, arguments), enforcing documentation updates while permitting private refactors.
- **Pass 2d (Hard Session Ripple Gate):** halts commits if any impacted child or umbrella article in the transitive DAG is left in a drifted state without simultaneous update or verification.
- **Pass 3 & 4 (Atomic multi-write and handoff):** applies temporary file writes with atomic retry and writes immutable handoff records.

### 5. Non-destructive protocol upgrader and doctor engine (`init_project.py`, `migration.py`, `doctor.py`)
- **Delimited blocks and progressive disclosure in `AGENTS.md`:** updates core protocol instructions between `<!-- brain79:start v{version} -->` and `<!-- brain79:end -->` while preserving custom persona headers and team project notes. Compacts root rules (`<= 6,500` bytes) and ships detailed operational manuals in the on-demand `brain79-wiki` skill.
- **Non-destructive `SCHEMA.md` synchronization:** elevates to `schema_version: 2`, preserving custom directory types and trailing extension sections.
- **Tier 1 portable MCP configuration:** auto-configures `.mcp.json` (Pi, Claude Code, Zed, OpenCode), `.agents/plugins/brain79/` (native Antigravity workspace plugin with on-demand skill), legacy `.agents/mcp_config.json`, and `.cursor/mcp.json` using portable `"command": "brain79"`.
- **Full-pass wiki reconditioning (`migrate_wiki` v2):** evaluates all articles, auto-completes fields, repairs footer backlinks, normalizes bullet colons, and downgrades incomplete articles to `legacy` status.
- **Operational diagnostics (`brain79 doctor`):** evaluates 7 health categories in $<50\text{ ms}$ with POSIX exit codes (`0/1/2`), text/JSON formats, and Git-aware `--fix` safety guards.

### 6. Storage, centralized locks, and cross-platform I/O (`locks.py`, `config.py`)
- **Zero cloud lock-in:** pure Markdown files stored directly in Git.
- **Centralized lock isolation (`.brain-79/.locks/`):** all inter-process `filelock` instances live exclusively in `.brain-79/.locks/`, eliminating `.lock` files from documentation directories.
- **Dynamic ancestor root discovery:** resolves project root by climbing upwards to an ancestor `.brain-79/` when `--project-root .` is specified, stopping at nested `.git` boundaries for subproject isolation.
- **Resilient atomic writes:** writes commit to `.tmp` files and execute `atomic_replace_with_retry()` with exponential backoff on Windows NTFS `PermissionError`.
- **Cross-platform normalization:** enforces strict POSIX paths (`.as_posix()`), pure LF (`\n`) line endings, and APFS segment-by-segment character casing parity on macOS.

---

## 3. Directory layout and roles

```
.brain-79/
├── SCHEMA.md                 ← Authoritative schema rules and frontmatter definitions
├── INDEX.md                  ← Central automated routing table (read first by agents)
├── .drift_manifest.json      ← Merkle leaf manifest tracking SHA-256 target digests
├── .navigation_registry.json ← Thread-safe navigation registry for O(1) lookups
├── .locks/                   ← Centralized mutex directory (excluded from git and search)
├── handoffs/                 ← Cryptographically stamped session handoffs
├── product/                  ← Product vision, domain models, and personas
├── architecture/             ← Subsystem topologies, current state, and roadmaps
├── features/                 ← Detailed functional living manuals
├── decisions/                ← Architectural Decision Records (ADRs)
├── changelog/                ← Versioned release records and consolidated logs
├── topics/                   ← Research findings, market data, and domain analyses
└── _raw/                     ← Append-only raw logs (excluded from search and index)
    ├── sessions/             ← Ingested session summaries
    └── commits/              ← Raw commit metadata
```

---

## 4. Key runtime invariants

| Component | Invariant | Purpose |
|:---|:---|:---|
| **Handoffs** | **strict immutability** | handoffs use unique timestamped files (`handoff-%Y-%m-%d-%H%M%S-%f.md`). They are never modified in place, maintaining a clean historical audit trail |
| **Handoffs** | **anti-hallucination guard** | if `pending_work` is empty, the agent is forced to explicitly write in `boot_instruction` that no pending work remains, preventing agents from imagining unfinished tasks |
| **Living manuals** | **write-time size limit** | living manuals exceeding 400 lines or 20,480 bytes are rejected synchronously at write time, preventing orient token budget exhaustion |
| **Living manuals** | **temporal decontamination** | milestone markers (`Phase X`, `Sprint Y`) and specification labels on shipped features are rejected across living manuals |
| **Drift engine** | **Hard Session Ripple Gate** | commits modifying governed source files cannot conclude without updating or verifying all transitively impacted articles |
| **Drift engine** | **AST Guard C verification** | mutations to public Python function or class signatures trigger strict documentation drift alerts |
| **Anti-sprawl** | **subsumption prevention** | articles governing file targets already fully covered by sibling articles are blocked from creation |
| **Wiki I/O** | **path traversal protection** | all file paths are strictly resolved against the repository root using `is_relative_to`, preventing sandbox escapes |
| **Wiki I/O** | **atomic file mutations** | every write or edit is guarded by a process mutex and executed through atomic temporary file replacement |
| **Linter** | **link and namespace guards** | absolute paths, broken relative references, or references pointing into `_raw/` fail strict lint checks immediately |

---

## 5. Typical lifecycle: the two-call session protocol

```
1. COLD START (Turn 1)
   AI agent awakens
   │
   └─► Calls brain79_orient(task, paths) ─► Ingests INDEX.md routing table,
                                             latest handoff state & authority decay evaluation,
                                             active schema summary, and inlined governing articles & ADRs

2. EXECUTION (Mid-Session)
   AI agent implements features or fixes bugs in codebase
   │
   ├─► Calls brain79_search(query) ──────► Instant ripgrep lookup across wiki
   ├─► Calls brain79_read(path, sections)► Retrieves specific sections (saves tokens)
   └─► Calls brain79_read_batch(reqs) ───► Reads multiple articles in 1 turn

3. FINALIZATION (Turn 2 — The Two-Call Protocol)
   AI agent concludes session atomically
   │
   └─► Calls brain79_session_commit(...) ─► All-or-nothing transaction:
                                             - Pass 1: pre-flight in-memory validation
                                             - Pass 2a: anti-sprawl subsumption check
                                             - Pass 2b: Merkle digest convergence
                                             - Pass 2c: AST Guard C public signature check
                                             - Pass 2d: Hard Session Ripple Gate
                                             - Pass 3: atomic article writes and edits
                                             - Pass 4: cryptographic handoff write
                                             - Navigation sync & receipt emission
```

---

## 6. Strategic evolution

Phases 0 through 7.1 are complete and active in production as of `v0.9.1`. For the upcoming execution roadmap (Phase 8: zero-clone installation via `uv tool` and visual web guide; Phase 9: automated battle-testing and chaos gauntlet), see:
- 🗺️ [**Industrial scale roadmap**](.brain-79/architecture/roadmap-industrial-scale.md)
- 📜 [**Changelog and releases**](CHANGELOG.md)
- 🏗️ [**System current state**](.brain-79/architecture/current-state.md)
