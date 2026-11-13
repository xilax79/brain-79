---
type: decision
summary: semantic versioning calibration to 0.7.2 for pre-GA maturation prior to public release
status: accepted
date: 2026-11-05
deciders: Team
last_updated: 2026-11-05
---

# ADR-017: Semantic versioning calibration for pre-GA maturation

## Status

Accepted

## Context

During initial private development, major version bumps were used internally to signal architectural protocol breaks (e.g. transitioning from the iterative multi-call v1 to the Two-Call session protocol v2). However, Brain-79 remains a private, unpublished repository that has not yet completed its distribution packaging (Phase 8: zero-clone `uvx brain79` distribution) or in-place project protocol upgrades (Phase 7: `brain79 update-project` / `doctor`).

Presenting a `2.0.x` tag upon first public release misrepresents the product's enterprise maturity level. Under Semantic Versioning 2.0.0 §4, `0.y.z` denotes initial pre-release development before official GA stability guarantees.

## Decision

We recalibrate the active package version from `2.0.2` to `0.7.2`:
- Current state (Phases 0 through 6.6 fully delivered): `0.7.2`.
- Phase 7 delivery (Project upgrader & doctor): `0.8.0`.
- Phase 8 delivery (Zero-clone distribution & context budget guardrails): `0.9.0`.
- Public General Availability (GA): `1.0.0`.

## Consequences

- Accurately aligns user expectations regarding maturity and adoption lifecycle.
- Preserves all historical commits without destructive Git rewrites.
- Establishes a disciplined, predictable milestone progression to `1.0.0` GA.

---

[← Volver al Índice](../INDEX.md)
