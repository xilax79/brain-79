---
type: decision
summary: adopt opt-in native lifecycle hooks backed by a read-only CLI CI gate and composite GitHub Action with dual-tier enforcement
status: accepted
date: 2026-11-24
deciders:
  - xilax
related:
  - decisions/adr-012-structural-quality-and-drift-detection.md
  - decisions/adr-014-centralized-locks-and-cross-platform-io.md
  - decisions/adr-020-focused-mcp-surface-and-cli-superset.md
last_updated: 2026-11-24
---

# ADR-021 — Passive lifecycle hooks and CI PR gate

## Status

Accepted (2026-11-24).

## Context

Prior to `v0.15.0`, `brain-79` relied on voluntary agent compliance with instruction files (`AGENTS.md`, `CLAUDE.md`) to invoke `brain79_orient` at session start and `brain79_session_commit` before session exit. Local `.git/hooks/pre-commit` hooks could be bypassed with `--no-verify` or skipped when third-party hook managers were installed, and human reviewers on GitHub Pull Requests had no automated summary of drifted governing articles or relevant ADRs in a PR diff.

## Decision

1. **Native CLI lifecycle hook engine (`brain79 ci-check --lifecycle-hook`)**: lifecycle hooks for Claude Code (`claude`), Antigravity (`agy`), and Cursor (`cursor`) invoke `brain79 ci-check --lifecycle-hook <session-start|stop> --client <client>` directly instead of generating `.sh` or `.ps1` wrapper scripts, ensuring uniform cross-platform execution.
2. **Fail-open and loop-immunity invariants**: `--lifecycle-hook` always exits `0`, caps `stdin` at `1 MB`, emits ASCII-safe JSON (`ensure_ascii=True`), respects `.git` walk boundaries, and fails open to `{}` on missing `.brain-79/`, malformed JSON, or active continuation/abort guards (`continuationActive`, `stop_hook_active`, `loop_count >= 1`, `terminationReason != "NO_TOOL_CALL"`, `status != "completed"`).
3. **Opt-in lifecycle hook installation**: `ClaudeHooksAdapter` (`.claude/settings.json`), `AntigravityHooksAdapter` (`.agents/plugins/brain79/hooks.json`), and `CursorHooksAdapter` (`.cursor/hooks.json`) are opt-in via `--install-lifecycle-hooks` or `--harnesses hooks` so default `brain79 init` remains non-intrusive.
4. **Dual-tier decoupled default in CI (`brain79 ci-check`)**: `.brain-79/SCHEMA.md` retains `enforcement: strict` as the global schema default, while `brain79 ci-check` defaults to `--enforcement strict` independently (configurable via `--enforcement <strict|balanced|advisory|schema>`), allowing teams to use `balanced` locally while enforcing `strict` on Pull Requests.
5. **Zero new Python network dependencies**: `brain79 ci-check` remains strictly offline and read-only on `.brain-79/`; GitHub PR commenting is handled in the composite `action.yml` via `gh api`.

## Consequences

- **Positive**: eliminates voluntary-compliance blind spots for supporting hosts, surfaces PR diff governance impact and active ADRs to human reviewers, and preserves zero-dependency core packaging.
- **Negative**: teams using shallow GitHub Actions checkouts (`fetch-depth: 1`) without fetching the base branch degrade PR diff impact to `shallow_fallback` while still validating full wiki drift and lint.

---

[← Back to Index](../INDEX.md)
