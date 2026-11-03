---
type: decision
summary: Single-source semantic versioning via Hatchling, FastMCP version handshake exposure, and automated release parity testing
status: accepted
date: 2026-11-03
deciders:
  - xilax
applies_to:
  - src/brain79/__init__.py
  - src/brain79/server.py
  - pyproject.toml
  - README.md
  - tests/test_version_governance.py
related:
  - architecture/roadmap-industrial-scale.md
  - features/version-governance.md
last_updated: 2026-11-03
---

# ADR-013 — Architecture — Single-Source Semantic Versioning and Mechanical Release Governance

## Status

Accepted

## Context

Prior to Phase 5 of the Industrial-Scale Roadmap, `brain-79` suffered from manual version triplication and release drift:
1. **Manual Version Drift:** Version strings were manually duplicated across `src/brain79/__init__.py`, `pyproject.toml`, and `README.md` badges. Bumping versions required manual edits across disparate files, risking accidental divergence.
2. **Missing MCP Server Handshake Metadata:** The FastMCP server instance in `src/brain79/server.py` did not pass `version=__version__`, causing the FastMCP framework to default to reporting its internal library version during JSON-RPC `initialize` handshakes rather than the `brain79` package version.
3. **Absence of Release Invariant Tests:** There were no mechanical tests enforcing that the active version followed Semantic Versioning, that changelog entries existed for the active version, or that README documentation matched reality.
4. **Major Version Paradigm Shift:** Phases 0 through 4 introduced foundational architectural shifts (Two-Call Session Protocol, multi-ontology declarative schemas, 3-signal context ranking, structural skeletons, and drift detection), creating breaking protocol improvements that warranted bumping the package version from `1.1.0` to `2.0.0`.

## Decision

We implemented **Phase 5: Single-Source Semantic Versioning and Mechanical Release Governance**:

1. **Single Source of Truth via Hatchling Dynamic Versioning:**
   - `src/brain79/__init__.py` is declared the canonical single source of truth (`__version__ = "2.0.0"`).
   - In `pyproject.toml`, the static `version = "..."` field is removed, replaced with:
     ```toml
     [project]
     dynamic = ["version"]

     [tool.hatch.version]
     path = "src/brain79/__init__.py"
     ```
   - Hatchling dynamically extracts the version at build/install time without duplicating strings.

2. **FastMCP Server Version Exposure:**
   - In `src/brain79/server.py`, `__version__` is imported from `brain79` and passed explicitly to `FastMCP("brain79", version=__version__, ...)`.
   - MCP client harnesses (Cursor, Claude Desktop, Pi) receive accurate package version metadata in the JSON-RPC `initialize` handshake response.

3. **Semantic Versioning Policy (`MAJOR.MINOR.PATCH`):**
   - **`MAJOR` (`X.0.0`)**: Paradigm shifts in the session protocol, breaking schema changes, or CLI/MCP tool restructuring.
   - **`MINOR` (`x.Y.0`)**: New CLI subcommands or MCP tools preserving 1:1 symmetry, new optional schema fields, or non-breaking linter rules.
   - **`PATCH` (`x.y.Z`)**: Bug fixes, performance optimizations, or documentation/help string updates.

4. **Automated Mechanical Release Parity Tests (`tests/test_version_governance.py`):**
   - Enforces strict SemVer syntax (`^\d+\.\d+\.\d+$`).
   - Verifies `pyproject.toml` dynamic versioning configuration and absence of static version fields.
   - Verifies FastMCP `server.mcp.version == __version__`.
   - Verifies `README.md` version badge parity.
   - Verifies `.brain-79/changelog/` contains an entry with matching `version: <__version__>`.
   - Verifies CLI `-v` and `--version` output matches `brain79 <__version__>`.

## Consequences

- **Positive**: Eliminates version triplication and human error during release packaging.
- **Positive**: Guarantees MCP clients receive accurate server version telemetry.
- **Positive**: Automated test suite acts as an unbreakable release gate preventing desynchronized documentation or missing changelogs.
- **Positive**: 100% test coverage and static typing compliance maintained.

---

[← Volver al Índice](../INDEX.md)
