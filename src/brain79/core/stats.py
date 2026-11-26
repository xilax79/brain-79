"""Read-only context budget and governance telemetry engine for brain-79."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import yaml

from brain79.config import get_project_root, project_context
from brain79.core.ast_guards import get_ast_guard_capabilities, get_inspector_for_path
from brain79.core.drift import (
    WorkspaceIndex,
    detect_all_drift,
    match_applies_to_pattern,
)
from brain79.core.frontmatter import (
    INACTIVE_STATUSES,
    PRE_IMPLEMENTATION_STATUSES,
    FrontmatterError,
    ValidationError,
    load_active_schema,
    parse_frontmatter,
)
from brain79.core.git_ops import GitSessionCache
from brain79.core.orient import MAX_ORIENT_INLINE_CHARS, orient
from brain79.core.locks import rel_posix
from brain79.core.validation import (
    MAX_ARTICLE_BYTES,
    MAX_ARTICLE_LINES,
    get_index_max_lines,
)

_IMMUTABLE_ARTICLE_TYPES: frozenset[str] = frozenset({"decision", "changelog"})
_INACTIVE_STABILITY: frozenset[str] = frozenset({"archived", "deprecated"})
_INSTRUCTION_FILE_CANDIDATES: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    ".cursor/rules/brain79.mdc",
    ".github/copilot-instructions.md",
)


def estimate_tokens(text: str) -> int:
    """Estimate token count using deterministic LF-normalized chars/4 ceiling heuristic."""
    lf_text = text.replace("\r\n", "\n")
    if not lf_text:
        return 0
    return math.ceil(len(lf_text) / 4)


@dataclass(frozen=True)
class StatsReport:
    """Structured telemetry report covering wiki inventory, context budget, coverage, and AST guards."""

    wiki: dict[str, Any]
    context_budget: dict[str, Any]
    coverage: dict[str, Any]
    ast_guards: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return deterministic, JSON-serializable report dictionary."""
        return {
            "wiki": dict(self.wiki),
            "context_budget": dict(self.context_budget),
            "coverage": dict(self.coverage),
            "ast_guards": dict(self.ast_guards),
        }

    def format_text(self) -> str:
        """Render a concise human-readable statistics report."""
        w = self.wiki
        cb = self.context_budget
        cov = self.coverage
        ast_g = self.ast_guards

        lines: list[str] = [
            "# Brain-79 — Context and Governance Statistics",
            "",
            "## Wiki inventory",
            f"- **Profile / enforcement**: `{w['profile']}` / `{w['enforcement']}`",
            f"- **Articles**: {w['total_articles']} total ({w['active_articles']} active)",
            f"- **Total size**: {w['total_bytes']:,} bytes ({w['total_chars']:,} chars, ~{w['estimated_tokens']:,} tokens)",
            f"- **INDEX.md**: {w['index_lines']} / {w['index_max_lines']} lines "
            f"({w['index_bytes']:,} bytes, ~{w['index_estimated_tokens']:,} tokens)",
            f"- **Handoffs**: {w['handoff_count']}",
        ]
        if w["articles_by_type"]:
            by_type_str = ", ".join(f"`{k}`: {v}" for k, v in w["articles_by_type"].items())
            lines.append(f"- **By type**: {by_type_str}")

        lines.extend([
            "",
            "## Context budget",
            f"- **Token estimator**: `{cb['token_estimator']}`",
            f"- **orient() payload**: {cb['orient_chars']:,} / {cb['orient_budget_chars']:,} chars "
            f"({cb['orient_budget_utilization_pct']}% utilization, ~{cb['orient_estimated_tokens']:,} tokens)",
            f"- **Full wiki**: {cb['full_wiki_chars']:,} chars (~{cb['full_wiki_estimated_tokens']:,} tokens)",
            f"- **Savings vs full wiki**: {cb['savings_vs_full_wiki_pct']}%",
            f"- **Instruction files**: {len(cb['instruction_files'])} detected "
            f"(~{cb['instruction_files_estimated_tokens']:,} tokens)",
        ])
        for inst in cb["instruction_files"]:
            lines.append(
                f"  - `{inst['path']}`: {inst['bytes']:,} bytes (~{inst['estimated_tokens']:,} tokens)"
            )

        lines.extend([
            "",
            "## Coverage and drift",
            f"- **Workspace files**: {cov['governed_workspace_files']} / {cov['total_workspace_files']} governed "
            f"({cov['coverage_pct']}%, {cov['ungoverned_workspace_files']} ungoverned)",
            f"- **Drifted articles**: {cov['drifted_articles_count']} ({cov['drift_items_count']} drift items)",
        ])
        if cov["drifted_articles"]:
            for drifted in cov["drifted_articles"]:
                lines.append(f"  - `{drifted}`")

        lines.extend([
            "",
            "## AST guards (Guard C)",
            f"- **Governed files AST-covered**: {ast_g['governed_files_ast_covered']} / "
            f"{cov['governed_workspace_files']} ({ast_g['governed_files_ast_coverage_pct']}%)",
            f"- **Polyglot installed**: {ast_g['polyglot_installed']} "
            f"(runtime available: {ast_g['polyglot_runtime_available']})",
            f"- **Active languages**: {', '.join(ast_g['active_languages']) or '(none)'}",
            f"- **Missing grammars**: {', '.join(ast_g['missing_grammars']) or '(none)'}",
        ])
        if ast_g["broken_grammars"]:
            broken_str = ", ".join(f"{k} ({v})" for k, v in sorted(ast_g["broken_grammars"].items()))
            lines.append(f"- **Broken grammars**: {broken_str}")
        else:
            lines.append("- **Broken grammars**: (none)")

        lines.extend(["", "## Largest articles"])
        if not w["largest_articles"]:
            lines.append("- *(none)*")
        else:
            for item in w["largest_articles"]:
                flag = " **[OVER LIMIT]**" if item["over_limit"] else ""
                lines.append(
                    f"- `{item['path']}`: {item['bytes']:,} bytes, {item['lines']} lines "
                    f"(~{item['estimated_tokens']:,} tokens){flag}"
                )

        return "\n".join(lines)


