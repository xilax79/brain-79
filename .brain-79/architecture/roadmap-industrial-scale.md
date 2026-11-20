---
type: architecture
summary: project roadmap covering completed foundation (phases 0-11) and prioritized evolution phases (12-15) for team collaboration, polyglot guards, and PyPI release
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
  - architecture/battle-testing-and-chaos-design.md
  - architecture/core-refactoring-and-hardening-design.md
  - architecture/public-release-readiness-design.md
  - architecture/team-collaboration-and-onboarding-design.md
last_updated: 2026-11-20
applies_to_digest: "sha256:6ba5881a8671db9a"
applies_to_count: 9
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering and product roadmap of `brain-79`.

`brain-79` is a mechanical implementation of Andrej Karpathy's **LLM-wiki** pattern. Instead of dumping everything into one huge `CLAUDE.md` file or relying on opaque vector databases, the AI maintains a structured Markdown wiki inside `.brain-79/` guarded by mechanical linters, SHA-256 Merkle drift tracking, and atomic MCP/CLI tools.

In accordance with **ADR-017 (Pre-GA Semantic Version Calibration)**, `brain-79` stays pre-GA (`0.y.z`). Each completed phase increments the minor version (`y` in `x.y.z`). No phase bumps to `v1.0.0`; the project owner alone decides when `1.0.0` happens, and no document may imply otherwise.

---

## Completed foundation (phases 0–10)

Detailed specifications for shipped phases live in their dedicated architecture docs and release changelogs.

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
- **[x] Phase 7.1 (`v0.9.1`)**: native `agy` plugin, progressive disclosure `AGENTS.md`/`SKILL.md`, ancestor root walk, doctor checks.
- **[x] Phase 8 (`v0.9.2`)**: zero-clone install via `uv tool`, CLI/Python 3.11+ alignment, and 3-layer Diátaxis documentation structure.
- **[x] Phase 9 (`v0.10.0`)**: automated battle-testing, multi-OS CI matrix, chaos fuzzing, 5-archetype gauntlet, and transactional rollback.
- **[x] Phase 10 (`v0.11.0`)**: core architectural refactoring and hardening (`OrderedFileLock`, full Pass 3 rollback, `core/git_ops.py`, fail-closed guardrails, symlink/CLI security, `core/ast_guards/`, `core/harnesses/`, `--mcp-profile`, `ProjectContext`). Specification: [core-refactoring-and-hardening-design.md](core-refactoring-and-hardening-design.md).
- **[x] Phase 11 (`v0.12.0`)**: public release readiness and friction removal (English-first backlinks, native Claude/Cursor MDC/Copilot instruction adapters, `core` 8-tool MCP default, honest `README.md` limitations, Windows CI `orient()` hot-path optimization). Specification: [public-release-readiness-design.md](public-release-readiness-design.md).
- **[x] Phase 12 (`v0.13.0`)**: team-safe Git collaboration and low-friction onboarding (git-ignored derived caches with deterministic zero-masking rebuilds, 3-way `INDEX.md` Git merge driver, `bootstrap --auto-map` with zero-overlap proposals, and configurable `strict`/`balanced`/`advisory` enforcement tiers). Specification: [team-collaboration-and-onboarding-design.md](team-collaboration-and-onboarding-design.md).

---

## Strategic evolution roadmap (`v0.14.0` onward)

```
+-----------------------------------------------------------------------------------+
| Phase 10 (Pre-P0): Core architectural refactoring & hardening (v0.11.0)           | [x] Done
+-----------------------------------------------------------------------------------+
| Phase 11 (P0): Public release readiness & friction removal (v0.12.0)              | [x] Done
+-----------------------------------------------------------------------------------+
| Phase 12 (P1): Team-safe Git collaboration & low-friction onboarding (v0.13.0)    | [x] Done
+-----------------------------------------------------------------------------------+
| Phase 13 (P1): Polyglot AST guards & hybrid local retrieval (v0.14.0)             | [ ] Next
+-----------------------------------------------------------------------------------+
| Phase 14 (P2): Passive agent lifecycle hooks, CI PR gate & observability (v0.15.0)| [ ] Planned
+-----------------------------------------------------------------------------------+
| Phase 15 (P2): Multi-agent isolation, benchmarks & PyPI release (v0.16.0)         | [ ] Planned
+-----------------------------------------------------------------------------------+
| Release 1.0.0: owner-decided; not tied to any phase                               | [ ] Undated
+-----------------------------------------------------------------------------------+
```

