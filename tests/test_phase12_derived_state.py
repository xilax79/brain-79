"""Phase 12 Stage 1 TDD tests: merge-conflict-free derived state and deterministic rebuild.

Covers R-1.1 through R-1.4 and AC-12.1 through AC-12.4.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from brain79 import config
from brain79.cli.dispatch import dispatch_cmd
from brain79.core.doctor import run_doctor
from brain79.core.drift import (
    check_article_drift,
    compute_applies_to_manifest,
    detect_all_drift,
    load_drift_manifest,
    rebuild_drift_manifest,
)
from brain79.core.init_project import init_project, sync_wiki_gitignore, update_project
from brain79.core.navigation import (
    REGISTRY_FILENAME,
    load_registry,
    rebuild_navigation_registry,
    regenerate_index_navigation,
)
from brain79.core.session_commit import commit_session
from brain79.core.frontmatter import ValidationError


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


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


# =============================================================================
# R-1.1 / AC-12.1: Git-ignored derived state manifest + doctor check
# =============================================================================


class TestDerivedStateGitignore:
    def test_sync_wiki_gitignore_creates_and_is_idempotent(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / ".brain-79"
        wiki_root.mkdir()

        changed, msg = sync_wiki_gitignore(wiki_root)
        assert changed is True
        assert ".gitignore" in msg

        gi_path = wiki_root / ".gitignore"
        lines = [ln.strip() for ln in gi_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        expected = [
            ".locks/",
            "*.lock",
            "*.tmp",
            "*.tmp.*",
            ".navigation_registry.json",
            ".drift_manifest.json",
            ".bootstrap_state.json",
        ]
        for entry in expected:
            assert entry in lines

        # Second call is a no-op
        changed2, _ = sync_wiki_gitignore(wiki_root)
        assert changed2 is False

    def test_sync_wiki_gitignore_preserves_custom_lines_and_supports_dry_run(self, tmp_path: Path) -> None:
        wiki_root = tmp_path / ".brain-79"
        wiki_root.mkdir()
        gi_path = wiki_root / ".gitignore"
        gi_path.write_text("# My custom rules\nlocal_scratch.md\n.locks/\n", encoding="utf-8")

        changed_dry, _ = sync_wiki_gitignore(wiki_root, dry_run=True)
        assert changed_dry is True
        assert ".navigation_registry.json" not in gi_path.read_text(encoding="utf-8")

        changed_real, _ = sync_wiki_gitignore(wiki_root, dry_run=False)
        assert changed_real is True
        content = gi_path.read_text(encoding="utf-8")
        assert "# My custom rules" in content
        assert "local_scratch.md" in content
        assert ".navigation_registry.json" in content
        assert ".drift_manifest.json" in content
        assert ".bootstrap_state.json" in content
        assert content.count(".locks/") == 1

    def test_init_and_update_project_sync_wiki_gitignore(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        gi_path = tmp_path / ".brain-79" / ".gitignore"
        content = gi_path.read_text(encoding="utf-8")
        assert ".navigation_registry.json" in content
        assert ".drift_manifest.json" in content
        assert ".bootstrap_state.json" in content

        # Simulate legacy project missing derived JSON entries
        gi_path.write_text(".locks/\n*.lock\n*.tmp\ncustom.local\n", encoding="utf-8")
        update_project(tmp_path, dry_run=False)
        updated = gi_path.read_text(encoding="utf-8")
        assert "custom.local" in updated
        assert ".navigation_registry.json" in updated
        assert ".drift_manifest.json" in updated
        assert ".bootstrap_state.json" in updated

    def test_doctor_warns_when_derived_json_is_tracked_in_git(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"

        # Force-track a derived JSON cache
        reg_file = wiki_root / ".navigation_registry.json"
        reg_file.write_text('{"articles": []}\n', encoding="utf-8")
        _git(tmp_path, "add", "-f", ".brain-79/.navigation_registry.json")
        _git(tmp_path, "commit", "-m", "track derived cache")

        report = run_doctor(project_root=tmp_path, wiki_root=wiki_root)
        check = next((c for c in report.checks if c.category == "derived_state_tracking"), None)
        assert check is not None
        assert check.status == "warning"
        assert ".navigation_registry.json" in check.message
        assert check.actionable is not None
        assert "git rm --cached" in check.actionable

        # Untrack and verify doctor reports ok
        _git(tmp_path, "rm", "--cached", ".brain-79/.navigation_registry.json")
        _git(tmp_path, "commit", "-m", "untrack derived cache")

        report_clean = run_doctor(project_root=tmp_path, wiki_root=wiki_root)
        check_clean = next((c for c in report_clean.checks if c.category == "derived_state_tracking"), None)
        assert check_clean is not None
        assert check_clean.status == "ok"


# =============================================================================
# R-1.2 / AC-12.2: Deterministic navigation registry rebuild
# =============================================================================


class TestNavigationRegistryRebuild:
    def test_rebuild_navigation_registry_scans_sorts_and_excludes(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"

        _write_md(
            wiki_root / "features" / "zeta.md",
            "---\ntype: feature\nsummary: zeta feature summary\napplies_to:\n  - src/zeta.py\n---\n\n# Zeta feature\n\nBody.\n",
        )
        _write_md(
            wiki_root / "architecture" / "alpha.md",
            "---\ntype: architecture\nsummary: alpha arch summary\nrelated:\n  - features/zeta.md\n---\n\n# Alpha architecture\n\nSee [Zeta](../features/zeta.md).\n",
        )
        _write_md(
            wiki_root / "overview.md",
            "---\ntype: topic\nsummary: top-level overview\n---\n\n# Overview\n\nTop-level.\n",
        )
        # Excluded files
        _write_md(wiki_root / "_raw" / "sessions" / "raw.md", "# Raw\n")
        _write_md(wiki_root / "handoffs" / "h1.md", "# Handoff\n")

        reg = rebuild_navigation_registry(wiki_root, persist=True)
        paths = [a["path"] for a in reg["articles"]]
        assert paths == ["architecture/alpha.md", "features/zeta.md", "overview.md"]

        by_path = {a["path"]: a for a in reg["articles"]}
        assert by_path["architecture/alpha.md"]["section"] == "architecture"
        assert by_path["architecture/alpha.md"]["title"] == "Alpha architecture"
        assert by_path["architecture/alpha.md"]["summary"] == "alpha arch summary"
        assert by_path["architecture/alpha.md"]["related"] == ["features/zeta.md"]
        assert "features/zeta.md" in by_path["architecture/alpha.md"]["outgoing_links"]
        assert by_path["features/zeta.md"]["applies_to"] == ["src/zeta.py"]
        assert by_path["overview.md"]["section"] == "root"

        # Persisted on disk
        reg_file = wiki_root / REGISTRY_FILENAME
        assert reg_file.is_file()
        disk_data = json.loads(reg_file.read_text(encoding="utf-8"))
        assert [a["path"] for a in disk_data["articles"]] == paths

    def test_rebuild_navigation_registry_handles_read_only_gracefully(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        _write_md(
            wiki_root / "topics" / "note.md",
            "---\ntype: topic\nsummary: a note\n---\n\n# Note\n\nContent.\n",
        )

        with patch("brain79.core.navigation._save_registry_unlocked", side_effect=PermissionError("read-only")):
            reg = rebuild_navigation_registry(wiki_root, persist=True)
        assert len(reg["articles"]) == 1
        assert reg["articles"][0]["path"] == "topics/note.md"

    def test_load_registry_auto_rebuilds_when_missing_or_corrupt(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        _write_md(
            wiki_root / "features" / "auth.md",
            "---\ntype: feature\nsummary: authentication flow\n---\n\n# Auth\n\nDetails.\n",
        )

        reg_file = wiki_root / REGISTRY_FILENAME
        reg_file.unlink(missing_ok=True)

        reg = load_registry(wiki_root)
        assert len(reg["articles"]) == 1
        assert reg["articles"][0]["path"] == "features/auth.md"
        # Read-only by default (does not mutate disk)
        assert not reg_file.exists()

        # persist=True writes reconstructed registry to disk
        reg_persisted = load_registry(wiki_root, persist=True)
        assert len(reg_persisted["articles"]) == 1
        assert reg_file.is_file()

        # Corrupt JSON triggers auto-rebuild
        reg_file.write_text("{corrupt json", encoding="utf-8")
        reg2 = load_registry(wiki_root)
        assert len(reg2["articles"]) == 1
        assert reg2["articles"][0]["path"] == "features/auth.md"

    def test_load_registry_reconciles_incomplete_or_stale_cache(self, tmp_path: Path) -> None:
        from brain79.core.navigation import register_article

        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        _write_md(
            wiki_root / "features" / "alpha.md",
            "---\ntype: feature\nsummary: alpha summary\n---\n\n# Alpha\n\nAlpha.\n",
        )
        _write_md(
            wiki_root / "features" / "beta.md",
            "---\ntype: feature\nsummary: beta summary\n---\n\n# Beta\n\nBeta.\n",
        )
        _write_md(
            wiki_root / "topics" / "gamma.md",
            "---\ntype: topic\nsummary: gamma summary\n---\n\n# Gamma\n\nGamma.\n",
        )

        # Write a valid but incomplete registry (only 1 of 3 articles)
        reg_file = wiki_root / REGISTRY_FILENAME
        reg_file.write_text(
            json.dumps(
                {
                    "articles": [
                        {
                            "path": "features/alpha.md",
                            "title": "Alpha",
                            "summary": "alpha summary",
                            "section": "features",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        # load_registry() reconciles against disk without mutating disk when persist=False
        reg = load_registry(wiki_root)
        assert [a["path"] for a in reg["articles"]] == [
            "features/alpha.md",
            "features/beta.md",
            "topics/gamma.md",
        ]

        # Stale deleted entry in cache triggers direct reconciliation in load_registry()
        reg_file.write_text(
            json.dumps(
                {
                    "articles": [
                        {"path": "features/alpha.md", "title": "Alpha", "summary": "s", "section": "features"},
                        {"path": "features/beta.md", "title": "Beta", "summary": "s", "section": "features"},
                        {"path": "topics/gamma.md", "title": "Gamma", "summary": "s", "section": "topics"},
                        {"path": "features/deleted.md", "title": "Deleted", "summary": "s", "section": "features"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        reg_reconciled = load_registry(wiki_root)
        assert [a["path"] for a in reg_reconciled["articles"]] == [
            "features/alpha.md",
            "features/beta.md",
            "topics/gamma.md",
        ]

        # Read-only filesystem safety when persist=True
        with patch("brain79.core.navigation._save_registry_unlocked", side_effect=PermissionError("read-only")):
            reg_ro = load_registry(wiki_root, persist=True)
        assert len(reg_ro["articles"]) == 3

        # regenerate_index_navigation(rebuild=False) heals INDEX.md and .navigation_registry.json without deadlock
        reg_file.write_text(
            json.dumps(
                {"articles": [{"path": "features/alpha.md", "title": "Alpha", "summary": "s", "section": "features"}]}
            ),
            encoding="utf-8",
        )
        regenerate_index_navigation(wiki_root, rebuild=False)
        index_text = (wiki_root / "INDEX.md").read_text(encoding="utf-8")
        assert "features/alpha.md" in index_text
        assert "features/beta.md" in index_text
        assert "topics/gamma.md" in index_text
        persisted = json.loads(reg_file.read_text(encoding="utf-8"))
        assert len(persisted["articles"]) == 3

        # register_article() holding _registry.lock does not deadlock when reconciling incomplete cache
        reg_file.write_text(
            json.dumps(
                {"articles": [{"path": "features/alpha.md", "title": "Alpha", "summary": "s", "section": "features"}]}
            ),
            encoding="utf-8",
        )
        register_article(wiki_root, "features/alpha.md", "Alpha", "alpha summary", "features")
        persisted_after_reg = json.loads(reg_file.read_text(encoding="utf-8"))
        assert [a["path"] for a in sorted(persisted_after_reg["articles"], key=lambda x: x["path"])] == [
            "features/alpha.md",
            "features/beta.md",
            "topics/gamma.md",
        ]

    def test_navigate_rebuild_cli_and_mcp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        _write_md(
            wiki_root / "features" / "billing.md",
            "---\ntype: feature\nsummary: billing subsystem\n---\n\n# Billing\n\nDetails.\n",
        )
        # Write stale empty registry
        (wiki_root / REGISTRY_FILENAME).write_text('{"articles": []}\n', encoding="utf-8")

        # Core regenerate with rebuild=True
        regenerate_index_navigation(wiki_root, rebuild=True)
        index_text = (wiki_root / "INDEX.md").read_text(encoding="utf-8")
        assert "features/billing.md" in index_text

        # CLI navigate --regenerate --rebuild
        (wiki_root / REGISTRY_FILENAME).write_text('{"articles": []}\n', encoding="utf-8")
        monkeypatch.setattr(config, "_project_root", tmp_path)
        rc = dispatch_cmd("navigate", ["--regenerate", "--rebuild"])
        assert rc == 0
        reg_after_cli = json.loads((wiki_root / REGISTRY_FILENAME).read_text(encoding="utf-8"))
        assert len(reg_after_cli["articles"]) == 1


# =============================================================================
# R-1.3 / AC-12.3: Drift-safe manifest rebuild without masking drift
# =============================================================================


class TestDriftManifestRebuild:
    def test_rebuild_drift_manifest_hydrates_only_matching_digest(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        src_clean = tmp_path / "src" / "clean.py"
        src_dirty = tmp_path / "src" / "dirty.py"
        src_clean.parent.mkdir(parents=True, exist_ok=True)
        src_clean.write_text("def clean() -> int:\n    return 1\n", encoding="utf-8")
        src_dirty.write_text("def dirty() -> int:\n    return 1\n", encoding="utf-8")

        clean_digest, clean_count, _ = compute_applies_to_manifest(["src/clean.py"], tmp_path, wiki_root)
        dirty_digest, dirty_count, _ = compute_applies_to_manifest(["src/dirty.py"], tmp_path, wiki_root)

        _write_md(
            wiki_root / "features" / "clean.md",
            f"---\ntype: feature\nsummary: clean module\napplies_to:\n  - src/clean.py\napplies_to_digest: \"{clean_digest}\"\napplies_to_count: {clean_count}\nlast_updated: 2026-01-01\n---\n\n# Clean\n",
        )
        _write_md(
            wiki_root / "features" / "dirty.md",
            f"---\ntype: feature\nsummary: dirty module\napplies_to:\n  - src/dirty.py\napplies_to_digest: \"{dirty_digest}\"\napplies_to_count: {dirty_count}\nlast_updated: 2026-01-01\n---\n\n# Dirty\n",
        )

        # Mutate src/dirty.py AFTER stamping so its digest no longer matches
        src_dirty.write_text("def dirty() -> int:\n    return 2\n", encoding="utf-8")

        # Delete any manifest and rebuild
        manifest_path = wiki_root / ".drift_manifest.json"
        manifest_path.unlink(missing_ok=True)

        rebuilt = rebuild_drift_manifest(wiki_root, project_root=tmp_path, persist=True)
        assert "features/clean.md" in rebuilt["articles"]
        assert "targets" in rebuilt["articles"]["features/clean.md"]
        assert "src/clean.py" in rebuilt["articles"]["features/clean.md"]["targets"]

        # Zero-masking invariant: drifted article MUST NOT have hydrated targets
        dirty_entry = rebuilt["articles"].get("features/dirty.md")
        assert dirty_entry is None or "targets" not in dirty_entry

        # detect_all_drift with missing manifest auto-rebuilds and still reports dirty.md drift
        manifest_path.unlink(missing_ok=True)
        drifts = detect_all_drift(wiki_root=wiki_root, project_root=tmp_path)
        drifted_articles = {d["article_path"] for d in drifts}
        assert "features/dirty.md" in drifted_articles
        assert "features/clean.md" not in drifted_articles

    def test_load_drift_manifest_auto_rebuild_flag(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        src_a = tmp_path / "src" / "a.py"
        src_a.parent.mkdir(parents=True, exist_ok=True)
        src_a.write_text("X = 1\n", encoding="utf-8")

        digest, count, _ = compute_applies_to_manifest(["src/a.py"], tmp_path, wiki_root)
        _write_md(
            wiki_root / "features" / "a.md",
            f"---\ntype: feature\nsummary: mod a\napplies_to:\n  - src/a.py\napplies_to_digest: \"{digest}\"\napplies_to_count: {count}\nlast_updated: 2026-01-01\n---\n\n# Mod A\n",
        )
        manifest_path = wiki_root / ".drift_manifest.json"
        manifest_path.unlink(missing_ok=True)

        # Default auto_rebuild=False returns empty without creating file
        empty = load_drift_manifest(wiki_root, auto_rebuild=False)
        assert empty["articles"] == {}
        assert not manifest_path.exists()

        # auto_rebuild=True hydrates and persists
        hydrated = load_drift_manifest(wiki_root, auto_rebuild=True, project_root=tmp_path)
        assert "features/a.md" in hydrated["articles"]
        assert manifest_path.is_file()


# =============================================================================
# R-1.4 / AC-12.4: Guard parity when .drift_manifest.json is absent
# =============================================================================


class TestGuardParityWithoutManifest:
    def test_fallback_drift_kind_added_deleted_missing_modified(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        f1 = pkg / "one.py"
        f2 = pkg / "two.py"
        f1.write_text("def one(): pass\n", encoding="utf-8")
        f2.write_text("def two(): pass\n", encoding="utf-8")

        digest, count, _ = compute_applies_to_manifest(["src/pkg/*.py"], tmp_path, wiki_root)
        assert count == 2
        art = wiki_root / "features" / "pkg.md"
        _write_md(
            art,
            f"---\ntype: feature\nsummary: pkg module\napplies_to:\n  - src/pkg/*.py\napplies_to_digest: \"{digest}\"\napplies_to_count: {count}\nlast_updated: 2026-01-01\n---\n\n# Pkg\n",
        )
        empty_manifest = {"version": "1.0", "articles": {}}

        # 1. Modified (same count=2, different digest)
        f2.write_text("def two(x: int): pass\n", encoding="utf-8")
        drifts_mod = check_article_drift(art, wiki_root=wiki_root, project_root=tmp_path, manifest_data=empty_manifest)
        assert len(drifts_mod) == 1
        assert drifts_mod[0]["drift_kind"] == "modified"
        assert drifts_mod[0]["fallback_targets"] == ["src/pkg/one.py", "src/pkg/two.py"]

        # 2. Added (count=3 > stored_count=2)
        f3 = pkg / "three.py"
        f3.write_text("def three(): pass\n", encoding="utf-8")
        drifts_add = check_article_drift(art, wiki_root=wiki_root, project_root=tmp_path, manifest_data=empty_manifest)
        assert len(drifts_add) == 1
        assert drifts_add[0]["drift_kind"] == "added"

        # 3. Deleted (count=1 < stored_count=2)
        f3.unlink()
        f2.unlink()
        drifts_del = check_article_drift(art, wiki_root=wiki_root, project_root=tmp_path, manifest_data=empty_manifest)
        assert len(drifts_del) == 1
        assert drifts_del[0]["drift_kind"] == "deleted"

        # 4. Missing (count=0)
        f1.unlink()
        drifts_miss = check_article_drift(art, wiki_root=wiki_root, project_root=tmp_path, manifest_data=empty_manifest)
        assert len(drifts_miss) == 1
        assert drifts_miss[0]["drift_kind"] == "missing"

    def test_session_commit_guard_a_and_guard_c_without_manifest(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        pkg = tmp_path / "src" / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        f1 = pkg / "a_first.py"
        f2 = pkg / "z_second.py"
        f1.write_text("def alpha() -> int:\n    return 1\n", encoding="utf-8")
        f2.write_text("def beta() -> int:\n    return 2\n", encoding="utf-8")

        digest, count, _ = compute_applies_to_manifest(["src/pkg/*.py"], tmp_path, wiki_root)
        art_rel = "features/pkg.md"
        _write_md(
            wiki_root / art_rel,
            f"---\ntype: feature\nsummary: pkg module\napplies_to:\n  - src/pkg/*.py\napplies_to_digest: \"{digest}\"\napplies_to_count: {count}\nlast_updated: 2026-01-01\n---\n\n# Pkg\n\n[← Back to Index](../INDEX.md)\n",
        )
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "initial commit")

        # Delete .drift_manifest.json completely
        (wiki_root / ".drift_manifest.json").unlink(missing_ok=True)

        # Case 1: Break public signature in the SECOND file (z_second.py) -> Guard C MUST block!
        f2.write_text("def beta(new_required_arg: str) -> int:\n    return 2\n", encoding="utf-8")
        with pytest.raises(ValidationError) as exc_c:
            commit_session(
                wiki_root=wiki_root,
                verified_articles=[
                    {"path": art_rel, "reason": "Internal refactor only, no public API changes at all."}
                ],
                allow_partial_ripple=True,
            )
        assert exc_c.value.rule == "verified_article_public_signature_changed"

        # Restore f2, add a new file -> Guard A MUST block!
        f2.write_text("def beta() -> int:\n    return 2\n", encoding="utf-8")
        f3 = pkg / "c_added.py"
        f3.write_text("def gamma() -> int:\n    return 3\n", encoding="utf-8")
        (wiki_root / ".drift_manifest.json").unlink(missing_ok=True)

        with pytest.raises(ValidationError) as exc_a:
            commit_session(
                wiki_root=wiki_root,
                verified_articles=[
                    {"path": art_rel, "reason": "Internal refactor only, no structural changes at all."}
                ],
                allow_partial_ripple=True,
            )
        assert exc_a.value.rule == "verified_article_structural_change_forbidden"
