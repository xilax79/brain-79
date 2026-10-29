---
type: decision
summary: Synchronous write-time schema validation with multi-error reporting and deterministic field auto-fill
status: accepted
date: 2026-08-11
deciders: [xilax]
last_updated: 2026-10-29
---

# ADR-004 — Curation — Synchronous Write-Time Frontmatter and Location Validation

## Status

Accepted (Amended on 2026-10-29 for deterministic auto-fill)

## Context

Allowing invalid or mislocated wiki articles to be written to disk defers error detection to post-commit or CI stages. By that point, agents have already finished their turn, resulting in broken documentation landing in git history.

However, strict manual requirement of deterministic fields (`type` derived from directory, `last_updated` timestamp, and `date` for decisions/changelogs) caused high agent retry overhead (48% failure rate on initial writes).

## Decision

We chose to enforce synchronous, write-time validation in `brain79_write` / `brain79 write`:
- Every write operation parses frontmatter and validates schema constraints before modifying the target file.
- **Deterministic Auto-Fill (2026-10-29 Amendment)**:
  - If `type` is missing in a subfolder article, it is automatically inferred from `LOCATION_TO_TYPE`.
  - `last_updated` is automatically normalized to today's UTC ISO date if omitted.
  - `date` is defaulted to today's UTC ISO date for `decision` and `changelog` types if omitted.
  - Commonly hallucinated frontmatter keys (`title`, `tags`, `created`) are stripped during write normalization so files stay clean without triggering hard validation aborts.
- Semantic fields that require human/agent intent (`status`, `stability`, `version`, `deciders`) continue to be strictly required and validated against enums.
- Multi-error validation: When validation fails, all schema violations are reported at once alongside a ready-to-paste frontmatter snippet template for the target type.
- An explicit bypass flag (`--force-validation-skip` or `force_validation_skip=True`) is provided for edge cases, which injects `force_validation_skipped: true` metadata visible in `brain79 lint`.

## Consequences

- **Positive**: Prevents malformed or misplaced articles from ever hitting disk.
- **Positive**: Eliminates multi-turn retry chains by auto-inferring deterministic fields and reporting all semantic errors at once.
- **Positive**: Immediate feedback loop to agents during writing steps with copy-paste templates.
- **Neutral**: The server injects or normalizes frontmatter during writes.

## Alternatives Considered

- **Asynchronous linter checks only**: Rejected because malformed files accumulated in the repository prior to linting.
- **Require LLM to guess all fields**: Rejected due to high token cost and multi-turn retry chains.

---

[← Volver al Índice](../INDEX.md)