### Priority order and rationale

| Priority | Phase | Target version | Primary objective |
|---|---|---|---|
| **Pre-P0** | Phase 10 | `v0.11.0` (Done) | Fixed concurrency/rollback/security defects and decomposed monoliths for phases 11–15. |
| **P0** | Phase 11 | `v0.12.0` (Done) | Removed immediate public-launch blockers and reduced per-turn token tax. |
| **P1** | Phase 12 | `v0.13.0` (Done) | Eliminated multi-developer Git merge conflicts and eased brownfield adoption. |
| **P1** | Phase 13 | `v0.14.0` | Extend AST protection beyond Python and upgrade local search quality. |
| **P2** | Phase 14 | `v0.15.0` | Enforce protocol via native agent hooks, PR gates, and human observability. |
| **P2** | Phase 15 | `v0.16.0` | Support concurrent multi-agent worktrees, publish benchmarks, and release to PyPI. |

---

## Phase 11 (`v0.12.0`) — Public release readiness and friction removal (P0)

Detailed specification and acceptance criteria: [public-release-readiness-design.md](public-release-readiness-design.md).

Goal: remove every avoidable adoption blocker before announcing `brain-79` publicly as a preview release.

- **English-first backlink standardization**: replace the hardcoded Spanish footer invariant (`[← Volver al Índice](../INDEX.md)`) with English (`[← Back to Index](../INDEX.md)`), allow schema-level customization, and auto-migrate existing wikis cleanly via `migrate_wiki`.
- **Native multi-harness instruction adapters**: plug new adapters into `core/harnesses/` for dominant coding agents: `CLAUDE.md` (Claude Code), `.cursor/rules/brain79.mdc` (Cursor), and `.github/copilot-instructions.md` (GitHub Copilot).
- **MCP tool surface compaction (`core` default)**: switch the default FastMCP server profile to `core` (~7–8 hot-path tools: `orient`, `session_commit`, `read`, `read_batch`, `edit`, `context`, `search`, `lint`) to cut per-turn system-prompt token overhead; expose administrative tools under `--mcp-profile full` or CLI.
- **Honest positioning**: add an explicit **Limitations and trade-offs** section to `README.md` and clarify `CHANGELOG.md` pre-GA version history.

---

## Phase 12 (`v0.13.0`) — Team-safe Git collaboration and low-friction onboarding (P1)

Detailed specification and acceptance criteria: [team-collaboration-and-onboarding-design.md](team-collaboration-and-onboarding-design.md).

Goal: make `brain-79` practical for multi-developer teams on parallel branches and fast to adopt on existing large codebases.

