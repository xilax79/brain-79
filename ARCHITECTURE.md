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

---

## 3. Directory Layout

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
