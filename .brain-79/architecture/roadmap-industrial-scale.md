---
type: architecture
summary: industrial-scale roadmap covering completed core protocol phases (0-6.5) and next-stage handoff freshness, adoption, and context guardrails (6.6-8)
stability: stable
applies_to:
  - src/brain79/__init__.py
  - src/brain79/__main__.py
  - pyproject.toml
related:
  - decisions/adr-009-declarative-schema-and-dual-ontologies.md
  - decisions/adr-010-orient-and-3-signal-context-ranking.md
  - decisions/adr-011-session-commit-and-batch-reading.md
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-013-versioning-and-release-governance.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-015-sentence-case-first-policy.md
  - features/version-governance.md
  - features/cross-platform-and-lock-isolation.md
  - features/session-triage-and-research-persistence.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - architecture/defect-backlog.md
last_updated: 2026-11-05
---

# Architecture — Industrial-scale roadmap and adoption evolution

## Overview

This document tracks the engineering roadmap of `brain-79`. Phases 0 through 6 established the core deterministic memory engine, the Two-Call Session Protocol, universal ontologies, release governance, and cross-platform `.locks/` isolation. Phases 6.5 through 8 focus on **session knowledge triage, zero-code research persistence, handoff freshness, universal harness adoption, and context-budget guardrails**.

---

## Completed foundation (Phases 0–6 — condensed)

- **[x] Phase 0 — Core invariant alignment**: unified write-time validation with organizational linting, enforced pure routing table rules on `INDEX.md` (ADR-008), fixed `bootstrap` templates, and standardized `_raw/sessions/` frontmatter.
- **[x] Phase 1 — Declarative schema & dual ontology (ADR-009)**: decoupled validation mechanism from ontology policy via `.brain-79/SCHEMA.md` with `<0.1ms` caching, built-in `software` and `general` profiles, and custom directory extensions.
- **[x] Phase 2 — Deterministic pre-work context & 1-call orientation (ADR-010)**: introduced `brain79_orient` and the 3-signal context ranker (`applies_to` path globs + field-weighted BM25 + 1-hop governing ADR graph expansion).
- **[x] Phase 3 — Zero-turn session execution (ADR-011)**: introduced `brain79_session_commit` (all-or-nothing pre-flight transaction for raw logs, writes, edits, and handoffs) and section-projected batch reads (`brain79_read_batch`).
- **[x] Phase 4 — Structural quality & drift detection (ADR-012)**: added per-type `## H2` structural skeleton enforcement, auto-injected backlink footers, and git-backed code-to-wiki drift detection (`documentation_drift_suspected`).
- **[x] Phase 5 — Versioning & release governance (ADR-013)**: single-source dynamic versioning via Hatchling (`__version__ = "2.0.0"`), FastMCP server version reporting, and automated release parity tests (SemVer, badges, changelog, CLI/MCP).
- **[x] Phase 5.5 — Defect backlog & agent protocol polish**: resolved `SCHEMA_GENERAL.md` broken root link (BUG-001) with code-fence safe footer normalizer, refined composite H2 atomicity heuristics (BUG-002), exposed active schema summary in `orient()` (INEF-002), made write receipts self-documenting (`INDEX.md auto-synced`) (INEF-001), and formalized the on-demand handoff policy across engine and manifests (INEF-003).
- **[x] Phase 6 — Centralized `.locks/` isolation, cross-platform OS portability & sentence case governance (ADR-014, ADR-015)**: isolated all mutex locks into `.brain-79/.locks/`, added automatic legacy lock purge, enforced segment-by-segment Linux case-sensitivity parity on macOS APFS, ensured POSIX path normalization across registries and engines, implemented atomic replace with retry on NTFS PermissionError, guaranteed pure LF line endings on all I/O, and standardized sentence case across all documentation and templates.
- **[x] Phase 6.5 — Session knowledge triage, research persistence guard, and handoff ergonomics**: introduced the Amnesia Test (3-way triage protocol), unpersisted research engine guard in handoff and session_commit, schema-level parameter alias tolerance (decisions, next_steps, open_questions, pending_tasks), profile-aware curation guide, redundant .brain-79/ path prefix stripping, and real-agent pre-merge E2E smoke suite (scripts/run_e2e_smoke.py).

---

## Upcoming execution roadmap (ordered by dependency and impact)

