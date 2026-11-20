"""AGENTS.md harness adapter."""

from __future__ import annotations

from pathlib import Path


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
        agents_md = project_root / "AGENTS.md"
        if not agents_md.is_file():
            return ["AGENTS.md is missing."]
        text = agents_md.read_text(encoding="utf-8", errors="replace")
        if "<!-- brain79:start" not in text or "<!-- brain79:end -->" not in text:
            return ["AGENTS.md is missing the delimited brain79 protocol block."]
        return []
