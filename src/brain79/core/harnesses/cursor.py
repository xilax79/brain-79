"""Cursor (.cursor/mcp.json) harness adapter."""

from __future__ import annotations

import json
from pathlib import Path


class CursorAdapter:
    """HarnessAdapter for Cursor IDE .cursor/mcp.json."""

    name: str = "cursor"

    def detect(self, project_root: Path) -> bool:
        return (project_root / ".cursor" / "mcp.json").is_file()

    def sync(self, project_root: Path) -> list[str]:
        from brain79.core.init_project import sync_project_mcp_configs

        sync_project_mcp_configs(project_root)
        return [".cursor/mcp.json"]

    def diagnose(self, project_root: Path) -> list[str]:
        cursor_path = project_root / ".cursor" / "mcp.json"
        if not cursor_path.is_file():
            return [".cursor/mcp.json is missing."]
        try:
            data = json.loads(cursor_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "brain79" not in data.get("mcpServers", {}):
                return [".cursor/mcp.json does not register the 'brain79' MCP server."]
        except (OSError, json.JSONDecodeError) as exc:
            return [f".cursor/mcp.json is unreadable or invalid JSON: {exc}"]
        return []
