---
type: architecture
summary: Industrial-scale roadmap focused on the Two-Call Session Protocol, graph-verified context loading, lightweight dual ontology (software + general), and invariant alignment
stability: experimental
last_updated: 2026-11-02
---

# Architecture — Industrial-Scale Roadmap & Performance Evolution

## Overview

Following the release of `brain-79` v1.1.0 (which introduced atomic batch writes, partial edits, deterministic field auto-fill, and token de-duplication), this document defines the engineering roadmap to take `brain-79` to an **industrial-grade AI memory protocol**.

Instead of bloating the tool with heavy machine-learning runtimes or unrelated static site generators, this roadmap focuses ruthlessly on four operational goals:

1. **Maximum Speed & Minimum Turn Tax (The Two-Call Session Protocol)**: Collapse cold-start orientation into a single tool call (`brain79_orient`) and end-of-session curation into a single atomic transaction (`brain79_session_commit`).
2. **Guaranteed Pre-Work Context Precision**: Ensure the agent always reads every governing decision, architecture invariant, and feature constraint *before* touching files, using deterministic path-to-wiki bindings (`applies_to`) and reference-graph expansion.
3. **High-Quality Authoring & Structural Integrity**: Enforce section-level document structure per article type and eliminate internal validation inconsistencies.
4. **Elegant Universal Adaptability (`software` + `general` Ontologies)**: Decouple the core engine from hardcoded software-only directories through a lightweight declarative schema in `SCHEMA.md`, making `brain-79` work natively for both software repositories (90% case) and general knowledge/research projects (10% case) without scope creep.

---

## Core Bottleneck Diagnosis

A technical audit of the v1.1.0 codebase and real-world agent sessions identifies five concrete bottlenecks:

1. **Cold-Start Turn Tax & Context Omission Risk**:
   - At session start, an agent must sequentially call `brain79_index()`, `brain79_handoff_read()`, optionally `brain79_context(task)`, and then 3–5 separate `brain79_read()` calls. This consumes 4–7 LLM round-trips (20–40 seconds of inference latency) before work even begins.
   - Worse, when selecting articles from `INDEX.md` by title alone, agents frequently miss governing ADRs or cross-cutting architectural constraints due to vocabulary mismatch.
2. **End-of-Session Turn Tax**:
   - Even with v1.1.0 improvements, closing a session requires 3 sequential round-trips: `brain79_ingest` $\rightarrow$ `brain79_write` / `brain79_edit` / `brain79_write_many` $\rightarrow$ `brain79_handoff_write`.
3. **Internal Invariant Contradictions (v1.0 $\rightarrow$ v1.1 Technical Debt)**:
   - `bootstrap.py` instructs agents to write frontmatter lacking required type fields (`stability`) and to add prose to `INDEX.md`, which contradicts write-time validation and ADR-008 (*Pure Routing Table*).
   - `lint_organizational.py` (`check_frontmatter_consistency`) only checks for `type` and `last_updated`, bypassing full `validate_frontmatter` checks (enums, required per-type fields, unknown keys) when files are edited outside MCP.
   - `validation.py` (`INDEX_ALLOWED_H2`) and `curate.py` still permit legacy prose sections in `INDEX.md` despite ADR-008 mandating a pure routing table.
   - `save_raw_session` in `wiki.py` writes files to `_raw/sessions/` without the `raw_session` YAML frontmatter defined in `TYPE_SCHEMA`.
4. **Hardcoded Software-Only Schema**:
   - `TYPE_SCHEMA` and `LOCATION_TO_TYPE` in `frontmatter.py` force every project to use `features/` (requiring semver `version`) and `architecture/` (requiring `stability`), and `handoff.py` restricts `session_type` to software tasks (`bugfix`, `feature`), creating friction when using `brain-79` in non-code directories.
5. **Lack of Body Structure & Code-to-Wiki Drift Tracking**:
   - Write validation checks YAML frontmatter and the presence of an `# H1`, but does not verify expected `## H2` sections per document type or detect when repository files change without updating their governing wiki articles.

---

## Execution Roadmap (Ordered by Dependency & Impact)

