# brain-79 Architecture & Design Specifications

This document outlines the internal architecture, design principles, and runtime invariants governing `brain-79`.

---

## 1. Dual-Memory Model & Adversarial Hierarchy

`brain-79` enforces a strict two-tier memory hierarchy:

```
+-------------------------------------------------------------+
|                      Long-Term Memory                       |
|               (.brain-79/ - Curated LLM Wiki)               |
|   • Invariant source of truth for repository context        |
|   • Architecture, ADRs, Domain Rules, Product Specifications|
+-------------------------------------------------------------+
                              ▲
                              | (Promoted via brain79_ingest)
+-------------------------------------------------------------+
|                      Short-Term Memory                      |
|          (.brain-79/handoffs/handoff-<timestamp>.md)        |
|   • Tactical, session-bound state transitions               |
|   • Strict isolation of completed vs. pending tasks         |
+-------------------------------------------------------------+
```

### Hierarchy Rules & Conflict Resolution
- **Wiki Primacy:** The Wiki is the ultimate source of truth. If a short-term handoff contradicts the Wiki, the Wiki always wins.
- **Explicit Deviation Justification:** A handoff may temporarily deviate from the Wiki only if it provides a non-empty `wiki_deviation_justification`.
- **Knowledge Promotion:** Hard-won empirical insights recorded under `knowledge_pending_promotion` in a handoff automatically trigger a warning during `brain79_handoff_read`, instructing the incoming agent to ingest those learnings into the long-term Wiki using `brain79_ingest`.

---

## 2. Technical Invariants & Runtime Validation

### Handoff Write Invariants (`brain79_handoff_write`)
1. **Enum Strictness:** `session_type` must be one of `{"feature", "bugfix", "research", "brainstorming"}` (case-insensitive and trimmed).
2. **Lineage Tracking:** `previous_handoff_ref` verifies existence of the referenced handoff (via exact filename, stem, or timestamp prefix).
3. **Anti-Hallucination Guard:** If `pending_work` is empty, `boot_instruction` must explicitly indicate that no pending tasks remain.
4. **Immutability:** Every handoff is written to a unique timestamped file (`handoff-%Y-%m-%d-%H%M%S-%f.md`), preventing overwrites and ensuring an immutable audit trail.

### Handoff Read Invariants (`brain79_handoff_read`)
1. **Flexible Reference Resolution:** `handoff_ref` handles `"latest"`, `"none"`, `""`, exact filenames, full timestamps, or prefix patterns (e.g., `"2024"` or `"2024-08"`).
2. **Promotion Trigger:** Inject dynamic warning banner if `## Conocimiento pendiente de promoción` is present in content.

### Wiki Linter Invariants (`brain79_lint`)
1. **Deterministic Sanitization:** Cleans frontmatter, fenced code blocks, images, and inline code spans (including multi-backtick spans) before link extraction.
2. **Local Link & Namespace Resolution:** Decodes percent-encoded URLs (`unquote`) and strips anchor fragments (`#...`). Validates target existence and flags links into `_raw/` as critical Namespace Violations.
3. **Multi-Root BFS Reachability:** Executes graph BFS from all `INDEX.md` entry points (`follow_symlinks=False`) to report orphan articles.
4. **Non-Blocking Lock & Resource Guards:** Checks file lock state via non-blocking `filelock` (skipping locked files as warnings), enforces a 1 MB file size limit, and limits execution to 15 seconds.

### Context Retrieval Invariants (`brain79_context`)
1. **NFKC & Stop-Word Sanitization:** Normalizes input via NFKC, strips apostrophes, tokenizes alnum sequences (`\w+`), deduplicates, and filters out stop-words (EN/ES/LLM domains) and tokens < 3 characters.
2. **Boundary Heuristic:** Enforces exact word boundary (`\b{kw}\b`) for alnum tokens <= 4 characters, and free substring matching for tokens > 4 characters.
3. **TF-IDF & Fallback Short-Circuit:** Ranks articles using TF-IDF (`TF * (log(N/df) + 1.0)`). If no valid keywords remain, short-circuits execution without launching `ThreadPoolExecutor` and enters Fallback Mode (returning `INDEX.md` and recent articles by `st_mtime_ns`).
4. **ARG_MAX & FD Safety:** Manages temporary file lists via `mkstemp` and POSIX file descriptor lifecycle management, executing parallel keyword search with fallback from `ripgrep` to pure Python regex.



---

## 3. Wiki Core IO Invariants (`wiki.py`)

1. **Path Traversal Security:** `_safe_resolve` strictly enforces absolute directory containment using `is_relative_to`, preventing sibling-prefix attacks and sandbox escapes.
2. **Atomic Writes & Concurrency Control:** All file modifications are protected by inter-process `filelock` and executed via atomic POSIX `rename` (writing to a `.md.tmp` file and replacing the target). This prevents race conditions between concurrent agents and protects against file corruption upon process crashes (e.g. SIGKILL).
3. **Isolated Search (Ripgrep):** `brain79_search` uses `ripgrep` (`rg`) for instantaneous, massive-scale exact string matching (with `-F` and null delimiters) for top performance, automatically and safely falling back to pure Python if `rg` is unavailable.
4. **Namespace Integrity:** The `_raw/` directory is strictly excluded from all public listings (`list_articles`, `search_articles`) to prevent bleeding unstructured text into the curated Wiki domain.

---

## 4. Directory Layout

```
.brain-79/
├── SCHEMA.md        ← Curation rules and guidelines for LLM curation
├── INDEX.md         ← Central directory index (always read first by LLMs)
├── handoffs/        ← Immutable short-term session handoffs
├── product/         ← Business domain and requirements
├── architecture/    ← System design, stack, and ADRs
├── features/        ← Per-feature functional specs
├── decisions/       ← Consolidated decision logs
└── _raw/            ← Immutable raw session logs
    ├── sessions/    ← Raw text session logs
    └── commits/     ← Commit metadata
```

---

## 5. Tool Provisioning & Installation Architecture (`scripts/install.py`)

Local installation and lifecycle management of the `brain79` binary is delegated exclusively to `scripts/install.py`.

- **Cross-Platform Tool Management:** Abstracts `uv tool install --editable --reinstall .`, `uv tool uninstall brain79`, and `uv tool list`.
- **Fail-Fast Environment Guards:** Pre-flight validation checks `uv` binary presence (`shutil.which`) and repository root integrity (`pyproject.toml`).
- **Clean Execution & Diagnostics:** Prevents raw traceback leakage by suppressing unhandled exceptions and providing clean error output to `stderr` with appropriate exit codes.
