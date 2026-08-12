---
type: decision
status: accepted
date: 2026-08-11
deciders: [xilax]
last_updated: 2026-08-11
---

# ADR-004 — Curation — Synchronous Write-Time Frontmatter and Location Validation

## Status

Accepted

## Context

Allowing invalid or mislocated wiki articles to be written to disk defers error detection to post-commit or CI stages. By that point, agents have already finished their turn, resulting in broken documentation landing in git history.

## Decision

We chose to enforce synchronous, write-time validation in `brain79_write` / `brain79 write`:
- Every write operation parses frontmatter and validates schema constraints before modifying the target file.
- If frontmatter is missing or invalid, or if the declared `type` does not match the target directory, write execution raises a `ValidationError` and rejects the write.
- An explicit bypass flag (`--force-validation-skip` or `force_validation_skip=True`) is provided for edge cases, which injects `force_validation_skipped: true` metadata visible in `brain79 lint`.

## Consequences

- **Positive**: Prevents malformed or misplaced articles from ever hitting disk.
- **Positive**: Immediate feedback loop to agents during writing steps.
- **Negative**: Requires caller to provide complete YAML frontmatter on every write attempt.

## Alternatives Considered

- **Asynchronous linter checks only**: Rejected because malformed files accumulated in the repository prior to linting.
