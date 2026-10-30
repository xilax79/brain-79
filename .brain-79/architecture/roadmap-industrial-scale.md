---
type: architecture
summary: Strategic roadmap for enterprise-grade scalability, concurrency, sub-second session commits, and local semantic retrieval
stability: experimental
last_updated: 2026-10-29
---

# Architecture — Industrial-Scale Roadmap & Performance Evolution

## Overview

Following the release of `brain-79` v1.1.0 (which introduced atomic batch writes, partial edits, and token de-duplication), this document sets out the architectural roadmap required to elevate `brain-79` from an artisanal single-agent developer utility to an **enterprise-grade, industrial-scale memory protocol**.

The target state supports massive monorepos, multi-agent orchestration swarms (such as Orca, Pi-conductor, or Devin fleets), sub-second session terminations, and zero-external-API semantic retrieval.

---

## Adversarial Bottleneck Analysis

A quantitative and architectural audit reveals four primary ceilings in the current implementation:

1. **The LLM Turn Tax (Network & Inference Overhead):**
   - Python-level execution in `brain-79` runs in under 10 ms. However, each tool interaction incurs a full round-trip: serialization across JSON-RPC over stdio $\rightarrow$ agent harness client forwarding $\rightarrow$ LLM context window ingestion $\rightarrow$ token generation $\rightarrow$ tool invocation.
   - Reading multiple articles or wrapping up a session in 3–4 sequential turns wastes 95% of total wall-clock time in inference latency.
2. **Filesystem Lock Contention:**
   - Inter-process locking via `.lock` files over flat JSON structures (`.navigation_registry.json`) creates serialization bottlenecks under multi-agent concurrency, risking `filelock.Timeout` exceptions (POSIX exit code 3).
3. **Keyword Retrieval Precision Ceiling:**
   - While `ripgrep` (`rg -F`) is instantaneous for exact tokens, `brain79_context` relies on an in-memory TF-IDF heuristic without semantic embedding support. Vocabulary mismatches (e.g. searching "rate-limiting" against an article titled "throttling") result in missed context and wasted token reads.
4. **CI/CD Integration Gaps:**
   - Text and JSON linter outputs require manual parsing in enterprise continuous integration pipelines rather than integrating natively with industry standards like GitHub Code Scanning.

---

## Strategic Pillars & Proposed Initiatives

```
+-----------------------------------------------------------------------------------+
| Milestone 1: Zero-Turn Overhead (Batch Read & Atomic Session Commit)              |
+-----------------------------------------------------------------------------------+
| Milestone 2: Concurrency & Transactional Storage (SQLite WAL Engine)              |
+-----------------------------------------------------------------------------------+
| Milestone 3: Zero-Dependency Embedded Vector Search (BM25 + sqlite-vec)           |
+-----------------------------------------------------------------------------------+
| Milestone 4: Enterprise Observability & Documentation Compilation                 |
+-----------------------------------------------------------------------------------+
```

---

### Pillar 1: Zero-Turn Overhead (Batch Read & Atomic Session Commit)

#### 1.1 `brain79_batch_read` (Projected Section Reads in 1 Round-Trip)
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

#### 1.2 `brain79_session_commit` (1-Call Complete Session Finalization)
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

### Pillar 2: High-Concurrency Transactional Storage (SQLite WAL)

#### 2.1 Embedded Registry Engine (`.brain-79/.cache.db`)
- **Problem:** `.navigation_registry.json` is a flat text file read and re-written under global file mutexes. Concurrent agent writes cause lock contention.
- **Solution:** Replace the internal JSON registry with an embedded SQLite database configured with **Write-Ahead Logging (WAL)**:
  - Concurrent readers never block writers; writers never block readers.
  - Microsecond metadata indexing and topological dependency mapping.
  - Markdown files in `.brain-79/` remain the human-readable, Git-versioned source of truth; SQLite acts strictly as an accelerated transactional cache.

#### 2.2 Fine-Grained Entity Locking
- **Problem:** Locking the entire registry or directory prevents agents from editing disjoint files concurrently.
- **Solution:** File-level transactional locking using hashed path mutexes, allowing $N$ agents to update separate articles simultaneously without interference.

---

### Pillar 3: Zero-Dependency Embedded Semantic Retrieval

#### 3.1 Local Vector & BM25 Hybrid Indexing (`sqlite-vec` + FTS5)
- **Problem:** Pure keyword search lacks semantic awareness, while external vector databases (Pinecone, Qdrant, OpenAI embeddings) introduce cloud latency, billing dependencies, and security concerns for private codebases.
- **Solution:** An on-device hybrid search engine inspired by `tobi/qmd`:
  - Full-text search via SQLite FTS5 (BM25).
  - Semantic vector search using `sqlite-vec`.
  - Local ONNX embedding runtime (`all-MiniLM-L6-v2` or `bge-small-en-v1.5`, ~30 MB footprint) executing in <15 ms on CPU with zero network calls.

#### 3.2 Semantic Query Primitive (`brain79_ask` / `brain79_search(semantic=true)`)
- Returns semantically ranked article passages with contextual relevance scores, completely preventing hallucinated file navigation.

---

### Pillar 4: Enterprise Observability & Documentation Compilation

#### 4.1 Native SARIF Linter Export for CI/CD
- **Problem:** Enterprise pipelines require machine-readable violation reports compatible with automated PR review gates.
- **Solution:** `brain79 lint --format sarif` outputs standard Static Analysis Results Interchange Format (SARIF), allowing direct ingestion into GitHub Code Scanning and GitLab Security dashboards.

#### 4.2 Knowledge Drift Detection
- **Problem:** Codebases evolve while documentation silently decays if developers or agents do not update related wiki articles.
- **Solution:** Algorithmic drift detection comparing file modification timestamps and git commit history between source trees (e.g. `src/`) and documentation (`.brain-79/`), flagging stale articles during lint passes.

#### 4.3 Static Documentation Compiler (`brain79 export --html`)
- Generates a static, zero-config HTML documentation site from the markdown wiki, ready for deployment to GitHub Pages or internal intranets.

---

## Recommended Execution Order

The sequence is prioritized by **impact-to-effort ratio**, targeting immediate latency reduction first, followed by structural concurrency and advanced retrieval:

| Phase | Initiative | Primary Benefit | Complexity |
|:---|:---|:---|:---|
| **Phase 1** | **`brain79_session_commit`** | Eliminates 3–4 LLM round-trips; wraps sessions in 1 instant call | Medium |
| **Phase 2** | **`brain79_batch_read` (with section projection)** | Drastically reduces cold-start token consumption and round-trips | Low |
| **Phase 3** | **SQLite WAL Engine (`.cache.db`)** | Eliminates lock contention under multi-agent swarms | Medium |
| **Phase 4** | **SARIF Export & Knowledge Drift Metrics** | Enterprise CI/CD integration and stale documentation prevention | Low |
| **Phase 5** | **Local Hybrid Semantic Search (`sqlite-vec`)** | Zero-API semantic discovery with local embeddings | High |

---

[← Volver al Índice](../INDEX.md)
