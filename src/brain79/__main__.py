import argparse
import sys
from pathlib import Path


def _cmd_init(project_root: str) -> None:
    from brain79.core.init_project import init_project

    init_project(Path(project_root).resolve())


def _cmd_serve(project_root: str) -> None:
    from brain79 import config
    from brain79.server import mcp

    config.set_project_root(Path(project_root).resolve())
    mcp.run()


def main() -> None:
    # Dispatch on first positional arg to avoid argparse subparser conflicts
    # with MCP clients that pass --project-root directly (no subcommand).
    args = sys.argv[1:]

    if args and args[0] == "init":
        parser = argparse.ArgumentParser(prog="brain79 init")
        parser.add_argument(
            "--project-root",
            default=".",
            metavar="PATH",
            help="Project root directory (default: current directory)",
        )
        parsed = parser.parse_args(args[1:])
        _cmd_init(parsed.project_root)
    else:
        # Default: MCP server mode (used by MCP clients via uvx / uv run)
        parser = argparse.ArgumentParser(
            prog="brain79",
            description="Per-project AI memory system — MCP server",
        )
        parser.add_argument(
            "--project-root",
            default=".",
            metavar="PATH",
            help="Project root directory (default: current directory)",
        )
        parsed = parser.parse_args(args)
        _cmd_serve(parsed.project_root)


if __name__ == "__main__":
    main()
