from dataclasses import dataclass
from pathlib import Path
import subprocess

from brain79.config import get_project_root
from brain79.core.context import rank_context_articles
from brain79.core.drift import WorkspaceIndex, detect_all_drift
from brain79.core.frontmatter import load_active_schema
from brain79.core.lint import lint_wiki
from brain79.core.lint_organizational import OrganizationalIssue, lint_organizational
from brain79.core.locks import normalize_posix_input


@dataclass
class WikiStateReport:
    """Summary of wiki state for curation guide generation."""
    has_index: bool
    index_line_count: int
    article_count: int
    critical_count: int
    warning_count: int
    issues_summary: list[str]


def analyze_wiki_state(
    wiki_root: Path, org_issues: list[OrganizationalIssue] | None = None
) -> WikiStateReport:
    """Analyze current wiki state and return structured report for curation."""
    index_file = wiki_root / "INDEX.md"
    has_index = index_file.exists()
    index_lines = len(index_file.read_text(encoding="utf-8").splitlines()) if has_index else 0

    articles = [
        f for f in wiki_root.rglob("*.md")
        if "_raw" not in f.parts and ".locks" not in f.parts
    ]
    if org_issues is None:
        org_issues = lint_organizational(wiki_root)

    critical_count = sum(1 for i in org_issues if i.severity == "error")
    warning_count = sum(1 for i in org_issues if i.severity == "warning")

    issues_summary: list[str] = []
    for issue in org_issues[:10]:
        issues_summary.append(f"- [{issue.severity.upper()}] {issue.path}: {issue.message}")

    return WikiStateReport(
        has_index=has_index,
        index_line_count=index_lines,
        article_count=len(articles),
        critical_count=critical_count,
        warning_count=warning_count,
        issues_summary=issues_summary,
    )