- **Merge-conflict-free derived state**: separate human-authored Markdown from machine-derived caches (`.drift_manifest.json`, `.navigation_registry.json`). Support deterministic rebuild-on-demand (gitignore-friendly derived state) and ship an optional Git merge driver for `INDEX.md` so parallel Pull Requests stop colliding on centralized index files.
- **Automated brownfield onboarding (`bootstrap --auto-map`)**: upgrade `bootstrap` from a passive scan manifest into a deterministic repository mapper that proposes initial `applies_to` boundaries from directory structure, package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`), and git history.
- **Configurable enforcement tiers (`strict` / `balanced` / `advisory`)**: allow repositories to declare enforcement strictness in `SCHEMA.md` so teams can start with non-blocking drift warnings during onboarding and graduate to Hard Session Ripple Gates once documentation stabilizes.

---

## Phase 13 (`v0.14.0`) — Polyglot AST guards and hybrid local retrieval (P1)

Goal: extend `brain-79`'s strongest mechanical moat beyond Python and close the retrieval gap against vector/database memory tools without sacrificing Git-native simplicity.

- **Polyglot AST Guard C via optional Tree-sitter extra**: plug an optional `brain79[polyglot]` extra into `core/ast_guards/` powered by `tree-sitter` covering **TypeScript/JavaScript, Go, Rust, and Java** public symbol and signature verification while keeping Python stdlib `ast` zero-dependency by default.
- **Hybrid local retrieval (SQLite FTS5 + optional local embeddings)**: augment Signal 2 in `context.py` with a local derived SQLite FTS5 index (stdlib `sqlite3`, zero external servers) for fast stemming and phrase search, plus an optional pluggable local-embedding backend for conceptual queries where keyword overlap fails. Plain Markdown in Git remains the sole source of truth.
- **Context budget telemetry (`brain79 stats`)**: report real token estimates, `orient()` budget utilization, and drift/coverage metrics so teams can quantify context savings against raw `CLAUDE.md` files.

---

## Phase 14 (`v0.15.0`) — Passive enforcement hooks, CI PR gate, and observability (P2)

Goal: close the voluntary-compliance gap where agents ignore `AGENTS.md`, and make `.brain-79/` immediately valuable to human reviewers.

- **Native agent lifecycle hooks**: ship opt-in hook templates via `core/harnesses/` for clients that support lifecycle events (such as Claude Code `SessionStart` / `Stop` hooks and Cursor/Antigravity hooks) to inject `brain79 orient` automatically on startup and surface drifted targets before session exit.
- **Reusable GitHub Action PR Gate (`brain79 ci-check`)**: post concise Pull Request summaries listing drifted governing articles, relevant ADRs for the PR diff, and `lint --strict` status—bringing `brain-79` directly into team code review workflows.
- **Human-facing observability (`brain79 report` / `graph`)**: generate zero-dependency terminal and Mermaid reports showing code-to-wiki coverage percentage, hot drifted nodes, and stale documentation clusters.

---

## Phase 15 (`v0.16.0`) — Multi-agent coordination, ecosystem proof, and PyPI release (P2)

Goal: establish `brain-79` as the standard deterministic memory substrate for parallel autonomous agents, back its claims with reproducible evidence, and publish the matured package to PyPI.

- **Multi-agent / worktree session isolation**: add `agent_id` and `worktree` scoping to handoffs and transactional commits (built on `ProjectContext`) so concurrent subagents in parallel git worktrees share canonical governing docs without clobbering each other's handoff streams.
- **Published empirical benchmark suite**: maintain a reproducible benchmark comparing `brain-79` against raw `CLAUDE.md` and lightweight Markdown wikis across token consumption, drift detection recall, and live-agent task recovery on multiple frontier and fast models.
- **PyPI distribution**: once the protocol, multi-harness adapters, team-safe state, and polyglot guards have matured, publish `brain79` to PyPI via automated GitHub Actions Trusted Publishers, enabling `uv tool install brain79`, `uvx brain79`, and `pipx install brain79` without raw Git URLs.

---

## Feasibility note: evolution vs. rewrite

Every phase in this roadmap is achievable **incrementally on the existing Python codebase** (`src/brain79/`) without rewriting from scratch:

- **Phase 10 prepares clean seams**: `core/git_ops.py`, `core/ast_guards/`, `core/harnesses/`, `create_mcp_server()`, and `ProjectContext` isolate every extension point needed by Phases 11–15.
- **Zero-dependency core preserved**: heavy capabilities (Tree-sitter polyglot AST, optional local embeddings) are isolated behind optional Python extras (`brain79[polyglot]`, `brain79[semantic]`), keeping base installation fast and portable.
- **Only boundary that could later justify packaging work (not a rewrite)**: if non-Python developer adoption stalls due to Python/uv prerequisites, standalone binary distribution (e.g., Homebrew / `npx` wrapper over `uvx` or compiled binaries) solves distribution without rewriting the core engine.

---

[← Back to Index](../INDEX.md)
