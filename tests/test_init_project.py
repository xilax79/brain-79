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
    assert "# Brain-79 AI memory protocol" in manifest_content
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
    assert "# Brain-79 AI memory protocol" in content

    # Second run should not append again if already present
    wiki_root = tmp_path / ".brain-79"
    shutil.rmtree(wiki_root)

    init_project(tmp_path)
    content2 = agents_manifest.read_text(encoding="utf-8")
    assert content2.count("# Brain-79 AI memory protocol") == 1


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
    """Verify that freshly initialized project passes linting cleanly with pure index routing table and has zero-modification invariant."""
    from brain79.config import set_project_root
    from brain79.core.lint import lint_wiki

    set_project_root(tmp_path)
    init_project(tmp_path)

    report = lint_wiki()
    assert "[Status: OK]" in report

    # Verify AGENTS.md includes No-Op idempotence rule
    agents_content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "No-Op Idempotence" in agents_content
    assert "Zero-Modification Rule" in agents_content

    # Verify SCHEMA.md includes operational invariants
    schema_content = (tmp_path / ".brain-79" / "SCHEMA.md").read_text(encoding="utf-8")
    assert "Zero-Modification Idempotence" in schema_content


def test_init_project_creates_agy_plugin_and_retains_legacy_agents_mcp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test fresh init_project generates Antigravity plugin and retains legacy .agents/mcp_config.json."""
    init_project(tmp_path)

    # 1. .agents/plugins/brain79/plugin.json
    plugin_json = tmp_path / ".agents" / "plugins" / "brain79" / "plugin.json"
    assert plugin_json.is_file()
    plugin_data = json.loads(plugin_json.read_text(encoding="utf-8"))
    assert plugin_data == {"name": "brain79"}

    # 2. .agents/plugins/brain79/mcp_config.json
    plugin_mcp = tmp_path / ".agents" / "plugins" / "brain79" / "mcp_config.json"
    assert plugin_mcp.is_file()
    plugin_mcp_data = json.loads(plugin_mcp.read_text(encoding="utf-8"))
    assert "brain79" in plugin_mcp_data.get("mcpServers", {})
    srv = plugin_mcp_data["mcpServers"]["brain79"]
    assert srv["command"] == "brain79"
    assert srv["args"] == ["--project-root", "."]
    assert "toolPrefix" not in srv

    # 3. .agents/plugins/brain79/skills/brain79-wiki/SKILL.md
    skill_file = tmp_path / ".agents" / "plugins" / "brain79" / "skills" / "brain79-wiki" / "SKILL.md"
    assert skill_file.is_file()
    skill_content = skill_file.read_text(encoding="utf-8")
    assert skill_content.startswith("---\nname: brain79-wiki\n")
    assert "description:" in skill_content

    # 4. Retained legacy .agents/mcp_config.json
    legacy_mcp = tmp_path / ".agents" / "mcp_config.json"
    assert legacy_mcp.is_file()
    legacy_data = json.loads(legacy_mcp.read_text(encoding="utf-8"))
    assert "brain79" in legacy_data.get("mcpServers", {})

    captured = capsys.readouterr()
    assert ".agents/plugins/brain79/" in captured.out


def test_sync_project_mcp_configs_preserves_custom_fields_in_plugin_json(
    tmp_path: Path,
) -> None:
    """Test re-run / update_project preserves custom fields in plugin.json and third-party mcpServers."""
    from brain79.core.init_project import sync_project_mcp_configs

    plugin_dir = tmp_path / ".agents" / "plugins" / "brain79"
    plugin_dir.mkdir(parents=True)
    plugin_json = plugin_dir / "plugin.json"
    plugin_json.write_text(
        json.dumps({"name": "custom-name", "disabled": True, "author": "acme"}, indent=2),
        encoding="utf-8",
    )

    plugin_mcp = plugin_dir / "mcp_config.json"
    plugin_mcp.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "third_party": {"command": "custom-tool", "args": ["serve"]},
                    "brain79": {"command": "/hardcoded/path/to/brain79", "args": ["--project-root", "."]},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    changed = sync_project_mcp_configs(tmp_path)

    # plugin.json preserves custom fields and non-empty name
    p_data = json.loads(plugin_json.read_text(encoding="utf-8"))
    assert p_data["name"] == "custom-name"
    assert p_data["disabled"] is True
    assert p_data["author"] == "acme"

    # mcp_config.json preserves third-party and sanitizes brain79 command
    m_data = json.loads(plugin_mcp.read_text(encoding="utf-8"))
    assert m_data["mcpServers"]["third_party"] == {"command": "custom-tool", "args": ["serve"]}
    assert m_data["mcpServers"]["brain79"]["command"] == "brain79"
    assert m_data["mcpServers"]["brain79"]["args"] == ["--project-root", "."]
    assert ".agents/plugins/brain79/mcp_config.json" in changed


def test_sync_project_mcp_configs_corrupt_json_backup_to_bak(
    tmp_path: Path,
) -> None:
    """Test corrupt or non-dict JSON in plugin.json and mcp_config.json backs up to .bak and recreates cleanly."""
    from brain79.core.init_project import sync_project_mcp_configs

    plugin_dir = tmp_path / ".agents" / "plugins" / "brain79"
    plugin_dir.mkdir(parents=True)

    plugin_json = plugin_dir / "plugin.json"
    plugin_json.write_text("[1, 2, 3]", encoding="utf-8")

    plugin_mcp = plugin_dir / "mcp_config.json"
    plugin_mcp.write_text("INVALID JSON {", encoding="utf-8")

    sync_project_mcp_configs(tmp_path)

    assert (plugin_dir / "plugin.json.bak").is_file()
    assert (plugin_dir / "plugin.json.bak").read_text(encoding="utf-8") == "[1, 2, 3]"
    p_data = json.loads(plugin_json.read_text(encoding="utf-8"))
    assert p_data == {"name": "brain79"}

    assert (plugin_dir / "mcp_config.json.bak").is_file()
    assert (plugin_dir / "mcp_config.json.bak").read_text(encoding="utf-8") == "INVALID JSON {"
    m_data = json.loads(plugin_mcp.read_text(encoding="utf-8"))
    assert m_data["mcpServers"]["brain79"]["command"] == "brain79"


def test_sync_project_mcp_configs_dry_run_creates_zero_files_or_dirs(
    tmp_path: Path,
) -> None:
    """Test dry_run=True creates zero files or directories under .agents/plugins/brain79/ and reports changes."""
    from brain79.core.init_project import sync_project_mcp_configs

    changed = sync_project_mcp_configs(tmp_path, dry_run=True)

    assert not (tmp_path / ".agents" / "plugins").exists()
    assert ".agents/plugins/brain79/plugin.json" in changed
    assert ".agents/plugins/brain79/mcp_config.json" in changed
    assert ".agents/plugins/brain79/skills/brain79-wiki/SKILL.md" in changed


def test_include_desktop_never_touches_gemini_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test include_desktop=True never creates or modifies ~/.gemini/config/mcp_config.json."""
    from brain79.core.init_project import sync_project_mcp_configs

    fake_home = tmp_path / "fake_home"
    fake_gemini_config = fake_home / ".gemini" / "config"
    fake_gemini_config.mkdir(parents=True)
    gemini_mcp = fake_gemini_config / "mcp_config.json"
    gemini_mcp.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: fake_home)

    sync_project_mcp_configs(tmp_path, include_desktop=True, desktop_config_dir=fake_gemini_config)

    # ~/.gemini/config/mcp_config.json must remain completely untouched
    gemini_data = json.loads(gemini_mcp.read_text(encoding="utf-8"))
    assert len(gemini_data["mcpServers"]) == 0
    assert not (fake_gemini_config / "mcp_config.json.bak").exists()


