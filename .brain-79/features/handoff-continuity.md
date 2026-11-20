---
type: feature
summary: tactical session transitions, freshness evaluation, authority decay, anti-hallucination work tracking, and operational purge
status: shipped
version: 0.8.0
last_updated: 2026-11-12
applies_to:
  - src/brain79/core/handoff.py
  - src/brain79/core/handoff_freshness.py
related:
  - decisions/adr-002-immutable-handoffs.md
  - decisions/adr-016-handoff-freshness-and-authority-decay.md
applies_to_digest: "sha256:792ee8d260df7270"
applies_to_count: 2
---

# Feature — Short-term handoff continuity, freshness, and lifecycle operations

## Overview

The Short-Term Handoff feature provides tactical transition management between AI development sessions. Unlike long-term wiki knowledge stored in dedicated subfolders (`architecture/`, `features/`, `decisions/`, `topics/`), handoffs are immutable, timestamped state snapshots stored in `.brain-79/handoffs/handoff-%Y-%m-%d-%H%M%S-%f.md`.

They track completed tasks, pending work items, boot instructions, and knowledge pending promotion to the long-term wiki, while enforcing cryptographic provenance, authority decay, and operational lifecycle control.

## Tools and commands

| Interface | Method | Description |
|---|---|---|
| CLI | `brain79 handoff-write --session-type <type> ...` | Write structured session handoff |
| CLI | `brain79 handoff-read [ref]` | Resolve and display handoff by ref ("latest", stem, or timestamp) |
| CLI | `brain79 handoff-purge [--apply]` | Purge short-term handoffs with dry-run default guard |
| MCP | `brain79_handoff_write(...)` | Write structured session handoff |
| MCP | `brain79_handoff_read(ref)` | Resolve and display handoff |
| MCP | `brain79_handoff_purge(apply)` | Purge short-term handoffs with dry-run default guard |

## Invariants and guardrails

1. **Session type strictness**: `session_type` must be one of the 11 whitelisted values: `{"feature", "bugfix", "refactor", "doc", "research", "brainstorming", "architecture", "chore", "release", "audit", "maintenance"}`.
2. **Anti-hallucination guard**: If `pending_work` is empty, `boot_instruction` must explicitly state that no pending tasks remain or indicate consultative closure.
3. **Research guard**: Pure research or brainstorming sessions (`session_type="research"` or `"brainstorming"`) require persisting findings to the wiki via `brain79_session_commit()` or providing an explicit justification.
4. **Lineage reference and cryptographic provenance**: Handoffs record `previous_handoff_ref`, `git_head`, `git_branch`, and `wiki_digest`.
5. **Freshness and authority decay (ADR-016)**: Handoff authority is perishable. When code, git HEAD, or wiki state changes after the handoff was written, `brain79_orient` tags the handoff with `[Status: STALE - DRIFT DETECTED]` or `[Status: ANOTHER BRANCH]`, treating pending instructions as historical advisory rather than commanding truth.
6. **Operational purge (`handoff-purge`)**: allows developers and agents to clean up accumulated tactical handoffs at milestone boundaries. Defaults to safe dry-run preview (`--apply` required to mutate disk).

## Usage examples

```bash
# Write handoff at end of session
brain79 handoff-write \
  --session-type feature \
  --previous-ref latest \
  --summary-file summary.txt \
  --boot-instruction-file boot.txt

# Read latest handoff at start of session
brain79 handoff-read latest

# Preview purge of old handoffs
brain79 handoff-purge

# Apply purge
brain79 handoff-purge --apply
```

## Known edge cases

- Handoffs are strictly immutable on disk; updating tactical state requires writing a new handoff or purging the collection via `brain79 handoff-purge`.
- Under the on-demand handoff policy, handoffs are only written when explicitly requested by the user or upon terminating autonomous sub-agent processes.

---

[← Volver al Índice](../INDEX.md)
