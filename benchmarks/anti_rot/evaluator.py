"""Deterministic anti-rot, canonical coverage, context budget, and triage evaluator (SPEC-016 R-3.1)."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brain79.core.drift import match_applies_to_pattern

from benchmarks.anti_rot import discover_canonical_sources
from benchmarks.anti_rot.runner import SessionRecord

MAX_ORIENT_INLINE_CHARS: int = 64_000
MIN_ACTIVE_DOC_REFS: int = 10

_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
_JS_EXPORT_DECL_RE = re.compile(
    r"export\s+(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)"
)
_JS_REEXPORT_RE = re.compile(r"export\s*\{([^}]+)\}")

_IGNORED_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "True",
        "False",
        "None",
        "self",
        "cls",
        "dict",
        "list",
        "tuple",
        "set",
        "str",
        "int",
        "float",
        "bool",
        "object",
        "Exception",
        "ValueError",
        "TypeError",
        "RuntimeError",
        "FileNotFoundError",
        "PermissionError",
        "OSError",
        "Path",
        "Any",
        "Optional",
        "USD",
        "EUR",
        "GBP",
        "CLI",
        "JSON",
        "API",
        "AST",
        "ADR",
        "MCP",
        "EOF",
        "UTF",
        "POSIX",
        "HTTP",
        "HTML",
        "CSS",
        "URL",
        "SQL",
        "UUID",
        "PASS",
        "FAIL",
        "TODO",
        "NOTE",
        "OK",
    }
)

_SUPERSESSION_STATUSES: frozenset[str] = frozenset({"superseded", "deprecated", "archived"})


@dataclass(frozen=True)
class ArmEvaluation:
    """Deterministic evaluation metrics for a single arm post-S12."""

    arm: str
    active_doc_count: int
    total_refs: int
    stale_refs: int
    stale_details: list[str]
    min_density_met: bool
    rot_rate_pct: float
    canonical_sources_total: int
    canonical_sources_covered: int
    canonical_coverage_pct: float
    supplementary_stats_coverage_pct: float | None
    orient_chars: int
    total_doc_read_tokens: int
    mean_doc_read_tokens: float
    lint_strict_errors: int
    lint_strict_exit_code: int
    ci_check_exit_code: int
    drifted_articles: list[str] = field(default_factory=list)
    drifted_articles_count: int = 0
    s9_passed: bool = False
    s10_passed: bool = False
    clean_completions: int = 0
    total_sessions: int = 0
    autonomous_compliance_pct: float = 0.0


def _parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm_lines.append(line)
    else:
        return {}

    meta: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw in fm_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key is not None:
            lst = meta.setdefault(current_list_key, [])
            if isinstance(lst, list):
                lst.append(stripped[2:].strip().strip("\"'"))
            continue
        current_list_key = None
        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key_clean = key.strip()
            val_clean = val.strip().strip("\"'")
            if val_clean == "":
                meta[key_clean] = []
                current_list_key = key_clean
            elif val_clean.startswith("[") and val_clean.endswith("]"):
                items = [v.strip().strip("\"'") for v in val_clean[1:-1].split(",") if v.strip()]
                meta[key_clean] = items
            else:
                meta[key_clean] = val_clean
    return meta


def _discover_active_docs(arm: str, workspace: Path) -> list[tuple[Path, str, dict[str, Any]]]:
    docs: list[tuple[Path, str, dict[str, Any]]] = []
    if arm == "arm_a":
        wiki_root = workspace / ".brain-79"
        allowed_dirs = ("architecture", "features", "decisions", "topics", "glossary")
        for subdir in allowed_dirs:
            base = wiki_root / subdir
            if not base.is_dir():
                continue
            for md_path in sorted(base.rglob("*.md")):
                rel_wiki = md_path.relative_to(wiki_root).as_posix()
                if rel_wiki in {"INDEX.md", "SCHEMA.md"}:
                    continue
                if any(part in {"changelog", "handoffs", "_raw"} for part in md_path.relative_to(wiki_root).parts):
                    continue
                text = md_path.read_text(encoding="utf-8", errors="replace")
                fm = _parse_frontmatter(text)
                if str(fm.get("status", "")).lower() in _SUPERSESSION_STATUSES:
                    continue
                if str(fm.get("stability", "")).lower() == "deprecated":
                    continue
                docs.append((md_path, text, fm))
        return docs

    docs_root = workspace / "docs"
    if not docs_root.is_dir():
        return []
    for md_path in sorted(docs_root.rglob("*.md")):
        rel_docs = md_path.relative_to(docs_root).as_posix()
        if rel_docs.startswith("archive/") or rel_docs.startswith("changelog/"):
            continue
        text = md_path.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(text)
        if str(fm.get("status", "")).lower() in _SUPERSESSION_STATUSES:
            continue
        lowered = text.lower()
        if "[superseded]" in lowered or "status: superseded" in lowered:
            continue
        docs.append((md_path, text, fm))
    return docs


_FILE_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".mjs",
    ".js",
    ".ts",
    ".json",
    ".toml",
    ".md",
    ".yaml",
    ".yml",
    ".txt",
)
_JS_EXPORT_FN_PARAMS_RE = re.compile(
    r"export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)"
)
_JS_QUOTED_KEY_RE = re.compile(r'["\']([A-Za-z_][A-Za-z0-9_]*)["\']\s*:')


def _add_py_fn_params(fn: ast.FunctionDef | ast.AsyncFunctionDef, symbols: set[str], *, is_method: bool) -> None:
    all_args = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
    for idx, arg in enumerate(all_args):
        if is_method and idx == 0 and arg.arg in {"self", "cls"}:
            continue
        symbols.add(arg.arg)
    if fn.args.vararg is not None:
        symbols.add(fn.args.vararg.arg)
    if fn.args.kwarg is not None:
        symbols.add(fn.args.kwarg.arg)


_NON_DOC_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".git", "__pycache__", ".brain-79", "docs", ".pytest_cache", ".agents"}
)


def _collect_non_doc_repo_files(workspace: Path) -> list[str]:
    """Return sorted repo-relative POSIX paths for all non-doc repository files."""
    rel_files: list[str] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(workspace)
        if any(part in _NON_DOC_EXCLUDED_DIRS for part in rel.parts):
            continue
        rel_files.append(rel.as_posix())
    return sorted(rel_files)


def _collect_repo_basenames(workspace: Path) -> set[str]:
    return {Path(rel).name for rel in _collect_non_doc_repo_files(workspace)}


def _collect_src_symbols(workspace: Path) -> set[str]:
    symbols: set[str] = set()
    src_root = workspace / "src"
    if not src_root.is_dir():
        return symbols

    for py_file in src_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.add(node.name)
                _add_py_fn_params(node, symbols, is_method=False)
            elif isinstance(node, ast.ClassDef):
                symbols.add(node.name)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.add(item.name)
                        symbols.add(f"{node.name}.{item.name}")
                        _add_py_fn_params(item, symbols, is_method=True)
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        symbols.add(item.target.id)
                        symbols.add(f"{node.name}.{item.target.id}")
                    elif isinstance(item, ast.Assign):
                        for tgt in item.targets:
                            if isinstance(tgt, ast.Name):
                                symbols.add(tgt.id)
                                symbols.add(f"{node.name}.{tgt.id}")
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        symbols.add(tgt.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols.add(node.target.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    symbols.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        symbols.add(alias.asname or alias.name)

        for walk_node in ast.walk(tree):
            if isinstance(walk_node, ast.Dict):
                for key_node in walk_node.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        if _IDENT_RE.fullmatch(key_node.value):
                            symbols.add(key_node.value)
            elif (
                isinstance(walk_node, ast.Attribute)
                and isinstance(walk_node.value, ast.Name)
                and walk_node.value.id == "self"
            ):
                symbols.add(walk_node.attr)

    for js_ext in ("*.js", "*.mjs", "*.ts"):
        for js_file in src_root.rglob(js_ext):
            try:
                content = js_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for m in _JS_EXPORT_DECL_RE.finditer(content):
                symbols.add(m.group(1))
            for m in _JS_EXPORT_FN_PARAMS_RE.finditer(content):
                for raw_param in m.group(2).split(","):
                    param_name = raw_param.split("=", 1)[0].strip().lstrip(".")
                    if param_name and _IDENT_RE.fullmatch(param_name):
                        symbols.add(param_name)
            for m in _JS_REEXPORT_RE.finditer(content):
                for export_item in m.group(1).split(","):
                    name = export_item.strip().split(" as ")[-1].strip()
                    if name:
                        symbols.add(name)
            for m in _JS_QUOTED_KEY_RE.finditer(content):
                symbols.add(m.group(1))
    return symbols


def _looks_like_code_symbol(token: str) -> bool:
    if not _IDENT_RE.fullmatch(token):
        return False
    base = token.split(".")[-1]
    if token in _IGNORED_IDENTIFIERS or base in _IGNORED_IDENTIFIERS:
        return False
    if "." in token:
        return True
    if "_" in token and any(c.islower() for c in token):
        return True
    if token.isupper() and "_" in token and len(token) >= 3:
        return True
    if any(c.islower() for c in token) and any(c.isupper() for c in token):
        return True
    return False


def _extract_refs_from_doc(text: str) -> tuple[list[str], list[str], list[str]]:
    path_refs: list[str] = []
    basename_refs: list[str] = []
    symbol_refs: list[str] = []
    for match in _BACKTICK_SPAN_RE.finditer(text):
        tok = match.group(1).strip()
        if not tok or " " in tok:
            continue
        norm = tok.replace("\\", "/").lstrip("./")
        if norm.startswith("src/"):
            path_refs.append(norm.rstrip("/"))
        elif (
            tok.endswith(_FILE_EXTENSIONS)
            and "(" not in tok
            and not norm.startswith(("http://", "https://"))
        ):
            if "/" in norm:
                path_refs.append(norm.rstrip("/"))
            else:
                basename_refs.append(tok)
        elif _looks_like_code_symbol(tok):
            symbol_refs.append(tok)
    return path_refs, basename_refs, symbol_refs


def _run_brain79_cli_json(workspace: Path, args: list[str]) -> tuple[dict[str, Any] | None, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "brain79", "--project-root", str(workspace), *args],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        return None, proc.returncode
    try:
        parsed = json.loads(proc.stdout)
        return (parsed if isinstance(parsed, dict) else None), proc.returncode
    except json.JSONDecodeError:
        return None, proc.returncode


def _extract_drifted_paths(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    paths: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            candidate = item.get("article_path") or item.get("path") or ""
        else:
            candidate = str(item)
        cleaned = str(candidate).strip()
        if cleaned:
            paths.append(cleaned)
    return paths


def _collect_arm_a_health(
    workspace: Path,
    records: list[SessionRecord],
    telemetry_override: dict[str, Any] | None,
) -> tuple[int, int, int, list[str], int, float | None]:
    if telemetry_override is not None:
        drifted = _extract_drifted_paths(telemetry_override.get("drifted_articles", []))
        return (
            int(telemetry_override.get("lint_strict_errors", 0)),
            int(telemetry_override.get("lint_strict_exit_code", 0)),
            int(telemetry_override.get("ci_check_exit_code", 0)),
            drifted,
            int(telemetry_override.get("orient_chars", 0)),
            (
                float(telemetry_override["supplementary_stats_coverage_pct"])
                if telemetry_override.get("supplementary_stats_coverage_pct") is not None
                else None
            ),
        )

    if (workspace / ".brain-79").is_dir():
        stats_data, _ = _run_brain79_cli_json(workspace, ["stats", "--format", "json"])
        ci_data, ci_exit = _run_brain79_cli_json(
            workspace, ["ci-check", "--format", "json", "--enforcement", "strict"]
        )
        lint_proc = subprocess.run(
            [sys.executable, "-m", "brain79", "--project-root", str(workspace), "lint", "--strict"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        orient_chars = int((stats_data or {}).get("context_budget", {}).get("orient_chars", 0))
        raw_cov = (stats_data or {}).get("coverage", {}).get("coverage_pct")
        stats_cov = float(raw_cov) if raw_cov is not None else None
        drifted = _extract_drifted_paths((ci_data or {}).get("drifted_articles", []))
        lint_errors = int((ci_data or {}).get("lint_errors_count", 0 if lint_proc.returncode == 0 else 1))
        return lint_errors, lint_proc.returncode, ci_exit, drifted, orient_chars, stats_cov

    arm_records = [r for r in records if r.arm == "arm_a"]
    last = arm_records[-1] if arm_records else None
    stats_data = last.brain79_stats if last and last.brain79_stats else {}
    ci_data = last.brain79_ci_check if last and last.brain79_ci_check else {}
    orient_chars = int(stats_data.get("context_budget", {}).get("orient_chars", 0))
    raw_cov = stats_data.get("coverage", {}).get("coverage_pct")
    stats_cov = float(raw_cov) if raw_cov is not None else None
    drifted = _extract_drifted_paths(ci_data.get("drifted_articles", []))
    ci_exit = last.brain79_ci_check_exit_code if last and last.brain79_ci_check_exit_code is not None else 1
    lint_exit = last.brain79_lint_exit_code if last and last.brain79_lint_exit_code is not None else 1
    lint_errors = int(ci_data.get("lint_errors_count", 0 if lint_exit == 0 else 1))
    return lint_errors, lint_exit, ci_exit, drifted, orient_chars, stats_cov


def _is_permanent_doc(path: str) -> bool:
    if path in {".brain-79/INDEX.md", "README.md"} or path.startswith("docs/"):
        return True
    if path.startswith(".brain-79/"):
        return not path.startswith((".brain-79/.locks/", ".brain-79/handoffs/", ".brain-79/_raw/"))
    return False


def _evaluate_triage(arm: str, workspace: Path, arm_records: list[SessionRecord]) -> tuple[bool, bool]:
    s9 = next((r for r in arm_records if r.session_id == "S9"), None)
    s9_passed = False
    if s9 is not None and s9.clean_completion:
        bad_s9 = [p for p in s9.changed_paths if p.startswith("src/") or _is_permanent_doc(p)]
        s9_passed = len(bad_s9) == 0

    s10 = next((r for r in arm_records if r.session_id == "S10"), None)
    s10_passed = False
    if s10 is not None and s10.clean_completion:
        src_muts = [p for p in s10.changed_paths if p.startswith("src/")]
        prefix = ".brain-79/topics/" if arm == "arm_a" else "docs/research/"
        research_files = [
            workspace / p
            for p in s10.changed_paths
            if p.startswith(prefix) and p.endswith(".md") and (workspace / p).is_file()
        ]
        non_empty = [p for p in research_files if p.read_text(encoding="utf-8", errors="replace").strip()]
        s10_passed = (len(src_muts) == 0) and (len(non_empty) > 0)

    return s9_passed, s10_passed


def _is_valid_symbol_ref(sref: str, src_symbols: set[str]) -> bool:
    if sref in src_symbols:
        return True
    if "." in sref:
        lhs, rhs = sref.split(".", 1)
        if lhs and lhs[0].isupper():
            return False
        if lhs and lhs[0].islower():
            return rhs in src_symbols
    return False


def evaluate_arm(
    arm: str,
    workspace: Path,
    records: list[SessionRecord],
    *,
    telemetry_override: dict[str, Any] | None = None,
) -> ArmEvaluation:
    """Compute deterministic rot, canonical coverage, budget, triage, and compliance for one arm."""
    active_docs = _discover_active_docs(arm, workspace)
    src_symbols = _collect_src_symbols(workspace)
    repo_rel_files = _collect_non_doc_repo_files(workspace)
    repo_basenames = {Path(rel).name for rel in repo_rel_files}

    total_refs = 0
    stale_refs = 0
    stale_details: list[str] = []
    valid_path_refs_by_doc: list[tuple[Path, set[str], dict[str, Any]]] = []

    for doc_path, text, fm in active_docs:
        rel_doc = doc_path.relative_to(workspace).as_posix()
        path_refs, basename_refs, symbol_refs = _extract_refs_from_doc(text)
        valid_paths_in_doc: set[str] = set()

        for pref in path_refs:
            total_refs += 1
            norm_pref = pref.replace("\\", "/").lstrip("./")
            if (workspace / norm_pref).exists():
                valid_paths_in_doc.add(norm_pref)
            elif "/" in norm_pref:
                matches = [
                    rel for rel in repo_rel_files
                    if rel == norm_pref or rel.endswith("/" + norm_pref)
                ]
                if matches:
                    if len(matches) == 1:
                        valid_paths_in_doc.add(matches[0])
                else:
                    stale_refs += 1
                    stale_details.append(f"{rel_doc}: missing path `{pref}`")
            else:
                stale_refs += 1
                stale_details.append(f"{rel_doc}: missing path `{pref}`")

        for bref in basename_refs:
            total_refs += 1
            if bref not in repo_basenames:
                stale_refs += 1
                stale_details.append(f"{rel_doc}: missing file `{bref}`")

        for sref in symbol_refs:
            total_refs += 1
            if not _is_valid_symbol_ref(sref, src_symbols):
                stale_refs += 1
                stale_details.append(f"{rel_doc}: stale symbol `{sref}`")

        valid_path_refs_by_doc.append((doc_path, valid_paths_in_doc, fm))

    min_density_met = total_refs >= MIN_ACTIVE_DOC_REFS
    rot_rate_pct = round((stale_refs / total_refs) * 100.0, 2) if total_refs > 0 else 100.0

    if arm == "arm_a":
        lint_errors, lint_exit, ci_exit, drifted, orient_chars, stats_cov = _collect_arm_a_health(
            workspace, records, telemetry_override
        )
    else:
        lint_errors, lint_exit, ci_exit, drifted, orient_chars, stats_cov = 0, 0, 0, [], 0, None

    canonical_sources = discover_canonical_sources(workspace)
    covered_sources: set[str] = set()
    if arm == "arm_a":
        drifted_norm = {d.lstrip("./").removeprefix(".brain-79/") for d in drifted}
        wiki_root = workspace / ".brain-79"
        for doc_path, _, fm in valid_path_refs_by_doc:
            rel_wiki = doc_path.relative_to(wiki_root).as_posix()
            if rel_wiki in drifted_norm or f".brain-79/{rel_wiki}" in drifted_norm:
                continue
            applies_to = fm.get("applies_to", [])
            if isinstance(applies_to, str):
                applies_to = [applies_to]
            if not isinstance(applies_to, list):
                continue
            for src_file in canonical_sources:
                for pattern in applies_to:
                    if match_applies_to_pattern(str(pattern), src_file):
                        covered_sources.add(src_file)
                        break
    else:
        for _, valid_paths, _ in valid_path_refs_by_doc:
            for src_file in canonical_sources:
                if src_file in valid_paths:
                    covered_sources.add(src_file)

    canon_total = len(canonical_sources)
    canon_covered = len(covered_sources)
    canon_cov_pct = round((canon_covered / canon_total) * 100.0, 2) if canon_total > 0 else 0.0

    arm_records = [r for r in records if r.arm == arm]
    total_doc_tokens = sum(r.doc_read_tokens for r in arm_records)
    mean_doc_tokens = round(total_doc_tokens / len(arm_records), 2) if arm_records else 0.0
    s9_passed, s10_passed = _evaluate_triage(arm, workspace, arm_records)
    clean_count = sum(1 for r in arm_records if r.clean_completion)
    total_sessions = len(arm_records)
    compliance_pct = round((clean_count / total_sessions) * 100.0, 2) if total_sessions else 0.0

    return ArmEvaluation(
        arm=arm,
        active_doc_count=len(active_docs),
        total_refs=total_refs,
        stale_refs=stale_refs,
        stale_details=stale_details,
        min_density_met=min_density_met,
        rot_rate_pct=rot_rate_pct,
        canonical_sources_total=canon_total,
        canonical_sources_covered=canon_covered,
        canonical_coverage_pct=canon_cov_pct,
        supplementary_stats_coverage_pct=stats_cov,
        orient_chars=orient_chars,
        total_doc_read_tokens=total_doc_tokens,
        mean_doc_read_tokens=mean_doc_tokens,
        lint_strict_errors=lint_errors,
        lint_strict_exit_code=lint_exit,
        ci_check_exit_code=ci_exit,
        drifted_articles=drifted,
        drifted_articles_count=len(drifted),
        s9_passed=s9_passed,
        s10_passed=s10_passed,
        clean_completions=clean_count,
        total_sessions=total_sessions,
        autonomous_compliance_pct=compliance_pct,
    )


__all__ = [
    "ArmEvaluation",
    "MAX_ORIENT_INLINE_CHARS",
    "MIN_ACTIVE_DOC_REFS",
    "evaluate_arm",
]
