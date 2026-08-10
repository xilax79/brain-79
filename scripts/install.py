#!/usr/bin/env -S uv run --script
"""Installer script for the brain79 CLI tool.

Usage:
    uv run scripts/install.py [uninstall|status]    # cross-platform
    ./scripts/install.py [uninstall|status]         # Unix/macOS (requires chmod +x)

Note: Both methods require `uv` to be installed. The script cannot install
brain79 without uv present on the system.

Commands:
    (default)  Install brain79 as an editable tool using uv.
    uninstall  Uninstall brain79 tool environment.
    status     Check if brain79 is currently installed in uv.
"""

from pathlib import Path
import os
import shutil
import subprocess
import sys


def validate_environment() -> None:
    """Validate that required tooling and root workspace files exist."""
    if not shutil.which("uv"):
        print("[ERR] 'uv' is not installed or not found in PATH.", file=sys.stderr)
        sys.exit(1)

    if not Path("pyproject.toml").exists():
        print(
            "[ERR] 'pyproject.toml' not found. Run this script from the root of the repository.",
            file=sys.stderr,
        )
        sys.exit(1)


def install_tool() -> None:
    """Install brain79 as an editable uv tool."""
    if sys.platform == "win32":
        path_env = os.environ.get("PATH", "").lower()
        uv_bin = str(Path.home() / ".local" / "bin").lower()
        cargo_bin = str(Path.home() / ".cargo" / "bin").lower()
        if (
            "uv" not in path_env
            and uv_bin not in path_env
            and cargo_bin not in path_env
        ):
            print(
                "[!] WARNING: Make sure uv's binary directory (e.g. %USERPROFILE%\\.local\\bin) is included in your PATH.",
                file=sys.stderr,
            )

    cmd = ["uv", "tool", "install", "--editable", "--reinstall", "."]
    try:
        subprocess.run(cmd, check=True)
        print("[OK] brain79 installed successfully.")
    except subprocess.CalledProcessError as e:
        print(
            f"[ERR] Installation failed with exit code {e.returncode}", file=sys.stderr
        )
        sys.exit(1)


def uninstall_tool() -> None:
    """Uninstall brain79 tool using uv."""
    cmd = ["uv", "tool", "uninstall", "brain79"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    stderr_lower = result.stderr.lower()
    stdout_lower = result.stdout.lower()

    if (
        "not installed" in stderr_lower
        or "no such tool" in stderr_lower
        or "not installed" in stdout_lower
    ):
        print("[--] brain79 was not installed.")
    elif result.returncode == 0:
        print("[OK] brain79 uninstalled successfully.")
    else:
        print(
            f"[ERR] Uninstall failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(1)


def status_tool() -> None:
    """Check installation status of brain79 in uv environment."""
    cmd = ["uv", "tool", "list"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"[ERR] 'uv tool list' failed with exit code {e.returncode}",
            file=sys.stderr,
        )
        sys.exit(1)

    if "brain79" in result.stdout:
        print("[OK] brain79 is installed in the uv environment.")
    else:
        print("[--] brain79 is NOT installed.")


def print_usage() -> None:
    """Print usage instructions to stderr."""
    print("Usage: uv run scripts/install.py [uninstall|status]", file=sys.stderr)


def main() -> None:
    """Main entry point for installer CLI."""
    if len(sys.argv) < 2:
        verb = "install"
    else:
        verb = sys.argv[1]

    if verb not in ("install", "uninstall", "status"):
        print_usage()
        sys.exit(1)

    validate_environment()

    if verb == "install":
        install_tool()
    elif verb == "uninstall":
        uninstall_tool()
    elif verb == "status":
        status_tool()


if __name__ == "__main__":
    main()
