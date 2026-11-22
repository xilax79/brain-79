---
spec_id: SPEC-XXX  # Roadmap phases: SPEC-013 (file: phase-13-<slug>.md); ad-hoc: SPEC-YYYYMM-<slug> (file: YYYY-MM-<slug>.md)
title: Short descriptive title
target_version: TBD  # Informational only; roadmap-industrial-scale.md owns release versions
status: draft  # Active (in specs/): draft | approved | in_progress; Closed (in specs/archive/): implemented | superseded | abandoned
owner: <github-handle>
last_updated: YYYY-MM-DD
related_wiki:  # Existing .brain-79/ articles providing context (paths relative to .brain-79/; must exist)
  - architecture/roadmap-industrial-scale.md
target_wiki:  # .brain-79/ living manuals to create or update by closure (must exist when status is implemented)
  - features/<target-living-manual>.md
---

# SPEC-XXX — Short descriptive title

## Problem statement and goal

Describe the concrete problem in 2–4 sentences and the measurable outcome this specification achieves. Focus on observable system behavior rather than internal refactoring steps.

## Non-goals (out of scope)

Explicitly list what agents and contributors MUST NOT build, refactor, or change under this specification:

- **Non-goal 1**: description of excluded capability or optimization.
- **Non-goal 2**: description of untouched subsystem or deferred work.

## Dependencies

List prerequisite phases, specs, architectural seams, or optional extras required before implementation begins:

- **Internal seams**: e.g., `src/brain79/core/ast_guards/` (shipped in Phase 10).
- **External / optional**: e.g., none (zero-dependency core) or optional extra `brain79[<extra>]`.

## Constraints and invariants

All requirements must preserve the repository's canonical invariants (link rather than duplicate prose):

- **Versioning**: pre-GA minor versioning per [ADR-017](../.brain-79/decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md).
- **Concurrency and cross-platform I/O**: lock hierarchy and atomic LF writes per [ADR-014](../.brain-79/decisions/adr-014-centralized-locks-and-cross-platform-io.md).
- **CLI and MCP symmetry**: 1:1 parity per [ADR-001](../.brain-79/decisions/adr-001-hybrid-cli.md) and [symmetry.md](../.brain-79/architecture/symmetry.md).
- **Exit codes**: POSIX exit code policy (`0`, `1`, `2`, `3`, `130`) per [dispatcher.md](../.brain-79/architecture/dispatcher.md).
- **Documentation style**: sentence case and living manual rules per [ADR-015](../.brain-79/decisions/adr-015-sentence-case-first-policy.md) and [ADR-018](../.brain-79/decisions/adr-018-living-manuals-and-temporal-decontamination.md).
- **Spec-specific invariants**: add any additional hard constraints unique to this spec.

## Open questions

All open questions MUST be resolved (`[x]`) before the `owner` transitions this specification from `draft` to `approved`. Agents MUST NOT implement a `draft` specification.

- [ ] **Q-1**: unresolved design or contract question (decision owner: `<handle>`).

## Requirements (EARS)

Author requirements using EARS (Easy Approach to Requirements Syntax):

- **Ubiquitous**: `THE <system> SHALL <response>.`
- **Event-driven**: `WHEN <trigger>, THE <system> SHALL <response>.`
- **State-driven**: `WHILE <state>, THE <system> SHALL <response>.`
- **Unwanted behavior**: `IF <fault/condition>, THEN THE <system> SHALL <response>.`
- **Optional feature**: `WHERE <feature/flag is enabled>, THE <system> SHALL <response>.`

Focus on observable contracts and public interfaces. Avoid prescribing private helper signatures unless they are deliberate architectural seams.

### Capability 1 — <capability name>

- **R-1.1**: WHEN `<event>`, THE `<component>` SHALL `<observable behavior>`.
- **R-1.2**: IF `<invalid input or failure condition>`, THEN THE `<component>` SHALL `<fail-closed/fallback behavior>`.

### Capability 2 — <capability name>

- **R-2.1**: WHERE `<flag or optional extra is active>`, THE `<component>` SHALL `<observable behavior>`.
- **R-2.2**: WHILE `<system state>`, THE `<component>` SHALL `<invariant behavior>`.

## Interface and error contract

