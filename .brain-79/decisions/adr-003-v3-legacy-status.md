---
type: decision
status: accepted
date: 2026-08-11
deciders: [xilax]
last_updated: 2026-08-11
---

# ADR-003 — Migration — Progressive V3 Migration with Legacy Status Default

## Status

Accepted

## Context

When migrating existing repositories or legacy wikis that lack frontmatter metadata, blindly assigning active statuses (e.g. `status: shipped` or `stability: stable`) creates false confidence in unverified documentation.

Conversely, failing to add frontmatter prevents automated linters from enforcing schema consistency.

## Decision

We chose to implement a progressive migration mechanism (`brain79 migrate`) that automatically injects baseline frontmatter with `status: legacy` or `stability: legacy`:
- `status: legacy` or `stability: legacy` satisfies frontmatter presence checks while signaling human review requirement.
- The linter flags these articles with severity `info` under `legacy_needs_review`.
- Human developers or agents can review and promote articles to `shipped`, `accepted`, or `stable` over time.

## Consequences

- **Positive**: Safe, non-destructive bulk onboarding of legacy wikis.
- **Positive**: Clear visibility into unreviewed legacy documentation via `brain79 lint`.
- **Negative**: Requires manual or agent follow-up to review and promote legacy statuses.

## Alternatives Considered

- **Strict failure on un-frontmattered legacy files**: Rejected because it blocks adoption on existing projects with large wikis.
- **Auto-promoting to `status: shipped`**: Rejected because unverified documentation would bypass human review.
