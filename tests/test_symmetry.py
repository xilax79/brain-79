import pytest

from brain79.cli.dispatch import WHITELIST
from brain79.server import ADMIN_TOOLS, CORE_TOOLS, create_mcp_server, mcp


@pytest.mark.asyncio
async def test_mcp_cli_symmetry() -> None:
    """Validate static symmetry for both full (22 tools) and default core (8 tools) profiles."""
    full_server = create_mcp_server(profile="full")
    try:
        full_tools = await full_server.list_tools()
        full_tool_names = {
            t.name.removeprefix("brain79_").replace("_", "-") for t in full_tools
        }

        cli_subs = set(WHITELIST)

        assert len(cli_subs) == 24, f"Expected 24 CLI subcommands, got {len(cli_subs)}"
        assert len(full_tool_names) == 22, f"Expected 22 MCP full tools, got {len(full_tool_names)}"
        assert full_tool_names.issubset(cli_subs), (
            f"MCP tools {full_tool_names - cli_subs} not present in CLI subcommands"
        )
        assert cli_subs - full_tool_names == {"init", "update"}, (
            f"Unexpected difference between CLI and MCP: {cli_subs - full_tool_names}"
        )

        # Default module-level mcp uses core profile (8 hot-path tools), all present in full
        core_tools = await mcp.list_tools()
        core_raw_names = {t.name for t in core_tools}
        core_tool_names = {
            t.name.removeprefix("brain79_").replace("_", "-") for t in core_tools
        }
        assert len(CORE_TOOLS) == 8
        assert len(ADMIN_TOOLS) == 14
        assert CORE_TOOLS.isdisjoint(ADMIN_TOOLS)
        assert len(CORE_TOOLS | ADMIN_TOOLS) == 22
        assert core_raw_names == CORE_TOOLS
        assert core_tool_names.issubset(full_tool_names)
    finally:
        for srv in (full_server, mcp):
            if hasattr(srv, "close") and callable(getattr(srv, "close")):
                res = srv.close()
                if hasattr(res, "__await__"):
                    await res


def test_update_project_and_doctor_parameter_symmetry() -> None:
    """Validate parameter symmetry for update-project and doctor between MCP and core."""
    import inspect
    from brain79.core.doctor import run_doctor
    from brain79.core.init_project import update_project
    from brain79.server import brain79_doctor, brain79_update_project

    # 1. update_project
    mcp_up = inspect.signature(brain79_update_project)
    core_up = inspect.signature(update_project)
    for p in ("dry_run", "commit_transition", "include_desktop"):
        assert p in mcp_up.parameters
        assert p in core_up.parameters
        assert mcp_up.parameters[p].default is False

    # 2. doctor
    mcp_doc = inspect.signature(brain79_doctor)
    core_doc = inspect.signature(run_doctor)
    for p in ("fix", "force", "include_desktop"):
        assert p in mcp_doc.parameters
        assert p in core_doc.parameters
        assert mcp_doc.parameters[p].default is False
    assert "format" in mcp_doc.parameters
    assert mcp_doc.parameters["format"].default == "text"


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

