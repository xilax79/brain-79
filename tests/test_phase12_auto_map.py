"""Phase 12 Stage 3 TDD tests: automated brownfield onboarding (bootstrap --auto-map).

Covers R-3.1 through R-3.4 and AC-12.8 through AC-12.10.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess

import pytest

from brain79 import config
from brain79.cli.dispatch import dispatch_cmd
from brain79.core.auto_map import (
    AutoMapReport,
    ModuleProposal,
    analyze_repository_boundaries,
)
from brain79.core.bootstrap import run_bootstrap
from brain79.core.drift import match_applies_to_pattern
from brain79.core.git_ops import NotAGitRepoError, git_recent_file_churn
from brain79.core.init_project import init_project
from brain79.server import brain79_bootstrap


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _init_git_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# =============================================================================
# R-3.1: git_recent_file_churn
# =============================================================================


class TestGitRecentFileChurn:
    def test_raises_not_a_git_repo_outside_git(self, tmp_path: Path) -> None:
        with pytest.raises(NotAGitRepoError):
            git_recent_file_churn(tmp_path)

    def test_returns_empty_dict_on_zero_commit_repo(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        assert git_recent_file_churn(tmp_path) == {}

    def test_counts_recent_commits_per_file(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path / "src" / "hot.py", "X = 1\n")
        _write(tmp_path / "src" / "cold.py", "Y = 1\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "c1")

        _write(tmp_path / "src" / "hot.py", "X = 2\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "c2")

        _write(tmp_path / "src" / "hot.py", "X = 3\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "c3")

        churn = git_recent_file_churn(tmp_path, max_commits=50)
        assert churn["src/hot.py"] == 3
        assert churn["src/cold.py"] == 1


# =============================================================================
# R-3.2 / AC-12.8: Manifest detection, directory topology, Git churn ranking
# =============================================================================


class TestAnalyzeRepositoryBoundaries:
    def test_detects_manifests_across_python_js_rust_go_and_degrades_non_git(self, tmp_path: Path) -> None:
        # Python package
        _write(tmp_path / "py_svc" / "pyproject.toml", '[project]\nname = "py-svc"\n')
        _write(tmp_path / "py_svc" / "main.py", "def run(): pass\n")
        # JS package
        _write(tmp_path / "web_app" / "package.json", json.dumps({"name": "web-app"}))
        _write(tmp_path / "web_app" / "index.ts", "export const x = 1;\n")
        # Rust crate
        _write(tmp_path / "rust_core" / "Cargo.toml", '[package]\nname = "rust-core"\nversion = "0.1.0"\n')
        _write(tmp_path / "rust_core" / "lib.rs", "pub fn hi() {}\n")
        # Go module
        _write(tmp_path / "go_worker" / "go.mod", "module example.com/go-worker\n\ngo 1.22\n")
        _write(tmp_path / "go_worker" / "main.go", "package main\nfunc main() {}\n")
        # Excluded directories
        _write(tmp_path / "tests" / "test_foo.py", "def test_x(): pass\n")
        _write(tmp_path / "docs" / "guide.py", "X = 1\n")

        report = analyze_repository_boundaries(tmp_path, max_modules=12)
        assert isinstance(report, AutoMapReport)
        assert report.git_available is False
        assert report.total_code_files == 4

        slugs = {p.slug for p in report.proposals}
        assert {"py-svc", "web-app", "rust-core", "go-worker"}.issubset(slugs)
        assert "tests" not in slugs
        assert "docs" not in slugs
        for p in report.proposals:
            assert p.recent_commits == 0
            assert any(s.startswith("manifest:") for s in p.signals)

    def test_propagates_manifest_to_nested_src_layouts_and_preserves_zero_overlap(self, tmp_path: Path) -> None:
        # Standard Rust crate layout: crates/auth/Cargo.toml + crates/auth/src/lib.rs
        _write(tmp_path / "crates" / "auth" / "Cargo.toml", '[package]\nname = "auth-crate"\nversion = "0.1.0"\n')
        _write(tmp_path / "crates" / "auth" / "src" / "lib.rs", "pub fn auth() {}\n")
        # Standard JS package layout: packages/web/package.json + packages/web/src/index.ts
        _write(tmp_path / "packages" / "web" / "package.json", json.dumps({"name": "@org/web-ui"}))
        _write(tmp_path / "packages" / "web" / "src" / "index.ts", "export const ui = true;\n")

        report = analyze_repository_boundaries(tmp_path, max_modules=12)
        by_slug = {p.slug: p for p in report.proposals}
        assert "auth-crate" in by_slug
        assert "web-ui" in by_slug
        assert "src" not in by_slug
        assert "manifest:Cargo.toml" in by_slug["auth-crate"].signals
        assert "manifest:package.json" in by_slug["web-ui"].signals

        # Zero-overlap check
        all_files = ["crates/auth/src/lib.rs", "packages/web/src/index.ts"]
        matched_auth = {f for f in all_files if any(match_applies_to_pattern(pat, f) for pat in by_slug["auth-crate"].applies_to)}
        matched_web = {f for f in all_files if any(match_applies_to_pattern(pat, f) for pat in by_slug["web-ui"].applies_to)}
        assert matched_auth == {"crates/auth/src/lib.rs"}
        assert matched_web == {"packages/web/src/index.ts"}
        assert matched_auth & matched_web == set()

    def test_git_churn_ranking_and_max_modules_truncation(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        _write(tmp_path / "src" / "alpha" / "a.py", "A = 1\n")
        _write(tmp_path / "src" / "beta" / "b.py", "B = 1\n")
        _write(tmp_path / "src" / "gamma" / "c.py", "C = 1\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "init")

        # Give gamma highest churn
        for i in range(3):
            _write(tmp_path / "src" / "gamma" / "c.py", f"C = {i + 2}\n")
            _git(tmp_path, "add", ".")
            _git(tmp_path, "commit", "-m", f"gamma {i}")

        report = analyze_repository_boundaries(tmp_path, max_modules=2)
        assert report.git_available is True
        assert len(report.proposals) == 2
        assert report.truncated_count == 1
        assert report.proposals[0].slug == "gamma"
        assert report.proposals[0].recent_commits == 4


# =============================================================================
# R-3.3 / AC-12.9: Zero-overlap anti-sprawl guarantee by construction
# =============================================================================


class TestZeroOverlapInvariant:
    def test_parent_and_child_modules_have_strictly_zero_file_intersection(self, tmp_path: Path) -> None:
        # Parent directory has root-level .py files AND child subdirectories with .py files
        _write(tmp_path / "src" / "pkg" / "app.py", "APP = 1\n")
        _write(tmp_path / "src" / "pkg" / "utils.py", "U = 1\n")
        _write(tmp_path / "src" / "pkg" / "auth" / "login.py", "L = 1\n")
        _write(tmp_path / "src" / "pkg" / "billing" / "charge.py", "C = 1\n")

        report = analyze_repository_boundaries(tmp_path, max_modules=12)
        assert len(report.proposals) >= 3

        all_workspace_files = [
            p.relative_to(tmp_path).as_posix()
            for p in tmp_path.rglob("*")
            if p.is_file()
        ]

        # Compute matched file set for every proposal
        matched_sets: list[tuple[str, set[str]]] = []
        for prop in report.proposals:
            matched = {
                f
                for f in all_workspace_files
                if any(match_applies_to_pattern(pat, f) for pat in prop.applies_to)
            }
            assert len(matched) > 0, f"Proposal {prop.slug} matched 0 files: {prop.applies_to}"
            matched_sets.append((prop.slug, matched))

        # Pairwise intersection MUST be strictly empty (0 shared files)
        for i in range(len(matched_sets)):
            for j in range(i + 1, len(matched_sets)):
                slug_i, files_i = matched_sets[i]
                slug_j, files_j = matched_sets[j]
                overlap = files_i & files_j
                assert overlap == set(), f"Overlap between {slug_i} and {slug_j}: {overlap}"


# =============================================================================
# R-3.4 / AC-12.10: Bootstrap integration and CLI/MCP parity
# =============================================================================


class TestBootstrapAutoMapParity:
    def test_bootstrap_default_unchanged_and_auto_map_cli_mcp_parity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        _write(tmp_path / "src" / "api" / "routes.py", "def route(): pass\n")
        _write(tmp_path / "src" / "db" / "models.py", "class Model: pass\n")
        monkeypatch.setattr(config, "_project_root", tmp_path)

        # Default auto_map=False does NOT include Auto-mapped governance boundaries
        default_out = run_bootstrap(force=True, auto_map=False)
        assert "## Auto-mapped governance boundaries" not in default_out

        # auto_map=True via MCP
        mcp_out = brain79_bootstrap(force=True, auto_map=True, max_modules=5)
        assert "## Auto-mapped governance boundaries" in mcp_out
        assert "applies_to:" in mcp_out
        assert "src/api" in mcp_out
        assert "src/db" in mcp_out

        # auto_map=True via CLI
        buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        rc = dispatch_cmd("bootstrap", ["--force", "--auto-map", "--max-modules", "5"])
        assert rc == 0
        cli_out = buf.getvalue().rstrip("\n")
        marker = "## Auto-mapped governance boundaries"
        assert cli_out.split(marker, 1)[1] == mcp_out.rstrip("\n").split(marker, 1)[1]
