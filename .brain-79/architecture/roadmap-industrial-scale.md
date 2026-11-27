---
type: architecture
summary: project roadmap covering completed foundation (phases 0-16 and v0.17.0) and prioritized evolution (phase 17 PyPI release and phase 18 external drift lockfile)
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
  - decisions/adr-019-external-specs-and-requirements-standard.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
  - decisions/adr-021-passive-lifecycle-hooks-and-ci-pr-gate.md
  - decisions/adr-022-polyglot-ast-guards-and-context-stats.md
  - features/version-governance.md
  - features/cross-platform-and-lock-isolation.md
  - features/session-triage-and-research-persistence.md
  - features/handoff-continuity.md
  - features/transitive-drift-and-ripple-guards.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - features/team-collaboration-and-onboarding.md
  - features/lifecycle-hooks-and-ci-gate.md
  - features/polyglot-ast-guards-and-stats.md
  - topics/v0-13-0-navigation-registry-and-lint-defects.md
  - topics/phase-16-anti-rot-benchmark-results.md
last_updated: 2026-11-26
applies_to_digest: "sha256:93eb4177afa38ce3"
applies_to_count: 12
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering and product roadmap of `brain-79`.

`brain-79` is a mechanical implementation of Andrej Karpathy's **LLM-wiki** pattern. Instead of dumping everything into one huge `CLAUDE.md` file or relying on opaque vector databases, the AI maintains a structured Markdown wiki inside `.brain-79/` guarded by mechanical linters, SHA-256 Merkle drift tracking, and atomic MCP/CLI tools.

In accordance with **ADR-017 (Pre-GA Semantic Version Calibration)**, `brain-79` stays pre-GA (`0.y.z`). Each completed phase increments the minor version (`y` in `x.y.z`). No phase bumps to `v1.0.0`; the project owner alone decides when `1.0.0` happens, and no document may imply otherwise.

Per **ADR-019**, upcoming phase specifications are authored under `specs/` outside `.brain-79/` using `specs/TEMPLATE.md` and distilled into `.brain-79/` living manuals upon completion.

---

## Completed foundation (phases 0–16)

Shipped capabilities live in their dedicated `.brain-79/features/` living manuals and release changelogs; archived pre-ADR-019 phase design specs live under `specs/archive/legacy/`.

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
- **[x] Phase 10 (`v0.11.0`)**: core architectural refactoring and hardening (`OrderedFileLock`, full Pass 3 rollback, `core/git_ops.py`, fail-closed guardrails, symlink/CLI security, `core/ast_guards/`, `core/harnesses/`, `--mcp-profile`, `ProjectContext`). Archived spec: `specs/archive/legacy/core-refactoring-and-hardening-design.md`.
- **[x] Phase 11 (`v0.12.0`)**: public release readiness and friction removal (English-first backlinks, native Claude/Cursor MDC/Copilot instruction adapters, `core` 8-tool MCP default, honest `README.md` limitations, Windows CI `orient()` hot-path optimization). Archived spec: `specs/archive/legacy/public-release-readiness-design.md`.
- **[x] Phase 12 (`v0.13.0`)**: team-safe Git collaboration and low-friction onboarding (git-ignored derived caches with deterministic zero-masking rebuilds, 3-way `INDEX.md` Git merge driver, `bootstrap --auto-map` with zero-overlap proposals, and configurable `strict`/`balanced`/`advisory` enforcement tiers). Living manual: [team-collaboration-and-onboarding.md](../features/team-collaboration-and-onboarding.md); archived spec: `specs/archive/legacy/team-collaboration-and-onboarding-design.md`.
- **[x] Patch `v0.13.1`**: integrity and version-skew hardening (`BUG-008` navigation registry disk reconciliation, `BUG-009` `index_desync` lint rule, `BUG-010` symmetric semver reverse version skew detection in `orient()`). Changelog: [v0-13-1.md](../changelog/v0-13-1.md).
- **[x] Phase 13 (`v0.14.0`)**: MCP surface pruning and focused CLI-superset architecture (pruned 13 redundant/administrative MCP wrappers and `--mcp-profile`, standardized 9-tool `MCP_TOOLS` ⊂ 24-command `WHITELIST`, ADR-020). Changelog: [v0-14-0.md](../changelog/v0-14-0.md); archived spec: `specs/archive/phase-13-mcp-surface-pruning.md`.
- **[x] Phase 14 (`v0.15.0`)**: passive lifecycle hooks and CI PR gate (opt-in `SessionStart`/`Stop` adapters for Claude Code, Antigravity, and Cursor, read-only `brain79 ci-check` engine, composite `action.yml`, dual-tier enforcement, 25-command `WHITELIST`, ADR-021). Living manual: [lifecycle-hooks-and-ci-gate.md](../features/lifecycle-hooks-and-ci-gate.md); changelog: [v0-15-0.md](../changelog/v0-15-0.md); archived spec: `specs/archive/phase-14-lifecycle-hooks-and-ci-gate.md`.
- **[x] Phase 15 (`v0.16.0`)**: polyglot AST guards, context budget telemetry, and language-agnostic docs (10 Tree-sitter parsers behind `brain79[polyglot]`, read-only `brain79 stats`, 26-command `WHITELIST`, ADR-022). Living manual: [polyglot-ast-guards-and-stats.md](../features/polyglot-ast-guards-and-stats.md); changelog: [v0-16-0.md](../changelog/v0-16-0.md); archived spec: `specs/archive/phase-15-polyglot-ast-and-stats.md`.
- **[x] Phase 16 + `SPEC-202611` (`v0.17.0`)**: longitudinal anti-rot release gate (`PASS` 7/7 on `gemini-4-hydrogen-low`: `0.0%` rot, `100.0%` canonical `src/**` coverage, `5.9x` fewer doc-read tokens, `24/24` blind recall) plus agent ergonomics, profile-aware `auto_map`, `brain79_read_batch(paths=[...])`, strict pre-flight parity, and clean `orient()` ranking. Results: [phase-16-anti-rot-benchmark-results.md](../topics/phase-16-anti-rot-benchmark-results.md); changelog: [v0-17-0.md](../changelog/v0-17-0.md); archived specs: `specs/archive/phase-16-longitudinal-anti-rot-gate.md`, `specs/archive/2026-11-agent-ergonomics-and-strict-governance.md`.

