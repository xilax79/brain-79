---
type: decision
summary: Standardize explicit frontmatter summary field and footer backlink navigation convention
status: accepted
date: 2026-10-29
deciders:
  - xilax
last_updated: 2026-10-29
---

# ADR-007 — Navigation — Explicit Frontmatter Summary and Article Backlinks

## Status

Accepted

## Context

Previously, `INDEX.md` Quick navigation summaries relied on an unconstrained heuristic in `extract_title_and_summary`: scanning lines after `# Title` and taking the first line of non-heading text. When articles began with section headings such as `## Problem` followed by a colon-terminated sentence (e.g. `LLMs maintain wikis that degrade organically:`), the extractor captured incomplete fragments, misrepresenting the document's purpose.

Additionally, navigating between wiki articles and the central index when inspecting markdown files in code editors (such as VS Code), local viewers (such as Obsidian), or GitHub required manual folder traversal, making contextual navigation cumbersome.

## Decision

1. **Explicit Frontmatter Summary (`summary:`)**:
   - Add `summary` as an officially recognized optional field across all frontmatter schemas in `TYPE_SCHEMA`.
   - Update `extract_title_and_summary` to prioritize reading `summary` from frontmatter in $O(1)$ time, guaranteeing accurate representation in `INDEX.md`.
2. **Hardened Fallback Heuristics**:
   - When frontmatter `summary` is omitted, the body scanner halts before subheadings (`## `, `### `), ignores bullet points (`- `, `* `, `1. `), code fences, and strips trailing colons (`:`) to avoid dangling phrases.
3. **Standardized Article Backlinks**:
   - Establish the convention that all articles residing in subdirectories (`architecture/`, `features/`, `decisions/`, `product/`, `changelog/`) end with a navigation link back to the central index:
     ```markdown
     ---

     [← Volver al Índice](../INDEX.md)
     ```

## Consequences

- **Positive**: `INDEX.md` Quick navigation accurately reflects author intent with zero heuristic ambiguity.
- **Positive**: Faster navigation indexing since frontmatter dictionary lookup is instantaneous.
- **Positive**: Seamless 1-click navigation back to `INDEX.md` when browsing articles in VS Code preview, Obsidian, and GitHub.
- **Positive**: Bidirectional link density increases graph connectivity, reducing risk of orphan nodes.

---

[← Volver al Índice](../INDEX.md)
