---
type: decision
summary: enforce sentence case first across all documentation, headings, lists, and wiki generation
status: accepted
deciders: Team
date: 2026-11-05
last_updated: 2026-11-05
---

# ADR-015: Sentence case first policy for documentation and wiki generation

## Status

Accepted

## Context

Technical documentation and generated wiki articles frequently suffered from artificial Title Case capitalization (e.g. "How It Works In Practice", "Centralized Lock Directory Isolation", capitalizing after colons). This practice:
1. Adds visual noise and corporate marketing fluff to technical writing.
2. Contradicts modern engineering documentation standards (Google Developer Documentation Style Guide, Microsoft Writing Style Guide, Apple Style Guide), which mandate sentence-style capitalization.
3. Is grammatically incorrect in Spanish (where capitalizing every word in a title is an anglicism error).

## Decision

Adopt a strict **Sentence case first** policy across the entire project, its internal wiki, and all generated templates:
1. **Headings and titles (H1, H2, H3):** capitalize only the initial letter. The rest must be lowercase.
2. **Proper nouns and acronyms:** the only exceptions to lowercase are genuine proper nouns (e.g. Python, Linux, macOS, Docker, Stripe, FastMCP) and acronyms (e.g. ADR, MCP, API, CI, JSON, POSIX, LF, CRLF, TF-IDF).
3. **Punctuation and colons:** text following a colon (`:`) begins with a lowercase letter unless it is a proper noun or acronym (e.g. `- feature: description`, never `- feature: Description`).
4. **Lists and table headers:** use sentence case. Title Case is rejected across all documentation artifacts.

## Consequences

- Documentation is clean, calm, professional, and accessible (CEFR B2 level).
- AI agent prose aligns with Google and Microsoft engineering standards rather than LLM marketing bias.
- Visual clutter from excessive capital letters is eliminated across the repository.

---

[← Volver al Índice](../INDEX.md)
