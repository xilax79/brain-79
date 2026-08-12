import json
from pathlib import Path
import shutil
import pytest

from brain79.core.init_project import WIKI_DIRS, init_project


def test_init_project_fresh(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test initializing brain79 in a clean directory."""
    init_project(tmp_path)

    # Check wiki structure
    wiki_root = tmp_path / ".brain-79"
    assert wiki_root.exists()
    for dir_path in WIKI_DIRS:
        assert (wiki_root / dir_path).is_dir()
        assert (wiki_root / dir_path / ".gitkeep").exists()

    # Check template files inside wiki
    assert (wiki_root / "SCHEMA.md").exists()
    assert (wiki_root / "INDEX.md").exists()
    assert (wiki_root / ".gitignore").exists()
    gitignore_content = (wiki_root / ".gitignore").read_text(encoding="utf-8")
    assert "*.lock" in gitignore_content
    assert "*.tmp" in gitignore_content

    # Check .agents/mcp_config.json
    mcp_config_path = tmp_path / ".agents" / "mcp_config.json"
    assert mcp_config_path.exists()
    agents_data = json.loads(mcp_config_path.read_text(encoding="utf-8"))
    assert "brain79" in agents_data["mcpServers"]

    # Check AGENTS.md
    agents_manifest = tmp_path / "AGENTS.md"
    assert agents_manifest.exists()
    manifest_content = agents_manifest.read_text(encoding="utf-8")
    assert "# Brain-79 AI Memory Protocol" in manifest_content
    assert "pi-mcp-adapter" in manifest_content
    assert "brain79_index" in manifest_content

    # Check .mcp.json
    mcp_json = tmp_path / ".mcp.json"
    assert mcp_json.exists()
    mcp_data = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert "brain79" in mcp_data["mcpServers"]
    assert mcp_data["mcpServers"]["brain79"]["args"] == ["--project-root", "."]

    captured = capsys.readouterr()
    assert "Initialized .brain-79/" in captured.out
    assert "AGENTS.md" in captured.out
    assert ".mcp.json" in captured.out


def test_init_project_already_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test init_project when .brain-79 already exists."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()

    init_project(tmp_path)

    captured = capsys.readouterr()
    assert f"Wiki already exists at {wiki_root}" in captured.out


def test_init_project_existing_agents_manifest(tmp_path: Path) -> None:
    """Test idempotent handling when AGENTS.md already exists."""
    agents_manifest = tmp_path / "AGENTS.md"
    agents_manifest.write_text(
        "# Pre-existing Instructions\n\n- Do not break things.", encoding="utf-8"
    )

    init_project(tmp_path)

    content = agents_manifest.read_text(encoding="utf-8")
    assert "# Pre-existing Instructions" in content
    assert "# Brain-79 AI Memory Protocol" in content

    # Second run should not append again if already present
    wiki_root = tmp_path / ".brain-79"
    shutil.rmtree(wiki_root)

    init_project(tmp_path)
    content2 = agents_manifest.read_text(encoding="utf-8")
    assert content2.count("# Brain-79 AI Memory Protocol") == 1


def test_init_project_existing_mcp_json(tmp_path: Path) -> None:
    """Test idempotent merging with existing .mcp.json."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"other_tool": {"command": "other", "args": []}}}),
        encoding="utf-8",
    )

    init_project(tmp_path)

    mcp_data = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert "other_tool" in mcp_data["mcpServers"]
    assert "brain79" in mcp_data["mcpServers"]
    assert mcp_data["mcpServers"]["other_tool"]["command"] == "other"


def test_init_project_existing_mcp_json_overwrite_brain79(tmp_path: Path) -> None:
    """Test updating pre-existing brain79 entry in .mcp.json."""
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "brain79": {"command": "old_brain79_path", "args": ["old"]},
                    "other": {"command": "other"},
                }
            }
        ),
        encoding="utf-8",
    )

    init_project(tmp_path)

    mcp_data = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert "other" in mcp_data["mcpServers"]
    assert mcp_data["mcpServers"]["brain79"]["args"] == ["--project-root", "."]


def test_init_project_corrupt_mcp_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test handling of corrupt .mcp.json file by creating backup and clean config."""
    mcp_json = tmp_path / ".mcp.json"
    corrupt_content = "NOT_VALID_JSON{"
    mcp_json.write_text(corrupt_content, encoding="utf-8")

    init_project(tmp_path)

    # Check backup file
    backup_file = tmp_path / ".mcp.json.bak"
    assert backup_file.exists()
    assert backup_file.read_text(encoding="utf-8") == corrupt_content

    # Check new .mcp.json
    mcp_data = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert "brain79" in mcp_data["mcpServers"]

    captured = capsys.readouterr()
    assert "invalid JSON" in captured.out
    assert "Backing up to" in captured.out


def test_init_project_mcp_json_is_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test defensive handling when .mcp.json is a directory."""
    mcp_json_dir = tmp_path / ".mcp.json"
    mcp_json_dir.mkdir()

    init_project(tmp_path)

    captured = capsys.readouterr()
    assert "exists and is a directory" in captured.out


def test_init_schema_template_compliance(tmp_path: Path) -> None:
    """Verify that freshly initialized project reports warnings for unfilled placeholders, and passes [Status: OK] once customized."""
    from brain79.config import set_project_root
    from brain79.core.lint import lint_wiki

    set_project_root(tmp_path)
    init_project(tmp_path)

    report = lint_wiki()
    assert "[Status: WARNING]" in report

    clean_index = """---
type: navigation
last_updated: 2026-08-11
---

# Project index

## Project

**Name:** Test
**Purpose:** Test purpose.
**Status:** Active

## Current focus
- Testing.

## Known issues
- None.

## Roadmap
- None.
"""
    (tmp_path / ".brain-79" / "INDEX.md").write_text(clean_index, encoding="utf-8")
    report_custom = lint_wiki()
    assert "[Status: OK]" in report_custom
