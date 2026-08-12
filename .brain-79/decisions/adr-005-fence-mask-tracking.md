---
type: decision
status: accepted
date: 2026-08-11
deciders: [xilax]
last_updated: 2026-08-11
---

# ADR-005 — Linter — Code Fence Masking for Decision and Debt Leakage Regex Rules

## Status

Accepted

## Context

Linter rules designed to detect decision leakage (e.g. `Decision:`, `ADR-001:`) or technical debt (e.g. `TD-1:`) in non-decision folders frequently suffered false positives when articles contained markdown code blocks or documentation examples explaining those patterns.

## Decision

We chose to implement CommonMark code-fence masking (`_mask_code_fences`) prior to executing leakage regex scans:
- `_mask_code_fences` scans the document for fenced code blocks (` ``` ` or ` ~~~ `).
- Lines inside fenced blocks are replaced with equal-length whitespace strings before pattern matching occurs.
- Line numbers and character offsets are preserved 1:1, ensuring accurate linter error position reporting.

## Consequences

- **Positive**: Eliminates false positives when documenting decision or technical debt syntax in code examples.
- **Positive**: Retains exact line numbers for true positive violations outside code blocks.
- **Negative**: Increases linter parsing work slightly by splitting and masking file lines.

## Alternatives Considered

- **Ignoring code blocks completely**: Rejected because line number alignment would be lost.
- **AST-based Markdown parsing**: Rejected to avoid external dependencies beyond basic standard library regex.
