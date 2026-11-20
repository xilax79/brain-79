import json
from pathlib import Path
import subprocess
import pytest

from brain79 import __version__
from brain79.core.init_project import (
    init_project,
    sync_agents_manifest,
    sync_git_hooks,
    sync_project_mcp_configs,
    sync_schema_file,
    update_project,
)


def _init_git_repo(path: Path) -> None:
    import subprocess
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CI Tester"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True, capture_output=True)


def test_sync_agents_manifest_clean_upgrade_preserves_custom_headers_and_notes(tmp_path: Path) -> None:
    manifest = tmp_path / "AGENTS.md"
    initial_content = (
        "# Custom Persona\n"
        "You are an assistant for Acme Corp.\n\n"
        "<!-- brain79:start v0.8.0 -->\n"
        "# Brain-79 AI memory protocol\n"
        "Old outdated protocol instructions.\n"
        "<!-- brain79:end -->\n\n"
        "## Project notes\n"
        "- Note 1: deploy to production on Fridays.\n"
        "- Note 2: internal runbook at https://acme.internal\n"
    )
    manifest.write_text(initial_content, encoding="utf-8")

    updated, msg = sync_agents_manifest(tmp_path)
    assert updated is True
    assert f"v{__version__}" in msg

    new_content = manifest.read_text(encoding="utf-8")
    assert new_content.startswith("# Custom Persona\nYou are an assistant for Acme Corp.\n\n")
    assert "<!-- brain79:start v" + __version__ + " -->" in new_content
    assert "<!-- brain79:end -->" in new_content
    assert new_content.endswith(
        "## Project notes\n"
        "- Note 1: deploy to production on Fridays.\n"
        "- Note 2: internal runbook at https://acme.internal\n"
    )
    assert "Old outdated protocol instructions" not in new_content


def test_sync_agents_manifest_legacy_unmarked_file_conversion(tmp_path: Path) -> None:
    manifest = tmp_path / "AGENTS.md"
    initial_content = (
        "# Custom Persona\n"
        "Keep it calm.\n\n"
        "# Brain-79 AI memory protocol\n"
        "Legacy unmarked instructions.\n\n"
        "## Project notes\n"
        "- Custom team guideline.\n"
    )
    manifest.write_text(initial_content, encoding="utf-8")

    updated, msg = sync_agents_manifest(tmp_path)
    assert updated is True

    new_content = manifest.read_text(encoding="utf-8")
    assert new_content.startswith("# Custom Persona\nKeep it calm.\n\n")
    assert "<!-- brain79:start v" + __version__ + " -->" in new_content
    assert "<!-- brain79:end -->" in new_content
    assert "## Project notes\n- Custom team guideline.\n" in new_content
    assert "Legacy unmarked instructions" not in new_content


