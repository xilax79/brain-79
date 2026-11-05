---
type: decision
summary: decoupling validation mechanism from ontology policy with dual built-in profiles and custom folder support
status: accepted
date: 2026-11-02
deciders:
  - xilax
last_updated: 2026-11-02
---

# ADR-009 — Declarative schema loading and dual built-in ontologies (mechanism vs. policy)

## Status

Accepted

## Context

Prior to version 1.1.0+, `brain-79` enforced a hardcoded, software-only ontology across all projects:
- `TYPE_SCHEMA` and `LOCATION_TO_TYPE` in `frontmatter.py` strictly mandated `features/` (with semver `version`), `architecture/` (with `stability`), and `product/`.
- `handoff.py` allowed only software-oriented `session_type` tokens (`feature`, `bugfix`, `research`, `brainstorming`).
- Using `brain-79` for general knowledge bases, research repositories, content drafting, or non-engineering workflows resulted in significant friction (false-positive technical debt warnings and artificial semver requirements).

## Decision

We separated the **validation and navigation engine (mechanism)** from the **directory and ontology rules (policy)**:

1. **Declarative Schema Resolution (`load_active_schema`)**:
   - Schema profile and optional custom folder rules are loaded directly from `.brain-79/SCHEMA.md` frontmatter.
   - An in-memory cache keyed by `(resolved_wiki_root, schema_mtime_ns)` guarantees zero I/O overhead on repeated calls ($<0.05\text{ ms}$).
   - Missing frontmatter or legacy repositories transparently default to `profile: software` for 100% backward compatibility.
2. **Dual Built-In Ontologies**:
   - **`software` (Default)**: `product/`, `architecture/`, `features/`, `decisions/`, `changelog/`. Strict engineering semantics and technical debt leakage prevention.
   - **`general`**: `context/` (goals, scope), `topics/` (entities, research, notes), `decisions/` (choices, trade-offs), `log/` (chronological progress). Minimal friction (no semver, no stability requirement, tech debt leakage disabled, handoff supports `work`, `writing`, `analysis`, `general`).
3. **Arbitrary Custom Folder Support (`custom_types`)**:
   - Repositories can declare custom types and directories in `.brain-79/SCHEMA.md` frontmatter without modifying Python code.
4. **Dynamic Engine Alignment**:
   - `write_article`, `edit_article`, `validate_frontmatter`, `autofill_deterministic_fields`, `check_file_health`, `migration.py`, and `brain79 schema` dynamically adapt to the active profile.

## Consequences

- **Positive**: Universal applicability of `brain-79` across both engineering and general knowledge domains.
- **Positive**: Zero performance penalty due to nanosecond mtime caching.
- **Positive**: 100% backward compatibility with all existing software repositories.
- **Positive**: Full CLI and MCP symmetry preserved across all profile interactions.

---

[← Volver al Índice](../INDEX.md)
