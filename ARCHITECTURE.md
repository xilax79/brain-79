# brain-79 architecture and technical specifications

> **System architecture, design principles, and mechanical runtime invariants.**

---

## 1. System overview and the dual-memory model

`brain-79` separates memory into two distinct operational tiers to prevent context confusion between immediate session tasks and long-term repository knowledge:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             LONG-TERM MEMORY                                │
│                     (.brain-79/ - curated knowledge wiki)                   │
│                                                                             │
│  • Single source of truth for repository context                            │
│  • Product requirements, architecture, ADRs, domain rules                   │
│  • Enforced YAML frontmatter and strict directory schemas                   │
└──────────────────────────────────────▲──────────────────────────────────────┘
                                       │
                                       │ Promoted via brain79_ingest
                                       │
┌──────────────────────────────────────┴──────────────────────────────────────┐
│                             SHORT-TERM MEMORY                               │
│                 (.brain-79/handoffs/handoff-<timestamp>.md)                 │
│                                                                             │
│  • Tactical state records generated at session boundaries                   │
│  • Clear separation between completed tasks and pending tasks               │
│  • Immutable transition log preventing context loss                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Hierarchy and conflict resolution rules

1. **Wiki primacy:** the wiki is the absolute source of truth. If a tactical handoff contradicts a wiki article, the wiki wins.
2. **Deviation justification:** a handoff may record an active deviation from the wiki only if it supplies an explicit, non-empty `wiki_deviation_justification`.
3. **Knowledge promotion:** critical discoveries flagged under `knowledge_pending_promotion` in a handoff trigger a runtime banner during `brain79_handoff_read`, instructing the incoming agent to distill those insights into the permanent wiki.

---

## 2. Core architectural layers

The system is organized into four clean, isolated layers:

```
                      [ AI agents ]            [ Developers & CI ]
                   (Pi, Claude, etc.)            (Terminal CLI)
                             │                         │
                             ▼                         ▼
  LAYER 1: INTERFACE   FastMCP stdio server      CLI dispatcher
                             (server.py)       (cli/dispatch.py)
                             └──────────┬──────────────┘
                                        ▼ (1:1 symmetry)
  LAYER 2: CORE ENGINE       Wiki operations and linter
                             (core/wiki.py, core/lint.py)
                                        │
                                        ▼
  LAYER 3: VALIDATION        Mechanical enforcement
                             (core/frontmatter.py, validation.py)
                                        │
                                        ▼
  LAYER 4: STORAGE           Atomic filesystem and navigation registry
                             (centralized .locks/ isolation, atomic retry, JSON cache)
```

### 1. The interface layer (1:1 symmetry)
- **FastMCP stdio server:** exposes tools to agent harnesses via JSON-RPC. Suppresses all stdout pollution to guarantee clean protocol handshakes.
- **CLI dispatcher:** exposes the exact same capabilities to developers and CI with colored human terminal output, machine-readable JSON flags, and standard POSIX exit codes.
- **Guaranteed parity:** unit tests (`tests/test_symmetry.py`) programmatically enforce that every CLI command has an identical MCP tool counterpart.

### 2. The core engine
- **Search:** high-speed file operations powered by Rust-backed `ripgrep` (`rg -F`) for instant text searches, with a pure Python fallback.
- **Context retrieval:** in-memory TF-IDF context retriever with multi-language stop-word filtering.
- **Graph reachability:** graph-based reachability analysis (BFS) mapping links from `INDEX.md`.

### 3. The validation and ontology layer
- **Declarative active schema:** loads ontology rules from `.brain-79/SCHEMA.md` with in-memory nanosecond caching keyed by mtime.
- **Dual ontologies:** supports `software` profile (default: `product/`, `architecture/`, `features/`, `decisions/`, `changelog/`) and `general` profile (`context/`, `topics/`, `decisions/`, `log/`).
- **Custom folder extensions:** any repository can define custom folder rules directly in `.brain-79/SCHEMA.md` frontmatter (`custom_types`).
- **Write-time enforcement:** validates required frontmatter keys, allowed enum values, and directory locations *before* touching the disk.
- **Reference integrity:** detects broken markdown links and prevents links into internal raw directories (`_raw/`).
- **Sanitization:** masks fenced code blocks and inline code spans before link extraction to prevent false-positive warnings on sample code.

### 4. Storage, concurrency, and cross-platform portability
- **Zero cloud lock-in:** plain markdown files stored in Git under `.brain-79/`.
- **Centralized lock isolation (`.brain-79/.locks/`):** inter-process `filelock` mutexes are strictly isolated into `.brain-79/.locks/` (e.g. `.locks/_registry.lock`, `.locks/decisions__adr-001.md.lock`). Documentation directories remain 100% free of `.lock` visual clutter.
- **Resilient atomic writes:** writes commit to `.tmp` files and execute `atomic_replace_with_retry()` with exponential backoff on transient `PermissionError` (handling Windows NTFS antivirus/indexer file locks) and atomic rename on POSIX.
- **Cross-platform I/O normalization:**
  - **Linux `ext4` parity on macOS:** segment-by-segment case verification (`has_exact_case_path`) prevents case-insensitive macOS APFS bypasses.
  - **Strict POSIX paths:** all internal references and registry records use `.as_posix()`, preventing Windows backslash (`\\`) registry corruption.
  - **Strict LF line endings:** incoming content normalizes `\r\n` $\rightarrow$ `\n` across reads, edits, and `session_commit`, and all writes pass `newline="\n"`.
- **Fast navigation cache:** maintains `.navigation_registry.json` for $O(1)$ section lookups and instant `INDEX.md` regeneration.

---

## 3. Directory layout and roles

```
.brain-79/
├── SCHEMA.md        ← Authoritative validation rules and frontmatter definitions
├── INDEX.md         ← Central knowledge index (read first by agents)
├── .locks/          ← Centralized mutex directory (excluded from git and search)
├── handoffs/        ← Immutable timestamped session handoff notes
├── product/         ← Product overview, user personas, and domain requirements
├── architecture/    ← Architectural specs, current state, and roadmaps
├── features/        ← Detailed functional specifications
├── decisions/       ← Architecture Decision Records (ADRs)
└── _raw/            ← Append-only raw logs (excluded from search and index)
    ├── sessions/    ← Ingested session dumps
    └── commits/     ← Raw commit metadata
```

---

## 4. Key runtime invariants

| Component | Invariant | Purpose |
|:---|:---|:---|
| **Handoffs** | **strict immutability** | handoffs use unique timestamped files (`handoff-%Y-%m-%d-%H%M%S-%f.md`). They are never modified in place, maintaining a clean historical audit trail |
| **Handoffs** | **anti-hallucination guard** | if `pending_work` is empty, the agent is forced to explicitly write in `boot_instruction` that no pending work remains, preventing agents from imagining unfinished tasks |
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
                                             latest handoff state & promotion alerts,
                                             and inlined governing articles & ADRs

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
                                             - Pre-flight in-memory validation
                                             - Saves raw session log
                                             - Applies article writes & edits
                                             - Writes immutable handoff
                                             - Syncs navigation registry & INDEX.md
                                             - Returns unified health receipt
```

---

## 6. Strategic evolution

For the upcoming industrial roadmap (dynamic multi-domain schemas, SQLite WAL storage, single-turn session commits, and embedded local semantic search), see:
- 🗺️ [**Industrial scale roadmap**](.brain-79/architecture/roadmap-industrial-scale.md)
- 📜 [**Changelog and releases**](CHANGELOG.md)
