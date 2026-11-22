---
type: decision
summary: isolate repository feature specifications in specs/ outside .brain-79/ using EARS, BDD Given/When/Then, explicit non-goals, and CI governance tests
status: accepted
date: 2026-11-21
deciders:
  - xilax
related:
  - decisions/adr-009-declarative-schema-and-dual-ontologies.md
  - decisions/adr-015-sentence-case-first-policy.md
  - decisions/adr-018-living-manuals-and-temporal-decontamination.md
  - architecture/roadmap-industrial-scale.md
  - architecture/dispatcher.md
last_updated: 2026-11-21
---

# Decision — ADR-019: External feature specifications and requirements standard

## Status

Accepted. Active for all repository specifications; legacy transition completed on 2026-11-21 (see `## Transition`).

## Context

Prior to Phase 13, implementation specifications for upcoming releases were stored inside `.brain-79/architecture/` (`agy-init-and-plugin-design.md`, `zero-clone-distribution-and-visual-docs.md`, `battle-testing-and-chaos-design.md`, `core-refactoring-and-hardening-design.md`, `public-release-readiness-design.md`, and `team-collaboration-and-onboarding-design.md`). Storing transient execution plans inside the governed wiki created five concrete conflicts:

1. **Temporal decontamination (ADR-018)**: living manuals in `architecture/` and `features/` prohibit milestone markers (`Phase X`, `Sprint Y`) and shipped specification terminology (`TEMPORAL_MILESTONE_REGEX`, `SHIPPED_SPECIFICATION_REGEX`). Change specifications are inherently milestone-bound and imperative.
2. **Index line budget**: `INDEX.md` enforces `DEFAULT_INDEX_MAX_LINES = 150`. Every historical phase design doc consumes a permanent line in the routing table even after its release ships.
3. **Anti-sprawl and `orient()` budget erosion**: cross-cutting phase specs span 13–29 files, forcing `allow_overlapping_governance: true` and injecting historical task checklists into `brain79_orient()`'s 64 KB context budget alongside live documentation.
4. **Tight size headroom**: `validation.py` enforces `MAX_ARTICLE_LINES = 400` and `MAX_ARTICLE_BYTES = 20_480` (20 KB). Existing prose-compact specs already measure 11.5–17.8 KB (141–186 lines), leaving insufficient headroom for structured BDD scenarios, error tables, migration plans, and amendment logs without truncating edge cases.
5. **Ad-hoc authoring gaps**: prior specs coupled private function signatures with observable requirements, omitted explicit non-goals and open-question gates, scattered error contracts across bullets, and lacked mechanical traceability between requirements (`R-X.Y`) and acceptance criteria (`AC-*`).

## Alternatives considered

### Alternative A — Governed `specs/` folder via `SCHEMA.md` `custom_types`
`brain-79` supports custom directories via `custom_types` (ADR-009). A governed `specs/` type could theoretically be exempted from `MAX_ARTICLE_BYTES` and temporal regexes, and filtered in `orient()` to surface only `status: in_progress`.

- **Why rejected**: it couples the generic `brain-79` memory engine to a software-phase specification workflow, requires special-case exemptions across `validation.py`, `lint_organizational.py`, `navigation.py`, and `INDEX.md`'s 150-line budget, and mixes transient build plans with permanent system knowledge.

### Alternative B — Retain `architecture/*-design.md` with `stability: archived` after release
Marking completed design docs `stability: archived` and removing their `applies_to` would silence them in `orient()`.

- **Why rejected**: it still consumes `INDEX.md` lines permanently, retains imperative milestone documents inside a living-manual namespace (violating ADR-018), and keeps the 20 KB ceiling in force during authoring.

### Alternative C — External `specs/` directory with CI governance (chosen)
Isolate change specifications in `specs/` outside `.brain-79/` as a **repository-level engineering standard**, enforced mechanically by `tests/test_specs_governance.py`.

## Decision

### 1. Scope (repository process vs. product feature)
This ADR defines a **repository-level engineering convention** for developing `brain-79` itself. Per ADR-009 (*mechanism vs. policy*), `brain-79` does **not** force `specs/` or EARS syntax onto external users (many of whom use `--profile general`, Jira, Linear, or external spec tools). Promoting any part of this workflow into an optional product feature requires empirical validation across Phases 13–14 and a separate product ADR.

### 2. When a specification is required (threshold)
- **Required**: roadmap phases, public CLI/MCP/schema contract changes, new runtime dependencies or optional extras, or changes spanning 3+ core modules.
- **Not required**: isolated bugfixes, CI/test-only fixes, internal refactors with zero public contract change, or standalone documentation edits.

### 3. External directory, naming, and single archive rule
- Active specifications live in `specs/` at the repository root using deterministic, collision-resistant names:
  - Roadmap phases: `specs/phase-<NN>-<slug>.md` with `spec_id: SPEC-0<NN>` (e.g., `specs/phase-13-polyglot-and-retrieval.md` → `SPEC-013`).
  - Ad-hoc specifications: `specs/YYYY-MM-<slug>.md` with `spec_id: SPEC-YYYYMM-<slug>` (assigned when opening the draft PR).