```
+-----------------------------------------------------------------------------------+
| Phase 0: Core Bug Fixes & Invariant Alignment (Foundation Cleanup) | [x] Completed (2026-11-02) |
+-----------------------------------------------------------------------------------+
| Phase 1: Mechanism vs. Policy — Declarative Schema & Dual Ontology | [x] Completed (2026-11-02) |
+-----------------------------------------------------------------------------------+
| Phase 2: Deterministic Pre-Work Context & Graph-Augmented Cold Start | [x] Completed (2026-11-02) |
+-----------------------------------------------------------------------------------+
| Phase 3: Zero-Turn Session Execution (Session Commit & Section-Projected Reads) | [x] Completed (2026-11-02) |
+-----------------------------------------------------------------------------------+
| Phase 4: Structural Article Quality & Deterministic Drift Detection | [ ] Next |
+-----------------------------------------------------------------------------------+
```

---

### Phase 0: Core Bug Fixes & Invariant Alignment

Before adding new capabilities, all internal contradictions between v1.0 modules and v1.1 invariants must be resolved so the validation and linting pipeline is 100% consistent.

#### 0.1 Fix `brain79_bootstrap` Manifest Compliance
- **Bug**: `src/brain79/core/bootstrap.py` instructs the agent to write articles using only `bootstrap: true`, `generated_by`, `generated_at`, and `project_type`, and tells the agent to edit `INDEX.md` with project descriptions. When the agent follows these instructions, `brain79_write` rejects the articles for missing `summary:` and `stability:` / `status:`, and rejects `INDEX.md` prose.
- **Fix**:
  - Update `_build_manifest` in `bootstrap.py` so every required/conditional seed article template includes valid type-specific frontmatter (`type`, `summary`, `stability: stable` for `architecture/`, etc.) alongside the bootstrap metadata keys.
  - Remove instructions to manually edit `INDEX.md` prose; instruct the agent to write `product/overview.md` and `architecture/overview.md` and let automatic navigation sync populate `INDEX.md`.

#### 0.2 Unify `lint_organizational.py` with `validate_frontmatter`
- **Bug**: `check_frontmatter_consistency` in `src/brain79/core/lint_organizational.py` only checks for the presence of `type` and `last_updated`. Direct file edits that omit required fields (e.g., `status`, `version`, `deciders`), introduce invalid enum values, or add unknown keys pass `brain79 lint --strict` unnoticed.
- **Fix**: Refactor `check_frontmatter_consistency` to invoke `validate_frontmatter(meta, rel_str)` directly and convert all returned `ValidationError.issues` into `OrganizationalIssue` items.

#### 0.3 Enforce ADR-008 (*Pure Routing Table*) Across Validator & Curation Guide
- **Bug**: `INDEX_ALLOWED_H2` in `src/brain79/core/validation.py` and the rules in `src/brain79/core/curate.py` still allow `Project`, `Current focus`, `Known issues`, and `Roadmap` in `INDEX.md`, contradicting ADR-008 and `AGENTS.md`.
- **Fix**:
  - Restrict `INDEX_ALLOWED_H2` in `validation.py` strictly to `frozenset({"Quick navigation"})`.
  - Update `curate.py` and `lint_organizational.py` (`generate_extraction_suggestions`) to reflect that `INDEX.md` only permits `## Quick navigation`.

#### 0.4 Add Valid Frontmatter to `_raw/sessions/` Writes & Require `summary` on Articles
- **Bug**: `save_raw_session` in `src/brain79/core/wiki.py` writes raw markdown without the `raw_session` frontmatter defined in `TYPE_SCHEMA`. Additionally, `summary` is documented as mandatory in `AGENTS.md` (ADR-007), but `TYPE_SCHEMA` still lists `summary` under `"optional"`.
- **Fix**:
  - Update `save_raw_session` to emit valid `type: raw_session` YAML frontmatter.
  - Promote `summary` to `"required"` for all indexable article types (`product`, `architecture`, `feature`, `decision`, `changelog`) in write-time validation, while keeping legacy migration fallback support.

---