```
+-----------------------------------------------------------------------------------+
| Phase 6.5: Session triage, research guard & ergonomics                | [x] Done   |
+-----------------------------------------------------------------------------------+
| Phase 6.6: Handoff freshness, provenance & authority decay            | [ ] Next   |
+-----------------------------------------------------------------------------------+
| Phase 7: Multi-harness zero-config & doctor diagnostics               | [ ] Queued |
+-----------------------------------------------------------------------------------+
| Phase 8: Zero-clone distribution & context budget guardrails          | [ ] Planned|
+-----------------------------------------------------------------------------------+
```

### Phase 6.5 (done): Session knowledge triage, zero-code research persistence guard and handoff ergonomics
- **Specification**: [Feature — Session knowledge triage, research persistence guard and handoff ergonomics](../features/session-triage-and-research-persistence.md)
- **Scope**: eliminate the loss of zero-code research sessions and MCP handoff/path friction prior to Phase 7:
  1. **The Amnesia Test (3-way session triage in `AGENTS.md`)**: replace the `git status`-coupled *No-Op Idempotence* rule across all manifests (`src/brain79/templates/AGENTS.md`, `AGENTS.md`, `~/.pi/agent/AGENTS.md`) with a 3-way classification distinguishing **Type A** (ephemeral chat $\rightarrow$ no-op), **Type B** (zero-code research, analysis & decisions $\rightarrow$ mandatory wiki persistence in `topics/`, `decisions/`, etc., even in non-Git workspaces), and **Type C** (workspace/code mutation $\rightarrow$ sync governing articles).
  2. **Engine guard against unpersisted research (`handoff.py` & `session_commit.py`)**: block closing a knowledge-producing session (`session_type` in `{"research", "brainstorming", "analysis", "writing"}`) if zero permanent wiki articles were created/updated during the session, `knowledge_pending_promotion` is empty, and `wiki_deviation_justification` is empty—returning an actionable error that lists the active profile's directories and directs the agent to `brain79_session_commit(writes=[...], handoff={...})`.
  3. **Handoff schema ergonomics, filler filtering & `.brain-79/` prefix tolerance (`server.py`, `handoff.py`, `cli/dispatch.py`, `locks.py`)**: add explicit optional alias parameters (`decisions`, `next_steps`, `open_questions`) to `brain79_handoff_write`, `handoff-write` CLI, and `brain79_session_commit` so FastMCP's strict JSON Schema accepts them natively (maintaining 1:1 CLI/MCP symmetry in `tests/test_symmetry.py`), strip conversational no-op placeholders (`"Ninguna."`, `"None"`, `"Atender la próxima tarea..."`), expand consultative closure keywords in `validate_handoff_params`, and strip redundant leading `.brain-79/` or `./.brain-79/` path prefixes in `normalize_posix_input()`.
  4. **Profile-aware curation guide (`curate.py`)**: make `prepare_curation_guide()` inspect `load_active_schema(wiki_root)` to output profile-specific target directories (`general` vs. `software`), exclude `.locks/` from article counts, and embed the Amnesia Test rubric.

### Phase 6.6 (immediate priority): Handoff freshness, provenance and authority decay
- **Problem**: `orient()` injects the lexicographically latest handoff verbatim under "Active Handoff State". Handoffs have no lifecycle. If a later session works without writing a handoff (allowed by the on-demand policy), the next session receives an outdated handoff as if it were current, including an imperative boot instruction. The engine cannot distinguish "nothing happened since" from "everything pending was already done". The handoff template also emits Spanish headings and colons inside bold, which contradicts ADR-015 and the English-artifacts rule.
- **Principle**: a handoff is a perishable transition note, not a source of truth. Authority order: code and git > wiki > handoff. A new session must always see the latest relevant handoff, but its authority must decay with measured drift. The engine measures drift deterministically. The LLM is never trusted to infer it.
- **Non-goals**:
  - no consume-on-read, no deletion, and no mutation of handoff files during `orient` or `handoff_read` (reads stay side-effect free and idempotent);
  - no change to the on-demand handoff policy (sessions are not forced to write handoffs);
  - no new MCP tools or CLI commands (CLI/MCP symmetry unchanged).

#### R1 — provenance in handoff frontmatter (`handoff.py::write_handoff`)
- Add frontmatter fields:
  - `created_at`: ISO 8601 UTC with seconds (`YYYY-MM-DDTHH:MM:SSZ`);
  - `git_branch`: branch name, `detached`, or `none` (non-git workspace);
  - `git_head`: full SHA, or `none`;
  - `wiki_digest`: sha256 (always present);
  - `code_digest`: sha256, `none` outside git, `unknown` on failure.
