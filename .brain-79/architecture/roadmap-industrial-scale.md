---
type: architecture
summary: project roadmap covering completed phases (0-7) and pre-GA maturation phases (8-9) for visual documentation and automated battle-testing
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

`brain-79` is a mechanical implementation of Andrej Karpathy's **LLM-wiki** pattern. Instead of dumping everything into one huge `CLAUDE.md` file or relying on vector RAG, the AI maintains a structured Markdown wiki inside `.brain-79/`. Because LLMs tend to break links, create duplicate files, or leave documentation outdated when code changes, `brain-79` surrounds that Markdown wiki with a mechanical linter, SHA-256 drift tracking, and atomic MCP/CLI tools.

In accordance with **ADR-017 (Pre-GA Semantic Version Calibration)**, `brain-79` remains in the `0.9.x` series until it completes both **Phase 8 (`v0.9.1` — Zero-clone install & visual documentation)** and **Phase 9 (`v0.9.2` — Automated battle-testing & chaos gauntlet)**. Only after surviving multi-OS, concurrency, and live-agent stress testing will the package graduate to `v1.0.0`.

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

## Upcoming execution roadmap (`v0.9.x` $\rightarrow$ `v1.0.0`)

```
+-----------------------------------------------------------------------------------+
| Phase 8: Zero-clone install, honest LLM-wiki docs & visual web guide (v0.9.1)     | [ ] Planned|
+-----------------------------------------------------------------------------------+
| Phase 9: Automated battle-testing, chaos fuzzing & multi-repo gauntlet (v0.9.2)   | [ ] Planned|
+-----------------------------------------------------------------------------------+
| Release 1.0.0: Public open-source launch (after Phase 8 & 9 verification)         | [ ] Planned|
+-----------------------------------------------------------------------------------+
```

---

### Phase 8: Zero-clone installation, honest LLM-wiki documentation, and visual web guide (`v0.9.1`)

Before opening the repository to external users, a newcomer must be able to understand what `brain-79` does in 30 seconds, see real before/after terminal examples, and install it with one command without cloning the repository.

#### Writing and communication rules (mandatory)
1. **No marketing hype or false promises**: never claim *"Zero hallucination"*, *"Zero context rot"*, or *"Your AI never forgets"*. No external tool controls LLM weights. State what `brain-79` actually does: it turns a Karpathy-style **LLM-wiki** into an enforced workflow by loading task-relevant files on startup, checking code-to-doc SHA-256 drift, and validating wiki writes before they hit the disk.
2. **Clean, human B2 English (no AI writing vices)**:
   - Write short, direct sentences (subject-verb-object).
   - Avoid AI clichés: no rule-of-three adjective chains, no endless `-ing` participial tails (*"...ensuring X, guaranteeing Y, and enabling Z"*), and no stuffing five technical terms into one sentence.
   - Show real terminal inputs and outputs instead of abstract prose.

#### Deliverable 8.1: Zero-clone installation and self-update (`src/brain79/core/update.py`)
- **Problem**: `brain79 update` currently assumes the user cloned the Git repository to a local folder and runs `git pull`. External users install CLI tools in one line via `uv tool install`.
- **Implementation**:
  1. Update `src/brain79/core/update.py` so `brain79 update` detects how it is installed. When running inside a local development git checkout, keep `git pull` + `uv tool install --editable . --force`. When installed as a standalone tool, run `uv tool install --force git+https://github.com/xilax79/brain-79.git` (or `uv tool upgrade brain79`).
  2. Standardize the primary installation command across all docs:
     ```bash
     uv tool install git+https://github.com/xilax79/brain-79.git
     ```

