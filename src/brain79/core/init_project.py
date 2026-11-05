from datetime import datetime, timezone
from importlib import resources
import json
from pathlib import Path
import shutil

WIKI_DIRS_SOFTWARE = [
    "_raw/sessions",
    "_raw/commits",
    "handoffs",
    "product",
    "architecture",
    "features",
    "decisions",
    "changelog",
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

from brain79.core.locks import cleanup_legacy_inline_locks

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
    git_dir = project_root / ".git"
    if not git_dir.exists() or not install:
        return

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    hook_path.write_text(PRE_COMMIT_HOOK_SCRIPT, encoding="utf-8", newline="\n")
    mode = hook_path.stat().st_mode
    hook_path.chmod(mode | 0o111)


def init_project(
    project_root: Path,
    install_git_hooks_flag: bool = True,
    profile: str = "software",
) -> None:
    """Bootstrap .brain-79/ in a project directory and register MCP configurations."""
    wiki_root = project_root / ".brain-79"

    if wiki_root.exists():
        print(f"Wiki already exists at {wiki_root}")
        print("Delete .brain-79/ manually if you want to re-initialize.")
        install_git_hooks(project_root, install=install_git_hooks_flag)
        return

    profile_clean = profile.strip().lower()
    if profile_clean not in ("software", "general"):
        raise ValueError(f"Unknown profile '{profile}'. Choose 'software' or 'general'.")

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

    binary_path = shutil.which("brain79") or "brain79"

    # Create .agents/mcp_config.json for agy per-project MCP registration
    agents_dir = project_root / ".agents"
    agents_dir.mkdir(exist_ok=True)
    mcp_config_path = agents_dir / "mcp_config.json"
    if not mcp_config_path.exists():
        mcp_config_path.write_text(
            '{\n  "mcpServers": {\n    "brain79": {\n      "command": "'
            + binary_path
            + '",\n      "args": ["--project-root", "."]\n    }\n  }\n}\n',
            encoding="utf-8",
            newline="\n",
        )

    # 1. Deploy AGENTS.md manifest (universal CLI standard) idempotently
    agents_manifest_path = project_root / "AGENTS.md"
    agents_manifest_template = (pkg_templates / "AGENTS.md").read_text(encoding="utf-8")
    if agents_manifest_path.exists():
        existing_manifest = agents_manifest_path.read_text(encoding="utf-8")
        if "Brain-79" not in existing_manifest:
            new_manifest = (
                existing_manifest.rstrip() + "\n\n" + agents_manifest_template
            )
            agents_manifest_path.write_text(new_manifest, encoding="utf-8", newline="\n")
    else:
        agents_manifest_path.write_text(agents_manifest_template, encoding="utf-8", newline="\n")

    # 2. Deploy or update .mcp.json (Pi / universal MCP server definition) idempotently
    mcp_path = project_root / ".mcp.json"
    mcp_data: dict = {}
    if mcp_path.exists():
        if mcp_path.is_dir():
            print(
                f"⚠️ Warning: {mcp_path} exists and is a directory. Skipping .mcp.json generation."
            )
            mcp_data = {}
        else:
            try:
                mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
                if not isinstance(mcp_data, dict):
                    print(
                        f"⚠️ Warning: {mcp_path} is not a JSON object. Backing up to {mcp_path}.bak"
                    )
                    mcp_path.rename(mcp_path.with_suffix(".json.bak"))
                    mcp_data = {}
            except json.JSONDecodeError as e:
                print(f"⚠️ Warning: Existing {mcp_path} is invalid JSON ({e}).")
                print(
                    f"  Backing up to {mcp_path.with_suffix('.json.bak')} and creating fresh config."
                )
                mcp_path.rename(mcp_path.with_suffix(".json.bak"))
                mcp_data = {}

    if not mcp_path.is_dir():
        if "mcpServers" not in mcp_data or not isinstance(mcp_data["mcpServers"], dict):
            mcp_data["mcpServers"] = {}

        mcp_data["mcpServers"]["brain79"] = {
            "command": binary_path,
            "args": ["--project-root", "."],
            "toolPrefix": "none",
        }
        mcp_path.write_text(json.dumps(mcp_data, indent=2) + "\n", encoding="utf-8", newline="\n")

    install_git_hooks(project_root, install=install_git_hooks_flag)

    print(f"Initialized .brain-79/ at {wiki_root}")
    print("Created .agents/mcp_config.json")
    print("Created/updated AGENTS.md (universal protocol manifest)")
    print("Created/updated .mcp.json (Pi and universal MCP registration)")
