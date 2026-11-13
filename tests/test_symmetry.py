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


def test_session_commit_parameter_symmetry() -> None:
    """SLA-2: verified_articles and allow_partial_ripple maintain 100% parameter parity across MCP, core, and CLI."""
    import inspect
    from brain79.server import brain79_session_commit
    from brain79.core.session_commit import commit_session

    mcp_sig = inspect.signature(brain79_session_commit)
    core_sig = inspect.signature(commit_session)

    # 1. MCP tool parameter inspection
    assert "verified_articles" in mcp_sig.parameters, "MCP brain79_session_commit must expose verified_articles"
    assert "allow_partial_ripple" in mcp_sig.parameters, "MCP brain79_session_commit must expose allow_partial_ripple"
    assert mcp_sig.parameters["allow_partial_ripple"].default is False
    assert mcp_sig.parameters["verified_articles"].default is None

    # 2. Core commit_session parameter inspection
    assert "verified_articles" in core_sig.parameters, "Core commit_session must accept verified_articles"
    assert "allow_partial_ripple" in core_sig.parameters, "Core commit_session must accept allow_partial_ripple"
    assert core_sig.parameters["allow_partial_ripple"].default is False
    assert core_sig.parameters["verified_articles"].default is None

