# brain-79 Architecture & Technical Specifications

> **System architecture, design principles, and mechanical runtime invariants.**

---

## 1. System Overview & The Dual-Memory Model

`brain-79` separates memory into two distinct operational tiers to prevent context confusion between immediate session tasks and long-term repository knowledge:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             LONG-TERM MEMORY                                │
│                     (.brain-79/ - Curated Knowledge Wiki)                   │
│                                                                             │
│  • Single source of truth for repository context                            │
│  • Product requirements, Architecture, ADRs, Domain rules                   │
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

### Hierarchy & Conflict Resolution Rules

1. **Wiki Primacy:** The Wiki is the absolute source of truth. If a tactical handoff contradicts a wiki article, the wiki wins.
2. **Deviation Justification:** A handoff may record an active deviation from the wiki only if it supplies an explicit, non-empty `wiki_deviation_justification`.
3. **Knowledge Promotion:** Critical discoveries flagged under `knowledge_pending_promotion` in a handoff trigger a runtime banner during `brain79_handoff_read`, instructing the incoming agent to distill those insights into the permanent wiki.

---

## 2. Core Architectural Layers

The system is organized into four clean, isolated layers:

```
                      [ AI Agents ]            [ Humans ]
                     (Pi, Claude, etc.)       (Terminal CLI)
                             │                      │
                             ▼                      ▼
  LAYER 1: INTERFACE   FastMCP Stdio Server     CLI Dispatcher
                      (server.py)             (cli/dispatch.py)
                             └──────────┬───────────┘
                                        ▼ (1:1 Symmetry)
  LAYER 2: CORE ENGINE       Wiki Operations & Linter
                             (core/wiki.py, core/lint.py)
                                        │
                                        ▼
  LAYER 3: VALIDATION        Mechanical Enforcement
                             (core/frontmatter.py, validation.py)
                                        │
                                        ▼
  LAYER 4: STORAGE           Atomic Filesystem & Navigation Registry
                             (POSIX filelock, atomic rename, JSON cache)
```

### 1. The Interface Layer (1:1 Symmetry)
- **FastMCP Stdio Server:** Exposes tools to agent harnesses via JSON-RPC. Suppresses all stdout pollution to guarantee clean protocol handshakes.
- **CLI Dispatcher:** Exposes the exact same capabilities to developers with colored human terminal output, machine-readable JSON flags, and standard POSIX exit codes.
- **Guaranteed Parity:** Unit tests (`tests/test_symmetry.py`) programmatically enforce that every CLI command has an identical MCP tool counterpart.

### 2. The Core Engine
- High-speed file operations powered by Rust-backed `ripgrep` (`rg -F`) for instant text searches, with a pure Python fallback.
- In-memory TF-IDF context retriever with multi-language stop-word filtering.
- Graph-based reachability analysis (BFS) mapping links from `INDEX.md`.

### 3. The Validation Layer
- **Write-Time Enforcement:** Validates required frontmatter keys, allowed enum values, and directory locations *before* touching the disk.
- **Reference Integrity:** Detects broken markdown links and prevents links into internal raw directories (`_raw/`).
- **Sanitization:** Masks fenced code blocks and inline code spans before link extraction to prevent false-positive warnings on sample code.

### 4. Storage & Concurrency
- **Zero Cloud Lock-in:** Plain Markdown files stored in Git under `.brain-79/`.
- **Atomic POSIX Writes:** All writes write to a temporary `.md.tmp` file and perform an atomic `os.replace` under an inter-process `filelock`. Crashes or terminations never leave corrupted files.
- **Fast Navigation Cache:** Maintains `.navigation_registry.json` for $O(1)$ section lookups and instant `INDEX.md` regeneration.

---

## 3. Directory Layout & Roles

```
.brain-79/
├── SCHEMA.md        ← Authoritative validation rules and frontmatter definitions
├── INDEX.md         ← Central knowledge index (read first by agents)
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

## 4. Key Runtime Invariants

| Component | Invariant | Purpose |
|:---|:---|:---|
| **Handoffs** | **Strict Immutability** | Handoffs use unique timestamped files (`handoff-%Y-%m-%d-%H%M%S-%f.md`). They are never modified in place, maintaining a clean historical audit trail. |
| **Handoffs** | **Anti-Hallucination Guard** | If `pending_work` is empty, the agent is forced to explicitly write in `boot_instruction` that no pending work remains, preventing agents from imagining unfinished tasks. |
| **Wiki IO** | **Path Traversal Protection** | All file paths are strictly resolved against the repository root using `is_relative_to`, preventing sandbox escapes. |
| **Wiki IO** | **Atomic File Mutations** | Every write or edit is guarded by a process mutex and executed through atomic temporary file replacement. |
| **Linter** | **Link & Namespace Guards** | Absolute paths, broken relative references, or references pointing into `_raw/` fail strict lint checks immediately. |

---

## 5. Typical Lifecycle: An Agent Session

```
1. COLD START
   AI Agent awakens
   │
   ├─► Calls brain79_index() ────────► Reads INDEX.md (Instant overview)
   └─► Calls brain79_handoff_read() ──► Ingests latest handoff & pending tasks

2. EXECUTION
   AI Agent designs or modifies features
   │
   ├─► Calls brain79_search(query) ──► Instant ripgrep lookup across wiki
   ├─► Calls brain79_read(path) ─────► Retrieves specific article
   └─► Calls brain79_edit(path, ...) ─► Applies targeted changes (saves tokens)

3. FINALIZATION
   AI Agent concludes work
   │
   ├─► Calls brain79_handoff_write() ─► Records what was completed & next steps
   └─► brain-79 auto-regenerates ───► Updates navigation index & runs linter
```

---

## 6. Strategic Evolution

For the upcoming industrial roadmap (dynamic multi-domain schemas, SQLite WAL storage, single-turn session commits, and embedded local semantic search), see:
- 🗺️ [**Industrial Scale Roadmap**](.brain-79/architecture/roadmap-industrial-scale.md)
- 📜 [**Changelog & Releases**](CHANGELOG.md)