---

## Strategic evolution roadmap (`v0.18.0` onward)

```
+-----------------------------------------------------------------------------------+
| Phase 17 (P1): Automated PyPI distribution via Trusted Publishers (v0.18.0)       | [ ] Planned (unblocked by Phase 16 AC-6 PASS)
+-----------------------------------------------------------------------------------+
| Phase 18 (P1): External drift lockfile (.brain-79/drift.lock) (v0.19.0)           | [ ] Approved (SPEC-018)
+-----------------------------------------------------------------------------------+
| Deferred backlog (demand-driven only): FTS5, worktree isolation, report/graph     | [ ] Deferred
+-----------------------------------------------------------------------------------+
| Release 1.0.0: owner-decided; not tied to any phase                               | [ ] Undated
+-----------------------------------------------------------------------------------+
```

### Priority order and rationale

| Priority | Milestone | Target version | Primary objective |
|---|---|---|---|
| **P1** | Phase 17 | `v0.18.0` | Publish validated `brain79` package to PyPI via GitHub Actions Trusted Publishers (`uvx brain79`, `uv tool install brain79`, `pipx install brain79`). |
| **P1** | Phase 18 | `v0.19.0` | Eliminate hash-only frontmatter churn in Git history by moving `applies_to_digest` and `applies_to_count` into a centralized `.brain-79/drift.lock` with a 3-way Git merge driver (`SPEC-018`). |
| **Deferred** | Backlog | Undated | Build only on real user demand (FTS5 search, multi-agent worktree isolation, `report`/`graph`, and optional large-scale 40–60 file anti-rot stress test). |

---

## Phase 17 (`v0.18.0`) — PyPI distribution (P1)

Goal: eliminate raw Git URL installation friction once Phase 16's longitudinal anti-rot gate passes.

- **Automated PyPI Trusted Publishers**: configure GitHub Actions OIDC release workflow publishing `brain79` (including the `[polyglot]` extra metadata) to PyPI, enabling `uvx brain79`, `uv tool install brain79`, `uv tool install "brain79[polyglot]"`, and `pipx install brain79`.

---

## Phase 18 (`v0.19.0`) — External drift lockfile (P1, approved)

Specification: `specs/phase-18-external-drift-lockfile.md` (`SPEC-018`, `approved`).

Goal: eliminate hash-only frontmatter churn in Git commits and PR diffs without weakening Merkle drift detection, Guard C AST checks, or `git blame` readability.

- **Centralized lockfile (`.brain-79/drift.lock`)**: relocates machine-managed `applies_to_digest` and `applies_to_count` out of individual Markdown frontmatters into a deterministic, sorted JSON lockfile tracked in Git (with `!drift.lock` exception in `.brain-79/.gitignore`).
- **3-way Git merge driver (`brain79 merge-drift-lock`)**: expands `WHITELIST` from 26 to 27 commands (while keeping `MCP_TOOLS == 9`), resolving concurrent branch merges cleanly and emitting fail-closed conflict sentinels on same-key `add/add` collisions.
- **Non-destructive migration**: `brain79 migrate-wiki` strips legacy frontmatter digest keys into `drift.lock` cleanly while preserving Guard C git-history semantics.

---

## Deferred backlog (demand-driven only)

These items are intentionally excluded from active phases until real user adoption demonstrates concrete need:

- **SQLite FTS5 lexical index**: build only if Signal 2 lexical retrieval exhibits measurable recall or latency gaps on wikis exceeding ~100 articles.
- **Multi-agent / worktree session isolation**: `agent_id` and `worktree` handoff scoping (built on `ProjectContext`), deferred until concurrent multi-worktree users report collisions.
- **Human-facing observability (`brain79 report` / `graph`)**: terminal and Mermaid coverage graphs, deferred as non-critical nice-to-have.
- **Explicitly removed — local dense embeddings & MCP Code Mode**: dropped from the roadmap; local embeddings contradict `brain-79`'s zero-vector-DB thesis, and Code Mode adds latency/round-trips and native Rust sandbox overhead (`pydantic-monty`) on top of an already compact ~2K-token two-call MCP surface.

---

## Feasibility note: evolution vs. rewrite

Every active milestone is achievable **incrementally on the existing Python codebase** (`src/brain79/`) without rewriting from scratch:

- **Phase 10 seams**: `core/git_ops.py`, `core/ast_guards/`, `core/harnesses/`, `create_mcp_server()`, and `ProjectContext` isolate every extension point needed by Phases 14–15.
- **Zero-dependency core preserved**: Tree-sitter polyglot AST stays isolated behind `brain79[polyglot]`, keeping base installation fast and portable.
- **Distribution fallback**: if non-Python developer adoption stalls after PyPI due to Python/uv prerequisites, a thin wrapper (`npx` over `uvx` or Homebrew formula) solves distribution without rewriting the core engine.

---

[← Back to Index](../INDEX.md)
