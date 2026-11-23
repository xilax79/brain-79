"""Tests for focused 9-tool MCP server surface and CLI profile removal (Phase 13: AC-1, AC-2, AC-3, AC-5)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

import brain79.server as server_mod
from brain79 import __version__
from brain79.server import MCP_TOOLS, create_mcp_server, mcp

EXPECTED_MCP_TOOLS = frozenset({
    "brain79_orient",
    "brain79_session_commit",
    "brain79_read",
    "brain79_read_batch",
    "brain79_edit",
    "brain79_context",
    "brain79_search",
    "brain79_lint",
    "brain79_bootstrap",
})

PRUNED_MCP_TOOLS = frozenset({
    "brain79_index",
    "brain79_schema",
    "brain79_write",
    "brain79_write_many",
    "brain79_list",
    "brain79_ingest",
    "brain79_handoff_read",
    "brain79_handoff_write",
    "brain79_handoff_purge",
    "brain79_navigate",
    "brain79_migrate",
    "brain79_update_project",
    "brain79_doctor",
})


def _registered_tool_names(server: object) -> set[str]:
    tools = asyncio.run(server.list_tools())  # type: ignore[attr-defined]
    return {t.name for t in tools}


def test_create_mcp_server_focused_surface() -> None:
    """AC-1: create_mcp_server() and mcp expose exactly the 9 MCP_TOOLS; pruned symbols removed."""
    assert MCP_TOOLS == EXPECTED_MCP_TOOLS
    assert len(MCP_TOOLS) == 9

    default_server = create_mcp_server()
    assert _registered_tool_names(default_server) == MCP_TOOLS
    assert _registered_tool_names(mcp) == MCP_TOOLS
    assert default_server.version == __version__
    assert mcp.version == __version__

    assert not hasattr(server_mod, "ADMIN_TOOLS")
    for pruned in PRUNED_MCP_TOOLS:
        assert not hasattr(server_mod, pruned), f"Pruned symbol {pruned} must not exist on brain79.server"

    with pytest.raises(TypeError):
        create_mcp_server(profile="full")  # type: ignore[call-arg]


def test_mcp_server_instructions_clean() -> None:
    """AC-2: server.instructions references only MCP_TOOLS and CLI, with zero stale references."""
    server = create_mcp_server()
    instructions = server.instructions or ""

    assert "brain79_orient" in instructions
    assert "brain79_session_commit" in instructions
    assert "brain79" in instructions
    assert "--mcp-profile" not in instructions
    assert "BRAIN79_MCP_PROFILE" not in instructions

    for pruned in PRUNED_MCP_TOOLS:
        assert pruned not in instructions, (
            f"Server instructions must not reference pruned tool '{pruned}'"
        )


def test_cli_removed_mcp_profile_and_env_var_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-3: --mcp-profile exits 2 with migration error; BRAIN79_MCP_PROFILE is silently ignored."""
    from brain79.__main__ import main

    # 1. --mcp-profile full -> stderr error + exit 2
    with pytest.raises(SystemExit) as exc1:
        main(["--mcp-profile", "full"])
    assert exc1.value.code == 2
    err1 = capsys.readouterr().err
    assert "--mcp-profile" in err1
    assert "v0.14.0" in err1

    # 2. --mcp-profile=core -> stderr error + exit 2
    with pytest.raises(SystemExit) as exc2:
        main(["--mcp-profile=core"])
    assert exc2.value.code == 2
    err2 = capsys.readouterr().err
    assert "--mcp-profile" in err2
    assert "v0.14.0" in err2

    # 3. --help has zero --mcp-profile or BRAIN79_MCP_PROFILE
    with pytest.raises(SystemExit) as exc_help:
        main(["--help"])
    assert exc_help.value.code == 0
    help_out = capsys.readouterr().out
    assert "--mcp-profile" not in help_out
    assert "BRAIN79_MCP_PROFILE" not in help_out

    # 4. BRAIN79_MCP_PROFILE=full during MCP stdio startup is silently ignored (zero stderr)
    monkeypatch.setenv("BRAIN79_MCP_PROFILE", "full")
    with patch("brain79.server.mcp.run") as mock_run:
        main(["--project-root", str(tmp_path)])
        mock_run.assert_called_once()
    captured = capsys.readouterr()
    assert captured.err == ""


def test_runtime_hints_and_templates_clean() -> None:
    """AC-5: core runtime hints and packaged templates contain zero pruned MCP tool or profile references."""
    repo_root = Path(__file__).resolve().parent.parent
    files_to_scan = [
        repo_root / "src" / "brain79" / "core" / "orient.py",
        repo_root / "src" / "brain79" / "core" / "handoff.py",
        repo_root / "src" / "brain79" / "core" / "bootstrap.py",
        repo_root / "src" / "brain79" / "templates" / "AGENTS.md",
        repo_root / "src" / "brain79" / "templates" / "SKILL.md",
        repo_root / "src" / "brain79" / "templates" / "SCHEMA.md",
        repo_root / "src" / "brain79" / "templates" / "SCHEMA_GENERAL.md",
    ]
    for path in files_to_scan:
        text = path.read_text(encoding="utf-8")
        assert "--mcp-profile" not in text, f"--mcp-profile found in {path.name}"
        assert "BRAIN79_MCP_PROFILE" not in text, f"BRAIN79_MCP_PROFILE found in {path.name}"
        for pruned in PRUNED_MCP_TOOLS:
            assert pruned not in text, f"Pruned tool '{pruned}' found in {path.name}"

    bootstrap_text = (repo_root / "src" / "brain79" / "core" / "bootstrap.py").read_text(encoding="utf-8")
    assert "generated_by: brain79_bootstrap" in bootstrap_text

    living_manuals = sorted(
        list((repo_root / ".brain-79" / "features").glob("*.md"))
        + list((repo_root / ".brain-79" / "product").glob("*.md"))
    )
    assert living_manuals, "Expected living manuals under .brain-79/features and .brain-79/product"
    for manual in living_manuals:
        manual_text = manual.read_text(encoding="utf-8")
        for pruned in PRUNED_MCP_TOOLS:
            assert pruned not in manual_text, f"Pruned tool '{pruned}' found in living manual {manual.name}"
