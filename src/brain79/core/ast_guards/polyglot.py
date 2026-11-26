"""Declarative polyglot public API extractors for all 10 POLYGLOT_LANGUAGES (R-2.3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from brain79.core.ast_guards.treesitter_inspector import (
    SignatureExtractor,
    header_has_error,
    node_text,
    normalize_node_text,
    normalize_slice_without_nodes,
)


@dataclass(frozen=True)
class PolyglotLanguageSpec:
    """Declarative metadata and extractor binding for a Tree-sitter language."""

    language: str
    module_name: str
    factory_names: tuple[str, ...]
    extensions: tuple[str, ...]
    extractor: SignatureExtractor


def _child_by_type(node: Any, *types: str) -> Any | None:
    for child in node.children:
        if child.type in types:
            return child
    return None


def _children_by_type(node: Any, *types: str) -> list[Any]:
    return [child for child in node.children if child.type in types]


# ---------------------------------------------------------------------------
# TypeScript / TSX / JavaScript
# ---------------------------------------------------------------------------


def _ts_param_types(params_node: Any, source_bytes: bytes) -> str:
    if params_node is None:
        return ""
    types: list[str] = []
    for child in params_node.named_children:
        if child.type in ("required_parameter", "optional_parameter", "rest_parameter"):
            type_ann = child.child_by_field_name("type")
            if type_ann is not None:
                # type_annotation usually starts with ':'
                t_text = normalize_node_text(type_ann, source_bytes)
                if t_text.startswith(":"):
                    t_text = t_text[1:].strip()
                types.append(t_text)
            else:
                types.append("any")
    return ", ".join(types)


def _ts_is_private_member(node: Any, source_bytes: bytes) -> bool:
    for child in node.children:
        if child.type == "accessibility_modifier":
            mod = normalize_node_text(child, source_bytes)
            if mod in ("private", "protected"):
                return True
        elif child.type == "private_property_identifier":
            return True
    name_node = node.child_by_field_name("name")
    if name_node is not None and name_node.type == "private_property_identifier":
        return True
    return False


def _js_is_private_member(node: Any, source_bytes: bytes) -> bool:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        if name_node.type == "private_property_identifier":
            return True
        name_txt = normalize_node_text(name_node, source_bytes)
        if name_txt.startswith("#") or name_txt.startswith("_"):
            return True
    return False


def _extract_ts_class_members(
    class_node: Any,
    qual_cls: str,
    source_bytes: bytes,
    sigs: dict[str, str],
    *,
    is_js: bool = False,
) -> None:
    body = class_node.child_by_field_name("body")
    if body is None:
        return
    for member in body.named_children:
        if member.type in ("method_definition", "method_signature", "abstract_method_signature"):
            if is_js and _js_is_private_member(member, source_bytes):
                continue
            if not is_js and _ts_is_private_member(member, source_bytes):
                continue
            mbody = member.child_by_field_name("body")
            if header_has_error(member, (mbody,)):
                continue
            name_node = member.child_by_field_name("name")
            mname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if not mname:
                continue
            params = member.child_by_field_name("parameters")
            ptypes = "" if is_js else _ts_param_types(params, source_bytes)
            if mname == "constructor":
                key = f"constructor {qual_cls}({ptypes})"
            else:
                key = f"method {qual_cls}.{mname}({ptypes})" if not is_js else f"method {qual_cls}.{mname}"
            sigs[key] = normalize_slice_without_nodes(member, (mbody,), source_bytes)
        elif member.type in ("public_field_definition", "property_signature", "field_definition"):
            if is_js and _js_is_private_member(member, source_bytes):
                continue
            if not is_js and _ts_is_private_member(member, source_bytes):
                continue
            val = member.child_by_field_name("value")
            excluded: tuple[Any, ...] = ()
            if val is not None and val.type in ("arrow_function", "function_expression"):
                vbody = val.child_by_field_name("body")
                excluded = (vbody,)
            if header_has_error(member, excluded):
                continue
            name_node = member.child_by_field_name("name")
            fname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if fname:
                sigs[f"field {qual_cls}.{fname}"] = normalize_slice_without_nodes(
                    member, excluded, source_bytes
                )


def _extract_ts_interface_members(
    iface_node: Any,
    qual_iface: str,
    source_bytes: bytes,
    sigs: dict[str, str],
) -> None:
    body = iface_node.child_by_field_name("body")
    if body is None:
        return
    for member in body.named_children:
        if header_has_error(member):
            continue
        if member.type == "property_signature":
            name_node = member.child_by_field_name("name")
            pname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if pname:
                sigs[f"property {qual_iface}.{pname}"] = normalize_node_text(member, source_bytes)
        elif member.type == "method_signature":
            name_node = member.child_by_field_name("name")
            mname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            params = member.child_by_field_name("parameters")
            ptypes = _ts_param_types(params, source_bytes)
            if mname:
                sigs[f"method {qual_iface}.{mname}({ptypes})"] = normalize_node_text(member, source_bytes)
        elif member.type in ("call_signature", "construct_signature", "index_signature"):
            sigs[f"{member.type} {qual_iface}.{normalize_node_text(member, source_bytes)}"] = (
                normalize_node_text(member, source_bytes)
            )


def _extract_ts_decl(
    decl: Any,
    scope: tuple[str, ...],
    source_bytes: bytes,
    sigs: dict[str, str],
    *,
    is_default: bool = False,
    is_js: bool = False,
    is_ambient: bool = False,
    decorators: Sequence[Any] = (),
) -> None:
    qual = ".".join(scope) + "." if scope else ""
    dec_prefix = (
        " ".join(normalize_node_text(d, source_bytes) for d in decorators) + " "
        if decorators
        else ""
    )

    if decl.type in (
        "function_declaration",
        "generator_function_declaration",
        "function_expression",
        "function_signature",
    ):
        body = decl.child_by_field_name("body")
        if header_has_error(decl, (body,)):
            return
        name_node = decl.child_by_field_name("name")
        fname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
        key = "export default function" if is_default and not fname else f"function {qual}{fname}"
        sigs[key] = dec_prefix + normalize_slice_without_nodes(decl, (body,), source_bytes)
        return

    if decl.type in ("class_declaration", "abstract_class_declaration", "class"):
        body = decl.child_by_field_name("body")
        if header_has_error(decl, (body,)):
            return
        name_node = decl.child_by_field_name("name")
        cname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
        qual_cls = f"{qual}{cname}" if cname else f"{qual}default"
        key = "export default class" if is_default and not cname else f"class {qual_cls}"
        sigs[key] = dec_prefix + normalize_slice_without_nodes(decl, (body,), source_bytes)
        _extract_ts_class_members(decl, qual_cls, source_bytes, sigs, is_js=is_js)
        return

    if decl.type == "interface_declaration":
        body = decl.child_by_field_name("body")
        if header_has_error(decl, (body,)):
            return
        name_node = decl.child_by_field_name("name")
        iname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
        if iname:
            qual_iface = f"{qual}{iname}"
            sigs[f"interface {qual_iface}"] = dec_prefix + normalize_slice_without_nodes(
                decl, (body,), source_bytes
            )
            _extract_ts_interface_members(decl, qual_iface, source_bytes, sigs)
        return

    if decl.type == "type_alias_declaration":
        if header_has_error(decl):
            return
        name_node = decl.child_by_field_name("name")
        tname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
        if tname:
            sigs[f"type {qual}{tname}"] = normalize_node_text(decl, source_bytes)
        return

    if decl.type == "enum_declaration":
        body = decl.child_by_field_name("body")
        if header_has_error(decl, (body,)):
            return
        name_node = decl.child_by_field_name("name")
        ename = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
        if ename:
            sigs[f"enum {qual}{ename}"] = normalize_node_text(decl, source_bytes)
        return

    if decl.type in ("internal_module", "module"):
        body = decl.child_by_field_name("body")
        if header_has_error(decl, (body,)):
            return
        name_node = decl.child_by_field_name("name")
        ns_name = (
            normalize_node_text(name_node, source_bytes).strip("\"'")
            if name_node is not None
            else ""
        )
        if ns_name:
            sigs[f"namespace {qual}{ns_name}"] = normalize_slice_without_nodes(
                decl, (body,), source_bytes
            )
            if body is not None:
                _walk_ts_statements(
                    body.named_children,
                    scope + (ns_name,),
                    source_bytes,
                    sigs,
                    in_ambient_module=is_ambient,
                    is_js=is_js,
                )
        return

    if decl.type == "ambient_declaration":
        for child in decl.named_children:
            _extract_ts_decl(child, scope, source_bytes, sigs, is_js=is_js, is_ambient=True)
        return

    if decl.type in ("lexical_declaration", "variable_declaration"):
        for vdecl in _children_by_type(decl, "variable_declarator"):
            name_node = vdecl.child_by_field_name("name")
            val_node = vdecl.child_by_field_name("value")
            type_node = vdecl.child_by_field_name("type")
            excluded: tuple[Any, ...] = ()
            if val_node is not None and val_node.type in ("arrow_function", "function_expression"):
                vbody = val_node.child_by_field_name("body")
                excluded = (vbody,)
            if header_has_error(vdecl, excluded):
                continue
            vname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if not vname:
                continue
            if val_node is not None and val_node.type in ("arrow_function", "function_expression"):
                sigs[f"const {qual}{vname}"] = normalize_slice_without_nodes(
                    vdecl, excluded, source_bytes
                )
            elif type_node is not None:
                sigs[f"const {qual}{vname}"] = (
                    f"{vname}{normalize_node_text(type_node, source_bytes)}"
                )
            else:
                sigs[f"const {qual}{vname}"] = normalize_node_text(vdecl, source_bytes)


def _walk_ts_statements(
    nodes: Sequence[Any],
    scope: tuple[str, ...],
    source_bytes: bytes,
    sigs: dict[str, str],
    *,
    in_ambient_module: bool = False,
    is_js: bool = False,
) -> None:
    for node in nodes:
        if node.type == "export_statement":
            decorators = _children_by_type(node, "decorator")
            raw_text = normalize_node_text(node, source_bytes)
            is_default = any(
                c.type == "default" or (not c.is_named and node_text(c, source_bytes) == "default")
                for c in node.children
            )
            decl = node.child_by_field_name("declaration")
            if decl is None:
                # Could be export default <expr> or export { ... } or export * ...
                for c in node.named_children:
                    if c.type in (
                        "function_declaration",
                        "generator_function_declaration",
                        "function_expression",
                        "class_declaration",
                        "abstract_class_declaration",
                        "class",
                        "interface_declaration",
                        "type_alias_declaration",
                        "enum_declaration",
                        "internal_module",
                        "module",
                        "lexical_declaration",
                        "variable_declaration",
                    ):
                        decl = c
                        break
            if decl is not None:
                _extract_ts_decl(
                    decl,
                    scope,
                    source_bytes,
                    sigs,
                    is_default=is_default,
                    is_js=is_js,
                    decorators=decorators,
                )
                continue

            if header_has_error(node):
                continue
            if _child_by_type(node, "export_clause") is not None:
                sigs[f"export {raw_text}"] = raw_text
            elif _child_by_type(node, "namespace_export") is not None or raw_text.startswith("export *"):
                sigs[f"export {raw_text}"] = raw_text
            elif raw_text.startswith("export =") or raw_text.startswith("export="):
                sigs[f"export= {raw_text}"] = raw_text
            elif is_default:
                sigs["export default"] = raw_text
        elif node.type == "ambient_declaration":
            _extract_ts_decl(node, scope, source_bytes, sigs, is_js=is_js, is_ambient=True)
        elif in_ambient_module:
            _extract_ts_decl(node, scope, source_bytes, sigs, is_js=is_js, is_ambient=True)
        elif is_js and node.type == "expression_statement":
            _extract_js_commonjs(node, source_bytes, sigs)


def _extract_js_commonjs(stmt: Any, source_bytes: bytes, sigs: dict[str, str]) -> None:
    assign = _child_by_type(stmt, "assignment_expression")
    if assign is None:
        return
    left = assign.child_by_field_name("left")
    right = assign.child_by_field_name("right")
    if left is None or right is None:
        return
    left_txt = "".join(normalize_node_text(left, source_bytes).split())
    if left_txt.startswith("exports.") or left_txt.startswith("module.exports."):
        name = left_txt.split(".", 2)[-1] if left_txt.startswith("module.exports.") else left_txt[8:]
        if right.type in ("function_expression", "arrow_function"):
            body = right.child_by_field_name("body")
            if header_has_error(assign, (body,)):
                return
            sigs[f"cjs {name}"] = normalize_slice_without_nodes(right, (body,), source_bytes)
        elif right.type == "class":
            body = right.child_by_field_name("body")
            if header_has_error(assign, (body,)):
                return
            sigs[f"cjs class {name}"] = normalize_slice_without_nodes(right, (body,), source_bytes)
            _extract_ts_class_members(right, name, source_bytes, sigs, is_js=True)
        else:
            if not header_has_error(assign):
                sigs[f"cjs {name}"] = "exported"
    elif left_txt == "module.exports":
        if right.type == "object":
            for pair in right.named_children:
                if pair.type == "pair":
                    k = pair.child_by_field_name("key")
                    v = pair.child_by_field_name("value")
                    kname = normalize_node_text(k, source_bytes) if k is not None else ""
                    if not kname:
                        continue
                    if v is not None and v.type in ("function_expression", "arrow_function"):
                        vbody = v.child_by_field_name("body")
                        if not header_has_error(pair, (vbody,)):
                            sigs[f"cjs {kname}"] = normalize_slice_without_nodes(
                                v, (vbody,), source_bytes
                            )
                    elif not header_has_error(pair):
                        sigs[f"cjs {kname}"] = "exported"
                elif pair.type == "shorthand_property_identifier":
                    kname = normalize_node_text(pair, source_bytes)
                    if kname:
                        sigs[f"cjs {kname}"] = "exported"
                elif pair.type == "method_definition":
                    mbody = pair.child_by_field_name("body")
                    kname_node = pair.child_by_field_name("name")
                    kname = (
                        normalize_node_text(kname_node, source_bytes)
                        if kname_node is not None
                        else ""
                    )
                    if kname and not header_has_error(pair, (mbody,)):
                        sigs[f"cjs {kname}"] = normalize_slice_without_nodes(
                            pair, (mbody,), source_bytes
                        )
        elif right.type == "class":
            body = right.child_by_field_name("body")
            if not header_has_error(assign, (body,)):
                cls_name_node = right.child_by_field_name("name")
                cls_name = (
                    normalize_node_text(cls_name_node, source_bytes)
                    if cls_name_node is not None
                    else "default"
                )
                sigs["cjs module.exports"] = normalize_slice_without_nodes(
                    right, (body,), source_bytes
                )
                _extract_ts_class_members(right, cls_name, source_bytes, sigs, is_js=True)
        elif right.type in ("function_expression", "arrow_function"):
            body = right.child_by_field_name("body")
            if not header_has_error(assign, (body,)):
                sigs["cjs module.exports"] = normalize_slice_without_nodes(
                    right, (body,), source_bytes
                )
        elif not header_has_error(assign):
            sigs["cjs module.exports"] = normalize_node_text(right, source_bytes)


def extract_typescript_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    _walk_ts_statements(root.named_children, (), source_bytes, sigs, is_js=False)
    return sigs


def extract_javascript_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    _walk_ts_statements(root.named_children, (), source_bytes, sigs, is_js=True)
    return sigs


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


def _go_receiver_type(param_list: Any, source_bytes: bytes) -> str:
    if param_list is None:
        return ""
    for pdecl in _children_by_type(param_list, "parameter_declaration"):
        type_node = pdecl.child_by_field_name("type")
        if type_node is not None:
            return normalize_node_text(type_node, source_bytes)
    return normalize_node_text(param_list, source_bytes)


def extract_go_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    for node in root.named_children:
        if node.type == "function_declaration":
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if name and name[0].isupper():
                sigs[f"func {name}"] = normalize_slice_without_nodes(node, (body,), source_bytes)

        elif node.type == "method_declaration":
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            recv_node = node.child_by_field_name("receiver")
            name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if name and name[0].isupper():
                recv_type = _go_receiver_type(recv_node, source_bytes)
                sigs[f"func ({recv_type}) {name}"] = normalize_slice_without_nodes(
                    node, (recv_node, body), source_bytes
                )

        elif node.type == "type_declaration":
            for spec in _children_by_type(node, "type_spec", "type_alias"):
                if header_has_error(spec):
                    continue
                name_node = spec.child_by_field_name("name")
                tname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
                if not tname or not tname[0].isupper():
                    continue
                type_node = spec.child_by_field_name("type")
                if type_node is not None and type_node.type == "struct_type":
                    sigs[f"type {tname}"] = "struct"
                    field_list = _child_by_type(type_node, "field_declaration_list")
                    if field_list is not None:
                        for fdecl in _children_by_type(field_list, "field_declaration"):
                            if header_has_error(fdecl):
                                continue
                            fnames = [
                                normalize_node_text(c, source_bytes)
                                for c in _children_by_type(fdecl, "field_identifier")
                            ]
                            ftype = fdecl.child_by_field_name("type")
                            ftext = normalize_node_text(ftype, source_bytes) if ftype is not None else ""
                            for fn in fnames:
                                if fn and fn[0].isupper():
                                    sigs[f"field {tname}.{fn}"] = ftext
                elif type_node is not None and type_node.type == "interface_type":
                    sigs[f"type {tname}"] = "interface"
                    for elem in type_node.named_children:
                        if elem.type == "method_elem":
                            mname_node = elem.child_by_field_name("name")
                            mname = (
                                normalize_node_text(mname_node, source_bytes)
                                if mname_node is not None
                                else ""
                            )
                            if mname and mname[0].isupper():
                                sigs[f"method {tname}.{mname}"] = normalize_node_text(
                                    elem, source_bytes
                                )
                        elif elem.type == "type_elem":
                            sigs[f"embed {tname}.{normalize_node_text(elem, source_bytes)}"] = (
                                normalize_node_text(elem, source_bytes)
                            )
                else:
                    sigs[f"type {tname}"] = normalize_node_text(spec, source_bytes)

        elif node.type in ("const_declaration", "var_declaration"):
            kind = "const" if node.type == "const_declaration" else "var"
            spec_type = "const_spec" if kind == "const" else "var_spec"
            spec_list_type = "const_spec_list" if kind == "const" else "var_spec_list"
            specs = list(_children_by_type(node, spec_type))
            for spec_list in _children_by_type(node, spec_list_type):
                specs.extend(_children_by_type(spec_list, spec_type))
            for spec in specs:
                if header_has_error(spec):
                    continue
                type_node = spec.child_by_field_name("type")
                explicit_type = (
                    normalize_node_text(type_node, source_bytes) if type_node is not None else ""
                )
                for ident in _children_by_type(spec, "identifier"):
                    vname = normalize_node_text(ident, source_bytes)
                    if vname and vname[0].isupper():
                        sigs[f"{kind} {vname}"] = explicit_type
    return sigs


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------


def _rust_is_exact_pub(node: Any, source_bytes: bytes) -> bool:
    vis = _child_by_type(node, "visibility_modifier")
    if vis is None:
        return False
    return normalize_node_text(vis, source_bytes) == "pub"


def _walk_rust_items(
    nodes: Sequence[Any],
    mod_prefix: str,
    source_bytes: bytes,
    sigs: dict[str, str],
) -> None:
    for node in nodes:
        if node.type == "function_item":
            if not _rust_is_exact_pub(node, source_bytes):
                continue
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if name:
                sigs[f"fn {mod_prefix}{name}"] = normalize_slice_without_nodes(
                    node, (body,), source_bytes
                )

        elif node.type == "struct_item":
            if not _rust_is_exact_pub(node, source_bytes):
                continue
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if name:
                sigs[f"struct {mod_prefix}{name}"] = normalize_slice_without_nodes(
                    node, (body,), source_bytes
                )
                if body is not None and body.type == "field_declaration_list":
                    for fdecl in _children_by_type(body, "field_declaration"):
                        if _rust_is_exact_pub(fdecl, source_bytes) and not header_has_error(fdecl):
                            fname_node = fdecl.child_by_field_name("name")
                            fname = (
                                normalize_node_text(fname_node, source_bytes)
                                if fname_node is not None
                                else ""
                            )
                            if fname:
                                sigs[f"field {mod_prefix}{name}.{fname}"] = normalize_node_text(
                                    fdecl, source_bytes
                                )

        elif node.type == "enum_item":
            if not _rust_is_exact_pub(node, source_bytes):
                continue
            if header_has_error(node):
                continue
            name_node = node.child_by_field_name("name")
            name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if name:
                sigs[f"enum {mod_prefix}{name}"] = normalize_node_text(node, source_bytes)

        elif node.type == "trait_item":
            if not _rust_is_exact_pub(node, source_bytes):
                continue
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if name:
                sigs[f"trait {mod_prefix}{name}"] = normalize_slice_without_nodes(
                    node, (body,), source_bytes
                )
                if body is not None:
                    for item in body.named_children:
                        if item.type in ("function_signature_item", "function_item"):
                            ibody = item.child_by_field_name("body")
                            if header_has_error(item, (ibody,)):
                                continue
                            mname_node = item.child_by_field_name("name")
                            mname = (
                                normalize_node_text(mname_node, source_bytes)
                                if mname_node is not None
                                else ""
                            )
                            if mname:
                                sigs[f"trait_fn {mod_prefix}{name}::{mname}"] = (
                                    normalize_slice_without_nodes(item, (ibody,), source_bytes)
                                )

        elif node.type == "type_item":
            if _rust_is_exact_pub(node, source_bytes) and not header_has_error(node):
                name_node = node.child_by_field_name("name")
                name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
                if name:
                    sigs[f"type {mod_prefix}{name}"] = normalize_node_text(node, source_bytes)

        elif node.type in ("const_item", "static_item"):
            if _rust_is_exact_pub(node, source_bytes):
                val_node = node.child_by_field_name("value")
                if header_has_error(node, (val_node,)):
                    continue
                name_node = node.child_by_field_name("name")
                type_node = node.child_by_field_name("type")
                name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
                ty = normalize_node_text(type_node, source_bytes) if type_node is not None else ""
                kind = "const" if node.type == "const_item" else "static"
                if name:
                    sigs[f"{kind} {mod_prefix}{name}"] = f"{name}: {ty}"

        elif node.type == "impl_item":
            body = node.child_by_field_name("body")
            if body is None or header_has_error(node, (body,)):
                continue
            type_node = node.child_by_field_name("type")
            trait_node = node.child_by_field_name("trait")
            type_txt = normalize_node_text(type_node, source_bytes) if type_node is not None else ""
            is_trait_impl = trait_node is not None
            if is_trait_impl:
                trait_txt = normalize_node_text(trait_node, source_bytes)
                impl_qual = f"{mod_prefix}{type_txt} as {trait_txt}::"
            else:
                impl_qual = f"{mod_prefix}{type_txt}::"
            for item in body.named_children:
                if item.type == "function_item":
                    if not is_trait_impl and not _rust_is_exact_pub(item, source_bytes):
                        continue
                    ibody = item.child_by_field_name("body")
                    if header_has_error(item, (ibody,)):
                        continue
                    mname_node = item.child_by_field_name("name")
                    mname = (
                        normalize_node_text(mname_node, source_bytes)
                        if mname_node is not None
                        else ""
                    )
                    if mname:
                        sigs[f"fn {impl_qual}{mname}"] = normalize_slice_without_nodes(
                            item, (ibody,), source_bytes
                        )

        elif node.type == "mod_item":
            if not _rust_is_exact_pub(node, source_bytes):
                continue
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            name = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if name:
                sigs[f"mod {mod_prefix}{name}"] = normalize_slice_without_nodes(
                    node, (body,), source_bytes
                )
                if body is not None:
                    _walk_rust_items(
                        body.named_children, f"{mod_prefix}{name}::", source_bytes, sigs
                    )


def extract_rust_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    _walk_rust_items(root.named_children, "", source_bytes, sigs)
    return sigs


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


def _java_modifiers(node: Any, source_bytes: bytes) -> set[str]:
    mods_node = _child_by_type(node, "modifiers")
    if mods_node is None:
        return set()
    return set(normalize_node_text(mods_node, source_bytes).split())


def _java_param_types(params_node: Any, source_bytes: bytes) -> str:
    if params_node is None:
        return ""
    types: list[str] = []
    for child in params_node.named_children:
        if child.type in ("formal_parameter", "spread_parameter"):
            t_node = child.child_by_field_name("type")
            if t_node is not None:
                types.append(normalize_node_text(t_node, source_bytes))
            else:
                types.append(normalize_node_text(child, source_bytes))
    return ", ".join(types)


def _walk_java_types(
    nodes: Sequence[Any],
    qual: str,
    source_bytes: bytes,
    sigs: dict[str, str],
    *,
    in_interface: bool = False,
) -> None:
    type_nodes = (
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    )
    for node in nodes:
        if node.type not in type_nodes:
            continue
        mods = _java_modifiers(node, source_bytes)
        if in_interface:
            if "private" in mods:
                continue
        elif "public" not in mods:
            continue
        body = node.child_by_field_name("body")
        if header_has_error(node, (body,)):
            continue
        name_node = node.child_by_field_name("name")
        tname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
        if not tname:
            continue
        kind = node.type.removesuffix("_declaration")
        qual_type = f"{qual}{tname}"
        sigs[f"{kind} {qual_type}"] = normalize_slice_without_nodes(node, (body,), source_bytes)
        if body is None:
            continue

        child_in_iface = node.type == "interface_declaration"
        body_members: list[Any] = []
        for child in body.named_children:
            if child.type == "enum_constant":
                if not header_has_error(child):
                    cname_node = child.child_by_field_name("name")
                    cname = (
                        normalize_node_text(cname_node, source_bytes)
                        if cname_node is not None
                        else ""
                    )
                    if cname:
                        sigs[f"enum_const {qual_type}.{cname}"] = cname
            elif child.type == "enum_body_declarations":
                body_members.extend(child.named_children)
            else:
                body_members.append(child)

        for member in body_members:
            if member.type in type_nodes:
                _walk_java_types(
                    (member,), f"{qual_type}.", source_bytes, sigs, in_interface=child_in_iface
                )
                continue
            m_mods = _java_modifiers(member, source_bytes)
            is_pub = ("private" not in m_mods) if child_in_iface else ("public" in m_mods)
            if not is_pub:
                continue
            if member.type == "constructor_declaration":
                mbody = member.child_by_field_name("body")
                if header_has_error(member, (mbody,)):
                    continue
                ptypes = _java_param_types(member.child_by_field_name("parameters"), source_bytes)
                sigs[f"constructor {qual_type}({ptypes})"] = normalize_slice_without_nodes(
                    member, (mbody,), source_bytes
                )
            elif member.type == "method_declaration":
                mbody = member.child_by_field_name("body")
                if header_has_error(member, (mbody,)):
                    continue
                mname_node = member.child_by_field_name("name")
                mname = (
                    normalize_node_text(mname_node, source_bytes)
                    if mname_node is not None
                    else ""
                )
                ptypes = _java_param_types(member.child_by_field_name("parameters"), source_bytes)
                if mname:
                    sigs[f"method {qual_type}.{mname}({ptypes})"] = normalize_slice_without_nodes(
                        member, (mbody,), source_bytes
                    )
            elif member.type in ("field_declaration", "constant_declaration"):
                if header_has_error(member):
                    continue
                type_node = member.child_by_field_name("type")
                ftype = normalize_node_text(type_node, source_bytes) if type_node is not None else ""
                for vdecl in _children_by_type(member, "variable_declarator"):
                    vname_node = vdecl.child_by_field_name("name")
                    fname = (
                        normalize_node_text(vname_node, source_bytes)
                        if vname_node is not None
                        else ""
                    )
                    if fname:
                        sigs[f"field {qual_type}.{fname}"] = f"{ftype} {fname}".strip()


def extract_java_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    _walk_java_types(root.named_children, "", source_bytes, sigs)
    return sigs


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------


def _cs_modifiers(node: Any, source_bytes: bytes) -> set[str]:
    return {normalize_node_text(c, source_bytes) for c in _children_by_type(node, "modifier")}


def _cs_param_types(params_node: Any, source_bytes: bytes) -> str:
    if params_node is None:
        return ""
    types: list[str] = []
    for child in params_node.named_children:
        if child.type == "parameter":
            t_node = child.child_by_field_name("type")
            if t_node is not None:
                types.append(normalize_node_text(t_node, source_bytes))
    return ", ".join(types)


def _walk_cs_nodes(
    nodes: Sequence[Any],
    qual: str,
    source_bytes: bytes,
    sigs: dict[str, str],
    *,
    in_interface: bool = False,
) -> None:
    type_nodes = (
        "class_declaration",
        "struct_declaration",
        "record_declaration",
        "interface_declaration",
        "enum_declaration",
    )
    active_qual = qual
    for node in nodes:
        if node.type == "file_scoped_namespace_declaration":
            name_node = node.child_by_field_name("name")
            ns = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if ns:
                active_qual = f"{active_qual}{ns}."
            continue

        if node.type == "namespace_declaration":
            name_node = node.child_by_field_name("name")
            ns = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            body = node.child_by_field_name("body")
            if ns and body is not None:
                _walk_cs_nodes(body.named_children, f"{active_qual}{ns}.", source_bytes, sigs)
            continue

        if node.type == "delegate_declaration":
            mods = _cs_modifiers(node, source_bytes)
            if "public" not in mods or header_has_error(node):
                continue
            name_node = node.child_by_field_name("name")
            dname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if dname:
                sigs[f"delegate {active_qual}{dname}"] = normalize_node_text(node, source_bytes)
            continue

        if node.type not in type_nodes:
            continue
        mods = _cs_modifiers(node, source_bytes)
        if in_interface:
            if "private" in mods or "internal" in mods:
                continue
        elif "public" not in mods:
            continue
        body = node.child_by_field_name("body")
        if header_has_error(node, (body,)):
            continue
        name_node = node.child_by_field_name("name")
        tname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
        if not tname:
            continue
        kind = node.type.removesuffix("_declaration")
        qual_type = f"{active_qual}{tname}"
        sigs[f"{kind} {qual_type}"] = normalize_slice_without_nodes(node, (body,), source_bytes)
        if body is None:
            continue

        child_in_iface = node.type == "interface_declaration"
        body_members: list[Any] = []
        for child in body.named_children:
            if child.type == "enum_constant":
                if not header_has_error(child):
                    cname_node = child.child_by_field_name("name")
                    cname = (
                        normalize_node_text(cname_node, source_bytes)
                        if cname_node is not None
                        else ""
                    )
                    if cname:
                        sigs[f"enum_const {qual_type}.{cname}"] = cname
            elif child.type == "enum_body_declarations":
                body_members.extend(child.named_children)
            else:
                body_members.append(child)

        for member in body_members:
            if member.type in (*type_nodes, "delegate_declaration"):
                _walk_cs_nodes(
                    (member,), f"{qual_type}.", source_bytes, sigs, in_interface=child_in_iface
                )
                continue
            m_mods = _cs_modifiers(member, source_bytes)
            is_pub = (
                ("private" not in m_mods and "internal" not in m_mods)
                if child_in_iface
                else ("public" in m_mods)
            )
            if not is_pub:
                continue
            if member.type == "constructor_declaration":
                mbody = member.child_by_field_name("body")
                if header_has_error(member, (mbody,)):
                    continue
                ptypes = _cs_param_types(member.child_by_field_name("parameters"), source_bytes)
                sigs[f"constructor {qual_type}({ptypes})"] = normalize_slice_without_nodes(
                    member, (mbody,), source_bytes
                )
            elif member.type == "method_declaration":
                mbody = member.child_by_field_name("body")
                if header_has_error(member, (mbody,)):
                    continue
                mname_node = member.child_by_field_name("name")
                mname = (
                    normalize_node_text(mname_node, source_bytes)
                    if mname_node is not None
                    else ""
                )
                ptypes = _cs_param_types(member.child_by_field_name("parameters"), source_bytes)
                if mname:
                    sigs[f"method {qual_type}.{mname}({ptypes})"] = normalize_slice_without_nodes(
                        member, (mbody,), source_bytes
                    )
            elif member.type == "property_declaration":
                acc_list = member.child_by_field_name("accessors")
                expr_clause = _child_by_type(member, "arrow_expression_clause")
                eq_clause = _child_by_type(member, "equals_value_clause")
                excluded_prop = (acc_list, expr_clause, eq_clause)
                if header_has_error(member, excluded_prop):
                    continue
                pname_node = member.child_by_field_name("name")
                pname = (
                    normalize_node_text(pname_node, source_bytes)
                    if pname_node is not None
                    else ""
                )
                acc_names = ""
                if acc_list is not None:
                    pub_accs: list[str] = []
                    for acc in _children_by_type(acc_list, "accessor_declaration"):
                        acc_mods = _cs_modifiers(acc, source_bytes)
                        if acc_mods & {"private", "protected", "internal"}:
                            continue
                        acc_name_node = acc.child_by_field_name("name")
                        if acc_name_node is not None:
                            pub_accs.append(normalize_node_text(acc_name_node, source_bytes))
                        else:
                            # Fallback: last non-body, non-modifier token (get/set/init)
                            tokens = normalize_slice_without_nodes(
                                acc, (acc.child_by_field_name("body"),), source_bytes
                            ).split()
                            if tokens:
                                pub_accs.append(tokens[-1].rstrip(";"))
                    acc_names = " ".join(sorted(pub_accs))
                if pname:
                    header_txt = normalize_slice_without_nodes(member, excluded_prop, source_bytes)
                    if acc_list is not None:
                        sigs[f"property {qual_type}.{pname}"] = (
                            f"{header_txt} {{ {acc_names} }}".strip()
                        )
                    else:
                        sigs[f"property {qual_type}.{pname}"] = header_txt
            elif member.type in ("field_declaration", "event_field_declaration", "event_declaration"):
                if header_has_error(member):
                    continue
                vdecl_container = _child_by_type(member, "variable_declaration")
                if vdecl_container is not None:
                    for vdecl in _children_by_type(vdecl_container, "variable_declarator"):
                        fname_node = vdecl.child_by_field_name("name")
                        fname = (
                            normalize_node_text(fname_node, source_bytes)
                            if fname_node is not None
                            else ""
                        )
                        if fname:
                            kind_lbl = "event" if "event" in member.type else "field"
                            sigs[f"{kind_lbl} {qual_type}.{fname}"] = normalize_node_text(
                                member, source_bytes
                            )
                else:
                    ename_node = member.child_by_field_name("name")
                    ename = (
                        normalize_node_text(ename_node, source_bytes)
                        if ename_node is not None
                        else ""
                    )
                    if ename:
                        sigs[f"event {qual_type}.{ename}"] = normalize_node_text(
                            member, source_bytes
                        )


def extract_csharp_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    _walk_cs_nodes(root.named_children, "", source_bytes, sigs)
    return sigs


# ---------------------------------------------------------------------------
# PHP
# ---------------------------------------------------------------------------


def _php_visibility(node: Any, source_bytes: bytes) -> str:
    vis = _child_by_type(node, "visibility_modifier")
    if vis is None:
        return "public"  # PHP default visibility is public
    return normalize_node_text(vis, source_bytes)


def _walk_php_nodes(
    nodes: Sequence[Any],
    ns_prefix: str,
    source_bytes: bytes,
    sigs: dict[str, str],
) -> None:
    active_ns = ns_prefix
    for node in nodes:
        if node.type == "namespace_definition":
            name_node = node.child_by_field_name("name")
            ns = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            body = node.child_by_field_name("body")
            if body is not None:
                _walk_php_nodes(body.named_children, f"{ns}\\" if ns else "", source_bytes, sigs)
            elif ns:
                active_ns = f"{ns}\\"
            continue

        if node.type == "function_definition":
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            fname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if fname and not fname.startswith("_"):
                sigs[f"function {active_ns}{fname}"] = normalize_slice_without_nodes(
                    node, (body,), source_bytes
                )

        elif node.type in (
            "class_declaration",
            "interface_declaration",
            "trait_declaration",
            "enum_declaration",
        ):
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            cname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if not cname:
                continue
            kind = node.type.removesuffix("_declaration")
            qual_cls = f"{active_ns}{cname}"
            sigs[f"{kind} {qual_cls}"] = normalize_slice_without_nodes(node, (body,), source_bytes)
            if body is None:
                continue
            for member in body.named_children:
                if member.type == "method_declaration":
                    vis = _php_visibility(member, source_bytes)
                    if vis in ("private", "protected"):
                        continue
                    mbody = member.child_by_field_name("body")
                    if header_has_error(member, (mbody,)):
                        continue
                    mname_node = member.child_by_field_name("name")
                    mname = (
                        normalize_node_text(mname_node, source_bytes)
                        if mname_node is not None
                        else ""
                    )
                    if mname and (mname == "__construct" or not mname.startswith("_")):
                        sigs[f"method {qual_cls}.{mname}"] = normalize_slice_without_nodes(
                            member, (mbody,), source_bytes
                        )
                elif member.type == "property_declaration":
                    vis = _php_visibility(member, source_bytes)
                    if vis != "public" or header_has_error(member):
                        continue
                    for prop in _children_by_type(member, "property_element"):
                        pname_node = prop.child_by_field_name("name")
                        pname = (
                            normalize_node_text(pname_node, source_bytes)
                            if pname_node is not None
                            else ""
                        )
                        if pname:
                            sigs[f"property {qual_cls}.{pname}"] = normalize_node_text(
                                member, source_bytes
                            )
                elif member.type == "const_declaration":
                    vis = _php_visibility(member, source_bytes)
                    if vis in ("private", "protected") or header_has_error(member):
                        continue
                    for c_el in _children_by_type(member, "const_element"):
                        cname_node = _child_by_type(c_el, "name")
                        const_name = (
                            normalize_node_text(cname_node, source_bytes)
                            if cname_node is not None
                            else ""
                        )
                        if const_name:
                            sigs[f"const {qual_cls}.{const_name}"] = normalize_node_text(
                                c_el, source_bytes
                            )


def extract_php_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    _walk_php_nodes(root.named_children, "", source_bytes, sigs)
    return sigs


# ---------------------------------------------------------------------------
# Ruby
# ---------------------------------------------------------------------------


def _ruby_symbol_names(arg_list: Any, source_bytes: bytes) -> list[str]:
    if arg_list is None:
        return []
    names: list[str] = []
    for child in arg_list.named_children:
        if child.type == "simple_symbol":
            names.append(normalize_node_text(child, source_bytes).lstrip(":"))
        elif child.type in ("string", "string_content"):
            names.append(normalize_node_text(child, source_bytes).strip("\"'"))
    return names


def _walk_ruby_body(
    nodes: Sequence[Any],
    qual: str,
    source_bytes: bytes,
    sigs: dict[str, str],
    *,
    in_class_or_mod: bool = False,
    singleton_scope: bool = False,
) -> None:
    visibility = "public"
    excluded_instance: set[str] = set()
    excluded_singleton: set[str] = set()

    for node in nodes:
        if in_class_or_mod and node.type == "identifier":
            ident = normalize_node_text(node, source_bytes)
            if ident in ("public", "private", "protected", "module_function"):
                visibility = ident
            continue

        if in_class_or_mod and node.type == "call":
            meth_node = node.child_by_field_name("method")
            m_txt = normalize_node_text(meth_node, source_bytes) if meth_node is not None else ""
            args = node.child_by_field_name("arguments")

            if m_txt in ("private", "protected") and args is not None:
                # Could be `private :foo` or `private def foo; end`
                for sym in _ruby_symbol_names(args, source_bytes):
                    excluded_instance.add(sym)
                    sigs.pop(f"def {qual}{sym}", None)
                continue

            if m_txt == "private_class_method" and args is not None:
                for sym in _ruby_symbol_names(args, source_bytes):
                    excluded_singleton.add(sym)
                    sigs.pop(f"def {qual}self.{sym}", None)
                continue

            if m_txt == "module_function" and args is not None:
                for sym in _ruby_symbol_names(args, source_bytes):
                    inst_key = f"def {qual}{sym}"
                    inst_val = sigs.pop(inst_key, None)
                    excluded_instance.add(sym)
                    if inst_val is not None and not sym.startswith("_"):
                        sigs[f"def {qual}self.{sym}"] = inst_val
                continue

            if m_txt in ("attr_reader", "attr_writer", "attr_accessor") and args is not None:
                if visibility == "public":
                    for sym in _ruby_symbol_names(args, source_bytes):
                        if not sym.startswith("_"):
                            sigs[f"attr {qual}{sym}"] = m_txt
                continue

        if node.type == "method":
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            mname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if not mname:
                continue
            if mname != "initialize" and mname.startswith("_"):
                continue
            if visibility == "module_function":
                if mname not in excluded_singleton:
                    sigs[f"def {qual}self.{mname}"] = normalize_slice_without_nodes(
                        node, (body,), source_bytes
                    )
                continue
            if visibility != "public":
                continue
            if singleton_scope:
                if mname in excluded_singleton:
                    continue
                sigs[f"def {qual}self.{mname}"] = normalize_slice_without_nodes(
                    node, (body,), source_bytes
                )
            else:
                if mname in excluded_instance:
                    continue
                sigs[f"def {qual}{mname}"] = normalize_slice_without_nodes(
                    node, (body,), source_bytes
                )

        elif node.type == "singleton_method":
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            mname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if not mname or mname.startswith("_") or visibility != "public":
                continue
            if mname in excluded_singleton:
                continue
            sigs[f"def {qual}self.{mname}"] = normalize_slice_without_nodes(
                node, (body,), source_bytes
            )

        elif node.type == "singleton_class":
            body = node.child_by_field_name("body")
            if body is not None:
                _walk_ruby_body(
                    body.named_children,
                    qual,
                    source_bytes,
                    sigs,
                    in_class_or_mod=True,
                    singleton_scope=True,
                )

        elif node.type in ("module", "class"):
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            cname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if not cname:
                continue
            qual_cls = f"{qual}{cname}"
            sigs[f"{node.type} {qual_cls}"] = normalize_slice_without_nodes(
                node, (body,), source_bytes
            )
            if body is not None:
                _walk_ruby_body(
                    body.named_children,
                    f"{qual_cls}.",
                    source_bytes,
                    sigs,
                    in_class_or_mod=True,
                )


def extract_ruby_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    _walk_ruby_body(root.named_children, "", source_bytes, sigs, in_class_or_mod=False)
    return sigs


# ---------------------------------------------------------------------------
# Bash
# ---------------------------------------------------------------------------


def extract_bash_signatures(root: Any, source_bytes: bytes) -> dict[str, str]:
    sigs: dict[str, str] = {}
    for node in root.named_children:
        if node.type == "function_definition":
            body = node.child_by_field_name("body")
            if header_has_error(node, (body,)):
                continue
            name_node = node.child_by_field_name("name")
            fname = normalize_node_text(name_node, source_bytes) if name_node is not None else ""
            if fname and not fname.startswith("_"):
                sigs[f"function {fname}"] = f"function {fname}"

        elif node.type == "declaration_command":
            if header_has_error(node) or not node.children:
                continue
            cmd = node_text(node.children[0], source_bytes).strip()
            flags: list[str] = []
            for child in node.children[1:]:
                if child.type != "word":
                    break
                tok = node_text(child, source_bytes).strip()
                if tok == "--" or not tok.startswith("-"):
                    break
                flags.append(tok)
            is_export_fn = cmd == "export" and any("f" in fl for fl in flags)
            is_export_var = (cmd == "export" and not is_export_fn) or (
                cmd == "declare" and any("x" in fl for fl in flags)
            )
            if not is_export_fn and not is_export_var:
                continue
            for child in node.named_children:
                if child.type == "variable_assignment":
                    vname_node = child.child_by_field_name("name")
                    vname = (
                        normalize_node_text(vname_node, source_bytes)
                        if vname_node is not None
                        else ""
                    )
                    if vname and not vname.startswith("_") and is_export_var:
                        sigs[f"export {vname}"] = f"export {vname}"
                elif child.type in ("variable_name", "word"):
                    tok = normalize_node_text(child, source_bytes)
                    if tok.startswith("-"):
                        continue
                    if tok and not tok.startswith("_"):
                        if is_export_fn:
                            sigs[f"export -f {tok}"] = f"export -f {tok}"
                        elif is_export_var:
                            sigs[f"export {tok}"] = f"export {tok}"
    return sigs


# ---------------------------------------------------------------------------
# Registry spec table for all 10 POLYGLOT_LANGUAGES
# ---------------------------------------------------------------------------

POLYGLOT_LANGUAGE_SPECS: tuple[PolyglotLanguageSpec, ...] = (
    PolyglotLanguageSpec(
        language="bash",
        module_name="tree_sitter_bash",
        factory_names=("language",),
        extensions=(".sh", ".bash"),
        extractor=extract_bash_signatures,
    ),
    PolyglotLanguageSpec(
        language="c_sharp",
        module_name="tree_sitter_c_sharp",
        factory_names=("language",),
        extensions=(".cs",),
        extractor=extract_csharp_signatures,
    ),
    PolyglotLanguageSpec(
        language="go",
        module_name="tree_sitter_go",
        factory_names=("language",),
        extensions=(".go",),
        extractor=extract_go_signatures,
    ),
    PolyglotLanguageSpec(
        language="java",
        module_name="tree_sitter_java",
        factory_names=("language",),
        extensions=(".java",),
        extractor=extract_java_signatures,
    ),
    PolyglotLanguageSpec(
        language="javascript",
        module_name="tree_sitter_javascript",
        factory_names=("language",),
        extensions=(".js", ".mjs", ".cjs", ".jsx"),
        extractor=extract_javascript_signatures,
    ),
    PolyglotLanguageSpec(
        language="php",
        module_name="tree_sitter_php",
        factory_names=("language_php", "language"),
        extensions=(".php",),
        extractor=extract_php_signatures,
    ),
    PolyglotLanguageSpec(
        language="ruby",
        module_name="tree_sitter_ruby",
        factory_names=("language",),
        extensions=(".rb",),
        extractor=extract_ruby_signatures,
    ),
    PolyglotLanguageSpec(
        language="rust",
        module_name="tree_sitter_rust",
        factory_names=("language",),
        extensions=(".rs",),
        extractor=extract_rust_signatures,
    ),
    PolyglotLanguageSpec(
        language="tsx",
        module_name="tree_sitter_typescript",
        factory_names=("language_tsx",),
        extensions=(".tsx",),
        extractor=extract_typescript_signatures,
    ),
    PolyglotLanguageSpec(
        language="typescript",
        module_name="tree_sitter_typescript",
        factory_names=("language_typescript",),
        extensions=(".ts", ".mts", ".cts"),
        extractor=extract_typescript_signatures,
    ),
)