- `wiki_digest`: sha256 over sorted `(posix_rel_path, sha256(file_bytes))` pairs of permanent `.md` articles under `.brain-79/`. Exclude `handoffs/`, `_raw/`, `.locks/`, `INDEX.md`, and `.navigation_registry.json`. Pure Python, profile-agnostic, and independent of mtime (safe after clone or checkout).
- `code_digest`: git workspaces only. sha256 over sorted `(path, blob_id)` pairs from `git ls-files --cached --others --exclude-standard`, hashed via `git hash-object --stdin-paths`, excluding `.brain-79/`. It must be commit-independent: committing the same working tree must not change the digest.
- Git calls run with `cwd=project_root`, a 3-second total budget, and never raise. On failure, write `unknown`.
- In `session_commit`, digests are computed after all writes and edits of the transaction are applied (the handoff stays the last step). A session's own writes must never make its own handoff stale.
- Digest and git helpers live in a new module `src/brain79/core/handoff_freshness.py`, shared by the write and read paths.

#### R2 — freshness evaluation (`handoff_freshness.py`)
- `compute_handoff_freshness(handoff_path, wiki_root) -> HandoffFreshness` (frozen dataclass) with: `state`, `reasons: list[str]`, `age_seconds`, `commits_since: int | None`, `handoff_branch`, `current_branch`, `changed_wiki_articles: list[str]`, `code_changed: bool | None`.
- States, evaluated in this precedence order:
  1. `foreign_branch`: both branches are known and differ;
  2. `stale`: the current `wiki_digest` differs, or both code digests are known and differ;
  3. `unverified`: legacy handoff without digests, or required digests are `unknown` (rendered like `stale`);
  4. `fresh`: all known digests are equal.
- `age_seconds`: from `created_at`. Legacy fallback parses the filename (`handoff-YYYY-MM-DD-HHMMSS-mmm.md`).
- `commits_since`: `git rev-list --count <git_head>..HEAD`. `None` if not git, `git_head` is unknown, or it is not an ancestor of `HEAD`.
- `changed_wiki_articles` is informational only and never decides the state. Git: `git diff --name-only <git_head> -- .brain-79/` plus untracked `.md` files under `.brain-79/`, after exclusions. Non-git: mtime newer than `created_at`. Cap the list at 10 entries plus "and N more".
- Pure read: no file writes and no locks.

#### R3 — authority-decay rendering in `orient()` and `read_handoff()`
- `fresh`: heading `## ⏱️ Active handoff state` plus a one-line banner (`> Fresh: written <age> ago on <branch>; no wiki or code changes since.`). Content verbatim.
- `stale` and `unverified`: heading `## ⏱️ Last handoff (stale: verify before acting)` plus a banner with age, commits since, changed articles, code changed (yes, no, or unknown), and reasons. In the rendered output only (never on disk), rename `## Boot instruction` to `## Boot instruction (historical: verify against current state)`.
- `foreign_branch`: heading `## ⏱️ Last handoff (from branch <x>, current branch <y>)`. Render only the provenance and `## Immediate context`. Omit pending work and the boot instruction. Add a hint to call `brain79_handoff_read` for the full text.
- `brain79_handoff_read` and `handoff-read` CLI: always return the full content, prefixed by the same banner (explicit reads are never truncated).
- The `has_promotion_pending` warning is preserved in all states.
- The renderer and the promotion detector must recognize legacy Spanish headings (`## Instrucción de arranque`, `## Contexto inmediato`, `## Conocimiento pendiente de promoción`) as well as the new English ones.

#### R4 — branch-aware `latest` resolution (`_resolve_handoff_path`)
- When the current branch is known, `latest` returns the newest handoff whose `git_branch` matches. Otherwise it falls back to the global newest (rendered as `foreign_branch` or `unverified`).
- Scan newest-first, read only frontmatter, and stop at the first match.
- Explicit refs (timestamps, prefixes, and filenames) are unaffected. `previous_ref: latest` in `write_handoff` uses the same resolution.

#### R5 — escalation of aging pending work
- When the state is not `fresh`, the handoff has `## Pending work` items, and either age ≥ `HANDOFF_ESCALATION_AGE_DAYS` (module constant, default 14) or `commits_since` ≥ `HANDOFF_ESCALATION_COMMITS` (default 20), `orient` appends: `> Pending work in this handoff is aging. Promote long-lived items to the roadmap or backlog (architecture/ or topics/), or run brain79 handoff-purge.`
- Advisory only: it never blocks.

