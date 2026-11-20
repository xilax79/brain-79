from datetime import datetime, timezone
from importlib import resources
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from brain79.core.locks import cleanup_legacy_inline_locks

WIKI_DIRS_SOFTWARE = [
    "_raw/sessions",
    "_raw/commits",
    "handoffs",
    "product",
    "architecture",
    "features",
    "decisions",
    "changelog",
    "topics",
]

# Backward compatibility alias
WIKI_DIRS = WIKI_DIRS_SOFTWARE

WIKI_DIRS_GENERAL = [
    "_raw/sessions",
    "_raw/commits",
    "handoffs",
    "context",
    "topics",
    "decisions",
    "log",
]

TEMPLATE_FILES = ["SCHEMA.md", "INDEX.md"]

PRE_COMMIT_HOOK_SCRIPT = """#!/usr/bin/env bash
# brain-79 pre-commit hook: validate wiki changes via lint --strict
set -e

# Augment PATH so non-interactive shells and GUI clients locate brain79
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$XDG_BIN_HOME:$USERPROFILE/.local/bin:$PATH"

# Find staged wiki files
STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E "^\\.brain-79/.*\\.md$" || true)
if [ -z "$STAGED" ]; then
    exit 0
fi

# Run lint --strict (fails on issues, blocks commit)
brain79 --project-root . lint --strict
"""


def install_git_hooks(project_root: Path, install: bool = True) -> None:
    """Install .git/hooks/pre-commit if .git directory exists and install is True."""
    sync_git_hooks(project_root, install=install)


from brain79.core.harnesses._delimited import (
    DELIMITED_END_REGEX as AGENTS_END_REGEX,
    DELIMITED_START_REGEX as AGENTS_START_REGEX,
    sync_delimited_file,
)