- Allowed subdirectories under `specs/`: `specs/archive/` (closed ADR-019 specs) and `specs/archive/legacy/` (pre-ADR-019 historical design docs). Unrecognized subdirectories under `specs/` are rejected by CI.
- **Lifecycle states and single archive mechanism**:
  - Active (`specs/*.md`): `draft` → `approved` → `in_progress`.
  - Closed (`specs/archive/*.md`): `implemented` | `superseded` | `abandoned`.
  - Closed specifications MUST ALWAYS be moved to `specs/archive/` (no dual `status: archived` enum).

### 4. Standardized template (`specs/TEMPLATE.md`) and approval gate
Every new specification is authored from `specs/TEMPLATE.md` and includes:
- Frontmatter: `spec_id`, `title`, `target_version` (informational), `status`, `owner`, `last_updated`, `related_wiki` (existing `.brain-79/` context articles), and `target_wiki` (`.brain-79/` living manuals to create or update by closure).
- Sections: `Problem statement and goal`, `Non-goals (out of scope)`, `Dependencies`, `Constraints and invariants` (linking canonical ADRs rather than duplicating prose), `Open questions`, `Requirements (EARS)`, `Interface and error contract` (aligned with `architecture/dispatcher.md` exit codes), `Migration and rollout`, `Acceptance criteria (Given / When / Then)` with `Verifies: R-X.Y`, `Method: test | inspection | demo | ci`, and `Test ref`, `Wiki impact map`, `Verification gate`, `Amendments`, and `Wiki distillation checklist`.
- **Approval gate**: only the `owner` may transition a spec from `draft` to `approved`, and only after every item in `## Open questions` is resolved (`[x]`). Agents MUST NOT implement a `draft` specification.
  - *Enforcement scope note*: while `brain-79` remains a single-maintainer repository, `owner`-only approval is enforced via PR review rather than GitHub `CODEOWNERS`; if external committers are added, enforce `specs/` ownership via `.github/CODEOWNERS` and branch protection.
- **Mid-flight changes**: contract adjustments during `in_progress` MUST be appended to `## Amendments` and reflected in affected `R-X.Y` / `AC-*` entries.

### 5. One-way reference boundary and discoverability
- `.brain-79/` articles (such as `architecture/roadmap-industrial-scale.md`) may link to `specs/*.md` for traceability, but MUST NEVER list `specs/` paths (or broad globs matching `specs/`) in `applies_to` or rely on external specs to document current system behavior.
- Because `specs/` is outside `brain79_orient()`, `AGENTS.md` and `CLAUDE.md` (`## Project notes`) instruct agents to inspect `specs/` (excluding `TEMPLATE.md` and `archive/`) whenever implementing work above the specification threshold.

### 6. Mechanical enforcement (`tests/test_specs_governance.py`)
CI mechanically enforces ADR-019 via `uv run pytest`:
- Rejects any `.brain-79/` article whose `applies_to` targets `specs/` directly or via broad globs (`**/*.md`, `./specs/...`, `.brain-79/specs/...`).
- Blocks new spec-like files across `.brain-79/architecture/`, `features/`, `product/`, and `topics/` by both filename (`*-design.md`, `*-spec.md`) and content (`R-X.Y` / `## Acceptance criteria`), subject only to the temporary transition allowlist below.
- Rejects unrecognized subdirectories under `specs/` (only `specs/archive/` and `specs/archive/legacy/` are permitted).
- Validates `specs/TEMPLATE.md` sections, filename ↔ `spec_id` correspondence, global `spec_id` uniqueness, active-vs-archive status hygiene, zero open questions on `approved`/`in_progress`/`implemented`, existing `related_wiki` targets, valid `Method:` values, and complete `R-X.Y` ↔ `AC-*` bidirectional traceability.
- **Closure and distillation gate (`status: implemented`)**: requires at least one `target_wiki` entry, zero `TBD` in `Test ref`, verifies that every `Method: test` node ID points to an existing test file, requires every item in `## Wiki distillation checklist` to be checked (`[x]`), and verifies that every `target_wiki` and `## Wiki impact map` article exists under `.brain-79/`.

## Transition

Completed (2026-11-21). All six pre-ADR-019 phase design documents were audited, distilled into `.brain-79/` living manuals, and archived under `specs/archive/legacy/` per `specs/archive/2026-11-legacy-design-doc-migration.md`. `LEGACY_ARCHITECTURE_SPECS_ALLOWLIST` in `tests/test_specs_governance.py` is now empty (`frozenset()`).

## Consequences

### Positive
- Specifications have unrestricted space for edge cases, error contracts, migration paths, and BDD acceptance criteria without fighting the 20 KB / 400-line wiki ceiling.
- `INDEX.md` and `brain79_orient()` stay dedicated to evergreen living manuals and immutable ADRs.
- Mechanical CI checks enforce both authoring quality and post-implementation distillation closure, preventing unverified `implemented` archives.
- Respects ADR-009 by keeping repository process policy decoupled from `brain-79`'s generic core engine.

### Negative
- **Deliberate distillation effort**: distilling new modules and behavior into `.brain-79/` living manuals at phase close is non-trivial engineering work; newly created source files are not guarded by the Hard Session Ripple Gate until mapped via `## Wiki impact map` and verified by the `implemented` closure gate.
- **External discoverability relies on `AGENTS.md` and `CLAUDE.md`**: agents must check `specs/` explicitly because external specs are not auto-inlined by `brain79_orient()`.
- **One-time migration cost**: tracked explicitly in `specs/2026-11-legacy-design-doc-migration.md` until the six legacy docs are archived.

---

[← Back to Index](../INDEX.md)
