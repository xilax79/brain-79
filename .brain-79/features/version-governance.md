---
type: feature
summary: single-source semantic versioning via Hatchling, MCP handshake version reporting, and automated changelog/badge parity checks
status: shipped
version: 0.16.0
applies_to:
  - src/brain79/__init__.py
  - pyproject.toml
  - src/brain79/core/update.py
related:
  - architecture/roadmap-industrial-scale.md
  - decisions/adr-013-versioning-and-release-governance.md
  - decisions/adr-017-semantic-version-calibration-for-pre-ga-maturation.md
last_updated: 2026-11-24
applies_to_digest: "sha256:565ae38a2f12fc7e"
applies_to_count: 3
---

# Feature — Versioning and release governance

## Overview

The Versioning and Release Governance system enforces mechanical release parity and single-source versioning for `brain-79`. It eliminates manual version duplication across configuration files, exposes accurate version metadata over MCP and CLI, and enforces release invariants under SemVer 2.0.0 §4 and ADR-017.

## Architecture and runtime invariants

### 1. Single source of truth (Hatchling dynamic version)
- **Canonical source**: `src/brain79/__init__.py` defines `__version__ = "<semver>"` (e.g. `"0.8.1"`), serving as the sole package authority.
- **Build configuration (`pyproject.toml`)**: uses Hatchling dynamic metadata resolution:
  ```toml
  [project]
  name = "brain79"
  dynamic = ["version"]

  [tool.hatch.version]
  path = "src/brain79/__init__.py"
  ```

### 2. Uniform CLI and FastMCP exposure
- **CLI (`src/brain79/__main__.py`)**: `brain79 -v` and `brain79 --version` read `brain79.__version__`.
- **FastMCP (`src/brain79/server.py`)**: instantiates `FastMCP("brain79", version=__version__)` to expose the package version during JSON-RPC `initialize` handshake.

### 3. Pre-GA semantic versioning policy (SemVer 2.0.0 §4 & ADR-017)
- **`MAJOR` (`0.y.z`)**: denotes pre-GA development prior to public distribution and GA.
- **`MINOR` (`0.Y.0`)**: architectural milestones, protocol paradigm shifts, or new subsystems (e.g. Phase 6.7 Merkle drift engine and ripple gates at `0.8.0`, Phase 7 project doctor at `0.9.0`).
- **`PATCH` (`0.y.Z`)**: backwards-compatible bug fixes and internal performance enhancements.

### 4. Mechanical release parity invariants (`tests/test_version_governance.py`)
Every test run verifies:
1. **Valid SemVer**: `brain79.__version__` matches `^\d+\.\d+\.\d+$`.
2. **Hatchling configuration**: `pyproject.toml` declares `dynamic = ["version"]` and points `[tool.hatch.version]` to `src/brain79/__init__.py`.
3. **README badge parity**: `README.md` contains the version badge matching `version-{__version__}-blue.svg`.
4. **Changelog entry parity**: at least one release note in `.brain-79/changelog/*.md` and a section in root `CHANGELOG.md` matches `__version__`.
5. **No phantom version skew**: no active documentation or feature article declares a version exceeding active `__version__`.
6. **CLI & MCP parity**: `brain79 --version` and the FastMCP server instance report the exact package version.

---

[← Back to Index](../INDEX.md)
