from dataclasses import dataclass
from pathlib import Path

from brain79.core.lint import lint_wiki
from brain79.core.lint_organizational import lint_organizational


@dataclass
class WikiStateReport:
    """Summary of wiki state for curation guide generation."""
    has_index: bool
    index_line_count: int
    article_count: int
    critical_count: int
    warning_count: int
    issues_summary: list[str]


def analyze_wiki_state(wiki_root: Path) -> WikiStateReport:
    """Analyze current wiki state and return structured report for curation."""
    index_file = wiki_root / "INDEX.md"
    has_index = index_file.exists()
    index_lines = len(index_file.read_text(encoding="utf-8").splitlines()) if has_index else 0

    articles = list(wiki_root.rglob("*.md"))
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
    state = analyze_wiki_state(wiki_root)
    lint_report = lint_wiki()

    lines: list[str] = [
        "# Brain-79 — State-Aware Ingest & Curation Guide",
        "",
        "Use this guide to structure and curate session knowledge into the project wiki.",
        "",
        "## Current Wiki Health Overview",
        f"- **Articles in Wiki**: {state.article_count}",
        f"- **INDEX.md Line Count**: {state.index_line_count} / 150 max lines",
        f"- **Active Health Issues**: {state.critical_count} error(s), {state.warning_count} warning(s)",
        "",
    ]

    if state.issues_summary:
        lines.append("### Specific Violations Needing Remediation")
        lines.extend(state.issues_summary)
        lines.append("")

    lines.extend([
        "## Mandatory Curation Rules",
        "1. Every new or updated article MUST include valid YAML frontmatter containing `type` and `last_updated`.",
        "2. Architectural decisions MUST be created as separate files in `decisions/` (never declared inline).",
        "3. Technical debt items MUST be recorded in `features/` or `decisions/`.",
        "4. `INDEX.md` MUST remain under 150 lines and contain ONLY whitelisted H2 section headers (`Project`, `Current focus`, `Quick navigation`, `Known issues`, `Roadmap`).",
        "",
        "## Step-by-Step Curation Workflow",
        "1. **Extract**: Identify new features, architectural decisions, or established conventions from session history.",
        "2. **Atomic Write**: Update existing target files or create new files in designated subdirectories (`features/`, `decisions/`, `architecture/`, `product/`).",
        "3. **Navigation Sync**: Register new articles using `brain79 navigate --regenerate` or MCP `brain79_navigate(regenerate=True)`.",
        "4. **Lint Verification**: Execute `brain79 lint --strict` to verify zero violations remain.",
        "",
    ])

    if raw_content:
        lines.append("## Session Input Snippet")
        snippet_lines = raw_content.splitlines()[:50]
        lines.extend(f"> {line_item}" for line_item in snippet_lines)
        lines.append("")

    lines.append("## Diagnostic Summary")
    lines.append(lint_report)

    # Apply 500 lines hard limit cap
    if len(lines) > 500:
        lines = lines[:495] + ["", "... [Curation guide capped at 500 lines]"]

    return "\n".join(lines)
