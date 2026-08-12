---
type: product
last_updated: 2026-08-11
---

# Brain-79 — Product Vision

## Problem

LLMs maintain wikis that degrade organically:
- They prefer writing to `INDEX.md` (visible) instead of creating articles in subfolders (correct).
- They inline decisions and technical debt instead of structuring them in dedicated folders.
- They lose history and context between development sessions.
- Manual documentation validation is tedious, error-prone, and inconsistent.

## Solution

`brain-79` is an **AI memory protocol** that enforces mechanical organization:

1. **Cold start**: The agent reads `INDEX.md` at session start to orient itself.
2. **Write-time validation**: Mechanical write operations validate frontmatter and file location.
3. **Pre-commit hook**: Bypass via direct editing is mechanically blocked before commit.
4. **Handoffs**: Continuity between sessions without losing operational context.
5. **Organizational enforcement**: A linter that detects 9 types of knowledge degradation.

## Target Users

- Development projects where an AI agent works in recurring sessions.
- Knowledge wikis with `INDEX.md` that grows uncontrollably or without structure.
- Teams that require mechanical and deterministic validation of project documentation.
