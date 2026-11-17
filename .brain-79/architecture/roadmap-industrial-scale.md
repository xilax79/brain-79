---
type: architecture
summary: project roadmap covering completed phases (0-7) and pre-GA phases (8-9) for visual documentation and automated battle-testing
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
last_updated: 2026-11-17
applies_to_digest: "sha256:8d8688bc0228430f"
applies_to_count: 9
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering roadmap of `brain-79`.

`brain-79` is a mechanical implementation of Andrej Karpathy's **LLM-wiki** pattern. Instead of dumping everything into one huge `CLAUDE.md` file or relying on vector RAG, the AI maintains a structured Markdown wiki inside `.brain-79/`. Because LLMs tend to break links, create duplicate files, or leave documentation outdated when code changes, `brain-79` surrounds that Markdown wiki with a mechanical linter, SHA-256 drift tracking, and atomic MCP/CLI tools.

In accordance with **ADR-017 (Pre-GA Semantic Version Calibration)**, `brain-79` stays pre-GA (`0.y.z`). Phases 7.1 and 8 shipped as `v0.9.1` and `v0.9.2`. From Phase 9 onward, each completed phase increments the minor number (`y` in `x.y.z`): Phase 9 ships as `v0.10.0`. No phase bumps to `v1.0.0`; the project owner alone decides when `1.0.0` happens, and no document may imply otherwise.

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
- **[x] Phase 8 (`v0.9.2`)**: zero-clone install via `uv tool`, CLI/Python 3.11+ alignment, and 3-layer Diátaxis documentation structure.
- **[x] Phase 9 (`v0.10.0`)**: automated battle-testing, multi-OS CI matrix, chaos fuzzing, 5-archetype gauntlet, and transactional rollback.

---

## Upcoming execution roadmap (`v0.10.x` onward)

```
+-----------------------------------------------------------------------------------+
| Phase 7.1: Antigravity (agy) native plugin, AGENTS.md split & root walk (v0.9.1)  | [x] Shipped|
+-----------------------------------------------------------------------------------+
| Phase 8: Zero-clone install, CLI/runtime alignment & Diátaxis docs (v0.9.2)       | [x] Shipped|
+-----------------------------------------------------------------------------------+
| Phase 9: Automated battle-testing, chaos fuzzing & multi-repo gauntlet (v0.10.0)  | [x] Shipped|
+-----------------------------------------------------------------------------------+
| Release 1.0.0: owner-decided; not tied to any phase                               | [ ] Undated|
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

### Phase 8: Zero-clone installation, CLI/Python 3.11+ alignment, and 3-layer Diátaxis documentation (`v0.9.2`)

Before opening the repository to external users, a newcomer must be able to understand what `brain-79` does in 30 seconds, see real before/after terminal examples, and install it with one command without cloning the repository. Full engineering contracts, error messages, module maps, and verification steps are specified in [the zero-clone distribution and visual docs design](zero-clone-distribution-and-visual-docs.md).

#### Writing and communication rules (mandatory)
1. **No marketing hype or false promises**: never claim *"Zero hallucination"*, *"Zero context rot"*, or *"Your AI never forgets"*. No external tool controls LLM weights. State what `brain-79` actually does: it turns a Karpathy-style **LLM-wiki** into an enforced workflow by loading task-relevant files on startup, checking code-to-doc SHA-256 drift, and validating wiki writes before they hit the disk.
2. **Clean, human B2 English (no AI writing vices)**:
   - Write short, direct sentences (subject-verb-object).
   - Avoid AI clichés: no rule-of-three adjective chains, no endless `-ing` participial tails (*"...ensuring X, guaranteeing Y, and enabling Z"*), and no stuffing five technical terms into one sentence.
   - Show real terminal inputs and outputs instead of abstract prose.

#### Deliverable 8.1: Zero-clone self-update and holistic CLI/runtime alignment (`update.py`, `dispatch.py`, `__main__.py`, `doctor.py`, `templates/AGENTS.md`)
- Update `src/brain79/core/update.py` so `brain79 update` distinguishes a local editable git checkout (excluding `site-packages`/`dist-packages` and `$HOME` dotfiles false positives) from a standalone zero-clone install.
- Inside a local dev checkout, run `git pull --ff-only` followed by `uv tool install --editable --force .`. Inside a standalone install, run `uv tool install --force git+https://github.com/xilax79/brain-79.git` (supporting `--branch` via `@<branch>` and handling Windows running-binary lock errors gracefully).
- Fix `brain79 update` help/flag descriptions in `dispatch.py` and `ROOT_HELP` in `__main__.py` (adding `update-project` and `doctor`), align `doctor.py` Python runtime checks to `>= 3.11` matching `pyproject.toml`, and replace `--editable .` hints in `doctor.py` and `src/brain79/templates/AGENTS.md` with `uv tool install git+https://github.com/xilax79/brain-79.git`.

