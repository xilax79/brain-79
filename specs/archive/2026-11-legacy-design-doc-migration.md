---
spec_id: SPEC-202611-legacy-design-doc-migration
title: Audit, distill, and archive the six pre-ADR-019 legacy design documents
target_version: TBD
status: implemented
owner: xilax
last_updated: 2026-11-21
related_wiki:
  - decisions/adr-018-living-manuals-and-temporal-decontamination.md
  - decisions/adr-019-external-specs-and-requirements-standard.md
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
target_wiki:
  - features/team-collaboration-and-onboarding.md
  - features/transitive-drift-and-ripple-guards.md
  - features/project-upgrade-and-multi-harness-doctor.md
  - features/mcp-server.md
  - architecture/roadmap-industrial-scale.md
  - architecture/current-state.md
  - product/overview.md
---

# SPEC-202611-legacy-design-doc-migration — Audit, distill, and archive the six pre-ADR-019 legacy design documents

## Problem statement and goal

Six pre-ADR-019 phase design documents remain inside `.brain-79/architecture/` (`agy-init-and-plugin-design.md`, `zero-clone-distribution-and-visual-docs.md`, `battle-testing-and-chaos-design.md`, `core-refactoring-and-hardening-design.md`, `public-release-readiness-design.md`, and `team-collaboration-and-onboarding-design.md`). They consume `INDEX.md` lines, inject historical task instructions into `brain79_orient()`, and hold live behavior (notably Phase 12 capabilities) that lacks dedicated living manuals. This specification governs auditing coverage, distilling missing live knowledge into `.brain-79/` living manuals, archiving the six documents to `specs/archive/legacy/`, and emptying the temporary allowlist in `tests/test_specs_governance.py`.

## Non-goals (out of scope)

- **No source code behavior changes**: do not modify runtime behavior under `src/brain79/`.
- **No Phase 13 authoring**: do not draft or implement Phase 13 (`v0.14.0`) features under this specification.
- **No rewrite of legacy prose**: archived files under `specs/archive/legacy/` are preserved as historical artifacts without converting them to EARS/BDD syntax.
- **No modification of `changelog/` or existing ADRs (ADR-001 through ADR-018)**: preserve Chesterton's Fence and immutable audit history.

## Dependencies

- **Accepted standard**: [ADR-019](../../.brain-79/decisions/adr-019-external-specs-and-requirements-standard.md) and `tests/test_specs_governance.py`.
- **External / optional**: none.

## Constraints and invariants

- **Living manuals and temporal decontamination**: per [ADR-018](../../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md) (`<= 20 KB`, `<= 400` lines, present-tense system truth, zero milestone markers in titles/overviews).
- **Documentation style**: sentence case and clean B2 English per [ADR-015](../../.brain-79/decisions/adr-015-sentence-case-first-policy.md).
- **One-way boundary**: no `.brain-79/` article may list `specs/` in `applies_to` per [ADR-019](../../.brain-79/decisions/adr-019-external-specs-and-requirements-standard.md).
- **Zero governance regression**: every production module currently governed exclusively by any of the six legacy design docs MUST retain `applies_to` coverage in an active living manual after archival.

## Open questions

- [x] **Q-1**: consolidate Phase 10/11 modules into existing living manuals (`core/ast_guards/**` -> `features/transitive-drift-and-ripple-guards.md`, `core/harnesses/**` -> `features/project-upgrade-and-multi-harness-doctor.md`, `core/auto_map.py` + `core/git_ops.py` -> new `features/team-collaboration-and-onboarding.md`) rather than creating a redundant `architecture/core-subsystems.md`.
- [x] **Q-2**: archive `battle-testing-and-chaos-design.md` directly to `specs/archive/legacy/` because it governed `tests/` and `.github/workflows/` rather than `src/brain79/` production modules.

## Requirements (EARS)

### Coverage audit and distillation

- **R-1.1**: BEFORE moving any of the six legacy design documents out of `.brain-79/architecture/`, THE migration SHALL audit every `applies_to` target in those six files and identify all `src/brain79/` modules lacking coverage in remaining living manuals.
- **R-1.2**: THE living manuals in `.brain-79/features/` and `.brain-79/architecture/` SHALL document all uncovered shipped capabilities (including Phase 12 derived-state rebuilds, `INDEX.md` Git merge driver, `bootstrap --auto-map`, and `strict`/`balanced`/`advisory` enforcement tiers) with non-overlapping `applies_to` patterns.

### Archival, link integrity, and allowlist removal

- **R-2.1**: WHEN distillation is complete, THE migration SHALL move all six legacy design documents to `specs/archive/legacy/` and remove them from `.brain-79/architecture/`.
- **R-2.2**: WHEN the six files are moved, THE wiki SHALL update all internal links and `related:` entries (including `architecture/roadmap-industrial-scale.md` and `architecture/current-state.md`) so `brain79 lint --strict` reports zero broken links and zero structural errors.
- **R-2.3**: WHEN all six legacy files are archived, `tests/test_specs_governance.py` SHALL empty `LEGACY_ARCHITECTURE_SPECS_ALLOWLIST` so zero legacy design specs remain exempted.

