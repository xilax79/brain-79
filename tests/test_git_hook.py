import os
from pathlib import Path
import subprocess

from brain79.cli.dispatch import run_cli
from brain79.config import set_project_root
from brain79.core.init_project import init_project, install_git_hooks


def test_install_git_hook_creates_executable_file(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    install_git_hooks(tmp_path, install=True)

    hook_path = git_dir / "hooks" / "pre-commit"
    assert hook_path.exists()
    assert os.access(hook_path, os.X_OK)

    content = hook_path.read_text(encoding="utf-8")
    assert "lint --strict" in content


def test_install_git_hook_skips_when_no_git_dir(tmp_path: Path) -> None:
    # No .git directory
    install_git_hooks(tmp_path, install=True)
    assert not (tmp_path / ".git").exists()


def test_init_no_git_hooks_flag(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    set_project_root(tmp_path)
    code = run_cli("init", ["--no-git-hooks", "--project-root", str(tmp_path)])
    assert code == 0

    hook_path = git_dir / "hooks" / "pre-commit"
    assert not hook_path.exists()


def test_pre_commit_script_runs_lint_strict(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    set_project_root(tmp_path)
    init_project(tmp_path, install_git_hooks_flag=True)

    hook_path = git_dir / "hooks" / "pre-commit"
    assert hook_path.exists()

    # Make INDEX.md compliant so lint --strict would pass
    index_file = tmp_path / ".brain-79" / "INDEX.md"
    index_file.write_text(
        "# Index\n\n[Schema](SCHEMA.md)\n\n## Project\nClean project.\n",
        encoding="utf-8",
    )

    # Initialize a real git repository inside tmp_path for git diff testing
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", ".brain-79/INDEX.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Run the pre-commit script directly
    res = subprocess.run([str(hook_path)], cwd=tmp_path, capture_output=True, text=True)
    assert res.returncode == 0