#### Deliverable 8.2: High-clarity, human-facing landing page (README.md) and user guide (USER_GUIDE.md)
- Rewrite `README.md` (~138 lines) in clean B2 English with ADR-015 sentence case: Karpathy LLM-wiki positioning, a 4-row comparison table, ASCII workflow diagram, and day-to-day usage walkthrough without internal engine jargon.
- Create `USER_GUIDE.md` as Diátaxis How-To and protocol reference: AGENTS.md + MCP connection, 5 concrete code-verified scenarios (cold-start orientation with 64 KB reading manifest, AST Guard C and Ripple Gate stale doc protection, gitless research, on-demand handoffs with cryptographic provenance, and MCP tool vs CLI symmetry table). Preserve the `version-0.9.2-blue.svg` badge required by `tests/test_version_governance.py`.

#### Deliverable 8.3: Developer-grade ARCHITECTURE.md (contributor-facing)
- Rewrite `ARCHITECTURE.md` retaining the three-class ontology, authority hierarchy, 1:1 symmetry (`24` CLI / `22` MCP), and `.brain-79/` layout while adding a complete 28-file `src/brain79/` module map, verified step-by-step traces of `orient()` and `commit_session()`, and cross-platform `.locks/` + atomic storage details.

#### Deliverable 8.4: Retirement of HTML documentation and 3-layer Diátaxis structure
- Remove stale `docs/whitepaper.html` and `docs/index.html` in favor of pure Markdown Diátaxis documentation (`README.md`, `USER_GUIDE.md`, `ARCHITECTURE.md`), eliminating redundant HTML maintenance and external CDN dependencies.

---

### Phase 9: Automated battle-testing, chaos fuzzing, and multi-repo gauntlet (`v0.10.0`)

Because `brain-79` is maintained by a solo builder, manual testing cannot cover every OS, git state, or LLM behavior. Phase 9 adds an automated battle-testing harness that stress-tests the engine as a pre-GA hardening step. Phase 9 changes tests, CI, scripts, and version files only; defects found are fixed in `src/` with a regression test. Full contracts, corpora, budgets, the failure catalog (F1–F16), and release gates are in [the battle-testing design](battle-testing-and-chaos-design.md).

#### Deliverable 9.1: Multi-OS GitHub Actions matrix (`.github/workflows/ci.yml`, `.gitattributes`, `tests/test_ci_workflow.py`)
- Nine jobs: Ubuntu, macOS, and Windows × Python `3.11`, `3.12`, `3.13`, `fail-fast: false`. Each runs `pytest`, `mypy src tests`, `brain79 lint --strict`, and `brain79 doctor`; doctor warnings fail the job unless allowlisted.
- Real-OS tests cover Windows file replace, `%APPDATA%`, CRLF digests, case-insensitive filenames, and POSIX hook execution.

#### Deliverable 9.2: Multiprocess stress and deterministic fuzzing (`tests/test_chaos_and_fuzzing.py`)
- 8 `spawn` workers with a barrier run `write_article`, `edit_article`, `navigate --regenerate`, and `session_commit` on one `.brain-79/`. Assert valid JSON state, no leftover temp files, all locks acquirable, no torn or lost writes, and `lint --strict` exit `0`. A SIGKILL case checks lock recovery on POSIX.
- Seeded stdlib fuzzing (no new dependency) feeds hostile YAML, encodings, Unicode, boundary sizes (`20,479`/`20,480`/`20,481` bytes), traversal paths, and wiki cycles into `validate_article_content`, `parse_frontmatter`, and `migrate_wiki`. Only `ValidationError` or `FrontmatterError` may be raised; no hang over 5 s.
- Environment faults (read-only dir, disk full, interrupt) must leave a commit fully applied or not applied.

#### Deliverable 9.3: Five-archetype gauntlet (`scripts/run_battle_gauntlet.py`, `tests/test_battle_gauntlet.py`)
- Runs a fixed 10-step lifecycle on five temporary workspaces: dirty polyglot monorepo, chaotic legacy wiki, gitless research (`--profile general`), git branch warfare with AST mutation, and a 200-article / 1,000-file scale benchmark.
- Latency budgets are in-process medians, calibrated with `scripts/benchmark_baseline.py` before they are frozen.

#### Deliverable 9.4: Live-agent recovery smoke (`scripts/run_e2e_smoke.py`)
- Add scenarios for `unresolved_session_ripple` and `duplicate_governance_target`. A real agent must self-correct from the `actionable` hint. It runs manually before release (not in CI) with `gemini-3.8-flash` at effort `low` (`medium` only if a scenario proves too complex); pass means at least 2 of 3 attempts succeed.

