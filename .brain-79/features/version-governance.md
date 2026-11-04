---
type: feature
summary: Single-source semantic versioning via Hatchling, MCP handshake version reporting, and automated changelog/badge parity checks
status: shipped
version: 2.0.0
applies_to:
  - src/brain79/__init__.py
  - src/brain79/server.py
  - pyproject.toml
  - README.md
related:
  - architecture/roadmap-industrial-scale.md
  - decisions/adr-013-versioning-and-release-governance.md
last_updated: 2026-11-04
---

# Feature — Versioning & Release Governance (Phase 5 Specification)

## Overview

This specification defines the mechanical versioning and release governance system for `brain-79` (Phase 5 of the Industrial-Scale Roadmap). It eliminates manual version duplication across configuration files, exposes accurate version metadata over MCP and CLI, transitions the project to `2.0.0`, and enforces release parity through automated test invariants.

---

## Problem Statement

1. **Manual Version Triplication:** Version strings are currently hardcoded separately in `src/brain79/__init__.py`, `pyproject.toml`, and `README.md` badges, creating drift risk during releases.
2. **Missing MCP Server Version:** `FastMCP("brain79")` in `src/brain79/server.py` does not pass `version=__version__`, omitting the package version during the JSON-RPC `initialize` handshake.
3. **Unenforced Changelog Parity:** No automated check verifies that the active `__version__` has a corresponding release entry in `.brain-79/changelog/`.
4. **Version Lag (`1.1.0` vs `2.0.0`):** Phases 0 through 4 introduced the Two-Call Session Protocol (`orient` + `session-commit`), declarative multi-ontology schemas (`software` + `general`), 3-signal context ranking (`applies_to` + 1-hop ADR expansion), and structural section validation, warranting a major release bump to `2.0.0`.

---

## Architecture & Design (4 Pillars)

### 1. Single Source of Truth (Hatchling Dynamic Version)
- **Canonical Source:** `src/brain79/__init__.py` (`__version__ = "2.0.0"`).
- **Build Configuration (`pyproject.toml`):**
  Replace the static `version = "1.1.0"` entry with dynamic resolution:
  ```toml
  [project]
  name = "brain79"
  dynamic = ["version"]

  [tool.hatch.version]
  path = "src/brain79/__init__.py"
  ```

### 2. Uniform CLI & FastMCP Exposure
- **CLI (`src/brain79/__main__.py`):** `brain79 -v` and `brain79 --version` read `brain79.__version__`.
- **FastMCP (`src/brain79/server.py`):** Pass `version=__version__` when instantiating `FastMCP("brain79", version=__version__)`.

### 3. Semantic Versioning Policy (`MAJOR.MINOR.PATCH`)
- **`MAJOR` (`X.0.0`):** Paradigm shifts in the session protocol, mandatory schema rules requiring `brain79 migrate --apply` on existing wikis, or removal/renaming of CLI/MCP tools.
- **`MINOR` (`x.Y.0`):** New CLI subcommands / MCP tools (preserving 1:1 symmetry), new optional frontmatter fields, or non-breaking linter warnings.
- **`PATCH` (`x.y.Z`):** Bug fixes, `--help` copy improvements, internal performance optimizations, or template refinements that do not alter validation contracts.

### 4. Mechanical Release Parity Invariants (`tests/test_version_governance.py`)
Every `pytest` run must mechanically verify:
1. **Valid SemVer:** `brain79.__version__` matches `^\d+\.\d+\.\d+$`.
2. **Hatchling Dynamic Configuration:** `pyproject.toml` declares `dynamic = ["version"]` and points `[tool.hatch.version]` to `src/brain79/__init__.py`.
3. **README Badge Parity:** `README.md` contains the version badge matching `version-{__version__}-blue.svg`.
4. **Changelog Entry Parity:** At least one article in `.brain-79/changelog/*.md` contains `version: <__version__>` in its YAML frontmatter.
5. **CLI & MCP Parity:** `brain79 --version` outputs `brain79 {__version__}`, and the FastMCP server instance exposes `__version__`.

---

## Implementation Checklist (Developer Agent)

1. **`src/brain79/__init__.py`:** Bump `__version__ = "2.0.0"`.
2. **`pyproject.toml`:** Switch to `dynamic = ["version"]` and add `[tool.hatch.version] path = "src/brain79/__init__.py"`.
3. **`src/brain79/server.py`:** Import `__version__` and pass `version=__version__` to `FastMCP`.
4. **`README.md`:** Update version badge to `2.0.0` and test count badge.
5. **Wiki & Governance Documentation:**
   - Create `.brain-79/changelog/v2-0.md` (`version: 2.0.0`) summarizing Phases 0–4 and CLI hardening.
   - Create `.brain-79/decisions/adr-013-versioning-and-release-governance.md` (`status: accepted`).
   - Update `.brain-79/features/version-governance.md` from `status: planned` to `status: shipped`.
   - Mark `Phase 5` as `[x] Completed` in `.brain-79/architecture/roadmap-industrial-scale.md`.
6. **Tests:** Create `tests/test_version_governance.py` and verify full test suite and `brain79 lint --strict` pass.

---

[← Volver al Índice](../INDEX.md)