#### Deliverable 8.2: High-clarity, example-driven `README.md` (user-facing)
Rewrite `README.md` to be light, visual, and grounded in concrete examples (~160–200 lines):
1. **Positioning (Karpathy's LLM-wiki with mechanical guardrails)**:
   - Explain the core idea in plain words: Andrej Karpathy popularized the **LLM-wiki** concept—giving coding agents a structured folder of Markdown files they read and update over time. In practice, raw LLM-wikis break down after a few sessions because agents leave docs outdated when code changes, create duplicate files (`auth-v2.md`), or blow up a single `CLAUDE.md` file. `brain-79` adds the mechanical layer (MCP + CLI) that keeps an LLM-wiki accurate.
2. **Visual "Without `brain-79` vs. With `brain-79`" comparison**:
   - A side-by-side table showing the 4 real failure modes:
     1. Monolithic `CLAUDE.md` / blind file reading $\rightarrow$ 1-call `brain79_orient` routed by `INDEX.md` and `applies_to`.
     2. Silent code-to-doc drift when `.py`/`.ts` files change $\rightarrow$ SHA-256 drift tracking and the session commit gate.
     3. Wiki sprawl (duplicate files for the same module) $\rightarrow$ write-time overlap check forcing edits to the existing article.
     4. Obsolete session handoffs after branch switches or manual commits $\rightarrow$ git-stamped handoffs (`fresh` vs `stale` / `foreign_branch`).
3. **Three real terminal walkthroughs ("Show, Don't Tell")**:
   - **Scene 1 — Starting a task**: what the agent receives when calling `brain79 orient --task "add refund endpoint" --paths "src/payments.py"`.
   - **Scene 2 — Catching outdated docs before session close**: the exact error message `brain79_session_commit` returns when `src/payments.py` changed its function signature and the agent forgot to update `features/payments.md` or `architecture/overview.md`.
   - **Scene 3 — Research without code (`--profile general`)**: how a research session saves structured notes into `topics/` and `decisions/`.
4. **3-command quick start & links**:
   - Install (`uv tool install git+https://...`), initialize (`brain79 init`), and diagnose (`brain79 doctor`).
   - Prominent link to the interactive visual guide on GitHub Pages (`docs/index.html`) and `ARCHITECTURE.md`.

#### Deliverable 8.3: Developer-grade `ARCHITECTURE.md` (contributor-facing)
Rewrite `ARCHITECTURE.md` in direct technical prose for engineers who want to understand how the engine works under the hood:
1. **Source code map (`src/brain79/`)**: a table mapping every `.py` module in `src/brain79/core/`, `cli/`, and `server.py` to its single responsibility.
2. **End-to-end execution flows**:
   - Step-by-step trace of `brain79_orient()` (index loading, handoff freshness check, 3-signal ranking, 64 KB inline budget).
   - Step-by-step trace of `brain79_session_commit()` under `.locks/_transaction.lock` (Pass 1 validation, Pass 2a anti-sprawl, Pass 2b Merkle digest update, Pass 2c AST signature check, Pass 2d ripple gate, Pass 3/4 atomic disk write).
3. **Storage & concurrency design**: how `.drift_manifest.json`, `.navigation_registry.json`, and `.brain-79/.locks/` work across macOS, Linux, and Windows.

#### Deliverable 8.4: Interactive visual web guide for GitHub Pages (`docs/index.html`)
Create a self-contained, zero-build static web page at `docs/index.html` (deployable directly via GitHub Pages from the `/docs` folder):
1. **Visual comparison timeline**: an interactive "Session 1 $\rightarrow$ Session 5 $\rightarrow$ Session 10" view contrasting an unmanaged `CLAUDE.md` / raw LLM-wiki against a `brain-79` workspace.
2. **Interactive dependency & ripple graph**: an interactive diagram where clicking a source file (e.g. `src/payments.py`) highlights the governed feature manual (`features/payments.md`) and the upstream umbrella overview (`architecture/current-state.md`), showing how code changes propagate through the wiki.
3. **Interactive walkthrough tabs**: switchable views for **Software Engineering (`--profile software`)**, **Research & Analysis (`--profile general`)**, and **Project Maintenance (`update-project` & `doctor`)** with realistic file trees and terminal outputs.

---

### Phase 9: Automated battle-testing, chaos fuzzing, and multi-repo gauntlet (`v0.9.2`)

Because `brain-79` is maintained by a solo builder, manual testing cannot cover every OS, git state, or LLM behavior. Phase 9 builds an automated 4-level battle-testing harness that stress-tests the engine against real-world chaos before `v1.0.0`.

#### Deliverable 9.1: Real multi-OS GitHub Actions matrix (`.github/workflows/ci.yml`)
- Run `pytest`, `mypy`, `brain79 lint --strict`, and `brain79 doctor` on real runners across **Ubuntu Linux (`ext4`)**, **macOS (`APFS`)**, and **Windows (`NTFS`)** on Python `3.10`, `3.11`, and `3.12`.
- Verify native Windows file locking, `%APPDATA%` paths, CRLF handling, and POSIX shell hook execution without relying solely on macOS mocks.

#### Deliverable 9.2: Multiprocess concurrency stress & property-based fuzzing (`tests/test_chaos_and_fuzzing.py`)
1. **8-worker multiprocess contention test**: spawn 8 concurrent OS processes executing `write_article`, `edit_article`, `navigate --regenerate`, and `session_commit` against the same `.brain-79/` folder simultaneously. Assert zero `JSONDecodeError` in `.navigation_registry.json` or `.drift_manifest.json`, zero leftover `.tmp` files, and 100% lock release.
2. **Adversarial input fuzzing**: feed malformed YAML, mixed `\r\r\n` line endings, exotic Unicode (RTL scripts, zero-width joiners, emoji slugs), deep cyclic `applies_to` graphs (`A -> B -> C -> A`), and boundary-sized payloads (`20,479` vs `20,481` bytes) into `validate_article`, `parse_frontmatter`, and `migrate_wiki`. Assert that the engine only raises structured `ValidationError` or `FrontmatterError` exceptions—never unhandled `KeyError`, `IndexError`, or `UnicodeDecodeError`.

#### Deliverable 9.3: The 5-Archetype Multi-Repo Gauntlet (`scripts/run_battle_gauntlet.py` & `tests/test_battle_gauntlet.py`)
An automated end-to-end gauntlet that builds 5 realistic workspace archetypes in temporary directories and runs a 10-step lifecycle on each:
1. **Archetype 1 — Dirty Polyglot Monorepo**: Python + TypeScript + binary assets (`.png`, `.sqlite`) + large ignored directories (`node_modules/`, `.venv/`, `dist/`). Verifies that `WorkspaceIndex` ignores junk, indexes under `< 50ms`, and tracks cross-language `applies_to` globs.
2. **Archetype 2 — Chaotic Pre-Brain79 Legacy Wiki**: 25 handwritten `.md` files with missing frontmatter, broken links, missing H2 sections, a custom Husky pre-commit hook, and hardcoded `/Users/old/brain79` paths in `.mcp.json`. Runs `brain79 init --upgrade` and `brain79 doctor --fix`, asserting zero data loss, automatic `status: legacy` exemptions, preserved Husky hooks, and `lint --strict` exit code `0`.
3. **Archetype 3 — Gitless Research Workspace (`--profile general`)**: zero code files and no `.git` directory across 10 simulated research and decision sessions. Verifies the Amnesia Test guard, custom `SCHEMA.md` folder types, and gitless handoff freshness.
4. **Archetype 4 — Git Branch Warfare & AST Mutation**: simulates switching between `main`, `feat/payments`, and `hotfix/auth`, rebasing commits, mutating public Python function signatures, and attempting rubber-stamp bypasses via `verified_articles`. Verifies `foreign_branch` / `stale` handoff detection, Guard C AST blocking, and ripple gate recovery.
5. **Archetype 5 — High-Scale Wiki Benchmark (200 wiki articles & 1,000 source files)**: verifies that `orient()`, `lint --strict`, and `doctor` stay within strict latency budgets (`< 150ms`) under heavy repository scale.

#### Deliverable 9.4: Live-agent auto-recovery smoke suite (`scripts/run_e2e_smoke.py` v2)
- Expand the headless agent E2E script to test **closed-loop error recovery**: intentionally place the workspace in a state where the agent's first `session_commit` triggers `unresolved_session_ripple` or `duplicate_governance_target`, and verify that a real LLM reads the `actionable` remediation hint and self-corrects on its very next tool call without human help.

---

## Acceptance criteria for Phases 8 & 9 (`v0.9.1` & `v0.9.2`)

| ID | Phase | Criterion | Verification |
|---|---|---|---|
| **AC-8.1** | `v0.9.1` | **Zero-clone `brain79 update`**: upgrades via `uv tool` outside a git clone and preserves editable git-pull behavior inside a dev clone. | `tests/test_update.py` |
| **AC-8.2** | `v0.9.1` | **Honest, B2-clear `README.md` & `ARCHITECTURE.md`**: zero hype claims; positions Karpathy's LLM-wiki pattern; includes real terminal outputs and a full `src/brain79/` module map. | Adversarial doc audit |
| **AC-8.3** | `v0.9.1` | **Interactive visual web guide (`docs/index.html`)**: zero-build static page with interactive ripple graph, session timeline, and tabbed walkthroughs for GitHub Pages. | Browser & link check |
| **AC-9.1** | `v0.9.2` | **Multi-OS CI matrix**: `.github/workflows/ci.yml` passes across Ubuntu, macOS, and Windows. | GitHub Actions workflow |
| **AC-9.2** | `v0.9.2` | **8-process concurrency & fuzzing**: zero file corruption, zero lock leaks, and zero unhandled exceptions under concurrent writes and adversarial fuzz inputs. | `tests/test_chaos_and_fuzzing.py` |
| **AC-9.3** | `v0.9.2` | **5-Archetype Battle Gauntlet**: all 5 realistic repository archetypes pass their full multi-session lifecycle and scale benchmarks (`< 150ms` at 200 articles / 1,000 files). | `tests/test_battle_gauntlet.py` |

---

[← Volver al Índice](../INDEX.md)
