"""Base protocol for declarative Tier 1 AI harness adapters (Phase 10 Stage 4: R-4.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class HarnessAdapter(Protocol):
    """Protocol implemented by every AI client harness adapter."""

    name: str

    def detect(self, project_root: Path) -> bool:
        """Return True if this harness configuration is present in project_root."""
        ...

    def sync(self, project_root: Path) -> list[str]:
        """Create or synchronize this harness configuration. Returns list of touched relative paths."""
        ...

    def diagnose(self, project_root: Path) -> list[str]:
        """Return a list of diagnostic issue messages for this harness (empty if healthy)."""
        ...
