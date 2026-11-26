"""Pluggable AST public-API inspector registry (Phase 10 Stage 4: R-4.1, Phase 15 Stages 1-2)."""

from __future__ import annotations

import importlib
import importlib.util
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from brain79.core.ast_guards.base import LanguageInspector, SignatureDiff
from brain79.core.ast_guards.orchestrator import (
    MAX_AST_SOURCE_BYTES,
    has_public_api_changes,
)
from brain79.core.ast_guards.polyglot import POLYGLOT_LANGUAGE_SPECS
from brain79.core.ast_guards.python_inspector import (
    PythonInspector,
    extract_public_python_signatures,
    has_public_python_api_changes,
)
from brain79.core.ast_guards.treesitter_inspector import TreeSitterInspector

POLYGLOT_LANGUAGES: tuple[str, ...] = tuple(
    sorted(spec.language for spec in POLYGLOT_LANGUAGE_SPECS)
)

_REGISTRY_LOCK = threading.Lock()
_INSPECTORS_BY_EXT: dict[str, LanguageInspector] = {}
_BROKEN_GRAMMARS: dict[str, str] = {}
_MISSING_GRAMMARS: set[str] = set()


def _normalize_ext(ext: str) -> str:
    return ext.lower() if ext.startswith(".") else f".{ext.lower()}"


def register_inspector(inspector: LanguageInspector) -> None:
    """Register a LanguageInspector for all its declared file extensions."""
    with _REGISTRY_LOCK:
        for ext in inspector.extensions:
            _INSPECTORS_BY_EXT[_normalize_ext(ext)] = inspector


def unregister_extensions(extensions: Iterable[str]) -> None:
    """Unregister any LanguageInspector bound to the given file extensions."""
    with _REGISTRY_LOCK:
        for ext in extensions:
            _INSPECTORS_BY_EXT.pop(_normalize_ext(ext), None)


def _validate_treesitter_inspector(inspector: TreeSitterInspector) -> bool:
    """Validate and memoize a lazy TreeSitterInspector; unregister on failure."""
    try:
        inspector.ensure_language()
        return True
    except (ImportError, ModuleNotFoundError):
        with _REGISTRY_LOCK:
            _MISSING_GRAMMARS.add(inspector.language)
            for ext in inspector.extensions:
                _INSPECTORS_BY_EXT.pop(_normalize_ext(ext), None)
        return False
    except Exception as exc:
        with _REGISTRY_LOCK:
            _BROKEN_GRAMMARS[inspector.language] = f"{type(exc).__name__}: {exc}"
            for ext in inspector.extensions:
                _INSPECTORS_BY_EXT.pop(_normalize_ext(ext), None)
        return False


def get_inspector_for_path(path: str | Path) -> LanguageInspector | None:
    """Return the registered LanguageInspector matching the file's extension, or None."""
    suffix = Path(path).suffix.lower()
    with _REGISTRY_LOCK:
        inspector = _INSPECTORS_BY_EXT.get(suffix)
    if isinstance(inspector, TreeSitterInspector):
        if not _validate_treesitter_inspector(inspector):
            return None
    return inspector


def list_registered_extensions() -> tuple[str, ...]:
    """Return all file extensions with registered AST inspectors."""
    with _REGISTRY_LOCK:
        return tuple(sorted(_INSPECTORS_BY_EXT.keys()))


def _is_tree_sitter_runtime_available(*, validate: bool = False) -> bool:
    try:
        if importlib.util.find_spec("tree_sitter") is None:
            return False
        if validate:
            importlib.import_module("tree_sitter")
        return True
    except Exception:
        return False


def discover_polyglot_inspectors(*, reset: bool = False) -> None:
    """Metadata-only discovery of optional Tree-sitter grammars via importlib.util.find_spec."""
    with _REGISTRY_LOCK:
        if reset:
            _BROKEN_GRAMMARS.clear()
            _MISSING_GRAMMARS.clear()
            poly_exts = {
                _normalize_ext(ext)
                for spec in POLYGLOT_LANGUAGE_SPECS
                for ext in spec.extensions
            }
            for ext in poly_exts:
                _INSPECTORS_BY_EXT.pop(ext, None)

        has_runtime = importlib.util.find_spec("tree_sitter") is not None
        if not has_runtime:
            _MISSING_GRAMMARS.update(POLYGLOT_LANGUAGES)
            return

        for spec in POLYGLOT_LANGUAGE_SPECS:
            if importlib.util.find_spec(spec.module_name) is None:
                _MISSING_GRAMMARS.add(spec.language)
                continue
            inspector = TreeSitterInspector(
                language=spec.language,
                extensions=spec.extensions,
                module_name=spec.module_name,
                factory_names=spec.factory_names,
                extractor=spec.extractor,
            )
            for ext in spec.extensions:
                _INSPECTORS_BY_EXT[_normalize_ext(ext)] = inspector


def get_ast_guard_capabilities() -> dict[str, Any]:
    """Return deterministic capability metadata for built-in and polyglot AST guards."""
    with _REGISTRY_LOCK:
        inspectors_snapshot = list(_INSPECTORS_BY_EXT.values())

    seen_ts: set[int] = set()
    for insp in inspectors_snapshot:
        if isinstance(insp, TreeSitterInspector) and id(insp) not in seen_ts:
            seen_ts.add(id(insp))
            _validate_treesitter_inspector(insp)

    runtime_available = _is_tree_sitter_runtime_available(validate=True)

    with _REGISTRY_LOCK:
        active_set: set[str] = {"python"}
        for insp in _INSPECTORS_BY_EXT.values():
            lang_id = getattr(insp, "language", type(insp).__name__.lower())
            active_set.add(str(lang_id))
        broken_copy = dict(_BROKEN_GRAMMARS)
        registered_exts = sorted(_INSPECTORS_BY_EXT.keys())

    missing_grammars = sorted(
        lang
        for lang in POLYGLOT_LANGUAGES
        if lang not in active_set and lang not in broken_copy
    )
    polyglot_installed = runtime_available and any(
        lang in active_set for lang in POLYGLOT_LANGUAGES
    )

    return {
        "built_in": ["python"],
        "polyglot_runtime_available": runtime_available,
        "polyglot_installed": polyglot_installed,
        "active_languages": sorted(active_set),
        "missing_grammars": missing_grammars,
        "broken_grammars": broken_copy,
        "registered_extensions": registered_exts,
    }


# Register built-in Python inspector and metadata-discover optional polyglot grammars
register_inspector(PythonInspector())
discover_polyglot_inspectors()

__all__ = [
    "MAX_AST_SOURCE_BYTES",
    "POLYGLOT_LANGUAGES",
    "LanguageInspector",
    "PythonInspector",
    "SignatureDiff",
    "TreeSitterInspector",
    "discover_polyglot_inspectors",
    "extract_public_python_signatures",
    "get_ast_guard_capabilities",
    "get_inspector_for_path",
    "has_public_api_changes",
    "has_public_python_api_changes",
    "list_registered_extensions",
    "register_inspector",
    "unregister_extensions",
]