## Interface and error contract

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `uv run brain79 lint --strict` | Broken relative link or dangling `related:` reference after moving files | Fail validation and report exact article and target path | Exit `1` |
| `uv run pytest tests/test_specs_governance.py` | Residual `*-design.md` or spec-like file in `.brain-79/` after allowlist is emptied | Fail governance test with offending file path | Exit `1` |
| `uv run brain79 navigate --regenerate --rebuild` | Removed articles linger in `.navigation_registry.json` or `INDEX.md` | Deterministically rebuild index from on-disk `.brain-79/` Markdown files | Exit `0` |

## Migration and rollout

- **Default behavior**: zero runtime impact on `brain79` CLI/MCP users; changes are scoped to repository documentation, `specs/archive/legacy/`, and `tests/test_specs_governance.py`.
- **Upgrade path**: not required for external repositories.
- **Rollback safety**: pure Git revert restores `.brain-79/architecture/` and `INDEX.md` cleanly.

## Acceptance criteria (Given / When / Then)

### AC-1 — Zero uncovered production modules after archival
- **Verifies**: `R-1.1`, `R-1.2`
- **Method**: `inspection`
- **Test ref**: `coverage audit script (0 uncovered src/brain79/ modules beyond core/__init__.py) + brain79 lint --strict`
- **Given**: the six legacy design documents are removed from `.brain-79/architecture/` and living manuals are updated.
- **When**: auditing `applies_to` coverage across `.brain-79/features/` and `.brain-79/architecture/` and running `uv run brain79 lint --strict`.
- **Then**: every production module under `src/brain79/` previously covered by the six legacy docs is governed by an active living manual with zero `anti_sprawl_overlap_violation` warnings and `<= 20 KB` per article.

### AC-2 — All six legacy docs archived under `specs/archive/legacy/`
- **Verifies**: `R-2.1`
- **Method**: `inspection`
- **Test ref**: `ls specs/archive/legacy/ (6 files) && test_no_new_design_specs_in_living_wiki_dirs`
- **Given**: the completed migration branch.
- **When**: listing `.brain-79/architecture/` and `specs/archive/legacy/`.
- **Then**: none of the six legacy files exist under `.brain-79/architecture/`, and all six exist intact under `specs/archive/legacy/`.

### AC-3 — Zero broken links and clean strict lint
- **Verifies**: `R-2.2`
- **Method**: `ci`
- **Test ref**: `uv run brain79 lint --strict ([Status: OK], 0 errors, 0 warnings, 0 orphans)`
- **Given**: updated links in `roadmap-industrial-scale.md`, `current-state.md`, and any affected `related:` frontmatter fields, plus regenerated `INDEX.md`.
- **When**: running `uv run brain79 lint --strict`.
- **Then**: command exits `0` with `[Status: OK]`, `0` broken local links, `0` namespace violations, `0` structural errors/warnings, and `0` orphans.

### AC-4 — Empty legacy allowlist enforced in CI
- **Verifies**: `R-2.3`
- **Method**: `test`
- **Test ref**: `tests/test_specs_governance.py::test_no_new_design_specs_in_living_wiki_dirs`
- **Given**: `LEGACY_ARCHITECTURE_SPECS_ALLOWLIST` in `tests/test_specs_governance.py` is empty (`frozenset()`).
- **When**: running `uv run pytest tests/test_specs_governance.py`.
- **Then**: all governance tests pass with exit code `0`.

## Wiki impact map

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/core/auto_map.py`, `src/brain79/core/git_ops.py` | `features/team-collaboration-and-onboarding.md` | `create` |
| `src/brain79/core/ast_guards/**` | `features/transitive-drift-and-ripple-guards.md` | `update` |
| `src/brain79/core/harnesses/**`, `init_project.py`, `doctor.py` | `features/project-upgrade-and-multi-harness-doctor.md` | `update` |
| `src/brain79/server.py`, `src/brain79/__main__.py` | `features/mcp-server.md` | `update` |
| `.brain-79/architecture/roadmap-industrial-scale.md` | `architecture/roadmap-industrial-scale.md` | `update` |
| `.brain-79/architecture/current-state.md` | `architecture/current-state.md` | `update` |
| `.brain-79/product/overview.md` | `product/overview.md` | `update` |

## Verification gate

```bash
uv run pytest
uv run mypy src tests
uv run brain79 lint --strict
uv run brain79 doctor
```

## Amendments

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| 2026-11-21 | xilax | Added `features/transitive-drift-and-ripple-guards.md` (for `core/ast_guards/**`), `features/mcp-server.md`, and `product/overview.md` (ripple umbrella) to `target_wiki` and `## Wiki impact map` based on coverage audit. | `R-1.2`, `AC-1` |

## Wiki distillation checklist (post-implementation)

- [x] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [x] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [x] Empty `LEGACY_ARCHITECTURE_SPECS_ALLOWLIST` in `tests/test_specs_governance.py`.
- [x] Update `.brain-79/decisions/adr-019-external-specs-and-requirements-standard.md` `## Transition` section to mark legacy migration complete.
- [x] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
