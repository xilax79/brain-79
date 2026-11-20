"""GitHub Copilot (.github/copilot-instructions.md) native instruction harness adapter."""

from __future__ import annotations

from pathlib import Path

from brain79.core.harnesses._delimited import (
    diagnose_delimited_file,
    render_compact_harness_block,
    sync_delimited_file,
)


class CopilotAdapter:
    """HarnessAdapter for .github/copilot-instructions.md delimited protocol block."""

    name: str = "copilot"

    def detect(self, project_root: Path) -> bool:
        return (project_root / ".github" / "copilot-instructions.md").is_file()

    def sync(self, project_root: Path, dry_run: bool = False) -> list[str]:
        target = project_root / ".github" / "copilot-instructions.md"
        block = render_compact_harness_block()
        changed, _ = sync_delimited_file(target, block, dry_run=dry_run)
        return [".github/copilot-instructions.md"] if changed else []

    def diagnose(self, project_root: Path) -> list[str]:
        return diagnose_delimited_file(
            project_root / ".github" / "copilot-instructions.md",
            rel_label=".github/copilot-instructions.md",
            required=False,
        )
