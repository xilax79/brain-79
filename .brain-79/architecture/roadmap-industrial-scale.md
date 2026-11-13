---
type: architecture
summary: project roadmap covering completed protocol phases (0-7) and the public launch readiness specification (Phase 8)
stability: stable
applies_to:
  - .brain-79/features/*.md
related:
  - decisions/adr-009-declarative-schema-and-dual-ontologies.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-013-versioning-and-release-governance.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-015-sentence-case-first-policy.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
  - decisions/adr-018-living-manuals-and-temporal-decontamination.md
  - features/version-governance.md
  - features/cross-platform-and-lock-isolation.md
  - features/session-triage-and-research-persistence.md
  - features/handoff-continuity.md
  - features/transitive-drift-and-ripple-guards.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - architecture/defect-backlog.md
last_updated: 2026-11-13
applies_to_digest: "sha256:4d6d69907e3419fd"
applies_to_count: 9
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering roadmap of `brain-79`.

`brain-79` is a production implementation of Andrej Karpathy's **LLM-wiki** pattern. Instead of dumping everything into one huge `CLAUDE.md` file or relying on vector RAG, the AI maintains a structured Markdown wiki inside `.brain-79/`. Because LLMs tend to break links, create duplicate files, or leave documentation outdated when code changes, `brain-79` surrounds that Markdown wiki with a mechanical linter, SHA-256 drift tracking, and atomic MCP/CLI tools.

Phases 0 through 7 built the core engine, the two-call session protocol, cross-platform lock isolation, transitive drift gates, and the multi-harness upgrader. **Phase 8 (`v1.0.0`)** prepares the project for public open-source release.

---

## Completed foundation (Phases 0–7)

- **[x] Phase 0 — Core invariant alignment**: unified write-time validation with organizational linting. Turned `INDEX.md` into an automated routing table (ADR-008) and standardized session frontmatter.
- **[x] Phase 1 — Declarative schema & dual ontology (ADR-009)**: separated the validation engine from folder rules via `.brain-79/SCHEMA.md`. Added built-in `software` and `general` profiles plus custom folder support.
- **[x] Phase 2 — 1-call orientation & 3-signal context ranking (ADR-010)**: added `brain79_orient`. It ranks relevant articles using `applies_to` file paths, field-weighted BM25, and linked ADRs.
- **[x] Phase 3 — Atomic session commits & batch reads (ADR-011)**: added `brain79_session_commit` for all-or-nothing writes, edits, and handoffs. Added section-projected batch reads (`brain79_read_batch`).
- **[x] Phase 4 — Section skeletons & drift detection (ADR-012)**: enforced required `## H2` sections per document type, automatic backlink footers, and initial code-to-wiki drift checks.
- **[x] Phase 5 — Versioning & release governance (ADR-013)**: set up single-source versioning via Hatchling, FastMCP version reporting, and automated release parity tests.
- **[x] Phase 5.5 — Agent protocol polish**: fixed root backlink handling, refined H2 section limits, added schema summaries to `orient()`, and set an on-demand handoff policy.
- **[x] Phase 6 — Cross-platform portability & `.locks/` isolation (ADR-014, ADR-015)**: moved all mutex locks into `.brain-79/.locks/`. Added exact case-sensitivity checks on macOS/Windows, POSIX path normalization, NTFS atomic replace retries, LF line endings, and sentence-case rules.
- **[x] Phase 6.5 — Session knowledge triage (the Amnesia Test)**: added a 3-way triage rule so research sessions without code changes (`Type B`) still save their findings to the wiki. Added parameter aliases and an E2E smoke script.
- **[x] Phase 6.6 — Handoff freshness & authority decay (ADR-016)**: stamped git and content hashes (`wiki_digest`, `code_digest`, `git_head`, `git_branch`) into handoffs. `orient()` now warns the agent when a handoff is `stale` or from a `foreign_branch`.
- **[x] Phase 6.7 — Transitive drift & ripple gates (`v0.8.0`)**: added `.drift_manifest.json` with SHA-256 leaf hashes, multi-hop drift propagation to umbrella articles, the Hard Session Ripple Gate in `session_commit`, the Anti-Sprawl Guard, AST signature checks (Guard C), and unbounded `applies_to` context loading.
- **[x] Phase 6.8 — Living manuals & temporal decontamination (ADR-018, `v0.8.1`)**: defined the three document classes (immutable audit logs, living manuals, and ephemeral handoffs). Blocked milestone tags like `(Phase X)` and oversized files (`> 20 KB`) in living manuals at write-time.
- **[x] Phase 7 — Multi-harness upgrader & doctor diagnostics (`v0.9.0`)**: added managed `<!-- brain79:start -->` blocks in `AGENTS.md`, non-destructive `SCHEMA.md` upgrades (`schema_version: 2`), portable MCP configs (`.mcp.json`, `.agents/`, `.cursor/`), full-pass `migrate_wiki` v2, and `brain79 doctor [--fix]`.

---

## Upcoming execution roadmap

```
+-----------------------------------------------------------------------------------+
| Phase 8: Public launch readiness, zero-clone install & visual docs (v1.0.0)      | [ ] Planned|
+-----------------------------------------------------------------------------------+
```

### Phase 8: Public launch readiness, zero-clone installation, and visual documentation (`v1.0.0`)

To open `brain-79` to the public, a new user must be able to understand what it does in 30 seconds, see concrete before/after examples, and install it with one command without cloning the repository.

#### Writing and communication rules (mandatory for all Phase 8 deliverables)
1. **No marketing hype or false promises**: never claim *"Zero hallucination"*, *"Zero context rot"*, or *"Your AI never forgets"*. No external tool controls LLM weights. State what `brain-79` actually does: it structures project knowledge as a Karpathy-style **LLM-wiki**, loads task-relevant files on startup, checks code-to-doc SHA-256 drift, and validates wiki writes before they hit the disk.
2. **Clean, human B2 English (no AI writing vices)**:
   - Write short, direct sentences (subject-verb-object).
   - Avoid AI clichés: no rule-of-three adjective chains, no endless `-ing` participial tails (*"...ensuring X, guaranteeing Y, and enabling Z"*), and no stuffing five technical terms into one sentence.
   - Explain one idea per paragraph. Show real terminal inputs and outputs instead of abstract prose.

#### Deliverable 8.1: Zero-clone installation and self-update (`src/brain79/core/update.py`)
- **Problem**: `brain79 update` and `scripts/install.py` currently assume the user cloned the Git repository to a local folder and ran `git pull`. External users expect a one-line install via `uv tool install`.
- **Implementation**:
  1. Update `src/brain79/core/update.py` so `brain79 update` detects how it is installed. If installed as a `uv` tool (not an editable local git checkout), run `uv tool install --force git+https://github.com/xilax79/brain-79.git` (or `uv tool upgrade brain79`) without requiring a local clone. Keep the `git pull` + `uv tool install --editable . --force` path when running inside a local development clone.
  2. Standardize the primary installation command across docs:
     ```bash
     uv tool install git+https://github.com/xilax79/brain-79.git
     ```

#### Deliverable 8.2: High-clarity, example-driven `README.md` (user-facing)
Rewrite `README.md` to be light, visual, and grounded in concrete examples (~160–200 lines):
1. **Positioning (Karpathy's LLM-wiki with mechanical guardrails)**:
   - Explain the core idea in plain words: Andrej Karpathy popularized the **LLM-wiki** concept—giving coding agents a structured folder of Markdown files they read and update over time. In practice, raw LLM-wikis break down after a few sessions because agents leave docs outdated when code changes, create duplicate files (`auth-v2.md`), or blow up a single `CLAUDE.md` file. `brain-79` adds the missing mechanical layer (MCP + CLI) that keeps an LLM-wiki accurate.
2. **Visual "Without `brain-79` vs. With `brain-79`" comparison**:
   - A clear side-by-side table showing the 4 real failure modes:
     1. Monolithic `CLAUDE.md` / blind file reading $\rightarrow$ 1-call `brain79_orient` routed by `INDEX.md` and `applies_to`.
     2. Silent code-to-doc drift when `.py`/`.ts` files change $\rightarrow$ SHA-256 drift tracking and the session commit gate.
     3. Wiki sprawl (duplicate files for the same module) $\rightarrow$ write-time overlap check forcing edits to the existing article.
     4. Obsolete session handoffs after branch switches or manual commits $\rightarrow$ git-stamped handoffs (`fresh` vs `stale` / `foreign_branch`).
3. **Three real terminal walkthroughs ("Show, Don't Tell")**:
   - **Scene 1 — Starting a task**: what the agent receives when calling `brain79 orient --task "add refund endpoint" --paths "src/payments.py"`.
   - **Scene 2 — Catching outdated docs before session close**: the exact error message `brain79_session_commit` returns when `src/payments.py` changed its function signature and the agent forgot to update `features/payments.md` or `architecture/overview.md`.
   - **Scene 3 — Research without code (`--profile general`)**: how a research session saves structured notes into `topics/` and `decisions/`.
4. **3-command quick start**:
   - Install (`uv tool install git+https://...`), initialize (`brain79 init`), and diagnose (`brain79 doctor`).
   - Prominent link to the interactive visual guide on GitHub Pages and `ARCHITECTURE.md`.

#### Deliverable 8.3: Developer-grade `ARCHITECTURE.md` (contributor-facing)
Rewrite `ARCHITECTURE.md` in clean, direct technical prose for engineers who want to understand how the engine works under the hood:
1. **Source code map (`src/brain79/`)**: a table mapping every `.py` module in `src/brain79/core/`, `cli/`, and `server.py` to its single responsibility.
2. **End-to-end execution flows**:
   - Step-by-step trace of `brain79_orient()` (index loading, handoff freshness check, 3-signal ranking, 64 KB inline budget).
   - Step-by-step trace of `brain79_session_commit()` under `.locks/_transaction.lock` (Pass 1 validation, Pass 2a anti-sprawl, Pass 2b Merkle digest update, Pass 2c AST signature check, Pass 2d ripple gate, Pass 3/4 atomic disk write).
3. **Storage & concurrency design**: how `.drift_manifest.json`, `.navigation_registry.json`, and `.brain-79/.locks/` work across macOS, Linux, and Windows.

#### Deliverable 8.4: Interactive visual web guide for GitHub Pages (`docs/index.html`)
Create a self-contained, zero-build static web page at `docs/index.html` (deployable directly via GitHub Pages from the `/docs` folder) that explains `brain-79` visually:
1. **Visual comparison timeline**: an interactive "Session 1 $\rightarrow$ Session 5 $\rightarrow$ Session 10" view contrasting an unmanaged `CLAUDE.md` / raw LLM-wiki against a `brain-79` workspace.
2. **Interactive dependency & ripple graph**: an interactive diagram where clicking a source file (e.g. `src/payments.py`) highlights the governed feature manual (`features/payments.md`) and the upstream umbrella overview (`architecture/current-state.md`), showing how code changes propagate through the wiki.
3. **Interactive walkthrough tabs**: switchable views for **Software Engineering (`--profile software`)**, **Research & Analysis (`--profile general`)**, and **Project Maintenance (`update-project` & `doctor`)** with realistic file trees and terminal outputs.

---

## Acceptance criteria for Phase 8 (`v1.0.0`)

| ID | Criterion | Verification |
|---|---|---|
| **AC-1** | **Zero-clone `brain79 update`**: `update.py` upgrades `brain79` via `uv tool` when run outside a git clone, and preserves editable git-pull behavior inside a development clone. | Unit tests in `tests/test_update.py` |
| **AC-2** | **Honest, B2-clear `README.md` with real outputs**: zero hype phrases (`Zero hallucination` removed); introduces Karpathy's LLM-wiki concept; includes concrete terminal outputs for `orient`, `session_commit` ripple blocking, and `init`/`doctor`. | Human & adversarial audit |
| **AC-3** | **Complete module map & flow traces in `ARCHITECTURE.md`**: documents every module in `src/brain79/` and traces `orient` and `session_commit` in plain, direct English. | Human & adversarial audit |
| **AC-4** | **Self-contained visual web page (`docs/index.html`)**: renders cleanly in any browser without external build steps, featuring the interactive ripple graph, session timeline, and tabbed walkthroughs for GitHub Pages. | Browser verification & link check |

---

[← Volver al Índice](../INDEX.md)
