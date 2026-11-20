"""Pluggable AST public-API inspector registry (Phase 10 Stage 4: R-4.1)."""

from __future__ import annotations

from pathlib import Path

from brain79.core.ast_guards.base import LanguageInspector, SignatureDiff
from brain79.core.ast_guards.python_inspector import (
    PythonInspector,
    extract_public_python_signatures,
    has_public_python_api_changes,
)

_INSPECTORS_BY_EXT: dict[str, LanguageInspector] = {}


def register_inspector(inspector: LanguageInspector) -> None:
    """Register a LanguageInspector for all its declared file extensions."""
    for ext in inspector.extensions:
        norm_ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        _INSPECTORS_BY_EXT[norm_ext] = inspector


def get_inspector_for_path(path: str | Path) -> LanguageInspector | None:
    """Return the registered LanguageInspector matching the file's extension, or None."""
    suffix = Path(path).suffix.lower()
    return _INSPECTORS_BY_EXT.get(suffix)


def list_registered_extensions() -> tuple[str, ...]:
    """Return all file extensions with registered AST inspectors."""
    return tuple(sorted(_INSPECTORS_BY_EXT.keys()))


# Register built-in Python inspector by default
register_inspector(PythonInspector())

__all__ = [
    "LanguageInspector",
    "PythonInspector",
    "SignatureDiff",
    "extract_public_python_signatures",
    "get_inspector_for_path",
    "has_public_python_api_changes",
    "list_registered_extensions",
    "register_inspector",
]
