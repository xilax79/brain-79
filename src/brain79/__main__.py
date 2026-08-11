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


def _cmd_serve(project_root: Path | None) -> None:
    from brain79 import config

    if project_root is not None:
        config.set_project_root(project_root)
    from brain79.server import mcp

    mcp.run()


def main() -> None:
    args = sys.argv[1:]
    project_root, debug, filtered = parse_global_flags(args)

    if project_root is not None:
        from brain79 import config

        config.set_project_root(project_root)

    from brain79.cli import WHITELIST, run_cli

    if filtered and filtered[0] in WHITELIST:
        cmd = filtered[0]
        sub_args = filtered[1:]
        sys.exit(run_cli(cmd, sub_args, debug=debug))
    else:
        _cmd_serve(project_root)


if __name__ == "__main__":
    main()