def test_agents_manifest_size_and_compatibility_anchors() -> None:
    """Test AGENTS.md template size is <= 6500 bytes and preserves all compatibility anchors."""
    from importlib import resources

    pkg_templates = resources.files("brain79.templates")
    template_raw = (pkg_templates / "AGENTS.md").read_text(encoding="utf-8")

    # Size cap requirement
    size_bytes = len(template_raw.encode("utf-8"))
    assert size_bytes <= 6500, f"AGENTS.md size {size_bytes} exceeds 6500 byte limit"

    # Compatibility anchors
    assert "<!-- brain79:start v{{VERSION}} -->" in template_raw
    assert "<!-- brain79:end -->" in template_raw
    assert "# Brain-79 AI memory protocol" in template_raw
    assert "pi-mcp-adapter" in template_raw
    assert "brain79_index" in template_raw
    assert "No-Op Idempotence" in template_raw
    assert "Zero-Modification Rule" in template_raw
    assert "## Project notes" in template_raw

    # Accurate agy setup instructions (no .mcp.json for agy)
    assert ".agents/plugins/brain79" in template_raw
    assert "agy mcp add" in template_raw or ".agents/plugins/brain79/" in template_raw

    # Zero-clone install instruction (no --editable user hint)
    assert "--editable" not in template_raw
    assert "git+https://github.com/xilax79/brain-79.git" in template_raw


