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
  - architecture/agy-init-and-plugin-design.md
last_updated: 2026-11-16
applies_to_digest: "sha256:8fa9a19a1945c88a"
applies_to_count: 9
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering roadmap of `brain-79`.

`brain-79` is a mechanical implementation of Andrej Karpathy's **LLM-wiki** pattern. Instead of dumping everything into one huge `CLAUDE.md` file or relying on vector RAG, the AI maintains a structured Markdown wiki inside `.brain-79/`. Because LLMs tend to break links, create duplicate files, or leave documentation outdated when code changes, `brain-79` surrounds that Markdown wiki with a mechanical linter, SHA-256 drift tracking, and atomic MCP/CLI tools.

In accordance with **ADR-017 (Pre-GA Semantic Version Calibration)**, `brain-79` remains in `0.9.x` until it completes **Phase 7.1 (`v0.9.1`)**, **Phase 8 (`v0.9.2`)**, and **Phase 9 (`v0.9.3`)**, before graduating to `v1.0.0`.

---

## Completed foundation (Phases 0–7)

- **[x] Phase 0**: unified write/lint validation; pure routing `INDEX.md` (ADR-008); standard frontmatter.
- **[x] Phase 1**: declarative `.brain-79/SCHEMA.md` and `software`/`general` profiles (ADR-009).
- **[x] Phase 2**: `brain79_orient` 1-call context ranking via `applies_to`, BM25, and ADRs (ADR-010).
- **[x] Phase 3**: atomic `brain79_session_commit` and section-projected `brain79_read_batch` (ADR-011).
- **[x] Phase 4**: H2 section skeletons per type, auto backlinks, and code-to-wiki drift checks (ADR-012).
- **[x] Phase 5**: Hatchling single-source versioning, FastMCP version handshake, and parity tests (ADR-013).
- **[x] Phase 5.5**: root backlinks, H2 limits, schema summaries in `orient()`, and on-demand handoffs.
- **[x] Phase 6**: `.brain-79/.locks/` isolation, POSIX paths, NTFS retries, LF, sentence case (ADR-014, ADR-015).
- **[x] Phase 6.5**: 3-way session triage (`Type B` research persistence), parameter aliases, E2E smoke script.
- **[x] Phase 6.6**: git/digest-stamped handoffs (`stale`/`foreign_branch` decay in `orient()`, ADR-016).
- **[x] Phase 6.7 (`v0.8.0`)**: `.drift_manifest.json`, DAG ripple, Hard Session Ripple Gate, Anti-Sprawl, AST checks.
- **[x] Phase 6.8 (`v0.8.1`)**: three document classes, temporal decontamination, `<= 20 KB` living manuals (ADR-018).
- **[x] Phase 7 (`v0.9.0`)**: managed `AGENTS.md` blocks, `SCHEMA.md` v2, MCP harnesses, `migrate_wiki` v2, `doctor`.
- **[x] Phase 7.1 (`v0.9.1`)**: native `agy` plugin, progressive disclosure AGENTS.md/SKILL.md, ancestor root walk, doctor checks.

---

## Upcoming execution roadmap (`v0.9.x` $\rightarrow$ `v1.0.0`)

```
+-----------------------------------------------------------------------------------+
| Phase 7.1: Antigravity (agy) native plugin, AGENTS.md split & root walk (v0.9.1)  | [x] Shipped|
+-----------------------------------------------------------------------------------+
| Phase 8: Zero-clone install, honest LLM-wiki docs & visual web guide (v0.9.2)     | [ ] Planned|
+-----------------------------------------------------------------------------------+
| Phase 9: Automated battle-testing, chaos fuzzing & multi-repo gauntlet (v0.9.3)   | [ ] Planned|
+-----------------------------------------------------------------------------------+
| Release 1.0.0: Public open-source launch (after Phase 7.1, 8 & 9 verification)    | [ ] Planned|
+-----------------------------------------------------------------------------------+
```

---

### Phase 7.1: Antigravity (`agy`) zero-config plugin, progressive disclosure, and root resolution (`v0.9.1`)

`agy` ignores `.agents/mcp_config.json` (it only reads `~/.gemini/config/mcp_config.json` or `.agents/plugins/<name>/mcp_config.json`), `AGENTS.md` (`13,439` bytes) consumes excessive rules budget with an inaccurate `.mcp.json` instruction for `agy`, and `--project-root .` pins `cwd` on subdirectory launches. Full contracts and test cases are specified in [the Antigravity plugin design spec](agy-init-and-plugin-design.md).

#### Deliverable 7.1.1: Native `agy` workspace plugin (`src/brain79/core/init_project.py`)
- In `sync_project_mcp_configs()`, generate `.agents/plugins/brain79/plugin.json` (`{"name": "brain79"}`), `.agents/plugins/brain79/mcp_config.json` (`command: "brain79"`, `args: ["--project-root", "."]`), and `.agents/plugins/brain79/skills/brain79-wiki/SKILL.md` (from `src/brain79/templates/SKILL.md`).
- Preserve custom `plugin.json` fields (including `"disabled"`) and third-party `mcpServers`, back up corrupt JSON to `.bak`, and support `dry_run=True`.
- **Backward compatibility**: keep syncing `.agents/mcp_config.json`, `.mcp.json`, and `.cursor/mcp.json`; never write `brain79-<project>` entries into `~/.gemini/config/mcp_config.json` under `--include-desktop`.

