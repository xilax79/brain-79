---
type: architecture
summary: technical design for zero-clone installation, CLI/Python alignment, and 3-layer Diátaxis documentation
stability: stable
allow_overlapping_governance: true
applies_to:
  - src/brain79/core/update.py
  - src/brain79/cli/dispatch.py
  - src/brain79/__main__.py
  - src/brain79/core/doctor.py
  - src/brain79/templates/AGENTS.md
  - README.md
  - ARCHITECTURE.md
  - USER_GUIDE.md
related:
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - features/version-governance.md
  - features/cli.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - decisions/adr-013-versioning-and-release-governance.md
  - decisions/adr-015-sentence-case-first-policy.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
last_updated: 2026-11-17
applies_to_digest: "sha256:6d5b8e988ca3833d"
applies_to_count: 8
---

# Architecture — Zero-clone distribution, honest documentation, and 3-layer Diátaxis structure

## Overview

This document defines the complete implementation contract for `v0.9.2` so an agent can execute every deliverable sequentially on a new branch without ambiguity or broken invariants.

Scope clarifications against older repository notes:
- **Target version**: `0.9.2` per [the roadmap](roadmap-industrial-scale.md) (superseding the early `0.10.0` estimate in ADR-017).
- **Context budget**: `orient()` already enforces `MAX_ORIENT_INLINE_CHARS = 64_000`; no `max_tokens` parameter or PyInstaller standalone binary is in scope.
- **Primary install path**: `uv tool install git+https://github.com/xilax79/brain-79.git` (`Python >= 3.11`).

---

## Zero-clone self-update contract (src/brain79/core/update.py)

### Installation mode detection

