"""Tests for configurable MCP server factory and core default profile (Phase 11 Stage 3: AC-11.7, AC-11.8)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain79.server import ADMIN_TOOLS, CORE_TOOLS, create_mcp_server, mcp


def _registered_tool_names(server: object) -> set[str]:
    tools = asyncio.run(server.list_tools())  # type: ignore[attr-defined]
    return {t.name for t in tools}


def test_create_mcp_server_core_default_and_full_profiles() -> None:
    """AC-11.7: create_mcp_server() defaults to 8-tool core profile; full registers all 22 tools."""
    assert len(CORE_TOOLS) == 8
    assert len(ADMIN_TOOLS) == 14
    assert CORE_TOOLS.isdisjoint(ADMIN_TOOLS)
    assert len(CORE_TOOLS | ADMIN_TOOLS) == 22

    # Default create_mcp_server() and module-level mcp both use core (8 tools)
    default_server = create_mcp_server()
    assert _registered_tool_names(default_server) == CORE_TOOLS
    assert _registered_tool_names(mcp) == CORE_TOOLS

    core_server = create_mcp_server(profile="core")
    assert _registered_tool_names(core_server) == CORE_TOOLS

    full_server = create_mcp_server(profile="full")
    full_names = _registered_tool_names(full_server)
    assert full_names == (CORE_TOOLS | ADMIN_TOOLS)
    assert len(full_names) == 22

    with pytest.raises(ValueError, match="Invalid MCP profile"):
        create_mcp_server(profile="invalid")  # type: ignore[arg-type]


def test_core_instructions_never_reference_admin_tools() -> None:
    """AC-11.8: core server instructions must not reference any tool absent from CORE_TOOLS."""
    core_server = create_mcp_server(profile="core")
    core_instructions = core_server.instructions or ""
    assert "brain79_orient" in core_instructions
    assert "brain79_session_commit" in core_instructions
    for admin_tool in ADMIN_TOOLS:
        assert admin_tool not in core_instructions, (
            f"Core instructions must not reference admin tool '{admin_tool}'"
        )

    full_server = create_mcp_server(profile="full")
    full_instructions = full_server.instructions or ""
    assert "brain79_orient" in full_instructions
    assert "brain79_schema" in full_instructions


def test_cli_mcp_profile_precedence_and_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-11.7: CLI --mcp-profile > BRAIN79_MCP_PROFILE > default 'core'; invalid values exit 2."""
    from brain79.__main__ import main

    # 1. Default (no flag, no env var) -> core profile via mcp.run()
    monkeypatch.delenv("BRAIN79_MCP_PROFILE", raising=False)
    with patch("brain79.server.mcp.run") as mock_core_run:
        main(["--project-root", str(tmp_path)])
        mock_core_run.assert_called_once()

    # 2. BRAIN79_MCP_PROFILE=full -> full profile
    monkeypatch.setenv("BRAIN79_MCP_PROFILE", "full")
    fake_full = MagicMock()
    with patch("brain79.server.create_mcp_server", return_value=fake_full) as mock_factory:
        main(["--project-root", str(tmp_path)])
        mock_factory.assert_called_once_with(profile="full")
        fake_full.run.assert_called_once()

    # 3. CLI flag overrides env var (BRAIN79_MCP_PROFILE=full + --mcp-profile core -> core)
    monkeypatch.setenv("BRAIN79_MCP_PROFILE", "full")
    with patch("brain79.server.mcp.run") as mock_core_run:
        main(["--project-root", str(tmp_path), "--mcp-profile", "core"])
        mock_core_run.assert_called_once()

    # 4. --mcp-profile=full overrides default
    monkeypatch.delenv("BRAIN79_MCP_PROFILE", raising=False)
    fake_full2 = MagicMock()
    with patch("brain79.server.create_mcp_server", return_value=fake_full2) as mock_factory2:
        main(["--project-root", str(tmp_path), "--mcp-profile=full"])
        mock_factory2.assert_called_once_with(profile="full")
        fake_full2.run.assert_called_once()

    # 5. Invalid --mcp-profile exits with code 2
    with pytest.raises(SystemExit) as exc_info:
        main(["--mcp-profile", "invalid"])
    assert exc_info.value.code == 2

    # 6. Invalid BRAIN79_MCP_PROFILE exits with code 2
    monkeypatch.setenv("BRAIN79_MCP_PROFILE", "bogus")
    with pytest.raises(SystemExit) as exc_info2:
        main(["--project-root", str(tmp_path)])
    assert exc_info2.value.code == 2
