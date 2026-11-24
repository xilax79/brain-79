"""Read-only CI governance gate engine (`brain79 ci-check`)."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Literal

from brain79.config import get_project_root, get_wiki_root, project_context
from brain79.core.drift import (
    WorkspaceIndex,
    detect_all_drift,
    match_applies_to_pattern,
)
from brain79.core.frontmatter import (
    INACTIVE_STATUSES,
    PRE_IMPLEMENTATION_STATUSES,
    load_active_schema,
    parse_frontmatter,
)
from brain79.core.git_ops import (
    GitError,
    NotAGitRepoError,
    _validate_git_range_ref,
    git_diff_range_names,
    git_dirty_paths,
)
from brain79.core.lint import WikiLintResult, collect_wiki_lint_results
from brain79.core.locks import (
    atomic_replace_with_retry,
    create_temp_path,
    normalize_posix_input,
    rel_posix,
)
from brain79.core.navigation import (
    extract_graph_metadata,
    extract_title_and_summary,
    load_registry,
)
from brain79.core.orient import orient

MAX_INPUT_BYTES = 1_048_576
_MAX_TASK_HINT_CHARS = 2_000
_AGY_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "hookEventName",
        "workspacePaths",
        "continuationActive",
        "terminationReason",
        "conversationId",
    }
)

_EPHEMERAL_WIKI_DIRS: frozenset[str] = frozenset({"_raw", ".locks", "handoffs"})
_EPHEMERAL_WIKI_FILES: frozenset[str] = frozenset({"INDEX.md", "SCHEMA.md"})
_ACTIVE_ADR_STATUSES: frozenset[str] = frozenset({"accepted", "stable", ""})
_MAX_LIST_ITEMS = 30
_MAX_LINT_ITEMS = 15


def _sanitize_inline_text(value: Any) -> str:
    """Collapse embedded newlines and normalize whitespace for single-line Markdown bullets."""
    return " ".join(str(value or "").splitlines()).strip()


@dataclass
class CiCheckReport:
    """Structured governance report produced by `run_ci_check()`."""

    status: Literal["ok", "warning", "failed"]
    exit_code: int
    enforcement: str
    diff_range: str
    changed_files: list[str] = field(default_factory=list)
    drifted_articles: list[dict[str, Any]] = field(default_factory=list)
    impacted_articles: list[dict[str, Any]] = field(default_factory=list)
    relevant_adrs: list[dict[str, Any]] = field(default_factory=list)
    lint_status: str = "OK"
    lint_errors_count: int = 0
    lint_warnings_count: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)
    markdown_summary: str = ""

    def format_markdown(self) -> str:
        """Render a GitHub-flavored Markdown summary prefixed with `<!-- brain79:ci-check -->`."""
        badge_status = {
            "ok": "PASSED",
            "warning": "WARNING",
            "failed": "FAILED",
        }.get(self.status, "FAILED")

        lines: list[str] = [
            "<!-- brain79:ci-check -->",
            "# Brain-79 CI governance report",
            "",
            f"[Status: {badge_status}] [Enforcement: {self.enforcement}] [Diff: {self.diff_range}]",
            "",
            "## Drifted governing articles",
        ]

        if not self.drifted_articles:
            lines.append("- None (0 drifted articles).")
        else:
            for item in self.drifted_articles[:_MAX_LIST_ITEMS]:
                art = _sanitize_inline_text(item.get("article_path", ""))
                kind = _sanitize_inline_text(item.get("drift_kind", ""))
                target = _sanitize_inline_text(item.get("workspace_file", ""))
                msg = _sanitize_inline_text(item.get("message", ""))
                detail = f"`{target}` ({kind})" if target else (kind or msg)
                lines.append(f"- `{art}`: {detail}")
            if len(self.drifted_articles) > _MAX_LIST_ITEMS:
                lines.append(f"- ... and {len(self.drifted_articles) - _MAX_LIST_ITEMS} more")

        lines.extend(["", "## Impacted governing articles for diff"])
        if not self.impacted_articles:
            lines.append("- None.")
        else:
            for item in self.impacted_articles[:_MAX_LIST_ITEMS]:
                art = _sanitize_inline_text(item.get("path", ""))
                matched = ", ".join(
                    f"`{_sanitize_inline_text(m)}`" for m in item.get("matched_files", [])
                )
                state = "updated in diff" if item.get("updated_in_diff") else "not updated in diff"
                lines.append(f"- `{art}` ({state}) — matched {matched}")
            if len(self.impacted_articles) > _MAX_LIST_ITEMS:
                lines.append(f"- ... and {len(self.impacted_articles) - _MAX_LIST_ITEMS} more")

        lines.extend(["", "## Relevant governing ADRs"])
        if not self.relevant_adrs:
            lines.append("- None.")
        else:
            for item in self.relevant_adrs[:_MAX_LIST_ITEMS]:
                adr_path = _sanitize_inline_text(item.get("path", ""))
                title = _sanitize_inline_text(item.get("title", "")) or adr_path
                summary = _sanitize_inline_text(item.get("summary", ""))
                if summary:
                    lines.append(f"- `{adr_path}` — {title}: {summary}")
                else:
                    lines.append(f"- `{adr_path}` — {title}")
            if len(self.relevant_adrs) > _MAX_LIST_ITEMS:
                lines.append(f"- ... and {len(self.relevant_adrs) - _MAX_LIST_ITEMS} more")

        lines.extend(["", "## Wiki lint summary"])
        lines.append(
            f"- Status: **{self.lint_status}** "
            f"(errors: {self.lint_errors_count}, warnings: {self.lint_warnings_count})"
        )
        actionable_issues = [
            i for i in self.issues if i.get("severity") in ("error", "warning")
        ]
        for issue in actionable_issues[:_MAX_LINT_ITEMS]:
            sev = str(issue.get("severity", "warning")).upper()
            i_path = _sanitize_inline_text(issue.get("path", ""))
            msg = _sanitize_inline_text(issue.get("message", ""))
            lines.append(f"- **[{sev}]** `{i_path}`: {msg}")
        if len(actionable_issues) > _MAX_LINT_ITEMS:
            lines.append(f"- ... and {len(actionable_issues) - _MAX_LINT_ITEMS} more")

        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to canonical JSON-compatible dictionary."""
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "enforcement": self.enforcement,
            "diff_range": self.diff_range,
            "changed_files": list(self.changed_files),
            "drifted_articles": list(self.drifted_articles),
            "impacted_articles": list(self.impacted_articles),
            "relevant_adrs": list(self.relevant_adrs),
            "lint_status": self.lint_status,
            "lint_errors_count": self.lint_errors_count,
            "lint_warnings_count": self.lint_warnings_count,
            "issues": list(self.issues),
            "markdown_summary": self.markdown_summary,
        }