### Phase 1: Mechanism vs. Policy — Declarative Schema & Dual Ontology

To make `brain-79` work seamlessly across any project directory without turning the codebase into a fragile collection of niche presets, we separate the **validation engine (mechanism)** from the **directory/type rules (policy)**.

#### 1.1 Declarative Schema Loading from `.brain-79/SCHEMA.md`
- **Design**:
  - Allow `.brain-79/SCHEMA.md` to declare the active project profile and optional custom folder/type mappings in its own YAML frontmatter (or a clean, deterministic schema header).
  - Implement `load_active_schema(wiki_root: Path)` in `frontmatter.py` with an in-memory cache keyed by `(wiki_root, schema_mtime_ns)` so schema resolution takes $<0.1\text{ ms}$.
  - If `SCHEMA.md` has no custom overrides, fall back to the built-in profile defaults.

#### 1.2 Dual Built-In Ontologies: `software` (Default) and `general`
Instead of inventing half-baked presets for specific professions, `brain79 init [--profile software|general]` provides two clean, battle-tested ontologies:

| Aspect | `software` Profile (Default — 90% use case) | `general` Profile (Universal Knowledge — 10% use case) |
|---|---|---|
| **Directories & Types** | `product/` (`product`)<br>`architecture/` (`architecture`)<br>`features/` (`feature`)<br>`decisions/` (`decision`)<br>`changelog/` (`changelog`) | `context/` (`context` — goals, scope, background)<br>`topics/` (`topic` — domain notes, research, drafts, entities)<br>`decisions/` (`decision` — choices, criteria, trade-offs)<br>`log/` (`log` — chronological milestones, progress) |
| **Required Fields** | Existing strict fields (`stability`, `status`, `version`, `deciders`, `summary`, `last_updated`) | Minimal friction: `type`, `summary`, `last_updated`, plus `status: [draft, active, archived, legacy]` on `topic` and `status: [proposed, accepted, superseded, rejected, legacy]` on `decision` (no semver `version` required) |
| **Handoff `session_type`** | `feature`, `bugfix`, `research`, `brainstorming` | Adds `work`, `general`, `writing`, `analysis` (or accepts any token declared in `SCHEMA.md`) |
| **Leakage Rules** | `decision_leakage` + `technical_debt_leakage` active | `decision_leakage` active (decisions still belong in `decisions/`); `technical_debt_leakage` disabled |

#### 1.3 Custom Folder Extension in Any Project
- Users or agents can add a custom folder to any project by declaring it in `.brain-79/SCHEMA.md` (e.g., `runbooks/` or `sources/`), specifying its required fields and enums without touching Python code.

---

### Phase 2: Deterministic Pre-Work Context & Graph-Augmented Cold Start

This phase directly solves the most critical cognitive problem in agent workflows: **ensuring the agent reads every relevant article and governing decision before starting work, in a single turn.**

#### 2.1 Path & Graph Binding in Frontmatter (`applies_to` & `related`)
- **Problem**: Keyword search (`brain79_search` / `brain79_context`) fails when the user's prompt uses different terminology than an ADR or architecture doc (vocabulary mismatch).
- **Solution**:
  - Standardize optional frontmatter list fields across all article types:
    - `applies_to: [src/brain79/core/validation.py, src/brain79/core/frontmatter.py]` — relative file paths or glob patterns in the project workspace that this article or ADR governs.
    - `related: [decisions/adr-004-strict-write-validation.md]` — explicit cross-links to governing or companion wiki articles.
    - `supersedes: [decisions/adr-001.md]` — lineage tracking so superseded decisions are deprioritized in favor of active ones.
  - Maintain a fast, auto-updated reverse index in `.navigation_registry.json` mapping:
    - `applies_to` globs $\rightarrow$ wiki article paths.
    - Outgoing and incoming markdown links (`file_graph`) between wiki articles.

