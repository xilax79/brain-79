"""Standard .mcp.json harness adapter."""

from __future__ import annotations

import json
from pathlib import Path


class McpJsonAdapter:
    """HarnessAdapter for root .mcp.json (Claude Code / OpenCode / standard MCP)."""

    name: str = "mcp_json"

    def detect(self, project_root: Path) -> bool:
        return (project_root / ".mcp.json").is_file()

    def sync(self, project_root: Path) -> list[str]:
        from brain79.core.init_project import sync_project_mcp_configs

        sync_project_mcp_configs(project_root)
        return [".mcp.json"]

    def diagnose(self, project_root: Path) -> list[str]:
        mcp_path = project_root / ".mcp.json"
        if not mcp_path.is_file():
            return [".mcp.json is missing."]
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "brain79" not in data.get("mcpServers", {}):
                return [".mcp.json does not register the 'brain79' MCP server."]
        except (OSError, json.JSONDecodeError) as exc:
            return [f".mcp.json is unreadable or invalid JSON: {exc}"]
        return []