1. Resolve `spec = importlib.util.find_spec("brain79")`. Return exit code `1` if missing or `brain79_path` does not exist.
2. Prevent false-positive `.git` matches (such as a user's `$HOME/.git` dotfiles repository when `uv` installs tools under `~/.local/share/uv/tools/`):
   - Treat `brain79_path` as a **standalone install** whenever `"site-packages"` or `"dist-packages"` appears in `brain79_path.parts` (unless PEP 610 `direct_url.json` declares `dir_info.editable == true` AND `dir_info` URL resolves to a local git checkout containing `pyproject.toml`).
   - Otherwise, walk `brain79_path.parents` for `.git`. If found, treat as a **local editable checkout**; if not found, treat as a **standalone install**.
   - Preserves `tests/test_update.py::test_missing_pyproject` (where `src/brain79/__init__.py` sits beside `.git` without `site-packages`).

### Branch A: local editable git checkout

Preserve all existing safety checks (`git` and `uv` in PATH $
ightarrow$ `4`; `pyproject.toml` exists $
ightarrow$ `1`; `origin` remote $
ightarrow$ `1`; clean tracked working tree $
ightarrow$ `1`; non-detached branch matching default or `--branch` $
ightarrow$ `1`; `git fetch origin` $
ightarrow$ `3`; up-to-date `HEAD == origin/<branch>` $
ightarrow$ `0`; `git pull --ff-only` $
ightarrow$ `1` on divergence or `3` on network failure).

Fix the rebuild bug on line 210 of `update.py`:
- Run `["uv", "tool", "install", "--editable", "--force", "."]` (`timeout=180`), not `uv tool install --force .` (which silently replaced editable dev installs with static wheel copies).
- On failure, warn with `"Please run 'uv tool install --editable --force .' manually."` and return `1`.
- On success, print `"[OK] Successfully updated brain79. Run 'brain79 update-project' inside existing repositories to sync templates."` and return `0`.

### Branch B: standalone zero-clone install

1. Verify `shutil.which("uv")`; if missing, print `"[ERR] Missing required binary: 'uv'."` and return `4`.
2. Define `UPSTREAM_REPO_URL = "https://github.com/xilax79/brain-79.git"`.
3. If `branch_override` is provided, validate it matches `^[A-Za-z0-9._/-]+$` (return `1` if invalid) and build `target_url = f"git+{UPSTREAM_REPO_URL}@{branch_override}"`; otherwise `target_url = f"git+{UPSTREAM_REPO_URL}"`.
4. Run `["uv", "tool", "install", "--force", target_url]` with `capture_output=True`, `text=True`, `timeout=180`.
5. Failure and platform guards:
   - `subprocess.TimeoutExpired` $
ightarrow$ print network/timeout error and return `3`.
   - Windows locked-executable guard: if `sys.platform == "win32"` and output contains `"access is denied"` or `"being used by another process"`, print an actionable message instructing the user to run `uv tool install --force git+https://github.com/xilax79/brain-79.git` from a fresh terminal and return `3`.
   - Other non-zero exit codes: print concise `stderr`/`stdout` diagnostic; return `3` for network/remote errors or `1` otherwise.
6. On success, print `"[OK] Successfully updated brain79. Run 'brain79 update-project' inside existing repositories to sync templates."` and return `0`.

---

## Holistic CLI, Python 3.11+, and template alignment

Apply these paired fixes so the whole product speaks with one voice:

1. **`src/brain79/cli/dispatch.py` (`cmd == "update"`)**:
   - Change `description` from *"Update project templates and schema..."* to `"Update the installed brain79 CLI tool from upstream Git or local development checkout."`.
   - Change `--branch` `help` from *"Template branch override..."* to `"Git branch to install or pull from (default: upstream default branch)"`.
2. **`src/brain79/__main__.py` (`ROOT_HELP`)**:
   - Change `update` line to: `update                Update the installed brain79 CLI tool`.
   - Add under `Maintenance & governance`: `update-project        Upgrade AGENTS.md, SCHEMA.md, and MCP harnesses in this repo` and `doctor                Run 7-point operational diagnostics and optional --fix`.
3. **`src/brain79/core/doctor.py`**:
   - Raise minimum runtime check from `(3, 10)` to `(3, 11)` to match `pyproject.toml` (`requires-python = ">=3.11"`) and `datetime.UTC` usage across `src/brain79/core/`.
   - Update missing binary hint (line 172) to: `"Run 'uv tool install git+https://github.com/xilax79/brain-79.git' or 'uv tool ensurepath'."`.
4. **`src/brain79/templates/AGENTS.md`** (synced to root `AGENTS.md` via `update-project`):
   - Replace `uv tool install --editable .` on line 5 with `uv tool install git+https://github.com/xilax79/brain-79.git`.
   - Keep total size `<= 6,500` bytes and preserve all test anchors (`<!-- brain79:start v{{VERSION}} -->`, `# Brain-79 AI memory protocol`, `pi-mcp-adapter`, `brain79_index`, `No-Op Idempotence`, `Zero-Modification Rule`, `## Project notes`).
5. **`scripts/install.py`**: keep intact as the local contributor editable installer (`tests/test_install.py` remains unchanged and green).

---

## Writing rules and honest README.md design

### Mandatory communication rules

- **Zero marketing hype**: forbid *"Zero hallucination"*, *"Zero context rot"*, *"Your AI never forgets"*, and *"Enterprise-ready"*. State accurately that `brain-79` turns a Karpathy-style **LLM-wiki** into an enforced workflow using startup routing, SHA-256 drift checks, and write validation.
- **Clean B2 English**: short subject-verb-object sentences; no rule-of-three adjective chains; no `-ing` participial tails.
- **ADR-015 sentence case**: apply sentence case across all headings, bullet labels, and table headers (`- **Label**: description`).

### README.md structure (~138 lines)

1. **Header and badges**: preserve `[![Version](https://img.shields.io/badge/version-0.9.2-blue.svg)](pyproject.toml)` (required by `tests/test_version_governance.py`), MIT license badge, and **Python 3.11+** badge.
2. **Karpathy LLM-wiki positioning**: concise explanation of raw LLM-wiki decay vs `brain-79` mechanical guardrails.
3. **Side-by-side comparison table** (*"Without `brain-79` vs. with `brain-79`"*): cover the 4 failure modes (`CLAUDE.md` bloat $
ightarrow$ `brain79_orient`; silent drift $
ightarrow$ `.drift_manifest.json` + ripple gate; wiki sprawl $
ightarrow$ subsumption check; obsolete handoffs $
ightarrow$ git-stamped freshness).
4. **Day-to-day usage walkthrough**: 3-step ASCII flow diagram explaining natural-language prompting via MCP without internal engine jargon, linking to `USER_GUIDE.md`.
5. **Capabilities and quick start**: software repos, gitless research (`--profile general`), multi-harness setup, and quick CLI maintenance (`init`, `doctor`, `update`, `update-project`).
6. **Diátaxis documentation links**: link to `USER_GUIDE.md`, `ARCHITECTURE.md`, and `CHANGELOG.md`.

---

## Developer-grade ARCHITECTURE.md design

Rewrite `ARCHITECTURE.md` in direct B2 technical prose with ADR-015 sentence case:

1. **Retained core models**: condense the Three-Class Document Ontology, Authority Hierarchy (`code and git > wiki > handoff`), 1:1 CLI/MCP symmetry (`24` CLI subcommands, `22` MCP tools), `.brain-79/` directory layout, and Key Runtime Invariants.
2. **Complete source code map (`src/brain79/`)**: map all **28 `.py` modules** to their single responsibility.
3. **Verified trace of `orient()` (`src/brain79/core/orient.py`)**:
   - `check_protocol_version_skew` $
ightarrow$ `INDEX.md` + Active Schema Summary $
ightarrow$ `WorkspaceIndex.build` $
ightarrow$ `_resolve_handoff_path("latest")` + `compute_handoff_freshness` $
ightarrow$ `git status --porcelain=v1 -z` $
ightarrow$ `detect_all_drift` $
ightarrow$ `rank_context_articles` $
ightarrow$ `MAX_ORIENT_INLINE_CHARS = 64_000` ceiling and Mandatory Reading Manifest (`brain79_read_batch`).
4. **Verified trace of `commit_session()` (`src/brain79/core/session_commit.py`)**:
   - Pass 1 (in-memory `virtual_fs` validation) $
ightarrow$ `_transaction.lock` $
ightarrow$ Pass 2a (`applies_to_target_missing` + `check_anti_sprawl_overlap`) $
ightarrow$ Pass 2b (2-iteration fixed-point digest convergence) $
ightarrow$ Pass 2c (bottom-up leaf-then-umbrella `verified_articles` Guards A/B/C) $
ightarrow$ Pass 2d (Hard Session Ripple Gate `unresolved_session_ripple`) $
ightarrow$ Pass 3 (atomic `.drift_manifest.json`, `_raw/sessions/`, `write_article`, single `regenerate_index_navigation`) $
ightarrow$ Pass 4 (post-persistence `write_handoff()`).
5. **Storage and cross-platform concurrency**: `.drift_manifest.json`, `.navigation_registry.json`, `.brain-79/.locks/` isolation, `atomic_replace_with_retry()`, POSIX `.as_posix()`, LF normalization, APFS case parity, and 64 KB CRLF/BOM-normalized SHA-256 streaming.

---

## Retirement of HTML documentation and Diátaxis Markdown adoption

- **Retire HTML documentation**: deleted `docs/whitepaper.html` and `docs/index.html` to eliminate redundant and desynchronized web files. All user and technical documentation is authored in clean, accessible Markdown following Diátaxis:
  1. Explanation & landing page: `README.md`
  2. How-To workflows and protocol reference: `USER_GUIDE.md`
  3. Technical architecture and runtime specifications: `ARCHITECTURE.md`
- **Zero build and zero external dependencies**: removes dual-format maintenance overhead, eliminates external CDN script/style attack surfaces, and guarantees complete readability across offline, CLI, and web environments.

---

## Verification, test suite, and release checklist

Execute sequentially on a new feature branch:

1. **Code updates**: implement `update.py`, `cli/dispatch.py`, `__main__.py`, `doctor.py`, and `templates/AGENTS.md`.
2. **Automated tests**:
   - Update `tests/test_update.py` for standalone `uv tool install --force`, `--branch` override, invalid `--branch` rejection, missing `uv` (exit `4`), timeout/network errors (exit `3`), Windows lock error handling, `$HOME/.git` dotfiles non-interference inside `site-packages`, and `--editable --force .` preservation in dev checkouts.
   - Add assertions in `tests/test_cli.py`, `tests/test_project_upgrade_and_doctor.py`, and `tests/test_init_project.py` verifying updated `update --help`, `ROOT_HELP`, `doctor` `>= 3.11` check, and `AGENTS.md` size `<= 6,500` bytes with zero `--editable` user hint.
3. **Documentation refactoring**: rewrite `README.md` and `ARCHITECTURE.md`, create `USER_GUIDE.md`, remove `docs/index.html` and `docs/whitepaper.html`, and verify zero external CDN URLs, zero broken anchors/links, zero `file:///Users/` paths, and zero hype phrases.
4. **Release parity (`v0.9.2`)**: bump `__version__ = "0.9.2"` in `src/brain79/__init__.py`, update `CHANGELOG.md`, create `.brain-79/changelog/v0-9-2.md`, and run `uv run brain79 update-project` to sync root `AGENTS.md` to `v0.9.2`.
5. **Wiki ripple closure**: update impacted articles (`features/version-governance.md`, `features/cli.md`, `features/project-upgrade-and-multi-harness-doctor.md`, `architecture/dispatcher.md`, `architecture/current-state.md`, `architecture/roadmap-industrial-scale.md`, `product/overview.md`), replace `docs/index.html` with `USER_GUIDE.md` in `applies_to`, and verify unchanged governed docs via `verified_articles` in `brain79_session_commit`.
6. **Final verification gate**: `uv run pytest`, `uv run mypy src tests`, `uv run brain79 lint --strict`, `uv run brain79 doctor`.

---

[← Volver al Índice](../INDEX.md)