#### 2.2 Graph-Augmented Context Ranking (`brain79_context` v2)
Upgrade `src/brain79/core/context.py` from pure keyword TF-IDF to a **3-signal deterministic ranker**:
1. **Signal 1 — Deterministic Path Match (Highest Priority)**: If `touched_paths` are provided (or file/directory names are mentioned in `task`), every active (`accepted`/`shipped`/`stable`) article whose `applies_to` glob matches those paths is automatically selected as mandatory reading.
2. **Signal 2 — Field-Weighted BM25/TF-IDF**: Weight matches in `title`, `summary`, and `## H2` headers $3\times$ higher than body text, and filter out `superseded` / `deprecated` articles unless explicitly requested.
3. **Signal 3 — 1-Hop Reference Graph Expansion (Anti-Omission Guard)**: For every top-ranked feature or architecture article selected by Signals 1 or 2, traverse its `related` frontmatter and markdown links into `decisions/` (`status: accepted`). If an article links to an active ADR, that ADR is automatically pulled into the reading set so the agent never modifies a subsystem without seeing its governing decisions.

#### 2.3 `brain79_orient` (1-Call Complete Session Cold Start)
- **Problem**: Starting a session currently takes 4–6 sequential tool calls (`brain79_index` $\rightarrow$ `brain79_handoff_read` $\rightarrow$ `brain79_context` $\rightarrow$ `brain79_read` $\times N$).
- **Solution**: Introduce `brain79_orient(task: str | None = None, paths: list[str] | None = None, max_articles: int = 4)` (and CLI `brain79 orient [--task ...] [--path ...]`).
- **Single-Call Payload**:
  1. **Wiki Routing Table**: The current `INDEX.md` content.
  2. **Active Handoff State**: The latest handoff summary, `pending_work`, `boot_instruction`, and any `knowledge_pending_promotion` alert (automatically resolved without a separate `handoff_read` call).
  3. **Pre-Loaded Governing Articles**: If `task` or `paths` are supplied, runs the 3-signal ranker (Path match + Weighted BM25 + 1-Hop ADR Graph Expansion) and **inlines the full content of the top $K$ mandatory articles** directly in the response, plus a list of secondary related paths.
- **Impact**: Cold start drops from **5+ tool calls (~30s)** to **1 tool call (<20ms local execution, 1 LLM turn)** with mathematical certainty that linked ADRs and path-bound docs are in the context window.

---

### Phase 3: Zero-Turn Session Execution (Batch Read & Atomic Session Commit)

#### 3.1 `brain79_read_batch` (Multi-Article & Section-Projected Reads)
- **Problem**: When an agent needs to inspect several articles mid-session, calling `brain79_read` sequentially wastes turns, and reading 350-line files when only one section is needed wastes context tokens.
- **Solution**: Add `brain79_read_batch(requests: list[dict])` (and extend `brain79_read` to accept an optional `sections: list[str]` parameter):
  ```json
  brain79_read_batch({
    "requests": [
      {"path": "architecture/mcp-server.md", "sections": ["Overview", "Tool Definitions"]},
      {"path": "decisions/adr-006-auto-navigation-and-batch-operations.md"}
    ]
  })
  ```
- **Behavior**:
  - Reads multiple articles in a single tool call.
  - If `sections` is specified, extracts only the frontmatter + `# H1` + requested `## H2` sections.
  - Appends a compact footer listing any outgoing links to `decisions/` from the read articles that the agent has not yet read (`💡 Linked ADRs: decisions/adr-004...`).

#### 3.2 `brain79_session_commit` (1-Call Atomic Session Finalization)
- **Problem**: Closing a session currently requires 3 separate tool calls (`brain79_ingest`, `brain79_write`/`edit`, `brain79_handoff_write`).
- **Solution**: Introduce `brain79_session_commit` (and CLI `brain79 session-commit`) to execute the entire end-of-session protocol in a single all-or-nothing transaction:
  ```json
  brain79_session_commit({
    "session_summary": "Implemented graph-augmented orientation and fixed bootstrap templates.",
    "edits": [
      {"path": "architecture/current-state.md", "edits": [{"old_text": "...", "new_text": "..."}]}
    ],
    "writes": [
      {"path": "decisions/adr-009-two-call-protocol.md", "content": "..."}
    ],
    "handoff": {
      "session_type": "feature",
      "summary": "Shipped Phase 2 and Phase 3 session tools.",
      "completed_work": ["Implemented brain79_orient", "Implemented brain79_session_commit"],
      "pending_work": [],
      "boot_instruction": "No pending tasks. Ready for Phase 4."
    }
  })
  ```
