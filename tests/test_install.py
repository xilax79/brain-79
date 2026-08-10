"""Unit tests for scripts/install.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess
import sys

import pytest

from scripts.install import (
    install_tool,
    main,
    status_tool,
    uninstall_tool,
    validate_environment,
)


def test_shebang_line_is_present() -> None:
    """Test that the first line of scripts/install.py is the required Unix shebang."""
    first_line = Path("scripts/install.py").read_text().splitlines()[0]
    assert first_line == "#!/usr/bin/env -S uv run --script"


def test_main_no_arguments() -> None:
    """Test that main defaults to install when no verb argument is given."""
    with (
        patch("scripts.install.validate_environment"),
        patch("scripts.install.install_tool") as mock_install,
        patch.object(sys, "argv", ["scripts/install.py"]),
    ):
        main()
        mock_install.assert_called_once()


def test_main_invalid_argument(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that main exits with code 1 when an unrecognized verb is passed."""
    with patch.object(sys, "argv", ["scripts/install.py", "invalid_verb"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "Usage: uv run scripts/install.py [uninstall|status]" in stderr


def test_validate_environment_missing_uv(capsys: pytest.CaptureFixture[str]) -> None:
    """Test environment validation failure when uv is missing."""
    with patch("shutil.which", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            validate_environment()
        assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "'uv' is not installed" in stderr


def test_validate_environment_missing_pyproject(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test environment validation failure when pyproject.toml is missing."""
    with (
        patch("shutil.which", return_value="/usr/local/bin/uv"),
        patch.object(Path, "exists", return_value=False),
    ):
        with pytest.raises(SystemExit) as exc_info:
            validate_environment()
        assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "'pyproject.toml' not found" in stderr


def test_install_tool_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Test successful tool installation."""
    with patch("subprocess.run") as mock_run:
        install_tool()
        mock_run.assert_called_once_with(
            ["uv", "tool", "install", "--editable", "--reinstall", "."],
            check=True,
        )
    stdout = capsys.readouterr().out
    assert "[OK] brain79 installed successfully." in stdout


def test_install_tool_windows_warning(capsys: pytest.CaptureFixture[str]) -> None:
    """Test warning output on Windows when uv binary directory is not in PATH environment variable."""
    with (
        patch("sys.platform", "win32"),
        patch("os.environ.get", return_value="C:\\Windows\\System32"),
        patch.object(Path, "home", return_value=Path("C:\\Users\\test")),
        patch("subprocess.run"),
    ):
        install_tool()
    stderr = capsys.readouterr().err
    assert "WARNING: Make sure uv's binary directory" in stderr


def test_install_tool_called_process_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Test installer behavior when subprocess fails with CalledProcessError."""
    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["uv", "tool", "install"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            install_tool()
        assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "[ERR] Installation failed with exit code 1" in stderr


def test_uninstall_tool_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Test successful uninstallation."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "Uninstalled 1 package"
    mock_res.stderr = ""

    with patch("subprocess.run", return_value=mock_res):
        uninstall_tool()
    stdout = capsys.readouterr().out
    assert "[OK] brain79 uninstalled successfully." in stdout


def test_uninstall_tool_not_installed(capsys: pytest.CaptureFixture[str]) -> None:
    """Test uninstalling when brain79 is not installed."""
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stdout = ""
    mock_res.stderr = "error: Tool `brain79` is not installed"

    with patch("subprocess.run", return_value=mock_res):
        uninstall_tool()
    stdout = capsys.readouterr().out
    assert "[--] brain79 was not installed." in stdout


def test_uninstall_tool_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """Test uninstall command unexpected failure."""
    mock_res = MagicMock()
    mock_res.returncode = 2
    mock_res.stdout = ""
    mock_res.stderr = "Fatal error"

    with patch("subprocess.run", return_value=mock_res):
        with pytest.raises(SystemExit) as exc_info:
            uninstall_tool()
        assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "[ERR] Uninstall failed with exit code 2" in stderr


def test_status_tool_installed(capsys: pytest.CaptureFixture[str]) -> None:
    """Test status tool when brain79 is installed."""
    mock_res = MagicMock()
    mock_res.stdout = "brain79 v0.1.0 (editable)"

    with patch("subprocess.run", return_value=mock_res):
        status_tool()
    stdout = capsys.readouterr().out
    assert "[OK] brain79 is installed in the uv environment." in stdout


def test_status_tool_not_installed(capsys: pytest.CaptureFixture[str]) -> None:
    """Test status tool when brain79 is NOT installed."""
    mock_res = MagicMock()
    mock_res.stdout = "other-tool v1.0.0"

    with patch("subprocess.run", return_value=mock_res):
        status_tool()
    stdout = capsys.readouterr().out
    assert "[--] brain79 is NOT installed." in stdout


def test_status_tool_called_process_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Test status tool when uv tool list fails."""
    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["uv", "tool", "list"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            status_tool()
        assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "[ERR] 'uv tool list' failed with exit code 1" in stderr


def test_main_dispatch() -> None:
    """Test main function dispatching for default install, explicit install, uninstall, and status."""
    with (
        patch("scripts.install.validate_environment"),
        patch("scripts.install.install_tool") as mock_install,
        patch.object(sys, "argv", ["scripts/install.py"]),
    ):
        main()
        mock_install.assert_called_once()

    with (
        patch("scripts.install.validate_environment"),
        patch("scripts.install.install_tool") as mock_install,
        patch.object(sys, "argv", ["scripts/install.py", "install"]),
    ):
        main()
        mock_install.assert_called_once()

    with (
        patch("scripts.install.validate_environment"),
        patch("scripts.install.uninstall_tool") as mock_uninstall,
        patch.object(sys, "argv", ["scripts/install.py", "uninstall"]),
    ):
        main()
        mock_uninstall.assert_called_once()

    with (
        patch("scripts.install.validate_environment"),
        patch("scripts.install.status_tool") as mock_status,
        patch.object(sys, "argv", ["scripts/install.py", "status"]),
    ):
        main()
        mock_status.assert_called_once()
