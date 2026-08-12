---
type: feature
status: shipped
version: 1.0.0
last_updated: 2026-08-11
---

# Feature — Short-Term Handoff Continuity

## Overview

The Short-Term Handoff feature provides tactical transition management between AI development sessions. Unlike long-term wiki knowledge stored in subfolders, handoffs are immutable, timestamped state snapshots stored in `.brain-79/handoffs/handoff-%Y-%m-%d-%H%M%S-%f.md`.

They track completed tasks, pending work items, boot instructions, and knowledge pending promotion to the long-term wiki.

## Tools & Commands

| Interface | Method | Description |
|---|---|---|
| CLI | `brain79 handoff-write --session-type <type> ...` | Write structured session handoff |
| CLI | `brain79 handoff-read [ref]` | Resolve and display handoff by ref ("latest", stem, or timestamp) |
| MCP | `brain79_handoff_write(...)` | Write structured session handoff |
| MCP | `brain79_handoff_read(ref)` | Resolve and display handoff |

## Invariants & Guardrails

1. **Session Type Strictness**: `session_type` must be one of `{"feature", "bugfix", "research", "brainstorming"}`.
2. **Anti-Hallucination Guard**: If `pending_work` is empty, `boot_instruction` must explicitly state that no pending tasks remain.
3. **Lineage Reference**: `previous_handoff_ref` verifies existence of the preceding handoff.
4. **Promotion Warning**: If `knowledge_pending_promotion` is non-empty, `brain79_handoff_read` injects a dynamic warning instructing the incoming agent to promote learnings to the wiki using `brain79_ingest`.

## Usage Examples

```bash
# Write handoff at end of session
brain79 handoff-write \
  --session-type feature \
  --previous-ref latest \
  --summary-file summary.txt \
  --boot-instruction-file boot.txt

# Read latest handoff at start of session
brain79 handoff-read latest
```

## Known Edge Cases

- Handoffs are strictly immutable. Updating state requires writing a new handoff that references the previous one.
- To wipe handoffs operational cleanup (e.g. end of sprint), use `brain79 handoff-purge`.
