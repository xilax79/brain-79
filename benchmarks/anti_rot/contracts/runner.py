"""Deterministic AST and triage contract runner for SPEC-016."""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from benchmarks.anti_rot import resolve_git_bin
from benchmarks.anti_rot.contracts.specs import (
    SESSION_CONTRACTS,
    JsSymbolSpec,
    PySymbolSpec,
    SessionContractSpec,
)

_JS_EXPORT_FN_RE = re.compile(
    r"export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)"
)
_JS_REEXPORT_RE = re.compile(r"export\s*\{([^}]+)\}")


@dataclass(frozen=True)
class ContractResult:
    """Outcome of running a single session contract against a workspace."""

    session_id: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    checked_symbols: list[str] = field(default_factory=list)


def _git_changed_paths(workspace: Path) -> list[str]:
    """Return paths changed in HEAD vs HEAD~1, or working tree if uncommitted."""
    git_bin = resolve_git_bin()
    status_proc = subprocess.run(
        [git_bin, "status", "--porcelain"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    dirty: list[str] = []
    if status_proc.returncode == 0 and status_proc.stdout.strip():
        for line in status_proc.stdout.splitlines():
            if len(line) > 3:
                dirty.append(line[3:].strip().replace("\\", "/"))
        return dirty

    diff_proc = subprocess.run(
        [git_bin, "diff", "--name-only", "HEAD~1", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    if diff_proc.returncode == 0:
        return [p.strip().replace("\\", "/") for p in diff_proc.stdout.splitlines() if p.strip()]
    return []


def _extract_py_ast(file_path: Path) -> tuple[ast.Module | None, str | None]:
    try:
        source = file_path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file_path)), None
    except (OSError, SyntaxError) as exc:
        return None, f"{file_path.name}: failed to parse Python AST ({exc})"


def _find_py_function(
    tree: ast.Module, spec: PySymbolSpec
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    if spec.class_name is None:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == spec.symbol_name:
                return node
        return None

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == spec.class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == spec.symbol_name:
                    return item
    return None


def _py_param_names(fn: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> tuple[str, ...]:
    all_args = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
    names = [a.arg for a in all_args]
    if is_method and names and names[0] in {"self", "cls"}:
        names = names[1:]
    return tuple(names)


def _extract_py_constants(tree: ast.Module) -> dict[str, object]:
    constants: dict[str, object] = {}
    for node in tree.body:
        value_node: ast.expr | None = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value_node = node.value
        if value_node is None:
            continue
        for tgt in targets:
            if isinstance(tgt, ast.Name):
                try:
                    constants[tgt.id] = ast.literal_eval(value_node)
                except (ValueError, SyntaxError):
                    pass
    return constants


def _check_js_symbol(source: str, spec: JsSymbolSpec) -> str | None:
    for match in _JS_EXPORT_FN_RE.finditer(source):
        fn_name = match.group(1)
        if fn_name != spec.symbol_name:
            continue
        if not spec.params:
            return None
        raw_params = [p.strip() for p in match.group(2).split(",") if p.strip()]
        parsed_params = tuple(p.split("=", 1)[0].strip().lstrip(".") for p in raw_params)
        if parsed_params != spec.params:
            return (
                f"{spec.module_path}: JS symbol '{spec.symbol_name}' params {parsed_params} "
                f"!= expected {spec.params}"
            )
        return None

    for match in _JS_REEXPORT_RE.finditer(source):
        exported = [item.strip().split(" as ")[-1].strip() for item in match.group(1).split(",")]
        if spec.symbol_name in exported:
            return None

    return f"{spec.module_path}: missing exported JS symbol '{spec.symbol_name}'"


def _is_permanent_doc_path(path: str) -> bool:
    if path in {".brain-79/INDEX.md", "README.md"} or path.startswith("docs/"):
        return True
    if path.startswith(".brain-79/"):
        ephemeral_prefixes = (".brain-79/.locks/", ".brain-79/handoffs/", ".brain-79/_raw/")
        return not path.startswith(ephemeral_prefixes)
    return False


def _is_research_doc_path(path: str) -> bool:
    return path.endswith(".md") and (
        path.startswith(".brain-79/topics/") or path.startswith("docs/research/")
    )


def _check_triage(
    spec: SessionContractSpec,
    workspace: Path,
    changed_paths: list[str],
    errors: list[str],
) -> None:
    src_changes = [p for p in changed_paths if p.startswith("src/")]
    if spec.triage_mode == "type_a":
        if src_changes:
            errors.append(f"{spec.session_id} (Type A): forbidden src/ mutations: {src_changes}")
        doc_changes = [p for p in changed_paths if _is_permanent_doc_path(p)]
        if doc_changes:
            errors.append(f"{spec.session_id} (Type A): forbidden permanent doc mutations: {doc_changes}")
    elif spec.triage_mode == "type_b":
        if src_changes:
            errors.append(f"{spec.session_id} (Type B): forbidden src/ mutations: {src_changes}")
        changed_research = [
            workspace / p
            for p in changed_paths
            if _is_research_doc_path(p) and (workspace / p).is_file()
        ]
        non_empty = [p for p in changed_research if p.read_text(encoding="utf-8").strip()]
        if not non_empty:
            errors.append(
                f"{spec.session_id} (Type B): no non-empty research document created/updated in "
                ".brain-79/topics/ or docs/research/ during this session"
            )


def run_session_contract(
    session_id: str,
    workspace: Path,
    *,
    changed_paths: list[str] | None = None,
) -> ContractResult:
    """Verify the pinned contract for `session_id` against `workspace`."""
    if session_id not in SESSION_CONTRACTS:
        return ContractResult(
            session_id=session_id,
            passed=False,
            errors=[f"Unknown session contract ID: {session_id}"],
        )

    spec = SESSION_CONTRACTS[session_id]
    errors: list[str] = []
    checked: list[str] = []
    ast_cache: dict[str, ast.Module] = {}

    for rel in spec.required_files:
        if not (workspace / rel).is_file():
            errors.append(f"{session_id}: missing required file '{rel}'")

    for rel in spec.forbidden_files:
        if (workspace / rel).exists():
            errors.append(f"{session_id}: forbidden file still exists '{rel}'")

    for py_spec in spec.py_symbols:
        label = f"{py_spec.module_path}::{py_spec.class_name + '.' if py_spec.class_name else ''}{py_spec.symbol_name}"
        checked.append(label)
        target = workspace / py_spec.module_path
        if not target.is_file():
            continue
        if py_spec.module_path not in ast_cache:
            tree, err = _extract_py_ast(target)
            if err or tree is None:
                errors.append(err or f"{py_spec.module_path}: parse failure")
                continue
            ast_cache[py_spec.module_path] = tree
        tree = ast_cache[py_spec.module_path]
        fn = _find_py_function(tree, py_spec)
        if fn is None:
            errors.append(f"{session_id}: missing Python symbol '{label}'")
            continue
        actual_params = _py_param_names(fn, is_method=py_spec.class_name is not None)
        if py_spec.params and actual_params != py_spec.params:
            errors.append(
                f"{session_id}: '{label}' params {actual_params} != expected {py_spec.params}"
            )

    for rel, sym_name in spec.forbidden_py_symbols:
        target = workspace / rel
        if not target.is_file():
            continue
        if rel not in ast_cache:
            tree, err = _extract_py_ast(target)
            if err or tree is None:
                continue
            ast_cache[rel] = tree
        if _find_py_function(ast_cache[rel], PySymbolSpec(module_path=rel, symbol_name=sym_name)) is not None:
            errors.append(f"{session_id}: deprecated symbol '{sym_name}' still exists in '{rel}'")

    for rel, expected_consts in spec.py_constants.items():
        target = workspace / rel
        if not target.is_file():
            continue
        if rel not in ast_cache:
            tree, err = _extract_py_ast(target)
            if err or tree is None:
                errors.append(err or f"{rel}: parse failure")
                continue
            ast_cache[rel] = tree
        actual_consts = _extract_py_constants(ast_cache[rel])
        for name, expected_val in expected_consts.items():
            checked.append(f"{rel}::{name}")
            if name not in actual_consts:
                errors.append(f"{session_id}: missing constant '{name}' in '{rel}'")
            elif actual_consts[name] != expected_val:
                errors.append(
                    f"{session_id}: constant '{name}' in '{rel}' is {actual_consts[name]!r}, expected {expected_val!r}"
                )

    for js_spec in spec.js_symbols:
        checked.append(f"{js_spec.module_path}::{js_spec.symbol_name}")
        target = workspace / js_spec.module_path
        if not target.is_file():
            continue
        js_err = _check_js_symbol(target.read_text(encoding="utf-8"), js_spec)
        if js_err:
            errors.append(f"{session_id}: {js_err}")

    if spec.triage_mode in {"type_a", "type_b"}:
        effective_changes = changed_paths if changed_paths is not None else _git_changed_paths(workspace)
        _check_triage(spec, workspace, effective_changes, errors)

    return ContractResult(
        session_id=session_id,
        passed=len(errors) == 0,
        errors=errors,
        checked_symbols=checked,
    )