def prepare_curation_guide(wiki_root: Path, raw_content: str | None = None) -> str:
    """Generate state-aware curation guide for AI agent ingest cycles. Max 500 lines."""
    org_issues = lint_organizational(wiki_root)
    state = analyze_wiki_state(wiki_root, org_issues=org_issues)

    try:
        schema = load_active_schema(wiki_root)
        profile_name = schema.profile
        dir_descriptions = [
            f"- `{d}/` (`{t}`)"
            for d, t in sorted(schema.location_to_type.items())
            if d != "handoffs" and not d.startswith("_raw") and not d.endswith(".md")
        ]
        target_dirs_text = "\n".join(dir_descriptions)
    except Exception:
        profile_name = "software"
        target_dirs_text = (
            "- `features/` (`feature`)\n"
            "- `decisions/` (`decision`)\n"
            "- `architecture/` (`architecture`)\n"
            "- `product/` (`product`)"
        )

    lines: list[str] = [
        "# Brain-79 — State-Aware Ingest & Curation Guide",
        "",
        "Use this guide to structure and curate session knowledge into the project wiki.",
        "",
        "## Current Wiki Health Overview",
        f"- **Active Schema Profile**: `{profile_name}`",
        f"- **Articles in Wiki**: {state.article_count}",
        f"- **INDEX.md Line Count**: {state.index_line_count} / 150 max lines",
        f"- **Active Health Issues**: {state.critical_count} error(s), {state.warning_count} warning(s)",
        "",
    ]

    if state.issues_summary:
        lines.append("### Specific Violations Needing Remediation")
        lines.extend(state.issues_summary)
        lines.append("")

    # Pillar 7.2: Session Impact & Drift Checklist
    p_root = (wiki_root.parent or get_project_root()).resolve()
    discovered_dirty_paths: list[str] = []
    try:
        res = subprocess.run(
            ["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z"],
            cwd=str(p_root),
            capture_output=True,
            check=False,
            timeout=2.0,
        )
        if res.returncode == 0 and res.stdout:
            raw_entries = res.stdout.split(b"\x00")
            idx = 0
            while idx < len(raw_entries):
                entry_bytes = raw_entries[idx]
                idx += 1
                if not entry_bytes:
                    continue
                entry_str = entry_bytes.decode("utf-8", errors="replace")
                if len(entry_str) >= 4 and entry_str[2] == " ":
                    xy = entry_str[:2]
                    p_str = entry_str[3:]
                    norm_p = normalize_posix_input(p_str).lstrip("/")
                    if norm_p and norm_p not in discovered_dirty_paths and not norm_p.startswith(".brain-79/"):
                        discovered_dirty_paths.append(norm_p)
                    if "R" in xy or "C" in xy:
                        if idx < len(raw_entries) and raw_entries[idx]:
                            orig_bytes = raw_entries[idx]
                            idx += 1
                            orig_str = orig_bytes.decode("utf-8", errors="replace")
                            norm_orig = normalize_posix_input(orig_str).lstrip("/")
                            if norm_orig and norm_orig not in discovered_dirty_paths and not norm_orig.startswith(".brain-79/"):
                                discovered_dirty_paths.append(norm_orig)
                    if len(discovered_dirty_paths) >= 50:
                        break
    except Exception:
        discovered_dirty_paths = []

    ws = WorkspaceIndex.build(p_root, wiki_root)
    active_drifts = detect_all_drift(wiki_root=wiki_root, project_root=p_root, workspace_index=ws)

    drift_items: list[str] = []
    seen_drifts: set[tuple[str, str, str]] = set()
    for d in active_drifts:
        art_path = d.get("article_path", "")
        ws_file = d.get("workspace_file", d.get("target_file", ""))
        kind = d.get("drift_kind", "modified").upper()
        key = (art_path, ws_file, kind)
        if key not in seen_drifts:
            seen_drifts.add(key)
            tag = "[TRANSITIVE]" if kind == "TRANSITIVE" else "[DIRECT]"
            msg = d.get("message", f"governed file {ws_file} modified")
            drift_items.append(f"- **{tag} `{art_path}`**: {msg}")

    governing_items: list[str] = []
    if discovered_dirty_paths:
        ranked = rank_context_articles(paths=discovered_dirty_paths, top_n=20, wiki_root=wiki_root)
        for _, art_p, reasons in ranked:
            if any(r.startswith("path:") for r in reasons):
                try:
                    rel_p = art_p.relative_to(wiki_root).as_posix()
                    governing_items.append(f"- **`{rel_p}`**: governs modified files in working tree")
                except ValueError:
                    pass

    lines.extend([
        "## 🎯 Session Impact & Drift Checklist",
        "Before calling `brain79_session_commit`, verify whether code modifications impacted the wiki:",
    ])
    if drift_items:
        lines.append("### Active Documentation Drift Detected (Must Be Resolved)")
        lines.extend(drift_items)
        lines.append("")
    if governing_items:
        lines.append("### Governing Articles for Modified Code Files")
        lines.extend(sorted(set(governing_items)))
        lines.append("")
    if not drift_items and not governing_items:
        lines.append("- [Status: OK] Zero documentation drift detected and working tree is clean.")
        lines.append("")
    lines.extend([
        "> **Hard Session Ripple Gate**: `brain79_session_commit` requires all impacted governing "
        "and umbrella articles to be updated in `writes`/`edits`, or verified as internal refactors in `verified_articles`.",
        "",
    ])

    lines.extend([
        "## Session Knowledge Triage (The Amnesia Test)",
        "Before closing or committing, ask: *'If this session were wiped, would valuable research, decisions, or context be lost?'*",
        "- **Type A (ephemeral / read-only chat)**: greetings, quick syntax lookups, or reading files without new findings -> **true no-op** (do NOT invent articles).",
        "- **Type B (zero-code research, analysis & decisions)**: domain research, forecasts, benchmarks, architecture spikes, or trade-off decisions -> **MUST persist into wiki** in target directories below (even with 0 code/git changes!). Synthesize structured articles; do not dump raw chat.",
        "- **Type C (workspace / code mutation)**: code or config files changed -> **MUST sync** governing wiki articles.",
        "",
        "## Target Wiki Directories (Active Profile)",
        target_dirs_text,
        "",
        "## Mandatory Curation Rules",
        "1. Every new or updated article MUST include valid YAML frontmatter containing `type` and `last_updated`.",
        "2. Architectural decisions MUST be created as separate files in `decisions/` (never declared inline).",
        "3. Technical debt items MUST be recorded in `features/` or `decisions/`.",
        "4. `INDEX.md` MUST remain under 150 lines and contain ONLY `## Quick navigation` as its H2 section header (Pure Routing Table Invariant).",
        "",
        "## Step-by-Step Curation Workflow",
        "1. **Triage**: Classify session into Type A (no-op), Type B (research/decisions deliverable), or Type C (code sync).",
        "2. **Extract & Synthesize**: If Type B or C, structure new findings or decisions into targeted articles with clean headings and frontmatter.",
        "3. **Atomic Commit**: Persist articles and close handoff in one call via `brain79_session_commit(writes=[...], handoff={...})`.",
        "4. **Lint Verification**: Automatic in session_commit; verify full health anytime with `brain79_lint()`.",
        "",
    ])

    if raw_content:
        lines.append("## Session Input Snippet")
        snippet_lines = raw_content.splitlines()[:5]
        lines.extend(f"> {line_item}" for line_item in snippet_lines)
        if len(raw_content.splitlines()) > 5:
            lines.append("> ...")
        lines.append("")

    lines.append("## Diagnostic Summary")
    if state.critical_count == 0 and state.warning_count == 0:
        lines.append("[Status: OK] Zero health violations detected.")
    else:
        lint_report = lint_wiki()
        lines.append(lint_report)

    # Apply 500 lines hard limit cap
    if len(lines) > 500:
        lines = lines[:495] + ["", "... [Curation guide capped at 500 lines]"]

    return "\n".join(lines)