#### Deliverable 9.5: Release parity (`v0.10.0`)
- Bump `__version__` to `0.10.0` (`src/brain79/__init__.py`, `README.md` badge, `CHANGELOG.md`, `.brain-79/changelog/v0-10-0.md`, `AGENTS.md` anchor) per ADR-013. Mark Phase 9 shipped here and in `current-state.md`, and update affected living manuals.

---

## Acceptance criteria for Phases 7.1, 8, and 9 (`v0.9.1`–`v0.10.0`)

| ID | Phase | Criterion | Verification |
|---|---|---|---|
| **AC-7.1.1** | `v0.9.1` | **Native `agy` workspace plugin**: `init` & `update-project` create `.agents/plugins/brain79/{plugin.json, mcp_config.json, skills/brain79-wiki/SKILL.md}` and retain `.agents/mcp_config.json`. | `tests/test_init_project.py` |
| **AC-7.1.2** | `v0.9.1` | **Progressive `AGENTS.md` split**: `AGENTS.md` `<= 6,500` bytes with all test anchors and accurate `agy` setup; full reference tables in `SKILL.md`. | `tests/test_init_project.py` |
| **AC-7.1.3** | `v0.9.1` | **Subdirectory root walk & `init` isolation**: `--project-root .` finds ancestor `.brain-79/`, stops at `.git` boundaries, and `init` stays local to `cwd`. | `tests/test_cli.py` |
| **AC-7.1.4** | `v0.9.1` | **Doctor & ADR-013 parity**: `doctor` flags missing `.agents/plugins/brain79/`, `doctor --fix` repairs it, and `pytest`/`mypy`/`lint --strict` pass at `v0.9.1`. | `tests/test_project_upgrade_and_doctor.py` |
| **AC-8.1** | `v0.9.2` | **Zero-clone `brain79 update` & CLI/Python alignment**: standalone installs upgrade via `uv tool install --force git+...`, local dev checkouts preserve `git pull` + `--editable --force .`, `dispatch.py`/`ROOT_HELP`/`doctor.py`/`AGENTS.md` align on `Python >= 3.11` and zero-clone hints. | `tests/test_update.py`, `tests/test_cli.py`, `tests/test_project_upgrade_and_doctor.py` |
| **AC-8.2** | `v0.9.2` | **Three-layer Diátaxis documentation structure**: human-facing `README.md`, How-To & protocol reference `USER_GUIDE.md`, and technical specifications `ARCHITECTURE.md` with zero hype, ADR-015 sentence case, and version badge parity (`0.9.2`). | `tests/test_version_governance.py`, doc audit |
| **AC-8.3** | `v0.9.2` | **HTML docs retirement**: `docs/whitepaper.html` and `docs/index.html` removed in favor of pure, zero-dependency Markdown documentation with zero `file:///Users/` paths. | `tests/test_version_governance.py` |
| **AC-8.4** | `v0.9.2` | **Release & Merkle ripple parity**: `__version__` bumped to `0.9.2`, `CHANGELOG.md` + `changelog/v0-9-2.md` + `AGENTS.md` synced, and all impacted wiki articles updated or verified with zero drift. | `pytest`, `mypy src tests`, `brain79 lint --strict`, `brain79 doctor` |
| **AC-9.1** | `v0.10.0` | **Multi-OS CI matrix**: all 9 cells green on the release commit; workflow structure is asserted statically. | GitHub Actions, `tests/test_ci_workflow.py` |
| **AC-9.2** | `v0.10.0` | **Concurrency and fuzzing**: zero corrupt state, zero leaked locks or temp files, zero lost writes, only structured exceptions, atomic commits under faults; 20 consecutive local runs pass. | `tests/test_chaos_and_fuzzing.py` |
| **AC-9.3** | `v0.10.0` | **Five-archetype gauntlet**: all archetypes pass the 10-step lifecycle with zero data loss and budgets met; runner exit codes and JSON report schema verified. | `tests/test_battle_gauntlet.py`, `scripts/run_battle_gauntlet.py` |
| **AC-9.4** | `v0.10.0` | **Live-agent recovery**: both scenarios reach 2 of 3 successes without hints; results recorded in the changelog. | `scripts/run_e2e_smoke.py` (manual) |
| **AC-9.5** | `v0.10.0` | **Release parity**: version `0.10.0` synced across all files, wiki updated with zero drift, no `xfail` masking defects. | `pytest`, `mypy src tests`, `brain79 lint --strict`, `brain79 doctor` |

---

[← Volver al Índice](../INDEX.md)