def _resolve_changed_files(
    p_root: Path,
    *,
    base_ref: str | None,
    head_ref: str,
) -> tuple[list[str], str]:
    """Resolve changed workspace paths and a human-readable diff_range descriptor."""
    if base_ref is not None:
        files = git_diff_range_names(p_root, base_ref, head_ref)
        return files, f"{base_ref}...{head_ref}"

    if head_ref != "HEAD":
        _validate_git_range_ref(head_ref, "head_ref")

    try:
        dirty = git_dirty_paths(p_root, exclude_prefix=None)
    except NotAGitRepoError:
        return [], "non_git"
    except GitError:
        return [], "working_tree"

    if dirty:
        return dirty, "working_tree"

    env_base = os.environ.get("GITHUB_BASE_REF", "").strip()
    if env_base:
        try:
            _validate_git_range_ref(env_base, "GITHUB_BASE_REF")
        except ValueError:
            return [], "shallow_fallback"

        for candidate_base in (f"origin/{env_base}", env_base):
            try:
                files = git_diff_range_names(p_root, candidate_base, head_ref)
                return files, f"{candidate_base}...{head_ref}"
            except (GitError, ValueError):
                continue
        return [], "shallow_fallback"

    return [], "working_tree"


def _is_ephemeral_wiki_rel(rel_inside_wiki: str) -> bool:
    """Return True if a wiki-relative path is ephemeral or non-article metadata."""
    norm = normalize_posix_input(rel_inside_wiki).lstrip("/")
    if not norm or norm in _EPHEMERAL_WIKI_FILES:
        return True
    parts = norm.split("/")
    if parts[0] in _EPHEMERAL_WIKI_DIRS:
        return True
    if any(part.startswith(".") for part in parts):
        return True
    return False


