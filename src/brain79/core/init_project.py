import importlib.resources as resources
from pathlib import Path

WIKI_DIRS = [
    "_raw/sessions",
    "_raw/commits",
    "product",
    "architecture",
    "features",
    "changelog",
    "decisions",
]

TEMPLATE_FILES = ["SCHEMA.md", "INDEX.md"]

MCP_CONFIG = """{{
  "mcpServers": {{
    "brain79": {{
      "command": "/Users/xilax/.local/bin/brain79",
      "args": ["--project-root", "."]
    }}
  }}
}}
"""


def init_project(project_root: Path) -> None:
    """Bootstrap .brain-79/ in a project directory."""
    wiki_root = project_root / ".brain-79"

    if wiki_root.exists():
        print(f"Wiki already exists at {wiki_root}")
        print("Delete .brain-79/ manually if you want to re-initialize.")
        return

    # Create directory structure
    for dir_path in WIKI_DIRS:
        target_dir = wiki_root / dir_path
        target_dir.mkdir(parents=True, exist_ok=True)
        # Keep empty dirs tracked by git
        (target_dir / ".gitkeep").touch()

    # Copy templates
    pkg_templates = resources.files("brain79.templates")
    for name in TEMPLATE_FILES:
        content = (pkg_templates / name).read_text(encoding="utf-8")
        (wiki_root / name).write_text(content, encoding="utf-8")

    # Create .agents/mcp_config.json for agy per-project MCP registration
    agents_dir = project_root / ".agents"
    agents_dir.mkdir(exist_ok=True)
    mcp_config_path = agents_dir / "mcp_config.json"
    if not mcp_config_path.exists():
        import shutil
        binary_path = shutil.which("brain79") or "/Users/xilax/.local/bin/brain79"
        mcp_config_path.write_text(
            '{\n  "mcpServers": {\n    "brain79": {\n      "command": "'
            + binary_path
            + '",\n      "args": ["--project-root", "."]\n    }\n  }\n}\n',
            encoding="utf-8",
        )

    print(f"Initialized .brain-79/ at {wiki_root}")
    print(f"Created .agents/mcp_config.json")
    print()
    print("Next steps:")
    print("  1. Edit .brain-79/SCHEMA.md  — customize curation rules for this project")
    print("  2. Edit .brain-79/INDEX.md   — fill in project name, purpose, and status")
    print("  3. For global agy access, add brain79 to ~/.gemini/config/mcp_config.json")
    print("     (see README for the exact JSON snippet)")
