"""Unit tests for brain79 update command."""

from collections.abc import Generator
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from brain79.core.update import update_project


@pytest.fixture
def mock_brain79_env(tmp_path: Path) -> Generator[Path, None, None]:
    """Setup a mock brain79 package environment with a .git folder and pyproject.toml."""
    pkg_dir = tmp_path / "src" / "brain79"
    pkg_dir.mkdir(parents=True)
    init_file = pkg_dir / "__init__.py"
    init_file.write_text("# mock", encoding="utf-8")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'brain79'\n", encoding="utf-8")

    mock_spec = MagicMock()
    mock_spec.origin = str(init_file)

    with patch("importlib.util.find_spec", return_value=mock_spec):
        yield tmp_path


def test_not_git_repo(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario A: .git directory not found in module parent hierarchy."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    code = update_project()
    assert code == 0
    captured = capsys.readouterr()
    assert "[--] brain79 not installed via editable install." in captured.out


def test_missing_git_binary(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario B: git binary not available in PATH."""

    def mock_which(cmd: str) -> str | None:
        if cmd == "git":
            return None
        return "/usr/bin/uv"

    with patch("shutil.which", side_effect=mock_which):
        code = update_project()

    assert code == 4
    captured = capsys.readouterr()
    assert "[ERR] Missing required binary: 'git'." in captured.out


def test_missing_uv_binary(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario B: uv binary not available in PATH."""

    def mock_which(cmd: str) -> str | None:
        if cmd == "uv":
            return None
        return "/usr/bin/git"

    with patch("shutil.which", side_effect=mock_which):
        code = update_project()

    assert code == 4
    captured = capsys.readouterr()
    assert "[ERR] Missing required binary: 'uv'." in captured.out


def test_dirty_working_tree(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario C: uncommitted local changes detected in git repository."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=" M src/brain79/core/update.py\n", stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert (
        "[ERR] Local modifications detected. Please commit or stash your changes before updating."
        in captured.out
    )


def test_detached_head(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario D: repository is in a detached HEAD state."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(
                cmd, 128, stdout="", stderr="fatal: ref HEAD is not a symbolic ref"
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert "[ERR] Detached HEAD. Cannot determine current branch." in captured.out


def test_non_main_branch(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario D: current branch differs from detected default branch."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="feature/my-branch\n", stderr=""
            )
        if "symbolic-ref" in cmd and "refs/remotes/origin/HEAD" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="refs/remotes/origin/main\n", stderr=""
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert (
        "[ERR] On branch 'feature/my-branch', not 'main'. Switching branches automatically is unsafe."
        in captured.out
    )


def test_no_origin_remote(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario E: remote origin missing."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(
                cmd, 2, stdout="", stderr="error: No such remote 'origin'"
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert (
        "[ERR] Failed to fetch from upstream. Check your internet connection or git remotes."
        in captured.out
    )


def test_network_failure(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario E: git fetch fails due to network failure."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "symbolic-ref" in cmd and "refs/remotes/origin/HEAD" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="refs/remotes/origin/main\n", stderr=""
            )
        if "fetch" in cmd:
            return subprocess.CompletedProcess(
                cmd, 128, stdout="", stderr="fatal: Could not read from remote"
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 3
    captured = capsys.readouterr()
    assert (
        "[ERR] Failed to fetch from upstream. Check your internet connection or git remotes."
        in captured.out
    )


def test_diverged_branches(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario F: fast-forward pull rejected due to branch divergence."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "symbolic-ref" in cmd and "refs/remotes/origin/HEAD" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="refs/remotes/origin/main\n", stderr=""
            )
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "rev-parse" in cmd:
            if "HEAD" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="abc1234\n", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="def5678\n", stderr="")
        if "pull" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                1,
                stdout="",
                stderr="fatal: Not possible to fast-forward, aborting.",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert (
        "[ERR] Local branch has diverged from origin. Resolve manually." in captured.out
    )


def test_already_up_to_date(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test happy path when local commit matches remote commit."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "symbolic-ref" in cmd and "refs/remotes/origin/HEAD" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="refs/remotes/origin/main\n", stderr=""
            )
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="same_hash\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 0
    captured = capsys.readouterr()
    assert "[OK] Already up to date." in captured.out


def test_uv_rebuild_failure(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario G: git pull succeeds but uv tool install fails."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "symbolic-ref" in cmd and "refs/remotes/origin/HEAD" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="refs/remotes/origin/main\n", stderr=""
            )
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "rev-parse" in cmd:
            if "HEAD" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="abc1234\n", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="def5678\n", stderr="")
        if "pull" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "uv" in cmd:
            return subprocess.CompletedProcess(
                cmd, 1, stdout="", stderr="error: failed to install"
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert (
        "[!] WARNING: Git update succeeded, but environment rebuild failed. Please run 'uv tool install --force .' manually."
        in captured.out
    )


def test_successful_update(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test happy path execution order and successful update."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "symbolic-ref" in cmd and "refs/remotes/origin/HEAD" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="refs/remotes/origin/main\n", stderr=""
            )
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "rev-parse" in cmd:
            if "HEAD" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="abc1234\n", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="def5678\n", stderr="")
        if "pull" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "uv" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="Installed", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 0
    captured = capsys.readouterr()
    assert "[OK] Successfully updated brain79." in captured.out


def test_keyboard_interrupt(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test handling of user cancellation via KeyboardInterrupt."""
    with patch("shutil.which", side_effect=KeyboardInterrupt):
        code = update_project()

    assert code == 130
    captured = capsys.readouterr()
    assert "[!] Update cancelled by user." in captured.out


def test_branch_override(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test branch override argument behavior."""

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="custom-branch\n", stderr=""
            )
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="hash123\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project(branch_override="custom-branch")

    assert code == 0
    captured = capsys.readouterr()
    assert "[OK] Already up to date." in captured.out


def test_missing_pyproject(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario H: pyproject.toml is missing from git root."""
    pyproject = mock_brain79_env / "pyproject.toml"
    pyproject.unlink()

    with patch("shutil.which", return_value="/usr/bin/mock"):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert "pyproject.toml not found at" in captured.out