def _validate_schema_file(wiki_root: Path) -> None:
    """Validate SCHEMA.md frontmatter strictly so malformed schemas fail closed."""
    schema_file = wiki_root / "SCHEMA.md"
    if not schema_file.is_file():
        return
    raw_bytes = schema_file.read_bytes()
    lf_text = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    try:
        meta, _ = parse_frontmatter(lf_text)
    except (FrontmatterError, ValueError, yaml.YAMLError) as exc:
        raise ValidationError(
            rule="invalid_schema",
            path="SCHEMA.md",
            message=f"Malformed SCHEMA.md frontmatter: {exc}",
            actionable="Fix YAML frontmatter in .brain-79/SCHEMA.md or run 'brain79 update-project'.",
        ) from exc
    if not isinstance(meta, dict) or not meta:
        raise ValidationError(
            rule="invalid_schema",
            path="SCHEMA.md",
            message="SCHEMA.md frontmatter must be a non-empty YAML mapping.",
            actionable="Fix YAML frontmatter in .brain-79/SCHEMA.md or run 'brain79 update-project'.",
        )


def _iter_governed_article_paths(wiki_root: Path) -> list[Path]:
    """Return sorted governed markdown article paths excluding metadata and ephemeral folders."""
    articles: list[Path] = []
    for md_path in sorted(wiki_root.rglob("*.md")):
        if not md_path.is_file():
            continue
        try:
            rel = md_path.relative_to(wiki_root)
        except ValueError:
            continue
        rel_str = rel.as_posix()
        if rel_str in ("INDEX.md", "SCHEMA.md"):
            continue
        if rel.parts and rel.parts[0] in ("_raw", ".locks", "handoffs"):
            continue
        articles.append(md_path)
    return articles


def _read_lf_metrics(path: Path) -> tuple[int, str, int, int, int]:
    """Read file bytes and return (bytes, lf_text, chars, lines, estimated_tokens)."""
    raw_bytes = path.read_bytes()
    lf_text = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    return (
        len(raw_bytes),
        lf_text,
        len(lf_text),
        len(lf_text.splitlines()),
        estimate_tokens(lf_text),
    )


