"""Phase 12 Stage 2 TDD tests: deterministic INDEX.md Git merge driver.

Covers R-2.1 through R-2.3 and AC-12.5 through AC-12.7.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from brain79.cli.dispatch import dispatch_cmd
from brain79.core.doctor import run_doctor
from brain79.core.git_ops import git_config_get_local, git_config_set_local
from brain79.core.init_project import init_project, sync_git_merge_driver, update_project
from brain79.core.navigation import merge_index_files


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _init_git_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")


def _make_index(
    *,
    last_updated: str = "2026-01-01",
    preamble: str = "# Project Wiki Index\n\nIntro paragraph.",
    quick_nav: str = "## Quick navigation\n\n### Features\n- [Alpha](features/alpha.md) — alpha summary",
    extra_meta: str = "",
) -> str:
    meta_block = f"---\ntype: navigation\nlast_updated: {last_updated}\n{extra_meta}---\n\n"
    return f"{meta_block}{preamble}\n\n{quick_nav}\n"


# =============================================================================
# R-2.1 / AC-12.6: Three-way deterministic INDEX.md merger
# =============================================================================


class TestMergeIndexFiles:
    def test_clean_three_way_merge_additions_deletions_and_max_date(self, tmp_path: Path) -> None:
        base_f = tmp_path / "base.md"
        ours_f = tmp_path / "ours.md"
        theirs_f = tmp_path / "theirs.md"

        base_f.write_text(
            _make_index(
                last_updated="2026-01-01",
                quick_nav=(
                    "## Quick navigation\n\n"
                    "### Features\n"
                    "- [Alpha](features/alpha.md) — alpha summary\n"
                    "- [Deprecated](features/old.md) — old summary"
                ),
            ),
            encoding="utf-8",
        )
        # Ours adds Beta, keeps Alpha & Old
        ours_f.write_text(
            _make_index(
                last_updated="2026-02-10",
                quick_nav=(
                    "## Quick navigation\n\n"
                    "### Features\n"
                    "- [Alpha](features/alpha.md) — alpha summary\n"
                    "- [Beta](features/beta.md) — beta summary\n"
                    "- [Deprecated](features/old.md) — old summary"
                ),
            ),
            encoding="utf-8",
        )
        # Theirs deletes Old, adds Arch, newer date
        theirs_f.write_text(
            _make_index(
                last_updated="2026-03-15",
                quick_nav=(
                    "## Quick navigation\n\n"
                    "### Architecture\n"
                    "- [Core](architecture/core.md) — core design\n\n"
                    "### Features\n"
                    "- [Alpha](features/alpha.md) — alpha summary"
                ),
            ),
            encoding="utf-8",
        )

        # Must operate without .navigation_registry.json or .locks/
        rc = merge_index_files(base_f, ours_f, theirs_f)
        assert rc == 0

        merged = ours_f.read_text(encoding="utf-8")
        assert "\r\n" not in merged
        assert "type: navigation" in merged
        assert "last_updated: 2026-03-15" in merged or "last_updated: '2026-03-15'" in merged
        assert "architecture/core.md" in merged
        assert "features/alpha.md" in merged
        assert "features/beta.md" in merged
        assert "features/old.md" not in merged
        # Canonical section order: Architecture before Features
        assert merged.index("### Architecture") < merged.index("### Features")

    def test_both_sides_modified_same_entry_reextracts_from_disk_or_takes_ours(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / ".brain-79"
        art = wiki_root / "features" / "alpha.md"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(
            "---\ntype: feature\nsummary: canonical disk summary\n---\n\n# Alpha Disk\n\nBody.\n",
            encoding="utf-8",
        )

        base_f = tmp_path / "base.md"
        ours_f = tmp_path / "ours.md"
        theirs_f = tmp_path / "theirs.md"

        base_f.write_text(_make_index(), encoding="utf-8")
        ours_f.write_text(
            _make_index(quick_nav="## Quick navigation\n\n### Features\n- [Alpha Ours](features/alpha.md) — ours summary"),
            encoding="utf-8",
        )
        theirs_f.write_text(
            _make_index(quick_nav="## Quick navigation\n\n### Features\n- [Alpha Theirs](features/alpha.md) — theirs summary"),
            encoding="utf-8",
        )

        rc = merge_index_files(base_f, ours_f, theirs_f, wiki_root=wiki_root)
        assert rc == 0
        merged = ours_f.read_text(encoding="utf-8")
        assert "[Alpha Disk](features/alpha.md) — canonical disk summary" in merged

        # Without wiki_root on disk, deterministically takes ours
        ours_f.write_text(
            _make_index(quick_nav="## Quick navigation\n\n### Features\n- [Alpha Ours](features/alpha.md) — ours summary"),
            encoding="utf-8",
        )
        rc2 = merge_index_files(base_f, ours_f, theirs_f, wiki_root=None)
        assert rc2 == 0
        assert "[Alpha Ours](features/alpha.md) — ours summary" in ours_f.read_text(encoding="utf-8")

    def test_preamble_divergent_edits_emit_conflict_markers_and_exit_1(self, tmp_path: Path) -> None:
        base_f = tmp_path / "base.md"
        ours_f = tmp_path / "ours.md"
        theirs_f = tmp_path / "theirs.md"

        base_f.write_text(_make_index(preamble="# Index\n\nBase intro."), encoding="utf-8")
        ours_f.write_text(_make_index(preamble="# Index\n\nOurs intro."), encoding="utf-8")
        theirs_f.write_text(_make_index(preamble="# Index\n\nTheirs intro."), encoding="utf-8")

        rc = merge_index_files(base_f, ours_f, theirs_f)
        assert rc == 1
        merged = ours_f.read_text(encoding="utf-8")
        assert "<<<<<<< ours" in merged
        assert "=======" in merged
        assert ">>>>>>> theirs" in merged
        assert "Ours intro." in merged
        assert "Theirs intro." in merged


# =============================================================================
# R-2.2: CLI entry point brain79 navigate --merge-driver BASE OURS THEIRS
# =============================================================================


class TestNavigateMergeDriverCLI:
    def test_cli_merge_driver_exit_codes(self, tmp_path: Path) -> None:
        base_f = tmp_path / "base.md"
        ours_f = tmp_path / "ours.md"
        theirs_f = tmp_path / "theirs.md"

        # Missing input files -> exit 2
        rc_missing = dispatch_cmd("navigate", ["--merge-driver", str(base_f), str(ours_f), str(theirs_f)])
        assert rc_missing == 2

        # Clean merge -> exit 0
        base_f.write_text(_make_index(), encoding="utf-8")
        ours_f.write_text(_make_index(last_updated="2026-02-01"), encoding="utf-8")
        theirs_f.write_text(_make_index(last_updated="2026-02-05"), encoding="utf-8")
        rc_ok = dispatch_cmd("navigate", ["--merge-driver", str(base_f), str(ours_f), str(theirs_f)])
        assert rc_ok == 0

        # Preamble conflict -> exit 1
        ours_f.write_text(_make_index(preamble="# Index\n\nOurs"), encoding="utf-8")
        theirs_f.write_text(_make_index(preamble="# Index\n\nTheirs"), encoding="utf-8")
        rc_conflict = dispatch_cmd("navigate", ["--merge-driver", str(base_f), str(ours_f), str(theirs_f)])
        assert rc_conflict == 1


# =============================================================================
# R-2.3 / AC-12.7: Git config helpers, sync_git_merge_driver, init, update, doctor
# =============================================================================


class TestGitMergeDriverSetupAndDoctor:
    def test_git_config_local_get_and_set(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        assert git_config_get_local(tmp_path, "merge.brain79-index.driver") is None
        git_config_set_local(tmp_path, "merge.brain79-index.driver", "brain79 navigate --merge-driver %O %A %B")
        assert git_config_get_local(tmp_path, "merge.brain79-index.driver") == "brain79 navigate --merge-driver %O %A %B"

    def test_sync_git_merge_driver_idempotent_and_preserves_custom_gitattributes(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        wiki_root = tmp_path / ".brain-79"
        wiki_root.mkdir()
        ga = wiki_root / ".gitattributes"
        ga.write_text("# Custom attribute\n*.md text eol=lf\n", encoding="utf-8")

        changed, _ = sync_git_merge_driver(tmp_path, install=True)
        assert changed is True
        ga_text = ga.read_text(encoding="utf-8")
        assert "# Custom attribute" in ga_text
        assert "*.md text eol=lf" in ga_text
        assert "INDEX.md merge=brain79-index" in ga_text
        assert git_config_get_local(tmp_path, "merge.brain79-index.driver") == "brain79 navigate --merge-driver %O %A %B"

        # Second call is idempotent
        changed2, _ = sync_git_merge_driver(tmp_path, install=True)
        assert changed2 is False

    def test_init_no_merge_driver_and_doctor_fix(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False, install_merge_driver=False)
        wiki_root = tmp_path / ".brain-79"

        assert git_config_get_local(tmp_path, "merge.brain79-index.driver") is None

        # Doctor detects missing merge driver
        rep_before = run_doctor(project_root=tmp_path, wiki_root=wiki_root)
        check_before = next((c for c in rep_before.checks if c.category == "git_merge_driver"), None)
        assert check_before is not None
        assert check_before.status == "warning"

        # Commit initial files so doctor --fix is allowed on clean tree
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", "initial")

        rep_fixed = run_doctor(project_root=tmp_path, wiki_root=wiki_root, fix=True)
        check_after = next((c for c in rep_fixed.checks if c.category == "git_merge_driver"), None)
        assert check_after is not None
        assert check_after.status == "ok"
        assert git_config_get_local(tmp_path, "merge.brain79-index.driver") == "brain79 navigate --merge-driver %O %A %B"


# =============================================================================
# AC-12.5: Real `git merge` integration test
# =============================================================================


class TestRealGitMergeIntegration:
    def test_real_git_merge_two_divergent_branches_resolves_index_cleanly(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"

        # Point local merge driver to current Python interpreter so it works in isolated venvs
        driver_cmd = f'"{sys.executable}" -m brain79 navigate --merge-driver %O %A %B'
        git_config_set_local(tmp_path, "merge.brain79-index.driver", driver_cmd)

        # Base state on default branch
        (wiki_root / "INDEX.md").write_text(
            _make_index(
                last_updated="2026-01-01",
                quick_nav=(
                    "## Quick navigation\n\n"
                    "### Features\n"
                    "- [Shared](features/shared.md) — shared feature\n"
                    "- [Legacy](features/legacy.md) — legacy feature"
                ),
            ),
            encoding="utf-8",
        )
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", "base wiki")
        base_branch = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

        # Branch A: adds branch-a feature, updates date to 2026-02-01
        _git(tmp_path, "checkout", "-b", "branch-a")
        (wiki_root / "INDEX.md").write_text(
            _make_index(
                last_updated="2026-02-01",
                quick_nav=(
                    "## Quick navigation\n\n"
                    "### Features\n"
                    "- [Branch A](features/branch-a.md) — branch A feature\n"
                    "- [Legacy](features/legacy.md) — legacy feature\n"
                    "- [Shared](features/shared.md) — shared feature"
                ),
            ),
            encoding="utf-8",
        )
        _git(tmp_path, "add", ".brain-79/INDEX.md")
        _git(tmp_path, "commit", "-m", "branch A index update")

        # Branch B (from base): deletes Legacy, adds Architecture entry, updates date to 2026-02-15
        _git(tmp_path, "checkout", base_branch)
        _git(tmp_path, "checkout", "-b", "branch-b")
        (wiki_root / "INDEX.md").write_text(
            _make_index(
                last_updated="2026-02-15",
                quick_nav=(
                    "## Quick navigation\n\n"
                    "### Architecture\n"
                    "- [System](architecture/system.md) — system arch\n\n"
                    "### Features\n"
                    "- [Shared](features/shared.md) — shared feature"
                ),
            ),
            encoding="utf-8",
        )
        _git(tmp_path, "add", ".brain-79/INDEX.md")
        _git(tmp_path, "commit", "-m", "branch B index update")

        # Merge branch-a into branch-b using real git merge!
        merge_res = _git(tmp_path, "merge", "branch-a", "-m", "merge branch-a", check=False)
        assert merge_res.returncode == 0, f"git merge failed:\nSTDOUT: {merge_res.stdout}\nSTDERR: {merge_res.stderr}"

        merged = (wiki_root / "INDEX.md").read_text(encoding="utf-8")
        assert "<<<<<<< " not in merged
        assert "2026-02-15" in merged
        assert "architecture/system.md" in merged
        assert "features/branch-a.md" in merged
        assert "features/shared.md" in merged
        assert "features/legacy.md" not in merged
        assert merged.index("### Architecture") < merged.index("### Features")