- **Atomic Execution Pipeline**:
  1. **Pre-Flight Validation**: Validates all `writes`, simulates and validates all `edits` in memory, and validates `handoff` constraints (including anti-hallucination guards). If *any* item fails validation, **zero files are modified on disk** and all actionable errors + templates are returned at once.
  2. **Commit Pass**: Writes the raw session to `_raw/sessions/` (if `session_summary` provided), applies all article `writes` and `edits`, writes the immutable `handoff` file, updates `.navigation_registry.json` once, and regenerates `INDEX.md` once under lock.
  3. **Inline Whole-Transaction Diagnostics**: Runs `check_file_health` across all touched articles and returns a unified commit receipt.
- **Impact**: End-of-session wrap-up drops from **3–5 tool calls** to **1 tool call**.

---

### Phase 4: Structural Article Quality & Deterministic Drift Detection

#### 4.1 Section-Level Structural Templates & Validation
- **Problem**: Agents occasionally write valid YAML frontmatter followed by unstructured walls of text lacking clear sections.
- **Solution**:
  - Define recommended/required `## H2` section skeletons per document type in the active schema (e.g., `decision` requires `## Status`, `## Context`, `## Decision`, `## Consequences`; `feature` requires `## Overview`).
  - Expose full markdown document skeletons (frontmatter + H2 headers + backlink footer) in `brain79_schema()`.
  - Add a linter check (`article_missing_required_sections`) in `lint_organizational.py` and inline write warnings when an article omits required structural headings.
  - Enforce the backlink invariant (`[← Volver al Índice](../INDEX.md)`) automatically during write normalization (`autofill_deterministic_fields` / body normalization) so the agent never has to remember to type the footer manually, eliminating human/agent forgetfulness.

#### 4.2 Deterministic Code-to-Wiki Drift Detection (`applies_to` + Git)
- **Problem**: Source code changes over time while governing documentation silently becomes outdated.
- **Solution**:
  - Add a drift check in `brain79 lint` (and `brain79_orient` warnings) powered by the `applies_to` frontmatter field:
  - Using `git log` / filesystem mtimes, if a workspace file matching an article's `applies_to` glob has been modified in commits *after* the article's `last_updated` date, flag an `info`/`warning` issue (`documentation_drift_suspected`):
    `Article 'architecture/validation.md' governs 'src/brain79/core/validation.py' (modified 2026-11-02), but article was last updated 2026-10-29. Verify accuracy and update last_updated.`

---

## Summary Execution Matrix

| Phase | Deliverable | Primary Metric Improved | Effort | Status |
|:---|:---|:---|:---|:---|
| **Phase 0** | Fix `bootstrap.py`, full frontmatter check in `lint_organizational.py`, strict ADR-008 `INDEX_ALLOWED_H2`, required `summary`, `_raw` frontmatter | **0 internal bugs / 100% validator-linter parity** | Low | **Completed** |
| **Phase 1** | Declarative `SCHEMA.md` loader + `software` & `general` profiles + custom folder support | **100% domain flexibility with zero bloat** | Low–Medium | **Completed** |
| **Phase 2** | `applies_to` / `related` graph indexing + `brain79_orient(task, paths)` | **Cold-start turns: 5 $\rightarrow$ 1 · Pre-work recall: near 100%** | Medium | **Completed** |
| **Phase 3** | `brain79_session_commit` + `brain79_read_batch` (with section projection) | **End-of-session turns: 3–4 $\rightarrow$ 1 · Context tokens: -50%** | Medium | **Completed** |
| **Phase 4** | Auto-injected backlinks, H2 section templates/validation, and `applies_to` Git drift detection | **Article structural quality & zero silent doc decay** | Low–Medium | Next |

---

[← Volver al Índice](../INDEX.md)