def _partition_changed_files(
    changed_files: list[str],
    wiki_rel: str,
) -> tuple[list[str], set[str], list[str]]:
    """Partition changed files into workspace files, modified wiki articles, and non-ephemeral files."""
    wiki_prefix = f"{wiki_rel}/" if wiki_rel else ""
    modified_workspace: list[str] = []
    modified_wiki_articles: set[str] = set()
    non_ephemeral: list[str] = []

    for raw_path in changed_files:
        norm = normalize_posix_input(raw_path).lstrip("/")
        if not norm:
            continue
        if wiki_prefix and norm.startswith(wiki_prefix):
            rel_inside = norm[len(wiki_prefix):]
            if _is_ephemeral_wiki_rel(rel_inside):
                continue
            if rel_inside.endswith(".md"):
                modified_wiki_articles.add(rel_inside)
            non_ephemeral.append(norm)
        elif norm == wiki_rel:
            continue
        else:
            modified_workspace.append(norm)
            non_ephemeral.append(norm)

    return modified_workspace, modified_wiki_articles, non_ephemeral


def _collect_impact_and_adrs(
    w_root: Path,
    wiki_rel: str,
    ws: WorkspaceIndex,
    non_ephemeral_changed: list[str],
    modified_wiki_articles: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Identify impacted active governing articles and 1-hop relevant active ADRs."""
    non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
    registry = load_registry(w_root, persist=False)
    registry_by_path: dict[str, dict[str, Any]] = {
        str(entry["path"]): entry
        for entry in registry.get("articles", [])
        if isinstance(entry, dict) and entry.get("path")
    }

    md_files = sorted(w_root.rglob("*.md"))
    active_articles: dict[str, tuple[Path, dict[str, Any], str]] = {}

    for md_file in md_files:
        try:
            rel_path = md_file.relative_to(w_root).as_posix()
        except ValueError:
            continue
        if _is_ephemeral_wiki_rel(rel_path):
            continue
        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        except OSError:
            continue
        meta, _ = parse_frontmatter(content) if content.startswith("---\n") else ({}, content)
        meta = meta or {}
        status = str(meta.get("status", "")).strip().lower()
        stability = str(meta.get("stability", "")).strip().lower()
        if status in non_active or stability in non_active:
            continue
        active_articles[rel_path] = (md_file, meta, content)

    impacted_articles: list[dict[str, Any]] = []
    impacted_paths_set: set[str] = set()

    for rel_path in sorted(active_articles):
        _, meta, _ = active_articles[rel_path]
        applies_raw = meta.get("applies_to", [])
        if isinstance(applies_raw, str):
            applies_patterns = [applies_raw]
        elif isinstance(applies_raw, list):
            applies_patterns = [str(p) for p in applies_raw if p]
        else:
            applies_patterns = []

        if not applies_patterns or not non_ephemeral_changed:
            continue

        self_full_path = f"{wiki_rel}/{rel_path}" if wiki_rel else rel_path
        matched_files: list[str] = []
        for cand in non_ephemeral_changed:
            if cand == self_full_path or cand == rel_path:
                continue
            if any(
                match_applies_to_pattern(
                    pat,
                    cand,
                    known_dirs=ws.known_dirs,
                    known_wiki_prefixes=ws.known_wiki_prefixes,
                    wiki_rel_posix=wiki_rel,
                )
                for pat in applies_patterns
            ):
                if cand not in matched_files:
                    matched_files.append(cand)

        if matched_files:
            impacted_paths_set.add(rel_path)
            impacted_articles.append(
                {
                    "path": rel_path,
                    "matched_files": sorted(matched_files),
                    "updated_in_diff": rel_path in modified_wiki_articles,
                }
            )

    relevant_adr_paths: set[str] = set()

    # Direct ADR matches via applies_to
    for item in impacted_articles:
        if item["path"].startswith("decisions/"):
            relevant_adr_paths.add(item["path"])

    # 1-hop Signal 3 ADR expansion from impacted articles
    for rel_path in sorted(impacted_paths_set):
        md_file, _, content = active_articles[rel_path]
        reg_entry = registry_by_path.get(rel_path)
        linked_targets: list[str] = []
        if reg_entry:
            linked_targets.extend(str(t) for t in reg_entry.get("related", []) if t)
            linked_targets.extend(str(t) for t in reg_entry.get("outgoing_links", []) if t)
        else:
            gm = extract_graph_metadata(content, rel_path=rel_path)
            linked_targets.extend(str(t) for t in gm.get("related", []) if t)
            linked_targets.extend(str(t) for t in gm.get("outgoing_links", []) if t)

        for target in linked_targets:
            norm_target = normalize_posix_input(target).strip().lstrip("/")
            if not (norm_target.startswith("decisions/") or "/decisions/" in norm_target):
                continue
            candidate_path = (w_root / norm_target).resolve()
            if not candidate_path.exists():
                candidate_path = (md_file.parent / norm_target).resolve()
            if not candidate_path.is_file() or not candidate_path.is_relative_to(w_root):
                continue
            adr_rel = candidate_path.relative_to(w_root).as_posix()
            if not adr_rel.startswith("decisions/"):
                continue
            relevant_adr_paths.add(adr_rel)

    relevant_adrs: list[dict[str, Any]] = []
    for adr_rel in sorted(relevant_adr_paths):
        if adr_rel not in active_articles:
            continue
        _, adr_meta, adr_content = active_articles[adr_rel]
        adr_status = str(adr_meta.get("status", "")).strip().lower()
        if adr_status not in _ACTIVE_ADR_STATUSES:
            continue
        reg_entry = registry_by_path.get(adr_rel)
        if reg_entry and (reg_entry.get("title") or reg_entry.get("summary")):
            title = str(reg_entry.get("title", "")).strip()
            summary = str(reg_entry.get("summary", "")).strip()
        else:
            title, summary = extract_title_and_summary(adr_content)
        if not summary:
            summary = str(adr_meta.get("summary", "")).strip()
        relevant_adrs.append(
            {
                "path": adr_rel,
                "title": _sanitize_inline_text(title or adr_rel),
                "summary": _sanitize_inline_text(summary),
            }
        )

    return impacted_articles, relevant_adrs


def _serialize_lint_issues(lint_res: WikiLintResult) -> tuple[list[dict[str, Any]], int, int]:
    """Convert structured lint results into canonical issue dictionaries and counts."""
    issues: list[dict[str, Any]] = []
    for origin, target in lint_res.broken_links:
        issues.append(
            {
                "rule": "broken_link",
                "path": origin,
                "line": None,
                "severity": "error",
                "message": f"Broken local link to '{target}'.",
                "actionable": "Fix or remove the broken link target.",
            }
        )
    for origin, target in lint_res.namespace_violations:
        issues.append(
            {
                "rule": "namespace_violation",
                "path": origin,
                "line": None,
                "severity": "error",
                "message": f"Link '{target}' targets an excluded namespace.",
                "actionable": "Link only to valid wiki articles.",
            }
        )
    for rel, err in lint_res.structural_errors:
        issues.append(
            {
                "rule": "structural_error",
                "path": rel,
                "line": None,
                "severity": "warning",
                "message": err,
                "actionable": "Ensure the article is non-empty, readable UTF-8, and has an H1 header.",
            }
        )
    for orphan in lint_res.orphans:
        issues.append(
            {
                "rule": "orphan_article",
                "path": orphan,
                "line": None,
                "severity": "warning",
                "message": "Article is not reachable from INDEX.md.",
                "actionable": "Link this article from INDEX.md or a linked article.",
            }
        )
    for org_issue in lint_res.org_issues:
        issues.append(
            {
                "rule": org_issue.rule,
                "path": org_issue.path,
                "line": org_issue.line,
                "severity": org_issue.severity,
                "message": org_issue.message,
                "actionable": org_issue.actionable,
            }
        )

    errors_count = sum(1 for i in issues if i["severity"] == "error")
    warnings_count = sum(1 for i in issues if i["severity"] == "warning")
    return issues, errors_count, warnings_count


def _persist_summaries(
    markdown_summary: str,
    *,
    summary_file: Path | None,
    write_step_summary: bool,
) -> None:
    """Persist rendered Markdown summary to `summary_file` and/or `$GITHUB_STEP_SUMMARY`."""
    normalized_md = markdown_summary.replace("\r\n", "\n")
    if not normalized_md.endswith("\n"):
        normalized_md += "\n"

    if summary_file is not None:
        if not summary_file.parent.exists():
            raise FileNotFoundError(f"Summary parent directory does not exist: {summary_file.parent}")
        if summary_file.exists() and summary_file.is_dir():
            raise IsADirectoryError(f"Summary target is a directory: {summary_file}")
        tmp_path = create_temp_path(summary_file)
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(normalized_md)
        atomic_replace_with_retry(tmp_path, summary_file)

    if write_step_summary:
        step_summary_env = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
        if step_summary_env:
            step_path = Path(step_summary_env)
            with open(step_path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(normalized_md)


def run_ci_check(
    project_root: Path | None = None,
    wiki_root: Path | None = None,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    enforcement: Literal["strict", "balanced", "advisory", "schema"] = "strict",
    fail_on_warnings: bool = False,
    summary_file: Path | None = None,
    write_step_summary: bool = False,
) -> CiCheckReport:
    """Execute read-only CI governance checks and return a structured `CiCheckReport`."""
    p_root = (project_root or get_project_root()).resolve()
    w_root = (
        wiki_root.resolve()
        if wiki_root is not None
        else ((p_root / ".brain-79").resolve() if project_root is not None else get_wiki_root().resolve())
    )

    changed_files, diff_range = _resolve_changed_files(
        p_root,
        base_ref=base_ref,
        head_ref=head_ref,
    )

    with project_context(p_root, w_root):
        if not w_root.is_dir() or not (w_root / "INDEX.md").is_file():
            effective_enforcement = "strict" if enforcement == "schema" else enforcement
            report = CiCheckReport(
                status="failed",
                exit_code=1,
                enforcement=effective_enforcement,
                diff_range=diff_range,
                changed_files=changed_files,
                lint_status="CRITICAL",
                lint_errors_count=1,
                lint_warnings_count=0,
                issues=[
                    {
                        "rule": "missing_wiki",
                        "path": ".brain-79/INDEX.md",
                        "line": None,
                        "severity": "error",
                        "message": "Wiki not initialized (.brain-79/INDEX.md missing).",
                        "actionable": "Run `brain79 init` to initialize the project wiki.",
                    }
                ],
            )
            report.markdown_summary = report.format_markdown()
            _persist_summaries(
                report.markdown_summary,
                summary_file=summary_file,
                write_step_summary=write_step_summary,
            )
            return report

        active_schema = load_active_schema(w_root)
        effective_enforcement = (
            active_schema.enforcement if enforcement == "schema" else enforcement
        )

        ws = WorkspaceIndex.build(p_root, w_root)
        try:
            wiki_rel = rel_posix(w_root, p_root)
        except ValueError:
            wiki_rel = ".brain-79"

        _, modified_wiki_articles, non_ephemeral_changed = _partition_changed_files(
            changed_files,
            wiki_rel,
        )

        impacted_articles, relevant_adrs = _collect_impact_and_adrs(
            w_root,
            wiki_rel,
            ws,
            non_ephemeral_changed,
            modified_wiki_articles,
        )

        raw_drifts = detect_all_drift(
            wiki_root=w_root,
            project_root=p_root,
            workspace_index=ws,
        )
        drifted_articles = [
            {
                "article_path": d.get("article_path", ""),
                "drift_kind": d.get("drift_kind", ""),
                "workspace_file": d.get("workspace_file", d.get("target_file", "")),
                "message": d.get("message", ""),
            }
            for d in raw_drifts
        ]

        lint_res = collect_wiki_lint_results(w_root, workspace_index=ws)
        issues, lint_errors_count, lint_warnings_count = _serialize_lint_issues(lint_res)

        if lint_res.status == "CRITICAL":
            status: Literal["ok", "warning", "failed"] = "failed"
            exit_code = 1
        elif len(drifted_articles) > 0 or lint_res.status == "WARNING":
            if effective_enforcement == "strict" or fail_on_warnings:
                status = "failed"
                exit_code = 1
            else:
                status = "warning"
                exit_code = 0
        else:
            status = "ok"
            exit_code = 0

        report = CiCheckReport(
            status=status,
            exit_code=exit_code,
            enforcement=effective_enforcement,
            diff_range=diff_range,
            changed_files=changed_files,
            drifted_articles=drifted_articles,
            impacted_articles=impacted_articles,
            relevant_adrs=relevant_adrs,
            lint_status=lint_res.status,
            lint_errors_count=lint_errors_count,
            lint_warnings_count=lint_warnings_count,
            issues=issues,
        )
        report.markdown_summary = report.format_markdown()
        _persist_summaries(
            report.markdown_summary,
            summary_file=summary_file,
            write_step_summary=write_step_summary,
        )
        return report


def _read_hook_payload(stdin_payload: str | None) -> dict[str, Any] | None:
    """Read and parse bounded JSON hook payload; return None to fail open."""
    if stdin_payload is not None:
        raw_text = stdin_payload
    elif sys.stdin is not None and not sys.stdin.isatty():
        raw_buf = getattr(sys.stdin, "buffer", None)
        if raw_buf is not None:
            raw_bytes = raw_buf.read(MAX_INPUT_BYTES + 1)
            if len(raw_bytes) > MAX_INPUT_BYTES:
                return None
            try:
                raw_text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return None
        else:
            raw_text = sys.stdin.read(MAX_INPUT_BYTES + 1)
    else:
        raw_text = ""

    if len(raw_text) > MAX_INPUT_BYTES or len(raw_text.encode("utf-8", errors="replace")) > MAX_INPUT_BYTES:
        return None

    if not raw_text.strip():
        return {}

    try:
        parsed = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        return None

    return parsed if isinstance(parsed, dict) else None


def _infer_hook_client(
    client: Literal["auto", "claude", "agy", "cursor"],
    payload: dict[str, Any],
) -> Literal["claude", "agy", "cursor"] | None:
    """Resolve target lifecycle hook client protocol."""
    if client != "auto":
        return client if client in ("claude", "agy", "cursor") else None

    if any(key in payload for key in _AGY_PAYLOAD_KEYS):
        return "agy"
    if (
        "workspace_roots" in payload
        or "loop_count" in payload
        or payload.get("hook_event_name") == "sessionStart"
    ):
        return "cursor"
    return "claude"


def _walk_for_wiki_root(start_dir: Path) -> tuple[Path | None, bool]:
    """Walk ancestors of `start_dir` for `.brain-79/`, stopping after any `.git` directory."""
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / ".brain-79").is_dir():
            return candidate, True
        if (candidate / ".git").exists():
            return None, True
    return None, False


def _resolve_hook_project_root(
    explicit_root: Path | None,
    payload: dict[str, Any],
) -> Path:
    """Resolve project_root from override, payload workspace candidates, or config fallback."""
    if explicit_root is not None:
        return explicit_root.resolve()

    raw_candidates: list[str] = []
    cwd_val = payload.get("cwd")
    if isinstance(cwd_val, str) and cwd_val.strip():
        raw_candidates.append(cwd_val.strip())

    for list_key in ("workspacePaths", "workspace_roots"):
        list_val = payload.get(list_key)
        if isinstance(list_val, list) and list_val:
            first = list_val[0]
            if isinstance(first, str) and first.strip():
                raw_candidates.append(first.strip())

    first_valid_dir: Path | None = None
    for raw in raw_candidates:
        try:
            cand_path = Path(raw).resolve()
        except (OSError, ValueError):
            continue
        if not cand_path.exists():
            continue
        if cand_path.is_file():
            cand_path = cand_path.parent
        if first_valid_dir is None:
            first_valid_dir = cand_path

        found_root, _ = _walk_for_wiki_root(cand_path)
        if found_root is not None:
            return found_root

    if first_valid_dir is not None:
        return first_valid_dir

    return get_project_root().resolve()


def _should_skip_stop_hook(payload: dict[str, Any]) -> bool:
    """Return True if loop-immunity or non-normal termination guards trigger."""
    if payload.get("continuationActive") is True or payload.get("stop_hook_active") is True:
        return True

    if "loop_count" in payload and payload["loop_count"] is not None:
        raw_loop = payload["loop_count"]
        if isinstance(raw_loop, bool):
            return True
        try:
            loop_val = float(raw_loop)
        except (TypeError, ValueError):
            return True
        if math.isnan(loop_val) or loop_val >= 1:
            return True

    term_reason = payload.get("terminationReason")
    if term_reason is not None:
        if not isinstance(term_reason, str):
            return True
        if term_reason.strip() and term_reason.strip() != "NO_TOOL_CALL":
            return True

    status_val = payload.get("status")
    if status_val is not None:
        if not isinstance(status_val, str):
            return True
        if status_val.strip() and status_val.strip() != "completed":
            return True

    return False


def _format_session_start_response(
    client: Literal["claude", "agy", "cursor"],
    orient_report: str,
) -> dict[str, Any]:
    """Wrap `orient()` markdown in the target client's SessionStart JSON schema."""
    if client == "agy":
        return {"injectSteps": [{"systemMessage": {"systemMessage": orient_report}}]}
    if client == "cursor":
        return {"additional_context": orient_report}
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": orient_report,
        }
    }


