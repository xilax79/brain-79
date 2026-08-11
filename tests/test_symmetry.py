import pytest

from brain79.cli.dispatch import WHITELIST
from brain79.server import mcp


@pytest.mark.asyncio
async def test_mcp_cli_symmetry() -> None:
    """Validate static symmetry: mcp_tools ⊆ cli_subs and cli_subs - mcp_tools == {'init', 'update'}."""
    try:
        tools = await mcp.list_tools()
        mcp_tool_names = {
            t.name.removeprefix("brain79_").replace("_", "-") for t in tools
        }

        cli_subs = set(WHITELIST)

        assert mcp_tool_names.issubset(cli_subs), (
            f"MCP tools {mcp_tool_names - cli_subs} not present in CLI subcommands"
        )
        assert cli_subs - mcp_tool_names == {"init", "update"}, (
            f"Unexpected difference between CLI and MCP: {cli_subs - mcp_tool_names}"
        )
    finally:
        if hasattr(mcp, "close") and callable(getattr(mcp, "close")):
            res = mcp.close()
            if hasattr(res, "__await__"):
                await res
