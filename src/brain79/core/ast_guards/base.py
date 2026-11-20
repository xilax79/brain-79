"""Base protocol and result types for pluggable AST public-API inspectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SignatureDiff:
    """Result of comparing public API signatures between two revisions of a source file."""

    has_changes: bool
    description: str


@runtime_checkable
class LanguageInspector(Protocol):
    """Protocol for language-specific public API signature inspectors."""

    extensions: tuple[str, ...]

    def extract_signatures(self, source_code: str) -> dict[str, Any]:
        """Extract public symbol signatures from source code."""
        ...

    def compare_sources(
        self,
        base_source: str,
        current_source: str,
        rel_path: str,
    ) -> SignatureDiff:
        """Compare base and current source code for public API changes."""
        ...