def test_skill_template_valid_frontmatter_and_content() -> None:
    """Test SKILL.md template has valid YAML frontmatter and comprehensive CLI/MCP reference."""
    from importlib import resources
    from brain79.core.frontmatter import parse_frontmatter

    pkg_templates = resources.files("brain79.templates")
    skill_file = pkg_templates / "SKILL.md"
    assert skill_file.is_file()

    content = skill_file.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(content)

    assert meta.get("name") == "brain79-wiki"
    assert meta.get("description") and len(str(meta["description"]).strip()) > 0
    assert "brain79_session_commit" in body
    assert "brain79_orient" in body
    assert "brain79 lint" in body


def test_sync_project_mcp_configs_repeated_corruption_overwrites_bak(tmp_path: Path) -> None:
    """Test repeated corrupt JSON replaces existing .bak without FileExistsError."""
    from brain79.core.init_project import sync_project_mcp_configs

    plugin_dir = tmp_path / ".agents" / "plugins" / "brain79"
    plugin_dir.mkdir(parents=True)
    plugin_json = plugin_dir / "plugin.json"
    plugin_bak = plugin_dir / "plugin.json.bak"
    plugin_bak.write_text("prior_backup", encoding="utf-8")

    plugin_json.write_text("corrupted_once", encoding="utf-8")
    sync_project_mcp_configs(tmp_path)
    assert plugin_bak.read_text(encoding="utf-8") == "corrupted_once"


def test_sync_project_mcp_configs_directory_collision_guarded(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test sync_project_mcp_configs guards against directory collisions cleanly."""
    from brain79.core.init_project import sync_project_mcp_configs

    plugin_dir = tmp_path / ".agents" / "plugins" / "brain79"
    (plugin_dir / "plugin.json").mkdir(parents=True)
    (plugin_dir / "mcp_config.json").mkdir(parents=True)
    (plugin_dir / "skills" / "brain79-wiki" / "SKILL.md").mkdir(parents=True)

    res = sync_project_mcp_configs(tmp_path)
    assert ".agents/plugins/brain79/mcp_config.json" not in res
    captured = capsys.readouterr()
    assert "is a directory" in captured.out




def test_harness_adapter_registry_drives_tier1_harnesses(tmp_path: Path) -> None:
    """AC-10.11: core.harnesses registry exposes all Tier 1 adapters with detect/sync/diagnose."""
    from brain79.core.harnesses import HarnessAdapter, get_harness_adapters

    adapters = get_harness_adapters()
    names = {a.name for a in adapters}
    assert {"agents_md", "mcp_json", "cursor", "antigravity"}.issubset(names)
    for adapter in adapters:
        assert isinstance(adapter, HarnessAdapter)
        sub = tmp_path / adapter.name
        sub.mkdir()
        # Before sync, not detected on an empty directory
        assert adapter.detect(sub) is False
        synced = adapter.sync(sub)
        assert isinstance(synced, list)
        assert adapter.detect(sub) is True
        diag = adapter.diagnose(sub)
        assert isinstance(diag, list)


def test_custom_harness_adapter_invoked_by_init_and_doctor(tmp_path: Path) -> None:
    """AC-10.11: Custom HarnessAdapter registered via register_harness_adapter is invoked by init_project and run_doctor."""
    from brain79.core.doctor import run_doctor
    from brain79.core.harnesses import _HARNESS_ADAPTERS, register_harness_adapter

    events: list[str] = []

    class _CustomAdapter:
        name: str = "custom_test_harness"

        def detect(self, project_root: Path) -> bool:
            return True

        def sync(self, project_root: Path) -> list[str]:
            events.append("sync")
            return ["custom.cfg"]

        def diagnose(self, project_root: Path) -> list[str]:
            events.append("diagnose")
            return []

    original_adapters = list(_HARNESS_ADAPTERS)
    register_harness_adapter(_CustomAdapter())
    try:
        init_project(tmp_path, install_git_hooks_flag=False)
        assert "sync" in events

        run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
        assert "diagnose" in events
    finally:
        _HARNESS_ADAPTERS[:] = original_adapters
