"""Phase 12 Stage 4 TDD tests: configurable enforcement tiers (strict / balanced / advisory).

Covers R-4.1 through R-4.4 and AC-12.11 through AC-12.15.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from brain79 import config
from brain79.cli.dispatch import dispatch_cmd
from brain79.core.doctor import run_doctor
from brain79.core.drift import compute_applies_to_manifest
from brain79.core.frontmatter import (
    ValidationError,
    clear_schema_cache,
    load_active_schema,
)
from brain79.core.git_ops import GitError
from brain79.core.init_project import init_project, sync_schema_file, update_project
from brain79.core.lint import lint_wiki
from brain79.core.orient import orient
from brain79.core.session_commit import commit_session
from brain79.core.wiki import write_article, write_many_articles


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


def _set_enforcement(wiki_root: Path, tier: str) -> None:
    schema_path = wiki_root / "SCHEMA.md"
    text = schema_path.read_text(encoding="utf-8")
    if "enforcement:" in text:
        lines = [
            f"enforcement: {tier}" if ln.strip().startswith("enforcement:") else ln
            for ln in text.splitlines()
        ]
        schema_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    else:
        schema_path.write_text(
            text.replace("schema_version: 2\n", f"schema_version: 2\nenforcement: {tier}\n", 1),
            encoding="utf-8",
            newline="\n",
        )
    clear_schema_cache()


def _valid_feature(title: str, applies_to: str | None = None, extra: str = "") -> str:
    applies_block = f"applies_to:\n  - {applies_to}\n" if applies_to else ""
    return (
        f"---\ntype: feature\nsummary: {title.lower()} summary\nstatus: shipped\n"
        f"version: v0.1.0\nlast_updated: 2026-01-01\n{applies_block}{extra}---\n\n"
        f"# {title}\n\n## Overview\n\nBody.\n\n[← Back to Index](../INDEX.md)\n"
    )


# =============================================================================
# R-4.1 / AC-12.11: SCHEMA.md enforcement parsing, fallback, init & update-project
# =============================================================================


class TestSchemaEnforcementConfig:
    def test_omitted_defaults_to_strict_and_invalid_falls_back_with_warning(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        # Strip enforcement line to test omission default
        schema_p = wiki_root / "SCHEMA.md"
        schema_p.write_text(
            "\n".join(ln for ln in schema_p.read_text(encoding="utf-8").splitlines() if not ln.startswith("enforcement:")) + "\n",
            encoding="utf-8",
        )
        clear_schema_cache()

        s_default = load_active_schema(wiki_root)
        assert s_default.enforcement == "strict"
        assert s_default.schema_warnings == []

        # Invalid value falls back to strict and records a structured warning
        _set_enforcement(wiki_root, "yolo")
        s_invalid = load_active_schema(wiki_root)
        assert s_invalid.enforcement == "strict"
        assert len(s_invalid.schema_warnings) == 1
        assert "yolo" in s_invalid.schema_warnings[0]

        # Surfaced by lint and doctor
        lint_out = lint_wiki(wiki_root=wiki_root)
        assert "[Enforcement: strict]" in lint_out
        assert "yolo" in lint_out

        doc = run_doctor(project_root=tmp_path, wiki_root=wiki_root)
        proto = next(c for c in doc.checks if c.category == "protocol_sync")
        assert proto.status == "warning"
        assert "yolo" in proto.message

    def test_init_enforcement_flag_and_update_project_preservation(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False, enforcement="balanced")
        wiki_root = tmp_path / ".brain-79"
        clear_schema_cache()
        assert load_active_schema(wiki_root).enforcement == "balanced"

        # update_project / sync_schema_file preserves user-selected enforcement
        sync_schema_file(wiki_root)
        clear_schema_cache()
        assert load_active_schema(wiki_root).enforcement == "balanced"

        update_project(tmp_path, dry_run=False)
        clear_schema_cache()
        assert load_active_schema(wiki_root).enforcement == "balanced"


# =============================================================================
# R-4.2 / R-4.4 / AC-12.12 / AC-12.13: Tier behavior matrix
# =============================================================================


class TestEnforcementTierMatrix:
    def test_core_structural_integrity_always_blocks_in_all_tiers(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"

        for tier in ("strict", "balanced", "advisory"):
            _set_enforcement(wiki_root, tier)
            with pytest.raises(ValidationError):
                write_article("features/broken.md", "# No frontmatter\n", wiki_root=wiki_root)

    def test_missing_applies_to_and_anti_sprawl_across_tiers_in_wiki_and_commit(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        src_a = tmp_path / "src" / "mod_a.py"
        src_a.parent.mkdir(parents=True, exist_ok=True)
        src_a.write_text("X = 1\n", encoding="utf-8")

        # Seed governing article for src/mod_a.py
        write_article("features/first.md", _valid_feature("First", applies_to="src/mod_a.py"), wiki_root=wiki_root)

        # 1. Missing applies_to target: strict=BLOCK, balanced=WARN, advisory=WARN
        _set_enforcement(wiki_root, "strict")
        with pytest.raises(ValidationError) as e_strict:
            write_article("features/missing1.md", _valid_feature("Missing1", applies_to="src/nope.py"), wiki_root=wiki_root)
        assert e_strict.value.rule == "applies_to_target_missing"

        _set_enforcement(wiki_root, "balanced")
        msg_bal = write_article("features/missing2.md", _valid_feature("Missing2", applies_to="src/nope.py"), wiki_root=wiki_root)
        assert "Warning" in msg_bal or "applies_to_target_missing" in msg_bal

        msg_batch = write_many_articles(
            [{"path": "features/missing3.md", "content": _valid_feature("Missing3", applies_to="src/nope2.py")}],
            wiki_root=wiki_root,
        )
        assert "applies_to_target_missing" in msg_batch

        # 2. Anti-sprawl overlap: strict=BLOCK, balanced=BLOCK, advisory=WARN
        _set_enforcement(wiki_root, "balanced")
        with pytest.raises(ValidationError) as e_bal_sprawl:
            write_article("features/overlap1.md", _valid_feature("Overlap1", applies_to="src/mod_a.py"), wiki_root=wiki_root)
        assert e_bal_sprawl.value.rule in ("anti_sprawl_overlap_violation", "duplicate_governance_target")

        _set_enforcement(wiki_root, "advisory")
        msg_adv = write_article("features/overlap2.md", _valid_feature("Overlap2", applies_to="src/mod_a.py"), wiki_root=wiki_root)
        assert "anti_sprawl_overlap_violation" in msg_adv or "duplicate_governance_target" in msg_adv

    def test_session_commit_guards_a_c_ripple_and_git_error_across_tiers(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        src_p = tmp_path / "src" / "api.py"
        src_p.parent.mkdir(parents=True, exist_ok=True)
        src_p.write_text("def greet() -> str:\n    return 'hi'\n", encoding="utf-8")

        digest, count, _ = compute_applies_to_manifest(["src/api.py"], tmp_path, wiki_root)
        art_rel = "features/api.md"
        write_article(
            art_rel,
            _valid_feature("API", applies_to="src/api.py", extra=f'applies_to_digest: "{digest}"\napplies_to_count: {count}\n'),
            wiki_root=wiki_root,
        )
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-m", "initial")

        # Break public signature in src/api.py (Guard C + Ripple)
        src_p.write_text("def greet(name: str) -> str:\n    return name\n", encoding="utf-8")

        # Strict: Guard C blocks
        _set_enforcement(wiki_root, "strict")
        with pytest.raises(ValidationError) as exc_c:
            commit_session(
                wiki_root=wiki_root,
                verified_articles=[{"path": art_rel, "reason": "Internal refactor only, no public API changes."}],
                allow_partial_ripple=True,
            )
        assert exc_c.value.rule == "verified_article_public_signature_changed"

        # Balanced: Guard C downgrades to warning!
        _set_enforcement(wiki_root, "balanced")
        rec_bal = commit_session(
            wiki_root=wiki_root,
            verified_articles=[{"path": art_rel, "reason": "Internal refactor only, no public API changes."}],
            allow_partial_ripple=True,
        )
        assert rec_bal["success"] is True
        assert rec_bal["enforcement"] == "balanced"
        assert rec_bal["health_status"] == "warnings"
        assert any("verified_article_public_signature_changed" in w for w in rec_bal["warnings"])

        # Add a new file matching a glob -> Guard A: balanced=BLOCK, advisory=WARN
        (tmp_path / "src" / "extra.py").write_text("E = 1\n", encoding="utf-8")
        art2 = "features/src_all.md"
        d2, c2, _ = compute_applies_to_manifest(["src/*.py"], tmp_path, wiki_root)
        write_article(
            art2,
            _valid_feature(
                "SrcAll",
                applies_to="src/*.py",
                extra=f'allow_overlapping_governance: true\napplies_to_digest: "{d2}"\napplies_to_count: {c2}\n',
            ),
            wiki_root=wiki_root,
        )
        (tmp_path / "src" / "extra2.py").write_text("E2 = 2\n", encoding="utf-8")

        _set_enforcement(wiki_root, "balanced")
        with pytest.raises(ValidationError) as exc_a:
            commit_session(
                wiki_root=wiki_root,
                verified_articles=[{"path": art2, "reason": "Internal refactor only, no structural changes."}],
                allow_partial_ripple=True,
            )
        assert exc_a.value.rule == "verified_article_structural_change_forbidden"

        _set_enforcement(wiki_root, "advisory")
        rec_adv = commit_session(
            wiki_root=wiki_root,
            verified_articles=[{"path": art2, "reason": "Internal refactor only, no structural changes."}],
            allow_partial_ripple=True,
        )
        assert rec_adv["success"] is True
        assert rec_adv["enforcement"] == "advisory"
        assert rec_adv["health_status"] == "warnings"
        assert any("verified_article_structural_change_forbidden" in w for w in rec_adv["warnings"])

        # Operational Git error: balanced=BLOCK, advisory=WARN
        _set_enforcement(wiki_root, "balanced")
        with patch("brain79.core.session_commit.git_dirty_paths", side_effect=GitError("git broke")):
            with pytest.raises(ValidationError) as exc_git:
                commit_session(
                    wiki_root=wiki_root,
                    writes=[{"path": "topics/note.md", "content": "---\ntype: topic\nsummary: a note\nlast_updated: 2026-01-01\n---\n\n# Note\n\n## Overview\n\nBody.\n\n[← Back to Index](../INDEX.md)\n"}],
                )
            assert exc_git.value.rule == "git_status_verification_failed"

        _set_enforcement(wiki_root, "advisory")
        with patch("brain79.core.session_commit.git_dirty_paths", side_effect=GitError("git broke")):
            rec_git = commit_session(
                wiki_root=wiki_root,
                writes=[{"path": "topics/note.md", "content": "---\ntype: topic\nsummary: a note\nlast_updated: 2026-01-01\n---\n\n# Note\n\n## Overview\n\nBody.\n\n[← Back to Index](../INDEX.md)\n"}],
            )
            assert rec_git["success"] is True
            assert rec_git["health_status"] == "warnings"
            assert any("git_status_verification_failed" in w for w in rec_git["warnings"])


# =============================================================================
# R-4.3 / AC-12.14 / AC-12.15: lint --strict exit codes, orient & doctor visibility
# =============================================================================


class TestLintOrientDoctorVisibility:
    def test_lint_strict_exit_codes_by_tier_and_fail_on_warnings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
        wiki_root = tmp_path / ".brain-79"
        # Create an orphan article (produces WARNING status, 0 CRITICAL)
        orphan = wiki_root / "topics" / "orphan.md"
        orphan.write_text(
            "---\ntype: topic\nsummary: orphan note\nlast_updated: 2026-01-01\n---\n\n# Orphan\n\n## Overview\n\nBody.\n\n[← Back to Index](../INDEX.md)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(config, "_project_root", tmp_path)

        # strict: lint --strict exits 1 on WARNING
        _set_enforcement(wiki_root, "strict")
        assert dispatch_cmd("lint", ["--strict"]) == 1

        # balanced: lint --strict exits 0 on WARNING, but --fail-on-warnings exits 1
        _set_enforcement(wiki_root, "balanced")
        assert dispatch_cmd("lint", ["--strict"]) == 0
        assert dispatch_cmd("lint", ["--strict", "--fail-on-warnings"]) == 1

        # advisory: lint --strict exits 0 on WARNING, but --fail-on-warnings exits 1
        _set_enforcement(wiki_root, "advisory")
        assert dispatch_cmd("lint", ["--strict"]) == 0
        assert dispatch_cmd("lint", ["--strict", "--fail-on-warnings"]) == 1

    def test_orient_and_doctor_display_active_enforcement_tier(self, tmp_path: Path) -> None:
        init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False, enforcement="balanced")
        wiki_root = tmp_path / ".brain-79"
        clear_schema_cache()

        orient_out = orient(wiki_root=wiki_root)
        assert "balanced" in orient_out
        assert "Enforcement" in orient_out

        doc = run_doctor(project_root=tmp_path, wiki_root=wiki_root)
        proto = next(c for c in doc.checks if c.category == "protocol_sync")
        assert "balanced" in proto.message
