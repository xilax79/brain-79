import inspect

import pytest

from brain79.cli.dispatch import WHITELIST
from brain79.server import MCP_TOOLS, create_mcp_server, mcp


@pytest.mark.asyncio
async def test_mcp_cli_symmetry() -> None:
    """Validate MCP-subset / CLI-superset invariant (9 focused MCP tools subset of 26 CLI subcommands)."""
    server = create_mcp_server()
    try:
        tools = await server.list_tools()
        raw_names = {t.name for t in tools}
        mcp_cli_names = {
            t.name.removeprefix("brain79_").replace("_", "-") for t in tools
        }

        cli_subs = set(WHITELIST)

        assert len(cli_subs) == 26, f"Expected 26 CLI subcommands, got {len(cli_subs)}"
        assert len(MCP_TOOLS) == 9, f"Expected 9 MCP tools, got {len(MCP_TOOLS)}"
        assert raw_names == MCP_TOOLS
        assert mcp_cli_names.issubset(cli_subs), (
            f"MCP tools {mcp_cli_names - cli_subs} not present in CLI subcommands"
        )

        # Module-level mcp matches create_mcp_server()
        default_tools = await mcp.list_tools()
        assert {t.name for t in default_tools} == MCP_TOOLS
    finally:
        for srv in (server, mcp):
            if hasattr(srv, "close") and callable(getattr(srv, "close")):
                res = srv.close()
                if hasattr(res, "__await__"):
                    await res


def test_session_commit_parameter_symmetry() -> None:
    """SLA-2: verified_articles and allow_partial_ripple maintain 100% parameter parity across MCP, core, and CLI."""
    from brain79.core.session_commit import commit_session
    from brain79.server import brain79_session_commit

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


def test_bootstrap_parameter_symmetry() -> None:
    """Phase 12/13: retained brain79_bootstrap (auto_map, max_modules) maintains CLI/MCP/core parity."""
    from brain79.core.bootstrap import run_bootstrap
    from brain79.server import brain79_bootstrap

    mcp_bs = inspect.signature(brain79_bootstrap)
    core_bs = inspect.signature(run_bootstrap)
    assert "auto_map" in mcp_bs.parameters and "auto_map" in core_bs.parameters
    assert mcp_bs.parameters["auto_map"].default is False
    assert core_bs.parameters["auto_map"].default is False
    assert "max_modules" in mcp_bs.parameters and "max_modules" in core_bs.parameters
    assert mcp_bs.parameters["max_modules"].default == 12
    assert core_bs.parameters["max_modules"].default == 12
