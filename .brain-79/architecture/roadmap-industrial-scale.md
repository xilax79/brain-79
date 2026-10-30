---
type: architecture
summary: Strategic roadmap for enterprise scalability, domain-agnostic schemas, sub-second session commits, and local semantic retrieval
stability: experimental
last_updated: 2026-10-29
---

# Architecture — Industrial-Scale Roadmap & Performance Evolution

## Overview

Following the release of `brain-79` v1.1.0 (which introduced atomic batch writes, partial edits, and token de-duplication), this document sets out the architectural roadmap required to elevate `brain-79` from an artisanal single-agent developer utility to an **enterprise-grade, domain-agnostic AI memory protocol**.

The target state supports:
1. **Any knowledge domain** (academic research, investigative journalism, long-form book drafting, legal/financial analysis, as well as software engineering).
2. **Sub-second session terminations** with zero turn tax.
3. **Multi-agent orchestration swarms** (such as Orca, Pi-conductor, or Devin fleets) without lock contention.
4. **Zero-external-API semantic retrieval** with on-device vector search.

---

## Adversarial Bottleneck Analysis

A quantitative and architectural audit reveals five primary ceilings in the current implementation:

1. **Software Domain Coupling (Architectural Rigidity):**
   - Current validation logic (`TYPE_SCHEMA`, `LOCATION_TO_TYPE`) is hard-coded to software engineering (`features/` with `status: [planned, shipped]`, `architecture/`, `decisions/`).
   - Linter rules unconditionally flag mentions of `Decision:` or `Technical debt:` outside `decisions/`, making `brain-79` unusable for non-code tasks (e.g. academic research, legal discovery, writing long-form books).
2. **The LLM Turn Tax (Network & Inference Overhead):**
   - Python-level execution in `brain-79` runs in under 10 ms. However, each tool interaction incurs a full round-trip: serialization across JSON-RPC over stdio $\rightarrow$ agent harness client forwarding $\rightarrow$ LLM context window ingestion $\rightarrow$ token generation $\rightarrow$ tool invocation.
   - Wrapping up a session or reading multiple documents across 3–5 sequential turns wastes 95% of total wall-clock time in inference latency.
3. **Filesystem Lock Contention:**
   - Inter-process locking via `.lock` files over flat JSON structures (`.navigation_registry.json`) creates serialization bottlenecks under multi-agent concurrency, risking `filelock.Timeout` exceptions (POSIX exit code 3).
4. **Keyword Retrieval Precision Ceiling:**
   - While `ripgrep` (`rg -F`) is instantaneous for exact tokens, `brain79_context` relies on an in-memory TF-IDF heuristic without semantic embedding support. Vocabulary mismatches (e.g. searching "rate-limiting" against an article titled "throttling") result in missed context and wasted token reads.
5. **CI/CD Integration Gaps:**
   - Text and JSON linter outputs require manual parsing in enterprise continuous integration pipelines rather than integrating natively with industry standards like GitHub Code Scanning.

---

## Strategic Pillars & Proposed Initiatives

```
+-----------------------------------------------------------------------------------+
| Milestone 1: Domain-Agnostic Schema Engine & Presets (Universal Memory)           |
+-----------------------------------------------------------------------------------+
| Milestone 2: Zero-Turn Overhead (Batch Read & Atomic Session Commit)              |
+-----------------------------------------------------------------------------------+
| Milestone 3: Concurrency & Transactional Storage (SQLite WAL Engine)              |
+-----------------------------------------------------------------------------------+
| Milestone 4: Zero-Dependency Embedded Vector Search (BM25 + sqlite-vec)           |
+-----------------------------------------------------------------------------------+
| Milestone 5: Enterprise Observability & Documentation Compilation                 |
+-----------------------------------------------------------------------------------+
```

---

### Pillar 1: Domain-Agnostic Schema Engine & Presets (Universal Memory)

#### 1.1 `SCHEMA.md` as Dynamic Source of Truth
- **Problem:** `TYPE_SCHEMA` and `LOCATION_TO_TYPE` in `src/brain79/core/frontmatter.py` hard-code directory structures to software projects.
- **Solution:** Parse schema rules and folder mappings dynamically from `.brain-79/SCHEMA.md`. Users and agents can define their own directories, required metadata, and allowed enum values directly in `SCHEMA.md` without editing Python source code.

#### 1.2 Domain Presets in `brain79 init`
- **Problem:** Seeding a wiki for non-code projects requires manually altering all templates.
- **Solution:** Add `--profile` flag to project initialization:
  - `brain79 init --profile software` (default): `architecture/`, `features/`, `decisions/`, `changelog/`.
  - `brain79 init --profile research`: `sources/`, `entities/`, `hypotheses/`, `claims/`, `synthesis/` (fields: `confidence`, `evidence_level`, `source_type`).
  - `brain79 init --profile writing`: `characters/`, `world/`, `chapters/`, `outlines/` (fields: `stage`, `pov`, `word_count`).
  - `brain79 init --profile generic`: `concepts/`, `notes/`, `summaries/` (minimal Karpathy-style wiki with mechanical link/orphan validation).

#### 1.3 Context-Aware Linter Rules
- Conditionally disable software-specific checks (e.g. decision leakage, ADR numbering format) when operating in non-software profiles.

---

### Pillar 2: Zero-Turn Overhead (Batch Read & Atomic Session Commit)

