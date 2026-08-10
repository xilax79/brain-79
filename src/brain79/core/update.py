"""Module for updating brain79 from git repository."""

import importlib.util
import shutil
import subprocess
from pathlib import Path


def _find_git_root(brain79_path: Path) -> Path | None:
    """Find the root directory of the git repository containing brain79."""
    for parent in brain79_path.parents:
        if (parent / ".git").exists():
            return parent
    return None


def update_project(branch_override: str | None = None) -> int:
    """Update brain79 to the latest version from origin.

    Returns:
        int: Exit code (0, 1, 2, 3, 4, or 130).
    """
    try:
        spec = importlib.util.find_spec("brain79")
        if spec is None or spec.origin is None:
            print("[ERR] Brain79 module specification or origin not found.")
            return 1

        brain79_path = Path(spec.origin).resolve()
        if not brain79_path.exists():
            print(
                f"[ERR] Installation path '{brain79_path}' does not exist. "
                "The symlink may be broken."
            )
            return 1

        git_root = _find_git_root(brain79_path)
        if git_root is None:
            print("[--] brain79 not installed via editable install.")
            return 0

        print(f"Updating brain79 from: {git_root}")

        # Verify binaries
        if not shutil.which("git"):
            print("[ERR] Missing required binary: 'git'.")
            return 4

        if not shutil.which("uv"):
            print("[ERR] Missing required binary: 'uv'.")
            return 4

        # Verify pyproject.toml structure
        pyproject_path = git_root / "pyproject.toml"
        if not pyproject_path.exists():
            print(
                f"[ERR] pyproject.toml not found at '{git_root}'. "
                "The repository structure may be invalid."
            )
            return 1

        # Check git remote
        remote_res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if remote_res.returncode != 0:
            print(
                "[ERR] Failed to fetch from upstream. Check your internet connection or git remotes."
            )
            return 1

        # Check working tree cleanliness
        status_res = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if status_res.returncode != 0 or status_res.stdout.strip():
            print(
                "[ERR] Local modifications detected. Please commit or stash your changes before updating."
            )
            return 1

        # Check branch (detached HEAD or valid branch)
        branch_res = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if branch_res.returncode != 0:
            print("[ERR] Detached HEAD. Cannot determine current branch.")
            return 1

        current_branch = branch_res.stdout.strip()

        # Determine default remote branch
        if branch_override:
            default_branch = branch_override
        else:
            ref_res = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ref_res.returncode == 0 and ref_res.stdout.strip():
                raw_ref = ref_res.stdout.strip()
                prefix = "refs/remotes/origin/"
                if raw_ref.startswith(prefix):
                    default_branch = raw_ref.removeprefix(prefix)
                else:
                    default_branch = raw_ref
            else:
                default_branch = "main"
                print(
                    "[!] Could not detect default branch. Assuming 'main'. Use --branch to override."
                )

        if current_branch != default_branch:
            print(
                f"[ERR] On branch '{current_branch}', not '{default_branch}'. "
                "Switching branches automatically is unsafe."
            )
            return 1

        # Fetch origin
        print("Fetching from origin...")
        try:
            fetch_res = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if fetch_res.returncode != 0:
                print(
                    "[ERR] Failed to fetch from upstream. Check your internet connection or git remotes."
                )
                return 3
        except subprocess.TimeoutExpired:
            print(
                "[ERR] Failed to fetch from upstream. Check your internet connection or git remotes."
            )
            return 3

        # Check diff (rev-parse)
        local_rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        remote_rev = subprocess.run(
            ["git", "rev-parse", f"origin/{default_branch}"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if (
            local_rev.returncode == 0
            and remote_rev.returncode == 0
            and local_rev.stdout.strip() == remote_rev.stdout.strip()
        ):
            print("[OK] Already up to date.")
            return 0

        # Pull updates
        try:
            pull_res = subprocess.run(
                ["git", "pull", "--ff-only", "origin", default_branch],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if pull_res.returncode != 0:
                output = pull_res.stderr + pull_res.stdout
                if (
                    "Not possible to fast-forward" in output
                    or "diverged" in output
                    or "Not fast-forward" in output
                ):
                    print(
                        "[ERR] Local branch has diverged from origin. Resolve manually."
                    )
                    return 1
                else:
                    print("[ERR] Git pull failed.")
                    return 3
        except subprocess.TimeoutExpired:
            print("[ERR] Git pull failed.")
            return 3

        # Rebuild package
        try:
            uv_res = subprocess.run(
                ["uv", "tool", "install", "--force", "."],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if uv_res.returncode != 0:
                print(
                    "[!] WARNING: Git update succeeded, but environment rebuild failed. "
                    "Please run 'uv tool install --force .' manually."
                )
                return 1
        except subprocess.TimeoutExpired:
            print(
                "[!] WARNING: Git update succeeded, but environment rebuild failed. "
                "Please run 'uv tool install --force .' manually."
            )
            return 1

        print("[OK] Successfully updated brain79.")
        return 0

    except KeyboardInterrupt:
        print("\n[!] Update cancelled by user.")
        return 130