Map public CLI flags, MCP parameters, configuration keys, and fault modes to the exit code policy in [dispatcher.md](../.brain-79/architecture/dispatcher.md) (`0` success, `1` validation/operational failure, `2` invalid argument or `FileNotFoundError`, `3` `PermissionError`/`TimeoutError`/`OSError`, `130` interrupt).

| Interface / input | Failure or edge condition | Expected behavior (`fail-closed` / fallback) | Exit code / exception |
|---|---|---|---|
| `brain79 <cmd> --flag` | Invalid flag value or missing input file (`FileNotFoundError`) | Emit actionable error to stderr; make zero disk mutations | Exit `2` |
| `<core API or I/O path>` | Permission error, lock timeout, or corrupt I/O (`PermissionError`/`TimeoutError`/`OSError`) | Preserve existing state atomically; surface structured error | `<ExceptionType>` / Exit `3` |

## Migration and rollout

Define backward-compatibility behavior for existing repositories:

- **Default behavior**: unchanged when new flags or schema keys are omitted.
- **Upgrade path**: specify whether `brain79 update-project`, `brain79 migrate`, or `brain79 doctor --fix` is required.
- **Rollback safety**: confirm whether reverting to the prior minor release leaves `.brain-79/` readable.

## Acceptance criteria (Given / When / Then)

Every requirement (`R-X.Y`) MUST be covered by at least one acceptance criterion. Declare `Method` (`test | inspection | demo | ci`) and populate `Test ref` before transitioning to `implemented` (required non-`TBD`, with an existing test file when `Method` is `test`).

### AC-1 — <short scenario name>
- **Verifies**: `R-1.1`
- **Method**: `test`  # test | inspection | demo | ci
- **Test ref**: `TBD`  # e.g., tests/test_example.py::test_scenario
- **Given**: initial repository, wiki, or runtime state.
- **When**: specific CLI command, MCP tool call, or API invocation.
- **Then**: exact observable outputs, side effects, return values, and exit codes.

### AC-2 — <short failure or edge scenario name>
- **Verifies**: `R-1.2`
- **Method**: `test`
- **Test ref**: `TBD`
- **Given**: fault condition or invalid input state.
- **When**: specific invocation.
- **Then**: expected error handling, zero state corruption, and exact exit code or exception.

## Wiki impact map

Plan all living manuals affected by new or modified files (newly created source files are not caught by the ripple gate until mapped in `applies_to`; every target path listed here MUST exist in `.brain-79/` when status is `implemented`):

| New or modified code paths | Target `.brain-79/` article | Action (`create` / `update` / `verify`) |
|---|---|---|
| `src/brain79/core/<new_module>.py` | `features/<living-manual>.md` | `create` |
| `src/brain79/cli/dispatch.py` | `architecture/dispatcher.md` | `update` |

## Verification gate

All commands must pass with exit code `0` before transitioning status to `implemented`:

```bash
uv run pytest
uv run mypy src tests
uv run brain79 lint --strict
uv run brain79 doctor  # Note: fresh CI checkouts may allowlist local-only git_merge_driver warnings (see tests/test_ci_workflow.py)
```

Note: `uv run pytest` includes `tests/test_specs_governance.py`, which mechanically verifies spec frontmatter, naming, `R-X.Y` ↔ `AC` traceability, `related_wiki`/`target_wiki`, and `implemented` closure criteria.

## Amendments

Append-only log of mid-implementation scope or contract changes recorded while status is `in_progress`:

| Date | Author | Change summary | Impacted IDs |
|---|---|---|---|
| — | — | No amendments recorded yet. | — |

## Wiki distillation checklist (post-implementation)

Every item MUST be checked (`[x]`) before setting `status: implemented` and moving this file to `specs/archive/`:

- [ ] Execute every row in `## Wiki impact map` (ADR-018 compliant, `<= 20 KB`, non-overlapping `applies_to`).
- [ ] Populate `Test ref` on every `AC-*` entry and ensure all amendments are recorded in `## Amendments`.
- [ ] Record any new architectural decision in `.brain-79/decisions/adr-XXX.md`.
- [ ] Add release notes in `CHANGELOG.md` and `.brain-79/changelog/v0-X-0.md`.
- [ ] Update `.brain-79/architecture/roadmap-industrial-scale.md` status and archive link.
- [ ] Set frontmatter `status: implemented` and move this file to `specs/archive/`.
