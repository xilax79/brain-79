from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

import brain79
from brain79 import __version__
from brain79.__main__ import main
from brain79.server import mcp


REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
README_PATH = REPO_ROOT / "README.md"
INIT_PATH = REPO_ROOT / "src" / "brain79" / "__init__.py"
CHANGELOG_DIR = REPO_ROOT / ".brain-79" / "changelog"
ROOT_CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"


def test_semver_format() -> None:
    """Verify brain79.__version__ follows strict Semantic Versioning (MAJOR.MINOR.PATCH)."""
    pattern = r"^\d+\.\d+\.\d+$"
    assert re.match(pattern, __version__), (
        f"__version__ '{__version__}' does not adhere to Semantic Versioning (MAJOR.MINOR.PATCH)."
    )


def test_hatchling_dynamic_version_configuration() -> None:
    """
    Verify pyproject.toml does not hardcode static version and instead
    uses Hatchling dynamic versioning pointing to src/brain79/__init__.py.
    """
    assert PYPROJECT_PATH.exists(), f"Missing pyproject.toml at {PYPROJECT_PATH}"
    with open(PYPROJECT_PATH, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    assert "version" not in project, (
        "pyproject.toml must not declare static 'version' in [project]; "
        "it must use dynamic versioning."
    )
    dynamic = project.get("dynamic", [])
    assert "version" in dynamic, (
        "pyproject.toml [project] must declare 'dynamic = [\"version\"]'."
    )

    tool = data.get("tool", {})
    hatch = tool.get("hatch", {})
    version_cfg = hatch.get("version", {})
    assert version_cfg.get("path") == "src/brain79/__init__.py", (
        "pyproject.toml must configure [tool.hatch.version] path = 'src/brain79/__init__.py'."
    )


def test_fastmcp_server_version_metadata() -> None:
    """Verify FastMCP server instance passes and exposes __version__."""
    assert mcp.version == __version__, (
        f"FastMCP server version '{mcp.version}' does not match package __version__ '{__version__}'."
    )


def test_readme_version_badge_parity() -> None:
    """Verify README.md contains a version badge matching active __version__."""
    assert README_PATH.exists(), f"Missing README.md at {README_PATH}"
    readme_text = README_PATH.read_text(encoding="utf-8")

    expected_badge = f"img.shields.io/badge/version-{__version__}-blue.svg"
    assert expected_badge in readme_text, (
        f"README.md does not contain the version badge for {__version__} ({expected_badge})."
    )


def test_changelog_entry_parity() -> None:
    """Verify .brain-79/changelog/ contains an entry matching active __version__."""
    assert CHANGELOG_DIR.is_dir(), f"Missing changelog directory at {CHANGELOG_DIR}"

    matching_changelogs: list[Path] = []
    for md_file in CHANGELOG_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta = yaml.safe_load(parts[1])
                    if isinstance(meta, dict) and str(meta.get("version")) == __version__:
                        matching_changelogs.append(md_file)
                except Exception:
                    continue

    assert matching_changelogs, (
        f"No changelog entry in {CHANGELOG_DIR} matches version '{__version__}'."
    )


def test_root_changelog_entry_parity() -> None:
    """Verify root CHANGELOG.md contains a section for the active __version__ and an Unreleased section."""
    assert ROOT_CHANGELOG_PATH.exists(), f"Missing root CHANGELOG.md at {ROOT_CHANGELOG_PATH}"
    content = ROOT_CHANGELOG_PATH.read_text(encoding="utf-8")

    version_header = f"## [{__version__}]"
    assert version_header in content, (
        f"Root CHANGELOG.md is missing entry header '{version_header}'."
    )
    assert "## [Unreleased]" in content, (
        "Root CHANGELOG.md is missing '## [Unreleased]' section header."
    )

    unreleased_idx = content.index("## [Unreleased]")
    version_idx = content.index(version_header)
    assert unreleased_idx < version_idx, (
        "Root CHANGELOG.md must position '## [Unreleased]' before released versions."
    )


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify brain79 -v and brain79 --version report brain79 {__version__}."""
    for flag in ["-v", "--version"]:
        with pytest.raises(SystemExit) as exc:
            main([flag])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == f"brain79 {__version__}"


def test_cli_subprocess_version() -> None:
    """Verify running brain79 via subprocess -v outputs exact version."""
    proc = subprocess.run(
        [sys.executable, "-m", "brain79", "--version"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == f"brain79 {__version__}"
