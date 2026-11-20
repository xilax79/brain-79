"""Declarative harness adapter registry (Phase 10 Stage 4: R-4.2)."""

from __future__ import annotations

from pathlib import Path

from brain79.core.harnesses.agents_md import AgentsMdAdapter
from brain79.core.harnesses.antigravity import AntigravityAdapter
from brain79.core.harnesses.base import HarnessAdapter
from brain79.core.harnesses.cursor import CursorAdapter
from brain79.core.harnesses.mcp_json import McpJsonAdapter

_HARNESS_ADAPTERS: list[HarnessAdapter] = [
    AgentsMdAdapter(),
    McpJsonAdapter(),
    AntigravityAdapter(),
    CursorAdapter(),
]


def register_harness_adapter(adapter: HarnessAdapter) -> None:
    """Register a custom HarnessAdapter (replaces existing adapter with the same name)."""
    for idx, existing in enumerate(_HARNESS_ADAPTERS):
        if existing.name == adapter.name:
            _HARNESS_ADAPTERS[idx] = adapter
            return
    _HARNESS_ADAPTERS.append(adapter)


def get_harness_adapters() -> tuple[HarnessAdapter, ...]:
    """Return all registered Tier 1 harness adapters in deterministic order."""
    return tuple(_HARNESS_ADAPTERS)


def sync_all_harnesses(project_root: Path) -> list[str]:
    """Synchronize all registered harness adapters for project_root."""
    touched: list[str] = []
    for adapter in _HARNESS_ADAPTERS:
        touched.extend(adapter.sync(project_root))
    return touched


def diagnose_all_harnesses(project_root: Path) -> dict[str, list[str]]:
    """Run diagnostics across all registered harness adapters."""
    return {adapter.name: adapter.diagnose(project_root) for adapter in _HARNESS_ADAPTERS}


__all__ = [
    "AgentsMdAdapter",
    "AntigravityAdapter",
    "CursorAdapter",
    "HarnessAdapter",
    "McpJsonAdapter",
    "diagnose_all_harnesses",
    "get_harness_adapters",
    "register_harness_adapter",
    "sync_all_harnesses",
]
