"""Antigravity CLI (.agents/mcp_config.json and .agents/plugins/brain79/) harness adapter."""

from __future__ import annotations

import json
from pathlib import Path


class AntigravityAdapter:
    """HarnessAdapter for Antigravity CLI (.agents/mcp_config.json + plugin)."""

    name: str = "antigravity"

    def detect(self, project_root: Path) -> bool:
        return (
            (project_root / ".agents" / "mcp_config.json").is_file()
            or (project_root / ".agents" / "plugins" / "brain79").is_dir()
        )

    def sync(self, project_root: Path) -> list[str]:
        from brain79.core.init_project import sync_project_mcp_configs

        sync_project_mcp_configs(project_root, targets={"antigravity"})
        return [".agents/mcp_config.json", ".agents/plugins/brain79/"]

    def diagnose(self, project_root: Path) -> list[str]:
        issues: list[str] = []
        mcp_cfg = project_root / ".agents" / "mcp_config.json"
        if not mcp_cfg.is_file():
            issues.append(".agents/mcp_config.json is missing.")
        else:
            try:
                data = json.loads(mcp_cfg.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or "brain79" not in data.get("mcpServers", {}):
                    issues.append(".agents/mcp_config.json does not register 'brain79'.")
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(f".agents/mcp_config.json is invalid JSON: {exc}")

        plugin_dir = project_root / ".agents" / "plugins" / "brain79"
        if not (plugin_dir / ".mcp.json").is_file():
            issues.append(".agents/plugins/brain79/.mcp.json is missing.")
        return issues
