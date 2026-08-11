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

---

## 6. Update Subcommand Architecture (`brain79 update`)

The `brain79 update` command enables in-place updating of editable installations directly from the upstream repository.

- **CLI Dispatch Mechanism (`__main__.py`):** Positionally dispatches `update` subcommands via `sys.argv[1:]` before initializing FastMCP, ensuring zero side-effects or stderr outputs during normal server operations.
- **Isolated Module Resolution (`importlib.util`):** Locates the installed package path dynamically using `importlib.util.find_spec("brain79")` without executing module import side-effects. Traverses directory parents to identify the `.git` repository root.
- **Fail-Fast Safety Checks:** Enforces strict invariants prior to mutating state:
  1. Validates presence of `git` and `uv` binaries.
  2. Ensures working tree is clean (`git status --porcelain`).
  3. Verifies git HEAD is not detached and resides on the remote default branch (`origin/HEAD` or `--branch` override).
- **Atomic Pull & Rebuild Protocol:** Executes `git fetch origin`, verifies hash diffs, performs fast-forward pull (`git pull --ff-only`), and rebuilds the tool environment (`uv tool install --force .`). Gracefully handles cancellation via `KeyboardInterrupt` (exit code `130`).

---

## 7. Bootstrap Tool Architecture (`bootstrap.py`)

`brain79_bootstrap` enables wiki seeding for existing projects without prior wiki history.

### Design Principles
- **LLM is the intelligence; scanner is the eyes.** The tool performs only deterministic
  file system operations. The LLM interprets the manifest and writes wiki articles using
  `brain79_write`.
- **Strict budget enforcement.** Total content returned is capped at 80 KB.
  Individual root files: 8 KB. Scope files: 4 KB. Files are read incrementally
  (never load full file into memory for truncation).
- **No hallucination surface from the tool.** Bootstrap Instructions explicitly prohibit
  the LLM from writing content not evidenced in the manifest.

### Idempotency & Concurrency Contract
1. `.brain-79/.bootstrap_state.json` is written atomically via `tmp+rename`.
2. A `filelock` protects the read-check and state-write phases only.
   The file scan itself runs outside the lock to avoid holding it during slow I/O.
3. Subsequent calls without `force=True` return a warning with the previous timestamp.
4. Corrupt or missing state is treated as "never run" — bootstrap proceeds.

### Security Invariants
1. **Excluded dirs:** `.git`, `node_modules`, `.venv`, `.brain-79`, and all
   cache dirs are never walked.
2. **Binary extension skip:** No content is read from known binary file types.
3. **Scope path validation:** Paths in `scope` that resolve outside `project_root`
   are silently dropped (no warning, no information leakage).
4. **In-bounds but missing paths:** Scope paths inside `project_root` that do not
   exist produce a warning in the manifest (usability).
5. **No writes to wiki:** The tool writes only `.bootstrap_state.json`. All wiki
   article creation is delegated to the LLM via `brain79_write`.

### Frontmatter Traceability
All bootstrap-generated articles carry YAML frontmatter (`bootstrap: true`,
`generated_by`, `generated_at`, `project_type`). This enables future tooling
to distinguish bootstrap content from organically curated knowledge.

### Scan Budget Algorithm
1. Root-level structural pass always runs first (tree + priority key files by category).
2. Remaining budget allocated to scope files if `scope` was provided.
3. Files read in priority order; scanning halts when `_TOTAL_CONTENT_BUDGET_BYTES` exhausted.
4. Per-file truncation uses incremental read — `stat().st_size` checked before allocation.

### Project Type Detection
Heuristic, priority-ordered. First matching signal wins. Returns one of:
`python-package`, `python-script`, `node-package`, `rust-crate`, `go-module`,
`java-maven`, `java-gradle`, `ruby-gem`, `docker-service`, `research-paper`,
`documentation`, `unknown`.

---

## 8. Hybrid CLI Subcommand & Dispatch Architecture

`brain79` features a closed-whitelist CLI dispatcher operating alongside the FastMCP server entrypoint.

### Core Purity & Banner Decoupling
1. **Core Invariant:** `core/` functions raise native Python exceptions (`ValueError`, `FileNotFoundError`, `OSError`, `PermissionError`, etc.) and return pure data. They do not print LLM-targeted warning banners to `stdout` or `stderr`.
2. **Interface Banner Decoupling:** `core.handoff.read_handoff(ref)` returns `tuple[str, bool]` (`(content, has_promotion_pending)`). `server.py` uses `has_promotion_pending` to append the LLM warning banner for MCP clients (`brain79_handoff_read`). The CLI `handoff-read` output remains neutral.

### Dispatcher Invariants & Global Flag Pre-Processing
1. **Strict Closed Whitelist:** Closed subcommand set `{"init", "update", "index", "read", "write", "list", "search", "ingest", "handoff-write", "handoff-read", "lint", "context", "bootstrap"}`.
2. **Dual-Position Pre-Processing:** Global flags `--project-root` and `--debug` are extracted from `sys.argv[1:]` prior to `argparse` dispatch, guaranteeing that `config.set_project_root()` is applied regardless of flag ordering (`brain79 --project-root /foo read` vs `brain79 read --project-root /foo`).
3. **Strict Import Order:** `FASTMCP_SHOW_SERVER_BANNER=false` is set in `__main__.py` before any module imports. FastMCP server initialization (`server.py`) is lazy-loaded only when no CLI subcommand matches.

### Input Ergonomics & Resilience
1. **Quoting Security:** Large text fields (`summary`, `boot_instruction`, `wiki_deviation_justification`, `instructions`, `content`) omit inline string flags. Inputs are accepted strictly via mutually exclusive `--<field>-file` or `--<field>-stdin` options.
2. **Fail-Fast Size & Encoding Guards:** File and stdin inputs enforce a 1 MB limit via `Path.stat()` / `os.fstat()` / stream byte checks before processing. Text decoding strictly enforces UTF-8 (`errors="strict"`).

### Standardized Unix Exit Code Taxonomy
| Exit Code | Exception / Trigger | Category |
|-----------|---------------------|----------|
| `0` | Clean execution | Success |
| `1` | `ValueError`, `json.JSONDecodeError`, input limit / encoding error | Validation & Domain Error |
| `2` | `FileNotFoundError`, `HandoffNotFoundError`, `argparse.ArgumentError` | Syntax / Entity Not Found |
| `3` | `OSError`, `PermissionError`, `filelock.Timeout` | I/O & Concurrency Contention |
| `4` | Missing binary dependency (`git`, `uv`) | Binary Dependency Error |
| `130` | `KeyboardInterrupt` | Interrupted |

### 1:1 Static Symmetry Guarantee
A static CI test (`tests/test_symmetry.py`) validates that `mcp_tools ⊆ cli_subs` and `cli_subs - mcp_tools == {"init", "update"}`.


