"""Reusable Tree-sitter AST public API inspector (Phase 15 Stage 2: R-2.2, R-2.6)."""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable, Sequence
from typing import Any

from brain79.core.ast_guards.base import SignatureDiff
from brain79.core.ast_guards.orchestrator import MAX_AST_SOURCE_BYTES

COMMENT_NODE_TYPES: frozenset[str] = frozenset(
    {
        "comment",
        "line_comment",
        "block_comment",
        "documentation_comment",
    }
)

ATOMIC_LITERAL_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "template_string",
        "raw_string_literal",
        "interpreted_string_literal",
        "string_literal",
        "char_literal",
        "character_literal",
    }
)

SignatureExtractor = Callable[[Any, bytes], dict[str, str]]


def _import_module_any(module_name: str) -> Any:
    """Import a module dynamically without static import-time dependency."""
    return importlib.import_module(module_name)


def node_text(node: Any, source_bytes: bytes) -> str:
    """Decode the exact UTF-8 slice of an AST node."""
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _node_span_key(node: Any) -> tuple[int, int, str]:
    return (int(node.start_byte), int(node.end_byte), str(node.type))


def _collect_tokens(
    node: Any,
    excluded_spans: set[tuple[int, int, str]],
    source_bytes: bytes,
    out: list[str],
) -> None:
    if _node_span_key(node) in excluded_spans or node.type in COMMENT_NODE_TYPES:
        return
    if node.child_count == 0 or node.type in ATOMIC_LITERAL_TYPES:
        txt = node_text(node, source_bytes)
        if node.type in ATOMIC_LITERAL_TYPES:
            if txt:
                out.append(txt)
        else:
            collapsed = " ".join(txt.split())
            if collapsed:
                out.append(collapsed)
        return
    for child in node.children:
        _collect_tokens(child, excluded_spans, source_bytes, out)


def normalize_slice_without_nodes(
    node: Any,
    excluded_nodes: Sequence[Any],
    source_bytes: bytes,
) -> str:
    """Normalize an AST node's text by omitting comment nodes and excluded subtrees.

    Walks AST leaf tokens (keeping literal nodes atomic) so comments and arbitrary
    whitespace runs are removed without regex stripping, preserving string literals
    such as URLs containing ``//`` or ``/*``.
    """
    excluded_spans = {_node_span_key(ex) for ex in excluded_nodes if ex is not None}
    tokens: list[str] = []
    _collect_tokens(node, excluded_spans, source_bytes, tokens)
    return " ".join(tokens)


def normalize_node_text(node: Any, source_bytes: bytes) -> str:
    """Normalize an AST node's text, omitting comment descendants and collapsing spaces."""
    return normalize_slice_without_nodes(node, (), source_bytes)


def header_has_error(node: Any, excluded_nodes: Sequence[Any] = ()) -> bool:
    """Return True if a declaration's header (excluding body subtrees) has syntax errors."""
    if getattr(node, "is_missing", False):
        return True
    excluded_spans = {_node_span_key(ex) for ex in excluded_nodes if ex is not None}
    for child in node.children:
        if _node_span_key(child) in excluded_spans:
            continue
        if getattr(child, "has_error", False) or getattr(child, "is_missing", False):
            return True
    return False


class TreeSitterInspector:
    """Thread-safe, lazy-loading LanguageInspector backed by Tree-sitter."""

    def __init__(
        self,
        *,
        language: str,
        extensions: tuple[str, ...],
        module_name: str,
        factory_names: tuple[str, ...],
        extractor: SignatureExtractor,
    ) -> None:
        self.language = language
        self.extensions = extensions
        self.module_name = module_name
        self.factory_names = factory_names
        self._extractor = extractor
        self._lock = threading.Lock()
        self._cached_language: Any | None = None
        self._init_error: BaseException | None = None
        self._initialized = False

    def ensure_language(self) -> Any:
        """Lazily import and validate the Tree-sitter Language object once under a lock."""
        with self._lock:
            if self._initialized:
                if self._init_error is not None:
                    raise self._init_error
                return self._cached_language

            try:
                ts_mod = _import_module_any("tree_sitter")
                grammar_mod = _import_module_any(self.module_name)
                factory: Any = None
                for fname in self.factory_names:
                    factory = getattr(grammar_mod, fname, None)
                    if callable(factory):
                        break
                if not callable(factory):
                    raise RuntimeError(
                        f"Module '{self.module_name}' exposes none of {self.factory_names}"
                    )
                lang_ptr = factory()
                lang_obj = ts_mod.Language(lang_ptr)
                self._cached_language = lang_obj
                self._initialized = True
                return lang_obj
            except BaseException as exc:
                self._init_error = exc
                self._initialized = True
                raise

    def _parse(self, source_code: str) -> tuple[Any, bytes]:
        lang_obj = self.ensure_language()
        ts_mod = _import_module_any("tree_sitter")
        parser = ts_mod.Parser(lang_obj)
        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)
        return tree, source_bytes

    def extract_signatures(self, source_code: str) -> dict[str, Any]:
        """Extract public API signatures using per-call Tree-sitter Parser isolation."""
        source_bytes = source_code.encode("utf-8")
        if len(source_bytes) > MAX_AST_SOURCE_BYTES:
            return {}
        tree, parsed_bytes = self._parse(source_code)
        return dict(self._extractor(tree.root_node, parsed_bytes))

    def compare_sources(
        self,
        base_source: str,
        current_source: str,
        rel_path: str,
    ) -> SignatureDiff:
        """Compare base and current source files for public API changes."""
        base_bytes = base_source.encode("utf-8")
        curr_bytes = current_source.encode("utf-8")
        if len(base_bytes) > MAX_AST_SOURCE_BYTES or len(curr_bytes) > MAX_AST_SOURCE_BYTES:
            return SignatureDiff(False, "")

        base_tree, base_parsed = self._parse(base_source)
        curr_tree, curr_parsed = self._parse(current_source)

        base_sigs = self._extractor(base_tree.root_node, base_parsed)
        curr_sigs = self._extractor(curr_tree.root_node, curr_parsed)

        base_unparseable = bool(base_source.strip()) and bool(base_tree.root_node.has_error) and not base_sigs
        curr_unparseable = bool(current_source.strip()) and bool(curr_tree.root_node.has_error) and not curr_sigs

        if not base_sigs and not curr_sigs:
            if base_unparseable and not curr_unparseable:
                return SignatureDiff(False, "")
            if curr_unparseable and not base_unparseable:
                return SignatureDiff(True, f"unparseable source in {rel_path}")
            return SignatureDiff(False, "")

        if curr_unparseable:
            return SignatureDiff(True, f"unparseable source in {rel_path}")

        if base_unparseable and curr_sigs:
            return SignatureDiff(True, f"added public symbol '{sorted(curr_sigs)[0]}' in {rel_path}")

        added = sorted(set(curr_sigs.keys()) - set(base_sigs.keys()))
        if added:
            return SignatureDiff(True, f"added public symbol '{added[0]}' in {rel_path}")

        removed = sorted(set(base_sigs.keys()) - set(curr_sigs.keys()))
        if removed:
            return SignatureDiff(True, f"removed public symbol '{removed[0]}' in {rel_path}")

        for sym in sorted(curr_sigs.keys()):
            if base_sigs.get(sym) != curr_sigs[sym]:
                return SignatureDiff(True, f"changed public signature for '{sym}' in {rel_path}")

        return SignatureDiff(False, "")