def compute_stats(
    project_root: Path | None = None,
    wiki_root: Path | None = None,
    *,
    task: str | None = None,
    paths: list[str] | None = None,
    max_articles: int = 4,
) -> StatsReport:
    """Compute read-only context budget, wiki inventory, coverage, and AST guard telemetry."""
    if max_articles < 1:
        raise ValueError(f"max_articles must be >= 1, got {max_articles}")

    p_root = (project_root or get_project_root()).resolve()
    w_root = (wiki_root or (p_root / ".brain-79")).resolve()

    with project_context(p_root, w_root):
        if not w_root.is_dir():
            raise FileNotFoundError(
                f"Wiki directory not found at '{w_root}'. Run 'brain79 init' to initialize it."
            )
        index_path = w_root / "INDEX.md"
        if not index_path.is_file():
            raise FileNotFoundError(
                f"INDEX.md not found at '{index_path}'. Run 'brain79 init' to initialize it."
            )

        _validate_schema_file(w_root)
        active_schema = load_active_schema(w_root)

        index_bytes, _index_text, index_chars, index_lines, index_tokens = _read_lf_metrics(index_path)
        index_max_lines = get_index_max_lines()

        handoffs_dir = w_root / "handoffs"
        handoff_count = (
            sum(1 for p in handoffs_dir.rglob("*.md") if p.is_file())
            if handoffs_dir.is_dir()
            else 0
        )

        non_active_statuses = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
        total_articles = 0
        active_articles = 0
        articles_by_type: dict[str, int] = {}
        total_bytes = 0
        total_chars = 0
        estimated_tokens = 0
        article_records: list[dict[str, Any]] = []
        active_patterns: list[str] = []

        for md_path in _iter_governed_article_paths(w_root):
            rel_str = md_path.relative_to(w_root).as_posix()
            f_bytes, lf_text, f_chars, f_lines, f_tokens = _read_lf_metrics(md_path)

            art_type = "unknown"
            status = ""
            stability = ""
            applies_to_raw: Any = []
            try:
                meta, _ = parse_frontmatter(lf_text)
                if isinstance(meta, dict):
                    raw_type = meta.get("type")
                    if isinstance(raw_type, str) and raw_type.strip():
                        art_type = raw_type.strip().lower()
                    status = str(meta.get("status") or "").strip().lower()
                    stability = str(meta.get("stability") or "").strip().lower()
                    applies_to_raw = meta.get("applies_to", [])
            except Exception:
                art_type = "unknown"

            is_active = (status not in non_active_statuses) and (stability not in _INACTIVE_STABILITY)
            over_limit = (art_type not in _IMMUTABLE_ARTICLE_TYPES) and (
                f_bytes > MAX_ARTICLE_BYTES or f_lines > MAX_ARTICLE_LINES
            )

            total_articles += 1
            if is_active:
                active_articles += 1
                if isinstance(applies_to_raw, list):
                    active_patterns.extend(str(item) for item in applies_to_raw if str(item).strip())
                elif isinstance(applies_to_raw, str) and applies_to_raw.strip():
                    active_patterns.append(applies_to_raw.strip())

            articles_by_type[art_type] = articles_by_type.get(art_type, 0) + 1
            total_bytes += f_bytes
            total_chars += f_chars
            estimated_tokens += f_tokens
            article_records.append({
                "path": rel_str,
                "bytes": f_bytes,
                "lines": f_lines,
                "estimated_tokens": f_tokens,
                "over_limit": over_limit,
            })

        largest_articles = sorted(article_records, key=lambda r: (-r["bytes"], r["path"]))[:5]

        git_cache = GitSessionCache()
        ws = WorkspaceIndex.build(p_root, w_root, git_cache=git_cache)

        all_drifts = detect_all_drift(
            wiki_root=w_root,
            project_root=p_root,
            workspace_index=ws,
            git_cache=git_cache,
        )
        drifted_articles = sorted(
            {str(d["article_path"]) for d in all_drifts if d.get("article_path")}
        )

        orient_text = orient(
            task=task,
            paths=paths,
            max_articles=max_articles,
            wiki_root=w_root,
            workspace_index=ws,
            git_cache=git_cache,
        )
        orient_lf = orient_text.replace("\r\n", "\n")
        orient_chars = len(orient_lf)
        orient_bytes = len(orient_lf.encode("utf-8"))
        orient_estimated_tokens = estimate_tokens(orient_lf)
        orient_budget_utilization_pct = round(
            (orient_chars / MAX_ORIENT_INLINE_CHARS) * 100.0, 1
        )
        full_wiki_chars = total_chars + index_chars
        full_wiki_estimated_tokens = estimated_tokens + index_tokens
        savings_vs_full_wiki_pct = (
            round(((full_wiki_chars - orient_chars) / full_wiki_chars) * 100.0, 1)
            if full_wiki_chars > 0
            else 0.0
        )

        instruction_files: list[dict[str, Any]] = []
        for rel_inst in _INSTRUCTION_FILE_CANDIDATES:
            inst_path = p_root / rel_inst
            if inst_path.is_file():
                i_bytes, _i_text, i_chars, _i_lines, i_tokens = _read_lf_metrics(inst_path)
                instruction_files.append({
                    "path": rel_inst,
                    "bytes": i_bytes,
                    "chars": i_chars,
                    "estimated_tokens": i_tokens,
                })
        instruction_files_estimated_tokens = sum(
            item["estimated_tokens"] for item in instruction_files
        )

        try:
            wiki_rel = rel_posix(w_root, p_root)
        except ValueError:
            wiki_rel = ".brain-79"

        non_wiki_files = sorted(
            p for p in ws.all_paths if p != wiki_rel and not p.startswith(f"{wiki_rel}/")
        )
        total_workspace_files = len(non_wiki_files)

        unique_patterns = list(dict.fromkeys(active_patterns))
        governed_set: set[str] = set()
        if unique_patterns and non_wiki_files:
            for cand in non_wiki_files:
                for pat in unique_patterns:
                    if match_applies_to_pattern(
                        pat,
                        cand,
                        known_dirs=ws.known_dirs,
                        known_wiki_prefixes=ws.known_wiki_prefixes,
                        wiki_rel_posix=wiki_rel,
                    ):
                        governed_set.add(cand)
                        break

        governed_workspace_files = len(governed_set)
        ungoverned_workspace_files = total_workspace_files - governed_workspace_files
        coverage_pct = (
            round((governed_workspace_files / total_workspace_files) * 100.0, 1)
            if total_workspace_files > 0
            else 0.0
        )

        caps = get_ast_guard_capabilities()
        governed_files_ast_covered = sum(
            1 for p in governed_set if get_inspector_for_path(p) is not None
        )
        governed_files_ast_coverage_pct = (
            round((governed_files_ast_covered / governed_workspace_files) * 100.0, 1)
            if governed_workspace_files > 0
            else 0.0
        )

        return StatsReport(
            wiki={
                "profile": active_schema.profile,
                "enforcement": active_schema.enforcement,
                "total_articles": total_articles,
                "active_articles": active_articles,
                "articles_by_type": dict(sorted(articles_by_type.items())),
                "total_bytes": total_bytes,
                "total_chars": total_chars,
                "estimated_tokens": estimated_tokens,
                "index_lines": index_lines,
                "index_max_lines": index_max_lines,
                "index_bytes": index_bytes,
                "index_chars": index_chars,
                "index_estimated_tokens": index_tokens,
                "handoff_count": handoff_count,
                "largest_articles": largest_articles,
            },
            context_budget={
                "token_estimator": "chars_div_4_ceil",
                "orient_chars": orient_chars,
                "orient_bytes": orient_bytes,
                "orient_estimated_tokens": orient_estimated_tokens,
                "orient_budget_chars": MAX_ORIENT_INLINE_CHARS,
                "orient_budget_utilization_pct": orient_budget_utilization_pct,
                "full_wiki_chars": full_wiki_chars,
                "full_wiki_estimated_tokens": full_wiki_estimated_tokens,
                "savings_vs_full_wiki_pct": savings_vs_full_wiki_pct,
                "instruction_files": instruction_files,
                "instruction_files_estimated_tokens": instruction_files_estimated_tokens,
            },
            coverage={
                "total_workspace_files": total_workspace_files,
                "governed_workspace_files": governed_workspace_files,
                "ungoverned_workspace_files": ungoverned_workspace_files,
                "coverage_pct": coverage_pct,
                "drifted_articles_count": len(drifted_articles),
                "drift_items_count": len(all_drifts),
                "drifted_articles": drifted_articles,
            },
            ast_guards={
                **caps,
                "governed_files_ast_covered": governed_files_ast_covered,
                "governed_files_ast_coverage_pct": governed_files_ast_coverage_pct,
            },
        )
