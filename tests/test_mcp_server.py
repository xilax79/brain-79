"""Tests for configurable MCP server factory (Phase 10 Stage 4: R-4.3, AC-10.12)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from brain79.server import ADMIN_TOOLS, CORE_TOOLS, create_mcp_server, mcp


def _registered_tool_names(server: object) -> set[str]:
    tools = asyncio.run(server.list_tools())  # type: ignore[attr-defined]
    return {t.name for t in tools}


def test_create_mcp_server_core_and_full_profiles() -> None:
    """AC-10.12: core profile registers only CORE_TOOLS; full profile registers all 22 tools."""
    assert CORE_TOOLS.isdisjoint(ADMIN_TOOLS)
    assert len(CORE_TOOLS | ADMIN_TOOLS) == 22

    core_server = create_mcp_server(profile="core")
    core_names = _registered_tool_names(core_server)
    assert core_names == CORE_TOOLS

    full_server = create_mcp_server(profile="full")
    full_names = _registered_tool_names(full_server)
    assert full_names == (CORE_TOOLS | ADMIN_TOOLS)
    assert len(full_names) == 22

    # Module-level mcp retains full 22-tool parity
    default_names = _registered_tool_names(mcp)
    assert default_names == full_names

    with pytest.raises(ValueError, match="Invalid MCP profile"):
        create_mcp_server(profile="invalid")  # type: ignore[arg-type]


def test_cli_mcp_profile_flag_dispatch(tmp_path: Path) -> None:
    """R-4.3: __main__.main supports --mcp-profile core|full and rejects invalid profiles with exit 2."""
    from unittest.mock import MagicMock, patch

    from brain79.__main__ import main

    # 1. --mcp-profile core invokes create_mcp_server(profile="core").run()
    fake_core = MagicMock()
    with patch("brain79.server.create_mcp_server", return_value=fake_core) as mock_factory:
        main(["--project-root", str(tmp_path), "--mcp-profile", "core"])
        mock_factory.assert_called_once_with(profile="core")
        fake_core.run.assert_called_once()

    # 2. --mcp-profile=full invokes mcp.run()
    with patch("brain79.server.mcp.run") as mock_full_run:
        main(["--project-root", str(tmp_path), "--mcp-profile=full"])
        mock_full_run.assert_called_once()

    # 3. Invalid --mcp-profile exits with code 2
    with pytest.raises(SystemExit) as exc_info:
        main(["--mcp-profile", "invalid"])
    assert exc_info.value.code == 2
