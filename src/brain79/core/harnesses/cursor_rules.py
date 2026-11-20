"""Cursor IDE (.cursor/rules/brain79.mdc) native instruction harness adapter."""

from __future__ import annotations

from pathlib import Path

from brain79.core.harnesses._delimited import (
    diagnose_delimited_file,
    render_compact_harness_block,
    sync_delimited_file,
)

_MDC_FRONTMATTER = (
    "---\n"
    "description: Brain-79 persistent AI memory protocol and wiki governance rules\n"
    "alwaysApply: true\n"
    "---\n\n"
)


class CursorRulesAdapter:
    """HarnessAdapter for Cursor .cursor/rules/brain79.mdc rule file."""

    name: str = "cursor_rules"

    def detect(self, project_root: Path) -> bool:
        return (project_root / ".cursor" / "rules" / "brain79.mdc").is_file()

    def sync(self, project_root: Path, dry_run: bool = False) -> list[str]:
        target = project_root / ".cursor" / "rules" / "brain79.mdc"
        block = render_compact_harness_block()
        initial = _MDC_FRONTMATTER + block + "\n"
        changed, _ = sync_delimited_file(
            target,
            block,
            full_initial_content=initial,
            dry_run=dry_run,
        )
        return [".cursor/rules/brain79.mdc"] if changed else []

    def diagnose(self, project_root: Path) -> list[str]:
        target = project_root / ".cursor" / "rules" / "brain79.mdc"
        issues = diagnose_delimited_file(
            target,
            rel_label=".cursor/rules/brain79.mdc",
            required=False,
        )
        if not issues and target.is_file():
            content = target.read_text(encoding="utf-8", errors="replace")
            if "alwaysApply: true" not in content:
                issues.append(".cursor/rules/brain79.mdc is missing 'alwaysApply: true' in MDC frontmatter.")
        return issues