def _format_stop_response(
    client: Literal["claude", "agy", "cursor"],
    reason: str,
) -> dict[str, Any]:
    """Wrap drift remediation reason in the target client's Stop JSON schema."""
    if client == "agy":
        return {"decision": "continue", "reason": reason}
    if client == "cursor":
        return {"followup_message": reason}
    return {"decision": "block", "reason": reason}


def run_lifecycle_hook(
    event: Literal["session-start", "stop"],
    *,
    client: Literal["auto", "claude", "agy", "cursor"] = "auto",
    stdin_payload: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Execute a passive fail-open lifecycle hook (`session-start` or `stop`)."""
    try:
        payload = _read_hook_payload(stdin_payload)
        if payload is None:
            return {}

        resolved_client = _infer_hook_client(client, payload)
        if resolved_client is None:
            return {}

        if event == "stop" and _should_skip_stop_hook(payload):
            return {}

        p_root = _resolve_hook_project_root(project_root, payload)
        w_root = (p_root / ".brain-79").resolve()
        if not w_root.is_dir() or not (w_root / "INDEX.md").is_file():
            return {}

        with project_context(p_root, w_root):
            if event == "session-start":
                task_hint: str | None = None
                for key in ("lastUserInput", "prompt"):
                    val = payload.get(key)
                    if isinstance(val, str):
                        stripped = val.strip()
                        if stripped:
                            task_hint = stripped[:_MAX_TASK_HINT_CHARS]
                            break
                orient_report = orient(task=task_hint, wiki_root=w_root, max_articles=4)
                return _format_session_start_response(resolved_client, orient_report)

            if event == "stop":
                active_schema = load_active_schema(w_root)
                if active_schema.enforcement == "advisory":
                    return {}
                drifts = detect_all_drift(wiki_root=w_root, project_root=p_root)
                if not drifts:
                    return {}
                drifted_paths = sorted(
                    {
                        str(d.get("article_path", "")).strip()
                        for d in drifts
                        if d.get("article_path")
                    }
                )
                shown = drifted_paths[:10]
                suffix = f" (+{len(drifted_paths) - 10} more)" if len(drifted_paths) > 10 else ""
                articles_str = ", ".join(shown) + suffix
                reason = (
                    f"Brain-79 detected documentation drift in: {articles_str}. "
                    "Please update the affected wiki articles or mark them via "
                    "brain79_session_commit (verified_articles) before finishing."
                )
                return _format_stop_response(resolved_client, reason)

        return {}
    except Exception:
        return {}