def sync_agents_manifest(
    project_root: Path,
    version: str | None = None,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Sync or wrap AGENTS.md protocol instructions inside delimited blocks non-destructively."""
    from brain79 import __version__

    pkg_templates = resources.files("brain79.templates")
    template_raw = (pkg_templates / "AGENTS.md").read_text(encoding="utf-8")
    active_version = version or __version__
    rendered_template = template_raw.replace("{{VERSION}}", active_version)

    manifest_path = project_root / "AGENTS.md"
    return sync_delimited_file(
        manifest_path,
        rendered_template,
        full_initial_content=rendered_template,
        dry_run=dry_run,
        legacy_header="# Brain-79 AI memory protocol",
        legacy_notes_header="## Project notes",
        version=active_version,
        error_code="corrupted_agents_manifest_delimiters",
    )


def sync_schema_file(wiki_root: Path, dry_run: bool = False) -> tuple[bool, str]:
    """Upgrade .brain-79/SCHEMA.md to schema_version 2 while preserving custom types and extensions."""
    schema_path = wiki_root / "SCHEMA.md"
    if not schema_path.exists():
        return False, "SCHEMA.md does not exist"

    content = schema_path.read_text(encoding="utf-8")
    from brain79.core.frontmatter import dump_frontmatter, parse_frontmatter

    try:
        meta, existing_body = parse_frontmatter(content)
    except Exception:
        meta = {}
        existing_body = content

    profile = str(meta.get("profile", "software")).strip().lower()
    pkg_templates = resources.files("brain79.templates")
    template_name = "SCHEMA_GENERAL.md" if profile == "general" else "SCHEMA.md"
    template_content = (pkg_templates / template_name).read_text(encoding="utf-8")
    _, template_body = parse_frontmatter(template_content)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    template_body = template_body.replace("YYYY-MM-DD", today)

    # Check for trailing custom extensions in existing_body
    ext_pattern = re.compile(r"(?im)^##\s+Project-specific\s+schema\s+extensions\b")
    m_ext = ext_pattern.search(existing_body)
    if m_ext:
        custom_tail = existing_body[m_ext.start() :]
        template_body = template_body.rstrip() + "\n\n" + custom_tail.lstrip()

    meta["schema_version"] = 2
    meta["last_updated"] = today

    new_content = dump_frontmatter(meta, template_body)
    if new_content == content:
        return False, "SCHEMA.md is already up-to-date"

    if not dry_run:
        schema_path.write_text(new_content, encoding="utf-8", newline="\n")
    return True, "upgraded SCHEMA.md to schema_version 2 with preserved extensions"


def sync_project_mcp_configs(
    project_root: Path,
    include_desktop: bool = False,
    desktop_config_dir: Path | None = None,
    dry_run: bool = False,
    targets: set[str] | None = None,
) -> list[str]:
    """Configure portable Tier 1 MCP configs and opt-in Tier 2 desktop integrations."""
    changed: list[str] = []
    active_targets = {"mcp_json", "antigravity", "cursor"} if targets is None else targets

    # 1. .mcp.json (Universal / Pi / Claude Code / Zed / OpenCode)
    if "mcp_json" in active_targets:
        mcp_file = project_root / ".mcp.json"
        mcp_data: dict[str, Any] = {}
        if mcp_file.is_file():
            try:
                mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
                if not isinstance(mcp_data, dict):
                    print(f"⚠️ Warning: {mcp_file} is not a JSON object. Backing up to {mcp_file}.bak")
                    if not dry_run:
                        mcp_file.rename(mcp_file.with_suffix(".json.bak"))
                    mcp_data = {}
            except json.JSONDecodeError as e:
                print(f"⚠️ Warning: Existing {mcp_file} is invalid JSON ({e}).")
                print(f"  Backing up to {mcp_file.with_suffix('.json.bak')} and creating fresh config.")
                if not dry_run:
                    mcp_file.rename(mcp_file.with_suffix(".json.bak"))
                mcp_data = {}
            except Exception:
                if not dry_run:
                    mcp_file.rename(mcp_file.with_suffix(".json.bak"))
                mcp_data = {}
        elif mcp_file.is_dir():
            print(f"⚠️ Warning: {mcp_file} exists and is a directory. Skipping .mcp.json generation.")

        if not mcp_file.is_dir():
            if "mcpServers" not in mcp_data or not isinstance(mcp_data["mcpServers"], dict):
                mcp_data["mcpServers"] = {}
            mcp_data["mcpServers"]["brain79"] = {
                "command": "brain79",
                "args": ["--project-root", "."],
                "toolPrefix": "none",
            }
            new_raw = json.dumps(mcp_data, indent=2) + "\n"
            old_raw = mcp_file.read_text(encoding="utf-8") if mcp_file.is_file() else None
            if old_raw != new_raw:
                if not dry_run:
                    mcp_file.write_text(new_raw, encoding="utf-8", newline="\n")
                changed.append(".mcp.json")

    # 2. .agents/mcp_config.json (Antigravity agy)
    if "antigravity" in active_targets:
        agents_dir = project_root / ".agents"
        if not dry_run:
            agents_dir.mkdir(exist_ok=True)
        agents_file = agents_dir / "mcp_config.json"
        agents_data: dict[str, Any] = {}
        if agents_file.is_file():
            try:
                agents_data = json.loads(agents_file.read_text(encoding="utf-8"))
                if not isinstance(agents_data, dict):
                    if not dry_run:
                        agents_file.rename(agents_file.with_suffix(".json.bak"))
                    agents_data = {}
            except Exception:
                if not dry_run:
                    agents_file.rename(agents_file.with_suffix(".json.bak"))
                agents_data = {}

        if "mcpServers" not in agents_data or not isinstance(agents_data["mcpServers"], dict):
            agents_data["mcpServers"] = {}
        agents_data["mcpServers"]["brain79"] = {
            "command": "brain79",
            "args": ["--project-root", "."],
        }
        new_raw = json.dumps(agents_data, indent=2) + "\n"
        old_raw = agents_file.read_text(encoding="utf-8") if agents_file.is_file() else None
        if old_raw != new_raw:
            if not dry_run:
                agents_dir.mkdir(exist_ok=True)
                agents_file.write_text(new_raw, encoding="utf-8", newline="\n")
            changed.append(".agents/mcp_config.json")

    # 3. .cursor/mcp.json (Cursor IDE)
    if "cursor" in active_targets:
        cursor_dir = project_root / ".cursor"
        if not dry_run:
            cursor_dir.mkdir(exist_ok=True)
        cursor_file = cursor_dir / "mcp.json"
        cursor_data: dict[str, Any] = {}
        if cursor_file.is_file():
            try:
                cursor_data = json.loads(cursor_file.read_text(encoding="utf-8"))
                if not isinstance(cursor_data, dict):
                    if not dry_run:
                        cursor_file.rename(cursor_file.with_suffix(".json.bak"))
                    cursor_data = {}
            except Exception:
                if not dry_run:
                    cursor_file.rename(cursor_file.with_suffix(".json.bak"))
                cursor_data = {}

        if "mcpServers" not in cursor_data or not isinstance(cursor_data["mcpServers"], dict):
            cursor_data["mcpServers"] = {}
        cursor_data["mcpServers"]["brain79"] = {
            "command": "brain79",
            "args": ["--project-root", "."],
        }
        new_raw = json.dumps(cursor_data, indent=2) + "\n"
        old_raw = cursor_file.read_text(encoding="utf-8") if cursor_file.is_file() else None
        if old_raw != new_raw:
            if not dry_run:
                cursor_dir.mkdir(exist_ok=True)
                cursor_file.write_text(new_raw, encoding="utf-8", newline="\n")
            changed.append(".cursor/mcp.json")

    # 4. .agents/plugins/brain79/ (Native Antigravity agy workspace plugin)
    if "antigravity" in active_targets:
        plugin_dir = project_root / ".agents" / "plugins" / "brain79"
        skill_dir = plugin_dir / "skills" / "brain79-wiki"

        # 4a. plugin.json
        plugin_file = plugin_dir / "plugin.json"
        plugin_data: dict[str, Any] = {}
        if plugin_file.is_dir():
            print(f"⚠️ Warning: {plugin_file} exists and is a directory. Skipping plugin.json generation.")
        else:
            if plugin_file.is_file():
                try:
                    plugin_data = json.loads(plugin_file.read_text(encoding="utf-8"))
                    if not isinstance(plugin_data, dict):
                        if not dry_run:
                            plugin_file.replace(plugin_file.with_suffix(".json.bak"))
                        plugin_data = {}
                except Exception:
                    if not dry_run:
                        plugin_file.replace(plugin_file.with_suffix(".json.bak"))
                    plugin_data = {}

            if not plugin_data.get("name"):
                plugin_data["name"] = "brain79"

            p_new_raw = json.dumps(plugin_data, indent=2) + "\n"
            p_old_raw = plugin_file.read_text(encoding="utf-8") if plugin_file.is_file() else None
            if p_old_raw != p_new_raw:
                if not dry_run:
                    plugin_dir.mkdir(parents=True, exist_ok=True)
                    plugin_file.write_text(p_new_raw, encoding="utf-8", newline="\n")
                changed.append(".agents/plugins/brain79/plugin.json")

        # 4b. mcp_config.json
        plugin_mcp_file = plugin_dir / "mcp_config.json"
        plugin_mcp_data: dict[str, Any] = {}
        if plugin_mcp_file.is_dir():
            print(f"⚠️ Warning: {plugin_mcp_file} exists and is a directory. Skipping mcp_config.json generation.")
        else:
            if plugin_mcp_file.is_file():
                try:
                    plugin_mcp_data = json.loads(plugin_mcp_file.read_text(encoding="utf-8"))
                    if not isinstance(plugin_mcp_data, dict):
                        if not dry_run:
                            plugin_mcp_file.replace(plugin_mcp_file.with_suffix(".json.bak"))
                        plugin_mcp_data = {}
                except Exception:
                    if not dry_run:
                        plugin_mcp_file.replace(plugin_mcp_file.with_suffix(".json.bak"))
                    plugin_mcp_data = {}

            if "mcpServers" not in plugin_mcp_data or not isinstance(plugin_mcp_data["mcpServers"], dict):
                plugin_mcp_data["mcpServers"] = {}
            plugin_mcp_data["mcpServers"]["brain79"] = {
                "command": "brain79",
                "args": ["--project-root", "."],
            }
            pm_new_raw = json.dumps(plugin_mcp_data, indent=2) + "\n"
            pm_old_raw = plugin_mcp_file.read_text(encoding="utf-8") if plugin_mcp_file.is_file() else None
            if pm_old_raw != pm_new_raw:
                if not dry_run:
                    plugin_dir.mkdir(parents=True, exist_ok=True)
                    plugin_mcp_file.write_text(pm_new_raw, encoding="utf-8", newline="\n")
                changed.append(".agents/plugins/brain79/mcp_config.json")

        # 4c. skills/brain79-wiki/SKILL.md
        skill_file = skill_dir / "SKILL.md"
        if skill_file.is_dir():
            print(f"⚠️ Warning: {skill_file} exists and is a directory. Skipping SKILL.md generation.")
        else:
            from brain79 import __version__

            pkg_templates = resources.files("brain79.templates")
            skill_template = (pkg_templates / "SKILL.md").read_text(encoding="utf-8")
            skill_rendered = skill_template.replace("{{VERSION}}", __version__)
            skill_old = skill_file.read_text(encoding="utf-8") if skill_file.is_file() else None
            if skill_old != skill_rendered:
                if not dry_run:
                    skill_dir.mkdir(parents=True, exist_ok=True)
                    skill_file.write_text(skill_rendered, encoding="utf-8", newline="\n")
                changed.append(".agents/plugins/brain79/skills/brain79-wiki/SKILL.md")

    # Tier 2 (Desktop configs, opt-in)
    if include_desktop:
        desktop_targets: list[Path] = []
        if desktop_config_dir:
            desktop_targets.append(desktop_config_dir / "claude_desktop_config.json")
            desktop_targets.append(desktop_config_dir / "mcp_config.json")
        else:
            home = Path.home()
            if sys.platform == "darwin":
                desktop_targets.append(home / "Library/Application Support/Claude/claude_desktop_config.json")
            elif sys.platform == "win32":
                appdata = os.environ.get("APPDATA")
                if appdata:
                    desktop_targets.append(Path(appdata) / "Claude/claude_desktop_config.json")
            else:
                desktop_targets.append(home / ".config/Claude/claude_desktop_config.json")
            desktop_targets.append(home / ".codeium/windsurf/mcp_config.json")

        for cfg in desktop_targets:
            if ".gemini" in cfg.parts:
                continue
            if cfg.parent.exists():
                cfg_data: dict[str, Any] = {}
                is_valid_json = False
                if cfg.is_file():
                    try:
                        cfg_data = json.loads(cfg.read_text(encoding="utf-8"))
                        if isinstance(cfg_data, dict):
                            is_valid_json = True
                        else:
                            cfg_data = {}
                    except Exception:
                        cfg_data = {}

                if "mcpServers" not in cfg_data or not isinstance(cfg_data["mcpServers"], dict):
                    cfg_data["mcpServers"] = {}
                srv_key = f"brain79-{project_root.name}"
                binary_path = shutil.which("brain79") or "brain79"
                cfg_data["mcpServers"][srv_key] = {
                    "command": binary_path,
                    "args": ["--project-root", str(project_root.resolve())],
                }
                new_raw = json.dumps(cfg_data, indent=2) + "\n"
                old_raw = cfg.read_text(encoding="utf-8") if cfg.is_file() else None
                if old_raw != new_raw:
                    if not dry_run:
                        if cfg.is_file() and is_valid_json:
                            try:
                                shutil.copy2(cfg, cfg.with_suffix(".json.bak"))
                            except Exception:
                                pass
                        cfg.write_text(new_raw, encoding="utf-8", newline="\n")
                    changed.append(str(cfg))

    return changed


def sync_git_hooks(project_root: Path, install: bool = True, dry_run: bool = False) -> tuple[bool, str]:
    """Install or sync .git/hooks/pre-commit while preserving third-party hook managers."""
    git_dir = project_root / ".git"
    if not git_dir.exists() or not install:
        return False, "no git repository detected"

    hooks_dir = git_dir / "hooks"
    if not dry_run:
        hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    if not hook_path.exists():
        if not dry_run:
            hook_path.write_text(PRE_COMMIT_HOOK_SCRIPT, encoding="utf-8", newline="\n")
            mode = hook_path.stat().st_mode
            hook_path.chmod(mode | 0o111)
        return True, "installed .git/hooks/pre-commit"

    content = hook_path.read_text(encoding="utf-8")
    if "# brain-79 pre-commit hook" in content:
        if content == PRE_COMMIT_HOOK_SCRIPT:
            return False, ".git/hooks/pre-commit is already up-to-date"
        if not dry_run:
            hook_path.write_text(PRE_COMMIT_HOOK_SCRIPT, encoding="utf-8", newline="\n")
            mode = hook_path.stat().st_mode
            hook_path.chmod(mode | 0o111)
        return True, "updated .git/hooks/pre-commit"

    # Third-party hook manager or custom hook
    return (
        False,
        "preserved third-party git hook manager; add 'brain79 --project-root . lint --strict' to your hook configuration",
    )


def update_project(
    project_root: Path,
    dry_run: bool = False,
    commit_transition: bool = False,
    include_desktop: bool = False,
    desktop_config_dir: Path | None = None,
) -> dict[str, Any]:
    """Non-destructively upgrade project templates, schemas, and multi-harness registrations."""
    from brain79 import __version__
    from brain79.core.migration import migrate_wiki

    wiki_root = project_root / ".brain-79"
    if not wiki_root.exists():
        return {
            "status": "error",
            "message": f"No .brain-79/ directory found at {project_root}. Run 'brain79 init' first.",
        }

    manifest_updated, m_msg = sync_agents_manifest(project_root, dry_run=dry_run)
    schema_updated, s_msg = sync_schema_file(wiki_root, dry_run=dry_run)
    mcp_configs = sync_project_mcp_configs(
        project_root,
        include_desktop=include_desktop,
        desktop_config_dir=desktop_config_dir,
        dry_run=dry_run,
    )
    from brain79.core.harnesses import (
        ClaudeCodeAdapter,
        CopilotAdapter,
        CursorRulesAdapter,
    )

    instruction_harnesses: list[str] = []
    for inst_adapter in (ClaudeCodeAdapter(), CursorRulesAdapter(), CopilotAdapter()):
        instruction_harnesses.extend(inst_adapter.sync(project_root, dry_run=dry_run))

    git_hook_updated, g_msg = sync_git_hooks(project_root, dry_run=dry_run)
    migration_report = migrate_wiki(wiki_root, dry_run=dry_run)

    transition_ref = None
    if commit_transition and not dry_run:
        from brain79.core.handoff import write_handoff

        transition_ref = write_handoff(
            session_type="maintenance",
            summary=f"Upgraded project protocol to brain79 v{__version__}",
            completed_work=[
                m_msg,
                s_msg,
                f"Synchronized {len(mcp_configs)} MCP configs",
                g_msg,
            ],
            pending_work=["Proceed with active development"],
            boot_instruction="Project protocol upgraded; proceed with active tasks.",
            wiki_root=wiki_root,
        )

    return {
        "status": "ok",
        "dry_run": dry_run,
        "manifest_updated": manifest_updated,
        "schema_updated": schema_updated,
        "mcp_configs": mcp_configs,
        "instruction_harnesses": instruction_harnesses,
        "git_hook": g_msg,
        "migration_report": migration_report,
        "transition_handoff": transition_ref,
    }


def init_project(
    project_root: Path,
    install_git_hooks_flag: bool = True,
    profile: str = "software",
    auto_git_init: bool = True,
    upgrade: bool = False,
    include_desktop: bool = False,
    harnesses: list[str] | None = None,
) -> None:
    """Bootstrap .brain-79/ in a project directory and register MCP configurations."""
    wiki_root = project_root / ".brain-79"

    if wiki_root.exists():
        if upgrade:
            print(f"Upgrading existing project protocol and configurations at {project_root}...")
            update_project(project_root, include_desktop=include_desktop)
            print("Project upgrade complete.")
            return
        else:
            print(f"Wiki already exists at {wiki_root}.")
            print("Run 'brain79 update-project' (or 'brain79 init --upgrade') to sync templates and MCP configs.")
            sync_git_hooks(project_root, install=install_git_hooks_flag)
            return

    profile_clean = profile.strip().lower()
    if profile_clean not in ("software", "general"):
        raise ValueError(f"Unknown profile '{profile}'. Choose 'software' or 'general'.")

    # In software profile, auto-initialize git repository if not already in a git worktree
    if profile_clean == "software" and auto_git_init:
        git_dir = project_root / ".git"
        if not git_dir.exists():
            from brain79.core.handoff_freshness import is_git_workspace
            if not is_git_workspace(project_root):
                try:
                    from brain79.core.git_ops import git_init

                    git_init(project_root)
                except Exception:
                    pass

    wiki_dirs = WIKI_DIRS_GENERAL if profile_clean == "general" else WIKI_DIRS_SOFTWARE

    # Create directory structure
    for dir_path in wiki_dirs:
        target_dir = wiki_root / dir_path
        target_dir.mkdir(parents=True, exist_ok=True)
        # Keep empty dirs tracked by git
        (target_dir / ".gitkeep").touch()

    # Copy templates
    pkg_templates = resources.files("brain79.templates")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # SCHEMA template selection
    schema_template_name = "SCHEMA_GENERAL.md" if profile_clean == "general" else "SCHEMA.md"
    schema_content = (pkg_templates / schema_template_name).read_text(encoding="utf-8")
    schema_content = schema_content.replace("YYYY-MM-DD", today)
    (wiki_root / "SCHEMA.md").write_text(schema_content, encoding="utf-8", newline="\n")

    # INDEX template
    index_content = (pkg_templates / "INDEX.md").read_text(encoding="utf-8")
    index_content = index_content.replace("YYYY-MM-DD", today)
    (wiki_root / "INDEX.md").write_text(index_content, encoding="utf-8", newline="\n")

    # Ignore lock and temporary files in wiki_root
    (wiki_root / ".gitignore").write_text(".locks/\n*.lock\n*.tmp\n", encoding="utf-8", newline="\n")
    cleanup_legacy_inline_locks(wiki_root)

    # Synchronize selected (or all registered) harness adapters via core/harnesses registry
    from brain79.core.harnesses import resolve_harness_selection

    selected_adapters = resolve_harness_selection(harnesses)
    for adapter in selected_adapters:
        adapter.sync(project_root)

    if include_desktop:
        sync_project_mcp_configs(project_root, include_desktop=True, targets=set())

    # Configure git pre-commit hook
    sync_git_hooks(project_root, install=install_git_hooks_flag)

    print(f"Initialized .brain-79/ at {wiki_root}")
    print("Configured Tier 1 MCP harnesses: .mcp.json, .agents/mcp_config.json, .agents/plugins/brain79/, .cursor/mcp.json")
    print("Created/updated AGENTS.md with delimited protocol block")