#### R6 — English handoff template and colon formatting (`write_handoff`, `server.py`)
- Title `# Handoff — <timestamp> (UTC)`. Metadata lines `**Session type**: <x>` and `**Previous ref**: <y>` (colon outside bold).
- Headings: `## Wiki deviation (temporary)`, `## Immediate context`, `## Completed work`, `## Pending work`, `## Knowledge pending promotion`, `## Resources`, `## Gotchas`, `## Boot instruction`.
- Translate the Spanish promotion message in `server.py` (near the `Conocimiento pendiente de promoción` string) to English.
- Update tests that assert Spanish strings: `tests/test_handoff.py` (`**Tipo de sesión:**` assertions) and `tests/test_session_triage_and_handoff_ergonomics.py` (`Trabajo pendiente` assertion).

#### R7 — manifests and documentation
- Add one rule to `AGENTS.md`, `src/brain79/templates/AGENTS.md`, and `~/.pi/agent/AGENTS.md`: a handoff marked stale or from another branch is historical context; verify it against the wiki and the code before acting on its pending work or boot instruction. Sentence case.
- Create `features/handoff-freshness.md` and `decisions/adr-016-handoff-freshness-and-authority-decay.md`. Update `CHANGELOG.md`.

#### Test plan (TDD: write first, in `tests/test_handoff_freshness.py`)
1. Fresh: write a handoff with no later changes → `fresh`; `orient` shows "Active handoff state".
2. Wiki change after the handoff → `stale`; the article is listed; the boot instruction is relabeled; the handoff file is byte-identical before and after `orient`.
3. Same-transaction safety: `session_commit` with writes and a handoff → `fresh` immediately after.
4. Commit independence (git): handoff written with uncommitted changes, then `git commit -am` → still `fresh`, `commits_since == 1`.
5. Code change after the handoff (git) → `stale`, `code_changed is True`.
6. Clone and checkout safety: touch the mtime of every article → still `fresh`.
7. Foreign branch: handoff on `main`, checkout `feature` → `foreign_branch`; `orient` omits pending work and the boot instruction; `handoff_read` returns full content.
8. Branch-aware latest: newer handoff on `feature`, older on `main`; on `main`, `latest` resolves to the `main` handoff.
9. Non-git workspace (`general` profile): `git_branch`, `git_head`, and `code_digest` are `none`; freshness relies on `wiki_digest` only.
10. Legacy handoff (no provenance, Spanish headings) → `unverified`; the promotion warning is still detected; age comes from the filename.
11. Git failure or timeout (monkeypatched) → `unknown`, no exception, `unverified` rendering.
12. The escalation banner appears only when a threshold is crossed and pending work exists.
13. New handoffs use English headings and colons outside bold; no Spanish headings.
14. Idempotence: two consecutive `orient` calls produce identical handoff sections and no filesystem changes (snapshot of `handoffs/` and `.locks/`).

#### Acceptance criteria
- Full test suite green, `tests/test_symmetry.py` green (no new tools), `brain79 lint --strict` OK, and `uv run mypy src tests` clean.
- Added `orient` latency ≤ 150 ms on this repository (measured before and after).
- `scripts/run_e2e_smoke.py`: all scenarios pass with zero MCP retries.

### Phase 7: Project protocol upgrade, legacy wiki reconditioning and doctor diagnostics (`brain79 doctor`)
- **Specification**: [Feature — Project upgrade, legacy wiki conditioning, multi-harness setup & doctor diagnostics](../features/project-upgrade-and-multi-harness-doctor.md)
- **Scope**: solve "Split-Brain" version skew across existing projects via delimited managed blocks in `AGENTS.md` (`<!-- brain79:start -->`), non-destructive `SCHEMA.md` upgrades (preserving `profile` and `custom_types`), two-tier legacy wiki reconditioning (`migrate_wiki` v2), GUI-safe absolute binary paths in MCP configs, and the `brain79 doctor [--fix]` diagnostic tool.

### Phase 8: Zero-clone distribution and context budget guardrails
- **Problem**: installing or updating `brain-79` currently assumes a cloned repository (`scripts/install.py` and `git pull` inside `brain79 update`). Additionally, oversized articles can inflate `orient` payloads.
- **Deliverables:**
  1. **Standalone package installation & update**: support `uv tool install` from Git/PyPI and `uvx brain79`, decoupling `brain79 update` from local git repository assumptions.
  2. **Context budget & article size guardrails**: enforce a configurable payload ceiling (`max_chars` / `max_tokens`) in `brain79_orient` and surface an `article_too_large` warning in `brain79 lint` when articles exceed optimal context size.

---

[← Volver al Índice](../INDEX.md)
