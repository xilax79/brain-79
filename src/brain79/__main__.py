import os
from pathlib import Path
import sys

# Must be set before fastmcp is imported so the banner is suppressed.
# MCP hosts (agy, opencode, etc.) treat any stderr output during the
# handshake phase as a server failure signal.
os.environ.setdefault("FASTMCP_SHOW_SERVER_BANNER", "false")


def parse_global_flags(args: list[str]) -> tuple[Path | None, bool, list[str]]:
    """Extract global --project-root and --debug flags regardless of position."""
    project_root: Path | None = None
    debug = False
    filtered_args: list[str] = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--debug":
            debug = True
            i += 1
        elif arg == "--project-root":
            if i + 1 < len(args):
                project_root = Path(args[i + 1]).resolve()
                i += 2
            else:
                sys.stderr.write("Error: --project-root requires a path argument.\n")
                sys.exit(2)

        elif arg.startswith("--project-root="):
            path_str = arg.split("=", 1)[1]
            project_root = Path(path_str).resolve()
            i += 1
        else:
            filtered_args.append(arg)
            i += 1

    return project_root, debug, filtered_args


ROOT_HELP = """usage: brain79 [-h] [-v] [--project-root PATH] [--debug] [command] ...

Persistent, curated memory and documentation protocol for AI-assisted projects.

Global options:
  -h, --help            Show this help message and exit
  -v, --version         Show installed version and exit
  --project-root PATH   Target project directory (default: current working directory)
  --debug               Print full error tracebacks for troubleshooting

Session & workflow:
  orient                Get project context, active handoff, and relevant articles for a task
  session-commit        Save session progress: apply documentation changes and record a handoff
  context               Find knowledge articles and decisions relevant to a task and files
  index                 Display the project documentation index (INDEX.md)
  ingest                Record raw notes, transcripts, or logs from a working session

Handoff continuity:
  handoff-write         Save a session handoff (completed work, pending tasks, next steps)
  handoff-read          Show the latest or a specific session handoff
  handoff-purge         Clean up old or temporary session handoffs (dry-run by default)

Documentation reading & writing:
  read                  Read an article (supports extracting specific sections)
  read-batch            Read multiple articles in a single operation
  write                 Create or update an article with schema validation
  edit                  Apply targeted text replacements to an article
  write-many            Create or update multiple articles in one batch
  list                  List documentation articles by section
  search                Search documentation by keywords

Maintenance & governance:
  lint                  Check wiki for broken links, missing metadata, and invalid structure
  schema                Show required frontmatter fields, templates, and document skeletons
  navigate              Display or refresh table of contents in INDEX.md
  migrate               Upgrade older documentation files to match current schema
  init                  Initialize a brain-79 memory wiki in the project
  update                Update wiki templates and schema to the latest version
  bootstrap             Analyze an existing project and generate initial documentation templates

Server mode:
  Running 'brain79' without subcommands starts the FastMCP stdio server for
  AI clients (Cursor, Claude Desktop, Pi, OpenCode).
"""


def _cmd_serve(project_root: Path | None) -> None:
    from brain79 import config

    if project_root is not None:
        config.set_project_root(project_root)
    from brain79.server import mcp

    mcp.run()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    project_root, debug, filtered = parse_global_flags(args)

    if project_root is not None:
        from brain79 import config

        config.set_project_root(project_root)

    # 1. No subcommand or arguments -> FastMCP stdio server fallback (ADR-001)
    if not filtered:
        _cmd_serve(project_root)
        return

    first = filtered[0]

    # 2. Help flags or help command
    if first in ("-h", "--help", "help"):
        if len(filtered) > 1:
            target = filtered[1]
            from brain79.cli import WHITELIST, run_cli

            if target in WHITELIST:
                sys.exit(run_cli(target, ["--help"], debug=debug))
            else:
                sys.stderr.write(
                    f"Error: Unknown command '{target}'. Run 'brain79 --help' for available commands.\n"
                )
                sys.exit(2)
        sys.stdout.write(ROOT_HELP)
        sys.exit(0)

    # 3. Version flags
    if first in ("-v", "--version"):
        from brain79 import __version__

        sys.stdout.write(f"brain79 {__version__}\n")
        sys.exit(0)

    # 4. Whitelisted subcommands
    from brain79.cli import WHITELIST, run_cli

    if first in WHITELIST:
        cmd = first
        sub_args = filtered[1:]
        sys.exit(run_cli(cmd, sub_args, debug=debug))

    # 5. Unknown command or flag -> exit code 2
    sys.stderr.write(
        f"Error: Unknown command or flag '{first}'. Run 'brain79 --help' for available commands.\n"
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