#### 2.1 `brain79_batch_read` (Projected Section Reads in 1 Round-Trip)
- **Problem:** When an agent orients itself or conducts research, it frequently issues sequential `brain79_read` calls for 3–6 articles. Ingesting full markdown files floods the context window with non-essential details.
- **Solution:** A vectorized read primitive:
  ```json
  brain79_read_batch({
    "targets": [
      {"path": "architecture/mcp-server.md", "sections": ["Overview", "Tool Definitions"]},
      {"path": "features/cli.md", "sections": ["Overview"]}
    ]
  })
  ```
  Returns only the requested H2 sections across multiple documents in a single round-trip, cutting input tokens by up to 60%.

#### 2.2 `brain79_session_commit` (1-Call Complete Session Finalization)
- **Problem:** Wrapping up an agent session currently requires separate invocations: editing existing articles, creating new ones, syncing navigation, and writing the final handoff note.
- **Solution:** A unified, atomic session finalizer:
  ```json
  brain79_session_commit({
    "edits": [{"path": "features/auth.md", "edits": [...]}],
    "new_articles": [{"path": "decisions/adr-008.md", "content": "..."}],
    "handoff": {
      "session_type": "feature",
      "summary": "Implemented auth tokens",
      "completed_work": [...],
      "pending_work": [...]
    }
  })
  ```
  In a single execution, the engine validates all frontmatter schemas, applies in-memory text replacements, writes markdown files, updates navigation, and appends the immutable handoff. The agent finalizes work in **exactly 1 tool call**.

---

### Pillar 3: High-Concurrency Transactional Storage (SQLite WAL)

#### 3.1 Embedded Registry Engine (`.brain-79/.cache.db`)
- **Problem:** `.navigation_registry.json` is a flat text file read and re-written under global file mutexes. Concurrent agent writes cause lock contention.
- **Solution:** Replace the internal JSON registry with an embedded SQLite database configured with **Write-Ahead Logging (WAL)**:
  - Concurrent readers never block writers; writers never block readers.
  - Microsecond metadata indexing and topological dependency mapping.
  - Markdown files in `.brain-79/` remain the human-readable, Git-versioned source of truth; SQLite acts strictly as an accelerated transactional cache.

#### 3.2 Fine-Grained Entity Locking
- **Problem:** Locking the entire registry or directory prevents agents from editing disjoint files concurrently.
- **Solution:** File-level transactional locking using hashed path mutexes, allowing $N$ agents to update separate articles simultaneously without interference.

---

### Pillar 4: Zero-Dependency Embedded Semantic Retrieval

#### 4.1 Local Vector & BM25 Hybrid Indexing (`sqlite-vec` + FTS5)
- **Problem:** Pure keyword search lacks semantic awareness, while external vector databases (Pinecone, Qdrant, OpenAI embeddings) introduce cloud latency, billing dependencies, and security concerns for private codebases.
- **Solution:** An on-device hybrid search engine inspired by `tobi/qmd`:
  - Full-text search via SQLite FTS5 (BM25).
  - Semantic vector search using `sqlite-vec`.
  - Local ONNX embedding runtime (`all-MiniLM-L6-v2` or `bge-small-en-v1.5`, ~30 MB footprint) executing in <15 ms on CPU with zero network calls.

#### 4.2 Semantic Query Primitive (`brain79_ask` / `brain79_search(semantic=true)`)
- Returns semantically ranked article passages with contextual relevance scores, completely preventing hallucinated file navigation.

---

### Pillar 5: Enterprise Observability & Documentation Compilation

#### 5.1 Native SARIF Linter Export for CI/CD
- **Problem:** Enterprise pipelines require machine-readable violation reports compatible with automated PR review gates.
- **Solution:** `brain79 lint --format sarif` outputs standard Static Analysis Results Interchange Format (SARIF), allowing direct ingestion into GitHub Code Scanning and GitLab Security dashboards.

#### 5.2 Knowledge Drift Detection
- **Problem:** Codebases evolve while documentation silently decays if developers or agents do not update related wiki articles.
- **Solution:** Algorithmic drift detection comparing file modification timestamps and git commit history between source trees (e.g. `src/`) and documentation (`.brain-79/`), flagging stale articles during lint passes.

#### 5.3 Static Documentation Compiler (`brain79 export --html`)
- Generates a static, zero-config HTML documentation site from the markdown wiki, ready for deployment to GitHub Pages or internal intranets.

---

## Recommended Execution Order

The sequence is prioritized fundamentally by **foundational generality and latency reduction**:

1. **Step 1 must be the Domain-Agnostic Schema Engine**: Generalizing schemas early ensures that subsequent tools (`brain79_session_commit`, `brain79_batch_read`, and SQLite indexing) are built from day one against dynamic, multi-domain schemas rather than having to be refactored twice.
2. **Step 2 is Turn Reduction (`brain79_session_commit`)**: Delivers immediate, dramatic speedups for users in all domains.

| Phase | Initiative | Strategic Justification | Complexity |
|:---|:---|:---|:---|
| **Phase 1** | **Domain-Agnostic Engine (`--profile`)** | Decouples the protocol from software; avoids refactoring later primitives | Medium |
| **Phase 2** | **`brain79_session_commit`** | Eliminates 3–4 LLM round-trips; wraps sessions in 1 instant call | Medium |
| **Phase 3** | **`brain79_batch_read` (section projection)** | Drastically reduces cold-start token consumption and round-trips | Low |
| **Phase 4** | **SQLite WAL Engine (`.cache.db`)** | Eliminates lock contention under multi-agent swarms | Medium |
| **Phase 5** | **SARIF Export & Knowledge Drift Metrics** | Enterprise CI/CD integration and stale documentation prevention | Low |
| **Phase 6** | **Local Hybrid Semantic Search (`sqlite-vec`)** | Zero-API semantic discovery with local embeddings | High |

---

[← Volver al Índice](../INDEX.md)