def test_sync_agents_manifest_corruption_guard_mismatched_tags(tmp_path: Path) -> None:
    manifest = tmp_path / "AGENTS.md"
    corrupted_content = (
        "# Custom Persona\n\n"
        "<!-- brain79:start v0.8.0 -->\n"
        "# Brain-79 AI memory protocol\n"
        "Broken block without ending tag.\n"
    )
    manifest.write_text(corrupted_content, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        sync_agents_manifest(tmp_path)

    assert "corrupted_agents_manifest_delimiters" in str(exc_info.value)
    # Ensure file on disk was not modified or truncated
    assert manifest.read_text(encoding="utf-8") == corrupted_content


def test_sync_agents_manifest_idempotent_no_op_when_already_latest(tmp_path: Path) -> None:
    updated1, _ = sync_agents_manifest(tmp_path)
    assert updated1 is True

    updated2, msg2 = sync_agents_manifest(tmp_path)
    assert updated2 is False
    assert "already up-to-date" in msg2


def test_sync_schema_file_preserves_custom_types_and_extensions(tmp_path: Path) -> None:
    w_root = tmp_path / ".brain-79"
    w_root.mkdir()
    schema_path = w_root / "SCHEMA.md"

    initial_content = (
        "---\n"
        "profile: software\n"
        "custom_types:\n"
        "  - runbooks\n"
        "  - playbooks\n"
        "organization: AcmeCorp\n"
        "---\n\n"
        "# Brain-79 — Wiki schema (normative)\n\n"
        "Old rules...\n\n"
        "## Project-specific schema extensions\n\n"
        "Custom rule definitions that must never be erased.\n"
    )
    schema_path.write_text(initial_content, encoding="utf-8")

    updated, msg = sync_schema_file(w_root)
    assert updated is True

    from brain79.core.frontmatter import parse_frontmatter

    new_content = schema_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(new_content)

    assert meta["profile"] == "software"
    assert meta["schema_version"] == 2
    assert meta["custom_types"] == ["runbooks", "playbooks"]
    assert meta["organization"] == "AcmeCorp"
    assert "## Project-specific schema extensions" in body
    assert "Custom rule definitions that must never be erased." in body


def test_tier1_mcp_configs_sanitizes_absolute_paths_and_preserves_third_party(tmp_path: Path) -> None:
    # Setup .mcp.json with absolute path and third-party server
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "third_party": {"command": "node", "args": ["app.js"]},
                    "brain79": {"command": "/Users/xilax/.local/bin/brain79", "args": ["--project-root", "."]},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Setup .agents/mcp_config.json with absolute path
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    agents_file = agents_dir / "mcp_config.json"
    agents_file.write_text(
        json.dumps(
            {"mcpServers": {"brain79": {"command": "/opt/homebrew/bin/brain79", "args": ["--project-root", "."]}}},
            indent=2,
        ),
        encoding="utf-8",
    )

    created_or_updated = sync_project_mcp_configs(tmp_path)
    assert len(created_or_updated) >= 3

    # 1. Verify .mcp.json
    mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert mcp_data["mcpServers"]["third_party"] == {"command": "node", "args": ["app.js"]}
    assert mcp_data["mcpServers"]["brain79"]["command"] == "brain79"
    assert mcp_data["mcpServers"]["brain79"]["toolPrefix"] == "none"

    # 2. Verify .agents/mcp_config.json
    agents_data = json.loads(agents_file.read_text(encoding="utf-8"))
    assert agents_data["mcpServers"]["brain79"]["command"] == "brain79"

    # 3. Verify .cursor/mcp.json was created
    cursor_file = tmp_path / ".cursor" / "mcp.json"
    assert cursor_file.is_file()
    cursor_data = json.loads(cursor_file.read_text(encoding="utf-8"))
    assert cursor_data["mcpServers"]["brain79"]["command"] == "brain79"
    assert cursor_data["mcpServers"]["brain79"]["args"] == ["--project-root", "."]


def test_tier1_mcp_configs_creates_bak_on_malformed_json(tmp_path: Path) -> None:
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text("{ malformed: true, unquoted json", encoding="utf-8")

    sync_project_mcp_configs(tmp_path)

    bak_file = tmp_path / ".mcp.json.bak"
    assert bak_file.is_file()
    assert bak_file.read_text(encoding="utf-8") == "{ malformed: true, unquoted json"

    # A clean fresh .mcp.json was created
    mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert mcp_data["mcpServers"]["brain79"]["command"] == "brain79"


def test_tier2_desktop_config_opt_in_with_backup(tmp_path: Path) -> None:
    desktop_dir = tmp_path / "desktop_config"
    desktop_dir.mkdir()
    claude_desktop = desktop_dir / "claude_desktop_config.json"
    claude_desktop.write_text(
        json.dumps({"mcpServers": {"fetch": {"command": "uvx", "args": ["mcp-server-fetch"]}}}, indent=2),
        encoding="utf-8",
    )

    # 1. include_desktop=False -> untouched
    sync_project_mcp_configs(tmp_path, include_desktop=False, desktop_config_dir=desktop_dir)
    assert not (desktop_dir / "claude_desktop_config.json.bak").exists()
    content = json.loads(claude_desktop.read_text(encoding="utf-8"))
    assert "fetch" in content["mcpServers"]
    assert len(content["mcpServers"]) == 1

    # 2. include_desktop=True -> merged with backup
    sync_project_mcp_configs(tmp_path, include_desktop=True, desktop_config_dir=desktop_dir)
    assert (desktop_dir / "claude_desktop_config.json.bak").exists()
    content2 = json.loads(claude_desktop.read_text(encoding="utf-8"))
    assert "fetch" in content2["mcpServers"]
    server_key = f"brain79-{tmp_path.name}"
    assert server_key in content2["mcpServers"]
    assert content2["mcpServers"][server_key]["args"] == ["--project-root", str(tmp_path.resolve())]


def test_git_hook_preserves_husky_and_precommit_managers(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    hook_file = git_dir / "pre-commit"
    hook_file.write_text("#!/bin/sh\n. \"$(dirname -- \"$0\")/_/husky.sh\"\nnpx lint-staged\n", encoding="utf-8")

    updated, msg = sync_git_hooks(tmp_path)
    assert updated is False
    assert "preserved third-party git hook manager" in msg
    assert "husky" in hook_file.read_text(encoding="utf-8")


def test_update_project_dry_run_does_not_mutate_disk(tmp_path: Path) -> None:
    # Initialize basic wiki
    init_project(tmp_path)
    manifest = tmp_path / "AGENTS.md"
    original_manifest = manifest.read_text(encoding="utf-8")

    res = update_project(tmp_path, dry_run=True)
    assert res["status"] == "ok"
    assert res["dry_run"] is True
    assert manifest.read_text(encoding="utf-8") == original_manifest


def test_sync_agents_manifest_rejects_duplicate_blocks(tmp_path: Path) -> None:
    manifest = tmp_path / "AGENTS.md"
    duplicate_content = (
        "<!-- brain79:start v0.8.0 -->\n"
        "# Brain-79 AI memory protocol\n"
        "Block 1\n"
        "<!-- brain79:end -->\n\n"
        "Middle content\n\n"
        "<!-- brain79:start v0.8.0 -->\n"
        "# Brain-79 AI memory protocol\n"
        "Block 2\n"
        "<!-- brain79:end -->\n"
    )
    manifest.write_text(duplicate_content, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        sync_agents_manifest(tmp_path)

    assert "corrupted_agents_manifest_delimiters" in str(exc_info.value)
    assert manifest.read_text(encoding="utf-8") == duplicate_content


def test_migrate_wiki_v2_repairs_backlink_colons_and_summary_on_existing_frontmatter(tmp_path: Path) -> None:
    from brain79.core.migration import migrate_wiki

    w_root = tmp_path / ".brain-79"
    feat_dir = w_root / "features"
    feat_dir.mkdir(parents=True)

    article = feat_dir / "existing-feat.md"
    initial_content = (
        "---\n"
        "type: feature\n"
        "summary: raw un-sanitized summary.\n"
        "status: shipped\n"
        "version: 1.0.0\n"
        "last_updated: 2026-11-01\n"
        "---\n\n"
        "# Feature — Test Feature\n\n"
        "## Overview\n"
        "- **Field:** Value with colon inside bold.\n"
    )
    article.write_text(initial_content, encoding="utf-8")

    report = migrate_wiki(w_root)
    assert "features/existing-feat.md" in report

    new_content = article.read_text(encoding="utf-8")
    assert "[← Volver al Índice](../INDEX.md)" in new_content
    assert "- **Field**: Value with colon inside bold." in new_content
    assert "summary: raw un-sanitized summary" in new_content


def test_migrate_wiki_v2_downgrades_incomplete_active_article_to_legacy(tmp_path: Path) -> None:
    from brain79.core.frontmatter import parse_frontmatter
    from brain79.core.migration import migrate_wiki

    w_root = tmp_path / ".brain-79"
    dec_dir = w_root / "decisions"
    dec_dir.mkdir(parents=True)

    adr_file = dec_dir / "adr-099-incomplete.md"
    # Lacks ## Consequences
    initial_content = (
        "---\n"
        "type: decision\n"
        "summary: decision without consequences section\n"
        "status: accepted\n"
        "date: 2026-11-01\n"
        "deciders: Team\n"
        "last_updated: 2026-11-01\n"
        "---\n\n"
        "# ADR-099: Incomplete Decision\n\n"
        "## Status\n"
        "Accepted\n\n"
        "## Context\n"
        "Context text.\n\n"
        "## Decision\n"
        "Decision text.\n\n"
        "[← Volver al Índice](../INDEX.md)\n"
    )
    adr_file.write_text(initial_content, encoding="utf-8")

    report = migrate_wiki(w_root)
    assert "decisions/adr-099-incomplete.md" in report

    meta, _ = parse_frontmatter(adr_file.read_text(encoding="utf-8"))
    assert meta["status"] == "legacy"


def test_migrate_wiki_v2_root_article_never_gets_parent_index_backlink(tmp_path: Path) -> None:
    from brain79.core.migration import migrate_wiki

    w_root = tmp_path / ".brain-79"
    w_root.mkdir(parents=True)

    # 1. Direct root article in .brain-79/root-overview.md
    direct_root = w_root / "root-overview.md"
    direct_root.write_text(
        "---\n"
        "type: product\n"
        "summary: direct root overview\n"
        "last_updated: 2026-11-01\n"
        "---\n\n"
        "# Product — Root Overview\n\n"
        "Direct root file overview.\n",
        encoding="utf-8",
    )

    # 2. Subfolder article
    sub_file = w_root / "topics" / "domain.md"
    sub_file.parent.mkdir(parents=True)
    sub_file.write_text(
        "---\n"
        "type: topic\n"
        "summary: root domain analysis\n"
        "last_updated: 2026-11-01\n"
        "---\n\n"
        "# Topic — Domain\n\n"
        "Overview text.\n",
        encoding="utf-8",
    )

    migrate_wiki(w_root)

    direct_content = direct_root.read_text(encoding="utf-8")
    assert "[← Volver al Índice](INDEX.md)" in direct_content
    assert "../INDEX.md" not in direct_content

    sub_content = sub_file.read_text(encoding="utf-8")
    assert "[← Volver al Índice](../INDEX.md)" in sub_content
    assert "../../INDEX.md" not in sub_content


def test_update_project_commit_transition_produces_fresh_handoff(tmp_path: Path) -> None:
    from brain79.core.handoff_freshness import compute_handoff_freshness

    init_project(tmp_path)
    res = update_project(tmp_path, commit_transition=True)

    assert res["status"] == "ok"
    assert res["transition_handoff"] is not None
    assert "migration_report" in res

    handoff_path = tmp_path / ".brain-79" / res["transition_handoff"]
    assert handoff_path.is_file()

    freshness = compute_handoff_freshness(handoff_path, wiki_root=tmp_path / ".brain-79")
    assert freshness.state == "fresh"


def test_orient_protocol_skew_banner_rendered_and_cleared(tmp_path: Path) -> None:
    from brain79.core.orient import orient

    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    # Corrupt AGENTS.md version to older version
    agents_file = tmp_path / "AGENTS.md"
    content = agents_file.read_text(encoding="utf-8")
    content = content.replace(f"v{__version__}", "v0.7.0")
    agents_file.write_text(content, encoding="utf-8")

    out_skewed = orient(wiki_root=w_root)
    assert "Protocol update available" in out_skewed
    assert "Run 'brain79 update-project'" in out_skewed

    # Run update_project
    update_project(tmp_path)
    out_clean = orient(wiki_root=w_root)
    assert "Protocol update available" not in out_clean


def test_doctor_7_checks_clean_environment_exit_code_0(tmp_path: Path) -> None:
    import subprocess
    from brain79.core.doctor import run_doctor

    # Setup git repo
    _init_git_repo(tmp_path)
    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    # Commit initial state so working tree is clean
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial", "--no-verify"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    report = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert report.status == "ok"
    assert report.exit_code == 0
    assert len(report.checks) == 7
    cats = {c.category for c in report.checks}
    assert cats == {
        "binary_and_environment",
        "protocol_sync",
        "wiki_structure",
        "mcp_harnesses",
        "locks_and_filesystem",
        "git_hooks",
        "handoff_hygiene",
    }


def test_doctor_protocol_skew_warning_exit_code_2(tmp_path: Path) -> None:
    from brain79.core.doctor import run_doctor

    _init_git_repo(tmp_path)
    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    # Introduce protocol skew: revert schema_version to 1
    schema_file = w_root / "SCHEMA.md"
    content = schema_file.read_text(encoding="utf-8")
    content = content.replace("schema_version: 2", "schema_version: 1")
    schema_file.write_text(content, encoding="utf-8")

    report = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert report.status == "warning"
    assert report.exit_code == 2
    proto_check = next(c for c in report.checks if c.category == "protocol_sync")
    assert proto_check.status == "warning"
    assert "schema_version 1" in proto_check.message


def test_doctor_critical_failure_exit_code_1(tmp_path: Path) -> None:
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    # Corrupt .mcp.json syntax
    mcp_file = tmp_path / ".mcp.json"
    mcp_file.write_text("{ unquoted invalid json", encoding="utf-8")

    report = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert report.status == "error"
    assert report.exit_code == 1
    mcp_check = next(c for c in report.checks if c.category == "mcp_harnesses")
    assert mcp_check.status == "error"
    assert "corrupt JSON" in mcp_check.message


def test_doctor_fix_dirty_git_safety_guard(tmp_path: Path) -> None:
    from brain79.core.doctor import run_doctor

    _init_git_repo(tmp_path)
    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-verify"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Modify AGENTS.md without committing
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text(agents_file.read_text(encoding="utf-8") + "\n# Uncommitted edit\n", encoding="utf-8")

    # fix=True without force=True must abort with dirty_working_tree
    report = run_doctor(project_root=tmp_path, wiki_root=w_root, fix=True, force=False)
    assert report.status == "error"
    assert report.exit_code == 1
    assert any(c.category == "dirty_working_tree" for c in report.checks)

    # fix=True with force=True proceeds
    report_forced = run_doctor(project_root=tmp_path, wiki_root=w_root, fix=True, force=True)
    assert report_forced.status == "ok"
    assert report_forced.exit_code == 0
    assert len(report_forced.fixed) > 0


def test_doctor_fix_heals_skew_to_exit_code_0(tmp_path: Path) -> None:
    from brain79.core.doctor import run_doctor

    _init_git_repo(tmp_path)
    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    # Simulate older project committed without .cursor
    cursor_cfg = tmp_path / ".cursor" / "mcp.json"
    if cursor_cfg.exists():
        cursor_cfg.unlink()
        (tmp_path / ".cursor").rmdir()

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "old_init", "--no-verify"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    report_pre = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert report_pre.status == "warning"

    report_post = run_doctor(project_root=tmp_path, wiki_root=w_root, fix=True)
    assert report_post.status == "ok"
    assert report_post.exit_code == 0
    assert cursor_cfg.is_file()


def test_doctor_json_and_text_formatting(tmp_path: Path) -> None:
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    report = run_doctor(project_root=tmp_path, wiki_root=w_root)
    d = report.to_dict()
    assert "status" in d
    assert "exit_code" in d
    assert "checks" in d
    assert len(d["checks"]) == 7

    text = report.format_text()
    assert "# Brain-79 Doctor Diagnostic Report" in text
    assert "[✓]" in text or "[!]" in text


def test_doctor_flags_missing_agy_plugin_when_legacy_agents_mcp_exists(tmp_path: Path) -> None:
    """Test doctor reports warning and actionable hint when legacy .agents/mcp_config.json exists without .agents/plugins/brain79."""
    import shutil
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    # Remove newly created plugin to simulate legacy project
    agy_plugin_dir = tmp_path / ".agents" / "plugins" / "brain79"
    if agy_plugin_dir.exists():
        shutil.rmtree(agy_plugin_dir)

    report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
    assert report.status == "warning"
    mcp_check = next(c for c in report.checks if c.category == "mcp_harnesses")
    assert mcp_check.status == "warning"
    assert "missing .agents/plugins/brain79" in mcp_check.message
    assert mcp_check.actionable is not None
    assert "update-project" in mcp_check.actionable or "doctor --fix" in mcp_check.actionable


def test_doctor_detects_invalid_or_corrupt_agy_plugin_files(tmp_path: Path) -> None:
    """Test doctor flags corrupt plugin.json or invalid command in .agents/plugins/brain79/mcp_config.json."""
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    plugin_mcp = tmp_path / ".agents" / "plugins" / "brain79" / "mcp_config.json"
    plugin_mcp.write_text(
        json.dumps({"mcpServers": {"brain79": {"command": "/invalid/absolute/path"}}}),
        encoding="utf-8",
    )

    report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
    mcp_check = next(c for c in report.checks if c.category == "mcp_harnesses")
    assert mcp_check.status == "warning"
    assert "non-portable command" in mcp_check.message


def test_doctor_fix_dirty_tree_guard_includes_agents_plugins(tmp_path: Path) -> None:
    """Test doctor --fix checks .agents/plugins/brain79 in dirty tree guard."""
    from brain79.core.doctor import run_doctor

    _init_git_repo(tmp_path)
    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-verify"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Modify .agents/plugins/brain79/plugin.json without committing
    p_file = tmp_path / ".agents" / "plugins" / "brain79" / "plugin.json"
    p_file.write_text(json.dumps({"name": "modified"}), encoding="utf-8")

    report = run_doctor(project_root=tmp_path, wiki_root=w_root, fix=True, force=False)
    assert report.status == "error"
    assert report.exit_code == 1
    assert any(c.category == "dirty_working_tree" for c in report.checks)


def test_doctor_fix_repairs_missing_agy_plugin(tmp_path: Path) -> None:
    """Test doctor --fix repairs missing .agents/plugins/brain79 files."""
    import shutil
    from brain79.core.doctor import run_doctor

    _init_git_repo(tmp_path)
    init_project(tmp_path)
    w_root = tmp_path / ".brain-79"

    agy_plugin_dir = tmp_path / ".agents" / "plugins" / "brain79"
    if agy_plugin_dir.exists():
        shutil.rmtree(agy_plugin_dir)

    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "legacy_state", "--no-verify"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    report_pre = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert report_pre.status == "warning"

    report_post = run_doctor(project_root=tmp_path, wiki_root=w_root, fix=True)
    assert report_post.status == "ok"
    assert report_post.exit_code == 0
    assert (agy_plugin_dir / "plugin.json").is_file()
    assert (agy_plugin_dir / "mcp_config.json").is_file()
    assert (agy_plugin_dir / "skills" / "brain79-wiki" / "SKILL.md").is_file()


def test_doctor_detects_non_portable_args_in_agy_mcp_config(tmp_path: Path) -> None:
    """Test doctor flags non-portable args in .agents/plugins/brain79/mcp_config.json."""
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    plugin_mcp = tmp_path / ".agents" / "plugins" / "brain79" / "mcp_config.json"
    plugin_mcp.write_text(
        json.dumps({
            "mcpServers": {
                "brain79": {"command": "brain79", "args": ["--project-root", "/abs/path"]}
            }
        }),
        encoding="utf-8",
    )

    report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
    mcp_check = next(c for c in report.checks if c.category == "mcp_harnesses")
    assert mcp_check.status == "warning"
    assert "non-portable arguments" in mcp_check.message


def test_doctor_flags_missing_agy_plugin_when_skill_or_mcp_missing(tmp_path: Path) -> None:
    """Test doctor flags missing plugin and suggests doctor --fix when SKILL.md is removed."""
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    skill_file = tmp_path / ".agents" / "plugins" / "brain79" / "skills" / "brain79-wiki" / "SKILL.md"
    skill_file.unlink()

    report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
    assert report.status == "warning"
    mcp_check = next(c for c in report.checks if c.category == "mcp_harnesses")
    assert "doctor --fix" in (mcp_check.actionable or "")


def test_doctor_python_runtime_below_3_11(tmp_path: Path) -> None:
    """Test doctor binary_and_environment flags Python runtime < 3.11."""
    import sys
    from unittest.mock import patch
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    with patch.object(sys, "version_info", (3, 10, 8)):
        report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")

    bin_check = next(c for c in report.checks if c.category == "binary_and_environment")
    assert bin_check.status == "error"
    assert "below minimum requirement 3.11" in bin_check.message
    assert "3.11" in (bin_check.actionable or "")


def test_doctor_missing_binary_actionable_hint(tmp_path: Path) -> None:
    """Test doctor missing binary hint suggests zero-clone uv tool install."""
    from unittest.mock import patch
    from brain79.core.doctor import run_doctor

    init_project(tmp_path)
    with patch("shutil.which", return_value=None):
        report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")

    bin_check = next(c for c in report.checks if c.category == "binary_and_environment")
    assert bin_check.status == "warning"
    assert "Executable 'brain79' not found in system PATH." in bin_check.message
    assert "uv tool install git+https://github.com/xilax79/brain-79.git" in (bin_check.actionable or "")





