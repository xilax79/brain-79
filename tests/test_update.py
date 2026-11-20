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


def test_not_git_repo_triggers_standalone_update(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Scenario A: .git directory not found triggers standalone zero-clone update."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "uv" in cmd and "install" in cmd:
            assert "--force" in cmd
            assert any("git+https://github.com/xilax79/brain-79.git" in c for c in cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="Installed", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 0
    captured = capsys.readouterr()
    assert (
        "[OK] Successfully updated brain79. Run 'brain79 update-project' inside existing repositories to sync templates."
        in captured.out
    )


def test_site_packages_standalone_ignores_home_dotgit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that module path inside site-packages ignores parent .git (e.g. $HOME/.git) unless PEP 610 editable."""
    site_packages = tmp_path / "home" / "user" / ".local" / "share" / "uv" / "tools" / "brain79" / "lib" / "python3.11" / "site-packages"
    pkg_dir = site_packages / "brain79"
    pkg_dir.mkdir(parents=True)
    init_file = pkg_dir / "__init__.py"
    init_file.write_text("# mock site-packages", encoding="utf-8")

    # Put a fake dotgit in $HOME to simulate dotfiles repo
    home_git = tmp_path / "home" / "user" / ".git"
    home_git.mkdir(parents=True)

    mock_spec = MagicMock()
    mock_spec.origin = str(init_file)

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "uv" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="Installed", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("importlib.util.find_spec", return_value=mock_spec),
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 0
    captured = capsys.readouterr()
    assert (
        "[OK] Successfully updated brain79. Run 'brain79 update-project' inside existing repositories to sync templates."
        in captured.out
    )


def test_site_packages_editable_pep610_routes_to_branch_a(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that site-packages install with PEP 610 direct_url.json editable:true routes to Branch A."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    (checkout / "pyproject.toml").write_text("[project]\nname='brain79'\n", encoding="utf-8")

    site_packages = tmp_path / "site-packages"
    pkg_dir = site_packages / "brain79"
    pkg_dir.mkdir(parents=True)
    init_file = pkg_dir / "__init__.py"
    init_file.write_text("# mock", encoding="utf-8")

    dist_info = site_packages / "brain79-0.9.2.dist-info"
    dist_info.mkdir(parents=True)
    import json
    direct_url_data = {
        "dir_info": {"editable": True},
        "url": checkout.as_uri(),
    }
    (dist_info / "direct_url.json").write_text(json.dumps(direct_url_data), encoding="utf-8")

    mock_spec = MagicMock()
    mock_spec.origin = str(init_file)

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "remote" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="origin_url", stderr="")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "symbolic-ref" in cmd and "--short" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if "symbolic-ref" in cmd and "refs/remotes/origin/HEAD" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="refs/remotes/origin/main\n", stderr="")
        if "fetch" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="same_hash\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with (
        patch("importlib.util.find_spec", return_value=mock_spec),
        patch("shutil.which", return_value="/usr/bin/mock"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project()

    assert code == 0
    captured = capsys.readouterr()
    assert f"Updating brain79 from: {checkout}" in captured.out
    assert "[OK] Already up to date." in captured.out


def test_standalone_network_failure_exit_3(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test standalone install returns exit code 3 on network/remote failure."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    fail_proc = subprocess.CompletedProcess(
        ["uv"], 1, stdout="", stderr="fatal: remote error: could not resolve host github.com"
    )

    with (
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", return_value=fail_proc),
    ):
        code = update_project()

    assert code == 3
    captured = capsys.readouterr()
    assert "[ERR] Failed to update from upstream Git" in captured.out


def test_standalone_generic_failure_exit_1(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test standalone install returns exit code 1 on generic tool install error."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    fail_proc = subprocess.CompletedProcess(
        ["uv"], 1, stdout="", stderr="error: Failed to build wheel for dependency foo"
    )

    with (
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", return_value=fail_proc),
    ):
        code = update_project()

    assert code == 1
    captured = capsys.readouterr()
    assert "[ERR] Update failed" in captured.out


def test_standalone_branch_override(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test standalone install with branch override."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    captured_cmds: list[list[str]] = []

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="Installed", stderr="")

    with (
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", side_effect=mock_run),
    ):
        code = update_project(branch_override="develop")

    assert code == 0
    assert any("git+https://github.com/xilax79/brain-79.git@develop" in c for c in captured_cmds[0])


def test_standalone_invalid_branch(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test standalone install with invalid branch name containing illegal chars."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    with patch("shutil.which", return_value="/usr/bin/uv"):
        code = update_project(branch_override="invalid branch; rm -rf")

    assert code == 1
    captured = capsys.readouterr()
    assert "[ERR] Invalid branch name" in captured.out


def test_standalone_missing_uv_binary(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test standalone install fails with exit 4 when uv binary is missing."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    with patch("shutil.which", return_value=None):
        code = update_project()

    assert code == 4
    captured = capsys.readouterr()
    assert "[ERR] Missing required binary: 'uv'." in captured.out


def test_standalone_timeout_expired(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test standalone install timeout returns exit code 3."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    with (
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["uv"], timeout=180)),
    ):
        code = update_project()

    assert code == 3
    captured = capsys.readouterr()
    assert "timeout" in captured.out.lower()


def test_standalone_windows_locked_binary(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test standalone install on Windows with locked executable."""
    git_dir = mock_brain79_env / ".git"
    git_dir.rmdir()

    fail_proc = subprocess.CompletedProcess(
        ["uv"], 1, stdout="", stderr="error: Access is denied. (os error 5)"
    )

    with (
        patch("sys.platform", "win32"),
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", return_value=fail_proc),
    ):
        code = update_project()

    assert code == 3
    captured = capsys.readouterr()
    assert "Cannot overwrite running executable on Windows" in captured.out


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
        "[!] WARNING: Git update succeeded, but environment rebuild failed. Please run 'uv tool install --editable --force .' manually."
        in captured.out
    )


def test_successful_update(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test happy path execution order and successful update."""
    executed_cmds: list[list[str]] = []

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        executed_cmds.append(cmd)
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
    assert (
        "[OK] Successfully updated brain79. Run 'brain79 update-project' inside existing repositories to sync templates."
        in captured.out
    )
    # Check that uv tool install --editable --force . was called
    uv_calls = [c for c in executed_cmds if "uv" in c and "install" in c]
    assert len(uv_calls) == 1
    assert "--editable" in uv_calls[0]
    assert "--force" in uv_calls[0]


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


def test_update_project_rejects_option_injection_branch_override(
    mock_brain79_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-10.9: branch_override starting with '-' is rejected with exit code 1 before invoking subprocess."""
    with patch("subprocess.run") as mock_run:
        for bad_branch in ("--upload-pack=evil", "-x", "--"):
            rc = update_project(branch_override=bad_branch)
            assert rc == 1
        mock_run.assert_not_called()