#### Deliverable 7.1.2: Progressive disclosure split (`templates/AGENTS.md`, `templates/SKILL.md`)
- Trim `AGENTS.md` to `<= 6,500` bytes (`always_on`), preserving compatibility anchors (`<!-- brain79:start v{{VERSION}} -->`, `# Brain-79 AI memory protocol`, `pi-mcp-adapter`, `brain79_index`, `No-Op Idempotence`, `Zero-Modification Rule`, `## Project notes`) and fixing the `agy` setup note to reference `.agents/plugins/brain79/` or `agy mcp add`.
- Move full CLI/MCP tables, JSON examples, lint/migration guides, and `force_validation_skip` to `src/brain79/templates/SKILL.md` (`name: brain79-wiki`).

#### Deliverable 7.1.3: Ancestor root walk & `init` isolation (`__main__.py`, `config.py`, `cli/dispatch.py`)
- In `parse_global_flags()`, leave `_project_root = None` when `--project-root` is `"."` or `"./"` so `get_project_root()` walks up from `Path.cwd().resolve()` to `.brain-79/`, stopping at `.git` boundaries for nested repos.
- In `dispatch_cmd()` for `init`, resolve omitted `--project-root` to `Path.cwd().resolve()` directly so `init` stays local.

#### Deliverable 7.1.4: Doctor diagnostics & version parity (`doctor.py`, `tests/`)
- Update `run_doctor()` in `src/brain79/core/doctor.py` to validate `.agents/plugins/brain79/{plugin.json, mcp_config.json, skills/brain79-wiki/SKILL.md}`, warn when `.agents/mcp_config.json` exists without the plugin, and add `".agents/plugins/brain79"` to the `--fix` dirty-tree guard.
- Bump `__version__` to `"0.9.1"` (`src/brain79/__init__.py`, `README.md`, `CHANGELOG.md`, `.brain-79/changelog/v0-9-1.md`) per ADR-013; verify with `pytest`, `mypy src/`, and `brain79 lint --strict`.

---

### Phase 8: Zero-clone installation, honest LLM-wiki documentation, and visual web guide (`v0.9.2`)

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

### Phase 9: Automated battle-testing, chaos fuzzing, and multi-repo gauntlet (`v0.9.3`)

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

## Acceptance criteria for Phases 7.1, 8, and 9 (`v0.9.1`–`v0.9.3`)

| ID | Phase | Criterion | Verification |
|---|---|---|---|
| **AC-7.1.1** | `v0.9.1` | **Native `agy` workspace plugin**: `init` & `update-project` create `.agents/plugins/brain79/{plugin.json, mcp_config.json, skills/brain79-wiki/SKILL.md}` and retain `.agents/mcp_config.json`. | `tests/test_init_project.py` |
| **AC-7.1.2** | `v0.9.1` | **Progressive `AGENTS.md` split**: `AGENTS.md` `<= 6,500` bytes with all test anchors and accurate `agy` setup; full reference tables in `SKILL.md`. | `tests/test_init_project.py` |
| **AC-7.1.3** | `v0.9.1` | **Subdirectory root walk & `init` isolation**: `--project-root .` finds ancestor `.brain-79/`, stops at `.git` boundaries, and `init` stays local to `cwd`. | `tests/test_cli.py` |
| **AC-7.1.4** | `v0.9.1` | **Doctor & ADR-013 parity**: `doctor` flags missing `.agents/plugins/brain79/`, `doctor --fix` repairs it, and `pytest`/`mypy`/`lint --strict` pass at `v0.9.1`. | `tests/test_project_upgrade_and_doctor.py` |
| **AC-8.1** | `v0.9.2` | **Zero-clone `brain79 update`**: upgrades via `uv tool` outside a git clone and preserves editable git-pull behavior inside a dev clone. | `tests/test_update.py` |
| **AC-8.2** | `v0.9.2` | **Honest, B2-clear `README.md` & `ARCHITECTURE.md`**: zero hype claims; positions Karpathy's LLM-wiki pattern; includes real terminal outputs and a full `src/brain79/` module map. | Adversarial doc audit |
| **AC-8.3** | `v0.9.2` | **Interactive visual web guide (`docs/index.html`)**: zero-build static page with interactive ripple graph, session timeline, and tabbed walkthroughs for GitHub Pages. | Browser & link check |
| **AC-9.1** | `v0.9.3` | **Multi-OS CI matrix**: `.github/workflows/ci.yml` passes across Ubuntu, macOS, and Windows. | GitHub Actions workflow |
| **AC-9.2** | `v0.9.3` | **8-process concurrency & fuzzing**: zero file corruption, zero lock leaks, and zero unhandled exceptions under concurrent writes and adversarial fuzz inputs. | `tests/test_chaos_and_fuzzing.py` |
| **AC-9.3** | `v0.9.3` | **5-Archetype Battle Gauntlet**: all 5 realistic repository archetypes pass their full multi-session lifecycle and scale benchmarks (`< 150ms` at 200 articles / 1,000 files). | `tests/test_battle_gauntlet.py` |

---

[← Volver al Índice](../INDEX.md)
