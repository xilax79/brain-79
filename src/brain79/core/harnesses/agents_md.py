"""AGENTS.md harness adapter."""

from __future__ import annotations

from pathlib import Path

from brain79.core.harnesses._delimited import diagnose_delimited_file


class AgentsMdAdapter:
    """HarnessAdapter for root AGENTS.md delimited protocol block."""

    name: str = "agents_md"

    def detect(self, project_root: Path) -> bool:
        return (project_root / "AGENTS.md").is_file()

    def sync(self, project_root: Path) -> list[str]:
        from brain79.core.init_project import sync_agents_manifest

        sync_agents_manifest(project_root)
        return ["AGENTS.md"]

    def diagnose(self, project_root: Path) -> list[str]:
        return diagnose_delimited_file(
            project_root / "AGENTS.md",
            rel_label="AGENTS.md",
            required=True,
        )
