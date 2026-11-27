"""Phase 17 Stage 3 tests: 3-way merge-drift-lock, gitignore/hooks/doctor, migrate --apply, lint advisory, and CI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any
from unittest.mock import patch

import pytest

from brain79.cli.dispatch import WHITELIST, run_cli
from brain79.core.doctor import run_doctor
from brain79.core.drift import (
    CONFLICT_SENTINEL_DIGEST,
    check_article_drift,
    compute_applies_to_manifest,
    load_drift_lock,
    parse_drift_lock_text,
    save_drift_lock,
)
from brain79.core.frontmatter import ValidationError
from brain79.core.git_ops import git_check_ignore, git_config_get_local
from brain79.core.init_project import (
    PRE_COMMIT_HOOK_SCRIPT,
    init_project,
    sync_git_merge_driver,
    sync_wiki_gitignore,
    update_project,
)
from brain79.core.lint_organizational import lint_organizational
from brain79.core.migration import migrate_wiki
from brain79.server import MCP_TOOLS


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True)


def _entry(digest: str, targets: dict[str, str] | None = None) -> dict[str, Any]:
    tgts = targets if targets is not None else {"src/a.py": digest}
    return {"digest": digest, "count": len(tgts), "targets": tgts}


# ---------------------------------------------------------------------------
# AC-5: 3-way brain79 merge-drift-lock driver & WHITELIST / MCP_TOOLS parity
# ---------------------------------------------------------------------------


def test_ac5_whitelist_and_mcp_parity() -> None:
    assert len(WHITELIST) == 27
    assert "merge-drift-lock" in WHITELIST
    assert len(MCP_TOOLS) == 9


def test_ac5_merge_drift_lock_disjoint_identical_and_delete(tmp_path: Path) -> None:
    d_a1 = "sha256:1111111111111111"
    d_a2 = "sha256:2222222222222222"
    d_b1 = "sha256:3333333333333333"
    d_c1 = "sha256:4444444444444444"
    d_d1 = "sha256:5555555555555555"

    base = {
        "version": "2.0",
        "articles": {
            "features/a.md": _entry(d_a1, {"src/a.py": d_a1}),
            "features/b.md": _entry(d_b1, {"src/b.py": d_b1}),
            "features/c.md": _entry(d_c1, {"src/c.py": d_c1}),
            "features/del_both.md": _entry(d_d1, {"src/d.py": d_d1}),
        },
    }
    ours = {
        "version": "2.0",
        "articles": {
            "features/a.md": _entry(d_a2, {"src/a.py": d_a2}),
            "features/b.md": _entry(d_b1, {"src/b.py": d_b1}),
            "features/c.md": _entry(d_c1, {"src/c.py": d_c1}),
            "features/only_ours.md": _entry(d_a1, {"src/o.py": d_a1}),
        },
    }
    theirs = {
        "version": "2.0",
        "articles": {
            "features/a.md": _entry(d_a1, {"src/a.py": d_a1}),
            "features/b.md": _entry(d_d1, {"src/b.py": d_d1}),
            "features/only_theirs.md": _entry(d_c1, {"src/t.py": d_c1}),
        },
    }

    base_p = tmp_path / "base.lock"
    ours_p = tmp_path / "ours.lock"
    theirs_p = tmp_path / "theirs.lock"
    base_p.write_text(json.dumps(base), encoding="utf-8", newline="\n")
    ours_p.write_text(json.dumps(ours), encoding="utf-8", newline="\n")
    theirs_p.write_text(json.dumps(theirs), encoding="utf-8", newline="\n")

    rc = run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p)])
    assert rc == 0

    merged_raw = ours_p.read_bytes()
    assert b"\r\n" not in merged_raw
    merged = parse_drift_lock_text(merged_raw.decode("utf-8"))
    assert set(merged["articles"].keys()) == {
        "features/a.md",
        "features/b.md",
        "features/only_ours.md",
        "features/only_theirs.md",
    }
    assert merged["articles"]["features/a.md"]["digest"] == d_a2
    assert merged["articles"]["features/b.md"]["digest"] == d_d1


def test_ac5_merge_drift_lock_empty_base_disjoint_and_conflicting_add_add(tmp_path: Path) -> None:
    d1 = "sha256:aaaaaaaaaaaaaaaa"
    d2 = "sha256:bbbbbbbbbbbbbbbb"
    base_p = tmp_path / "base.lock"
    ours_p = tmp_path / "ours.lock"
    theirs_p = tmp_path / "theirs.lock"

    base_p.write_text("", encoding="utf-8")
    ours_p.write_text(
        json.dumps(
            {
                "version": "2.0",
                "articles": {
                    "features/ours_only.md": _entry(d1, {"src/o.py": d1}),
                    "features/shared.md": _entry(d1, {"src/s.py": d1}),
                },
            }
        ),
        encoding="utf-8",
    )
    theirs_p.write_text(
        json.dumps(
            {
                "version": "2.0",
                "articles": {
                    "features/theirs_only.md": _entry(d2, {"src/t.py": d2}),
                    "features/shared.md": _entry(d2, {"src/s.py": d2}),
                },
            }
        ),
        encoding="utf-8",
    )

    rc = run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p)])
    assert rc == 0
    merged = parse_drift_lock_text(ours_p.read_text(encoding="utf-8"))
    assert "features/ours_only.md" in merged["articles"]
    assert "features/theirs_only.md" in merged["articles"]
    assert merged["articles"]["features/shared.md"] == {
        "conflict": True,
        "count": 0,
        "digest": CONFLICT_SENTINEL_DIGEST,
        "targets": {},
    }

    # Verify check_article_drift detects the conflict sentinel explicitly
    proj = tmp_path / "repo"
    wiki = proj / ".brain-79"
    (wiki / "features").mkdir(parents=True)
    (proj / "src").mkdir()
    (proj / "src" / "s.py").write_text("x = 1\n", encoding="utf-8")
    (wiki / "features" / "shared.md").write_text(
        "---\n"
        "type: feature\n"
        "summary: shared\n"
        "status: shipped\n"
        "version: 0.1.0\n"
        "applies_to:\n  - src/s.py\n"
        "last_updated: 2026-11-27\n"
        "---\n\n# Feature — Shared\n\n## Overview\n\nText.\n\n[← Back to Index](../INDEX.md)\n",
        encoding="utf-8",
    )
    save_drift_lock(wiki, merged)
    drifts = check_article_drift("features/shared.md", wiki_root=wiki, project_root=proj, lock_data=merged)
    assert len(drifts) == 1
    assert drifts[0]["drift_kind"] == "conflict"


def test_ac5_merge_drift_lock_modify_and_delete_conflicts_with_wiki_root(tmp_path: Path) -> None:
    d_base = "sha256:1111111111111111"
    d_ours = "sha256:2222222222222222"
    d_theirs = "sha256:3333333333333333"

    base = {
        "version": "2.0",
        "articles": {
            "features/mod_mod.md": _entry(d_base, {"src/m.py": d_base}),
            "features/del_mod.md": _entry(d_base, {"src/d.py": d_base}),
        },
    }
    ours = {
        "version": "2.0",
        "articles": {
            "features/mod_mod.md": _entry(d_ours, {"src/m.py": d_ours}),
            # deleted del_mod.md in ours
        },
    }
    theirs = {
        "version": "2.0",
        "articles": {
            "features/mod_mod.md": _entry(d_theirs, {"src/m.py": d_theirs}),
            "features/del_mod.md": _entry(d_theirs, {"src/d.py": d_theirs}),
        },
    }

    base_p = tmp_path / "base.lock"
    ours_p = tmp_path / "ours.lock"
    theirs_p = tmp_path / "theirs.lock"

    # Without --wiki-root: revert both mod_mod and del_mod to base[k]
    base_p.write_text(json.dumps(base), encoding="utf-8")
    ours_p.write_text(json.dumps(ours), encoding="utf-8")
    theirs_p.write_text(json.dumps(theirs), encoding="utf-8")
    assert run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p)]) == 0
    m_no_root = parse_drift_lock_text(ours_p.read_text(encoding="utf-8"))
    assert m_no_root["articles"]["features/mod_mod.md"]["digest"] == d_base
    assert m_no_root["articles"]["features/del_mod.md"]["digest"] == d_base

    # With --wiki-root where mod_mod.md exists and del_mod.md is absent on disk:
    wiki_root = tmp_path / "wiki"
    (wiki_root / "features").mkdir(parents=True)
    (wiki_root / "features" / "mod_mod.md").write_text("# exists\n", encoding="utf-8")
    ours_p.write_text(json.dumps(ours), encoding="utf-8")
    assert run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p), "--wiki-root", str(wiki_root)]) == 0
    m_with_root = parse_drift_lock_text(ours_p.read_text(encoding="utf-8"))
    assert m_with_root["articles"]["features/mod_mod.md"]["digest"] == d_base
    assert "features/del_mod.md" not in m_with_root["articles"]


@pytest.mark.parametrize(
    "bad_payload",
    [
        "",
        "{bad json",
        '{"version": "2.0", "articles": {}, "articles": {}}',
        '{"version": "2.0", "articles": {"a.md": {"digest": "sha256:1111111111111111", "count": NaN, "targets": {}}}}',
        '{"version": "1.0", "articles": {}}',
        '{"version": "2.0", "articles": {"a.md": {"digest": "sha256:1111111111111111", "count": 0, "targets": {}, "conflict": false}}}',
    ],
)
def test_ac5_merge_drift_lock_corrupt_inputs_exit_1_untouched_ours(tmp_path: Path, bad_payload: str) -> None:
    valid = json.dumps({"version": "2.0", "articles": {}})
    base_p = tmp_path / "base.lock"
    ours_p = tmp_path / "ours.lock"
    theirs_p = tmp_path / "theirs.lock"
    base_p.write_text(valid, encoding="utf-8")
    ours_p.write_text(bad_payload, encoding="utf-8")
    theirs_p.write_text(valid, encoding="utf-8")

    rc = run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p)])
    assert rc == 1
    assert ours_p.read_text(encoding="utf-8") == bad_payload


def test_ac5_merge_drift_lock_missing_args_missing_files_invalid_wiki_root_exit_2(tmp_path: Path) -> None:
    valid = json.dumps({"version": "2.0", "articles": {}})
    base_p = tmp_path / "base.lock"
    ours_p = tmp_path / "ours.lock"
    theirs_p = tmp_path / "theirs.lock"
    base_p.write_text(valid, encoding="utf-8")
    ours_p.write_text(valid, encoding="utf-8")

    assert run_cli("merge-drift-lock", [str(base_p), str(ours_p)]) == 2
    assert run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p)]) == 2
    assert ours_p.read_text(encoding="utf-8") == valid

    theirs_p.write_text(valid, encoding="utf-8")
    missing_wiki = tmp_path / "no_such_dir"
    assert run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p), "--wiki-root", str(missing_wiki)]) == 2
    assert ours_p.read_text(encoding="utf-8") == valid


def test_ac5_merge_drift_lock_write_permission_error_exit_3(tmp_path: Path) -> None:
    valid = json.dumps({"version": "2.0", "articles": {}})
    base_p = tmp_path / "base.lock"
    ro_dir = tmp_path / "ro"
    ro_dir.mkdir()
    ours_p = ro_dir / "ours.lock"
    theirs_p = tmp_path / "theirs.lock"
    base_p.write_text(valid, encoding="utf-8")
    ours_p.write_text(valid, encoding="utf-8")
    theirs_p.write_text(
        json.dumps({"version": "2.0", "articles": {"features/x.md": _entry("sha256:1111111111111111")}}),
        encoding="utf-8",
    )

    if os.name == "nt":
        with patch("brain79.core.drift_merge.atomic_replace_with_retry", side_effect=PermissionError("denied")):
            rc = run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p)])
            assert rc == 3
    else:
        ro_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            rc = run_cli("merge-drift-lock", [str(base_p), str(ours_p), str(theirs_p)])
            assert rc == 3
        finally:
            ro_dir.chmod(stat.S_IRWXU)
    assert ours_p.read_text(encoding="utf-8") == valid


# ---------------------------------------------------------------------------
# AC-6: .gitignore negation ordering, merge driver, pre-commit hook, doctor
# ---------------------------------------------------------------------------


def test_ac6_gitignore_ordering_repair_and_git_check_ignore(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    init_project(tmp_path, auto_git_init=False)
    wiki = tmp_path / ".brain-79"
    gi = wiki / ".gitignore"

    lines = [ln.strip() for ln in gi.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines.index("!drift.lock") > max(i for i, ln in enumerate(lines) if ln == "*.lock")
    assert not git_check_ignore(tmp_path, ".brain-79/drift.lock")
    assert git_check_ignore(tmp_path, ".brain-79/.drift_manifest.json")
    assert git_check_ignore(tmp_path, ".brain-79/.locks/_drift_lock.lock")

    # Simulate inverted .gitignore where !drift.lock appears before *.lock
    gi.write_text("# custom\n!drift.lock\n*.lock\n.locks/\n", encoding="utf-8", newline="\n")
    assert git_check_ignore(tmp_path, ".brain-79/drift.lock")

    changed, _ = sync_wiki_gitignore(wiki)
    assert changed
    repaired_lines = [ln.strip() for ln in gi.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert "# custom" in repaired_lines
    assert repaired_lines.index("!drift.lock") > max(i for i, ln in enumerate(repaired_lines) if ln == "*.lock")
    assert not git_check_ignore(tmp_path, ".brain-79/drift.lock")
    assert not sync_wiki_gitignore(wiki)[0]


def test_ac6_merge_driver_doctor_diagnostics_and_non_git_fallback(tmp_path: Path) -> None:
    # 1. Outside Git: doctor uses .gitignore rule-ordering fallback
    wiki_nongit = tmp_path / "nongit" / ".brain-79"
    wiki_nongit.mkdir(parents=True)
    (wiki_nongit / "SCHEMA.md").write_text("---\nprofile: software\nschema_version: 2\nenforcement: strict\n---\n", encoding="utf-8")
    (wiki_nongit / "INDEX.md").write_text("---\ntype: navigation\nlast_updated: 2026-11-27\n---\n\n# Project index\n", encoding="utf-8")
    (wiki_nongit / ".gitignore").write_text("!drift.lock\n*.lock\n", encoding="utf-8")

    rep_ng = run_doctor(project_root=tmp_path / "nongit", wiki_root=wiki_nongit)
    dst_ng = next(c for c in rep_ng.checks if c.category == "derived_state_tracking")
    assert dst_ng.status == "warning"

    # 2. Inside Git: init configures both merge drivers; drift.lock not flagged as legacy lock
    proj = tmp_path / "gitrepo"
    proj.mkdir()
    _init_git_repo(proj)
    init_project(proj, auto_git_init=False)
    wiki = proj / ".brain-79"
    save_drift_lock(wiki, {"version": "2.0", "articles": {"features/a.md": _entry("sha256:1111111111111111")}})

    ga_text = (wiki / ".gitattributes").read_text(encoding="utf-8")
    assert "INDEX.md merge=brain79-index" in ga_text
    assert "drift.lock merge=brain79-drift-lock" in ga_text
    assert git_config_get_local(proj, "merge.brain79-index.driver") == "brain79 navigate --merge-driver %O %A %B"
    assert git_config_get_local(proj, "merge.brain79-drift-lock.driver") == "brain79 merge-drift-lock %O %A %B"

    rep_ok = run_doctor(project_root=proj, wiki_root=wiki)
    locks_chk = next(c for c in rep_ok.checks if c.category == "locks_and_filesystem")
    md_chk = next(c for c in rep_ok.checks if c.category == "git_merge_driver")
    dst_chk = next(c for c in rep_ok.checks if c.category == "derived_state_tracking")
    assert locks_chk.status == "ok"
    assert md_chk.status == "ok"
    assert dst_chk.status == "ok"

    # Break .gitignore & drift-lock merge driver, then verify doctor warns and --fix repairs without redundant migrate_wiki
    (wiki / ".gitignore").write_text("*.lock\n", encoding="utf-8")
    subprocess.run(["git", "config", "--unset", "merge.brain79-drift-lock.driver"], cwd=proj, check=True)

    rep_warn = run_doctor(project_root=proj, wiki_root=wiki)
    assert next(c for c in rep_warn.checks if c.category == "derived_state_tracking").status == "warning"
    assert next(c for c in rep_warn.checks if c.category == "git_merge_driver").status == "warning"

    with patch("brain79.core.doctor.migrate_wiki", create=True) as mock_mig:
        rep_fixed = run_doctor(project_root=proj, wiki_root=wiki, fix=True, force=True)
        mock_mig.assert_not_called()

    assert any("gitignore" in item.lower() for item in rep_fixed.fixed)
    assert next(c for c in rep_fixed.checks if c.category == "derived_state_tracking").status == "ok"
    assert next(c for c in rep_fixed.checks if c.category == "git_merge_driver").status == "ok"


def test_ac6_pre_commit_hook_triggers_on_staged_drift_lock(tmp_path: Path) -> None:
    assert r"^\.brain-79/(.*\.md|drift\.lock)$" in PRE_COMMIT_HOOK_SCRIPT or r"^\.brain-79/(.*\.md|drift\.lock)$".replace("\\\\", "\\") in PRE_COMMIT_HOOK_SCRIPT
    if os.name == "nt":
        return

    proj = tmp_path / "hookrepo"
    proj.mkdir()
    _init_git_repo(proj)
    init_project(proj, auto_git_init=False)
    wiki = proj / ".brain-79"
    (wiki / "drift.lock").write_text("{corrupt", encoding="utf-8")
    subprocess.run(["git", "add", ".brain-79/drift.lock"], cwd=proj, check=True)

    # Shim brain79 under HOME/.local/bin so pre-commit's PATH export resolves to current workspace code
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    shim = bin_dir / "brain79"
    shim.write_text(f"#!/usr/bin/env bash\nexec {sys.executable!r} -m brain79 \"$@\"\n", encoding="utf-8")
    shim.chmod(0o755)
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    hook_proc = subprocess.run(
        [str(proj / ".git" / "hooks" / "pre-commit")],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
    )
    assert hook_proc.returncode == 1


# ---------------------------------------------------------------------------
# AC-7: Idempotent zero-masking migration (--apply) and lint legacy advisory
# ---------------------------------------------------------------------------


def _write_md(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")


def test_ac7_migrate_zero_masking_idempotent_and_lint_advisory(tmp_path: Path) -> None:
    proj = tmp_path / "migrepo"
    proj.mkdir()
    _init_git_repo(proj)
    init_project(proj, auto_git_init=False)
    wiki = proj / ".brain-79"

    # Source files
    (proj / "src").mkdir()
    for name, content in [
        ("clean.py", "def clean(): return 1\n"),
        ("drifted_with_man.py", "def dr1(): return 'changed'\n"),
        ("drifted_no_man.py", "def dr2(): return 'changed'\n"),
        ("malformed.py", "def mal(): return 1\n"),
        ("newer.py", "def new(): return 1\n"),
        ("demoted.py", "def dem(): return 1\n"),
        ("inactive.py", "def ina(): return 1\n"),
        ("unhashed_clean.py", "def uc(): return 1\n"),
        ("unhashed_stale.py", "def us(): return 2\n"),
    ]:
        (proj / "src" / name).write_text(content, encoding="utf-8")

    # Set mtime for unhashed_stale.py to future date relative to last_updated
    future_ts = 1893456000  # 2030-01-01
    past_ts = 1704067200    # 2024-01-01
    os.utime(proj / "src" / "unhashed_stale.py", (future_ts, future_ts))
    os.utime(proj / "src" / "unhashed_clean.py", (past_ts, past_ts))

    clean_dig, clean_cnt, clean_tgts = compute_applies_to_manifest(["src/clean.py"], proj, wiki)
    assert clean_dig is not None
    old_dig1 = "sha256:1111111111111111"
    old_dig2 = "sha256:2222222222222222"
    newer_dig = "sha256:3333333333333333"

    # Legacy .drift_manifest.json matching drifted_with_man.py's old_dig1
    (wiki / ".drift_manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "articles": {
                    "features/drifted-with-man.md": {
                        "digest": old_dig1,
                        "count": 1,
                        "targets": {"src/drifted_with_man.py": old_dig1},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    # Pre-existing drift.lock with newer entry + Paso-B-demoted entry
    save_drift_lock(
        wiki,
        {
            "version": "2.0",
            "articles": {
                "features/newer.md": _entry(newer_dig, {"src/newer.py": newer_dig}),
                "features/demoted.md": _entry("sha256:4444444444444444", {"src/demoted.py": "sha256:4444444444444444"}),
            },
        },
    )

    # 1. Clean hashed article
    _write_md(
        wiki / "features" / "clean.md",
        f"---\ntype: feature\nsummary: clean\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/clean.py\nlast_updated: 2026-11-27\napplies_to_digest: \"{clean_dig}\"\napplies_to_count: {clean_cnt}\n---\n\n# Feature — Clean\n\n## Overview\n\nOk.\n\n[← Back to Index](../INDEX.md)\n",
    )
    # 2a. Drifted hashed article with matching legacy manifest
    _write_md(
        wiki / "features" / "drifted-with-man.md",
        f"---\ntype: feature\nsummary: drifted1\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/drifted_with_man.py\nlast_updated: 2026-11-27\napplies_to_digest: \"{old_dig1}\"\napplies_to_count: 1\n---\n\n# Feature — Drifted1\n\n## Overview\n\nOk.\n\n[← Back to Index](../INDEX.md)\n",
    )
    # 2b. Drifted hashed article without matching legacy manifest
    _write_md(
        wiki / "features" / "drifted-no-man.md",
        f"---\ntype: feature\nsummary: drifted2\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/drifted_no_man.py\nlast_updated: 2026-11-27\napplies_to_digest: \"{old_dig2}\"\napplies_to_count: 1\n---\n\n# Feature — Drifted2\n\n## Overview\n\nOk.\n\n[← Back to Index](../INDEX.md)\n",
    )
    # 3. Malformed legacy digest
    _write_md(
        wiki / "features" / "malformed.md",
        "---\ntype: feature\nsummary: malformed\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/malformed.py\nlast_updated: 2026-11-27\napplies_to_digest: \"not-a-sha\"\napplies_to_count: 1\n---\n\n# Feature — Malformed\n\n## Overview\n\nOk.\n\n[← Back to Index](../INDEX.md)\n",
    )
    # 4. Already in drift.lock with newer digest than frontmatter
    _write_md(
        wiki / "features" / "newer.md",
        f"---\ntype: feature\nsummary: newer\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/newer.py\nlast_updated: 2026-11-27\napplies_to_digest: \"{old_dig1}\"\napplies_to_count: 1\n---\n\n# Feature — Newer\n\n## Overview\n\nOk.\n\n[← Back to Index](../INDEX.md)\n",
    )
    # 5. Missing ## Overview -> Paso B demotes to legacy
    _write_md(
        wiki / "features" / "demoted.md",
        "---\ntype: feature\nsummary: demoted\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/demoted.py\nlast_updated: 2026-11-27\napplies_to_digest: \"sha256:4444444444444444\"\napplies_to_count: 1\n---\n\n# Feature — Demoted\n\nNo overview heading.\n\n[← Back to Index](../INDEX.md)\n",
    )
    # 6. Inactive article with legacy digest
    _write_md(
        wiki / "features" / "inactive.md",
        "---\ntype: feature\nsummary: inactive\nstatus: deprecated\nversion: 0.1.0\napplies_to:\n  - src/inactive.py\nlast_updated: 2026-11-27\napplies_to_digest: \"sha256:5555555555555555\"\napplies_to_count: 1\n---\n\n# Feature — Inactive\n\n## Overview\n\nOld.\n\n[← Back to Index](../INDEX.md)\n",
    )
    # 7a & 7b. Unhashed clean vs timestamp-drifted
    _write_md(
        wiki / "features" / "unhashed-clean.md",
        "---\ntype: feature\nsummary: unhashed clean\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/unhashed_clean.py\nlast_updated: 2026-11-27\n---\n\n# Feature — Unhashed clean\n\n## Overview\n\nOk.\n\n[← Back to Index](../INDEX.md)\n",
    )
    _write_md(
        wiki / "features" / "unhashed-stale.md",
        "---\ntype: feature\nsummary: unhashed stale\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/unhashed_stale.py\nlast_updated: 2026-11-27\n---\n\n# Feature — Unhashed stale\n\n## Overview\n\nOk.\n\n[← Back to Index](../INDEX.md)\n",
    )

    # Dry-run makes zero disk mutations
    before_clean = (wiki / "features" / "clean.md").read_text(encoding="utf-8")
    dry_report = migrate_wiki(wiki, dry_run=True)
    assert "DRY RUN" in dry_report
    assert (wiki / "features" / "clean.md").read_text(encoding="utf-8") == before_clean

    # First --apply
    apply1 = migrate_wiki(wiki, dry_run=False)
    assert "APPLIED" in apply1
    lock1 = load_drift_lock(wiki)
    assert lock1 is not None
    arts = lock1["articles"]

    assert arts["features/clean.md"] == {"digest": clean_dig, "count": clean_cnt, "targets": clean_tgts}
    assert arts["features/drifted-with-man.md"] == {
        "digest": old_dig1,
        "count": 1,
        "targets": {"src/drifted_with_man.py": old_dig1},
    }
    assert arts["features/drifted-no-man.md"] == {"digest": old_dig2, "count": 1, "targets": {}}
    assert arts["features/newer.md"]["digest"] == newer_dig
    assert "features/demoted.md" not in arts
    assert "features/inactive.md" not in arts
    assert "features/unhashed-clean.md" in arts
    assert "features/unhashed-stale.md" not in arts
    # Malformed fell through to unhashed check (stamped cleanly if not timestamp drifted)
    assert "features/malformed.md" in arts
    assert arts["features/malformed.md"]["digest"] != "not-a-sha"

    for md_name in ["clean.md", "drifted-with-man.md", "drifted-no-man.md", "malformed.md", "newer.md", "demoted.md", "inactive.md"]:
        txt = (wiki / "features" / md_name).read_text(encoding="utf-8")
        assert "applies_to_digest" not in txt
        assert "applies_to_count" not in txt

    # Second --apply with older INDEX.md last_updated date: must modify 0 files on disk
    idx_path = wiki / "INDEX.md"
    old_idx = idx_path.read_text(encoding="utf-8").replace("2026-11-27", "2020-01-01")
    idx_path.write_text(old_idx, encoding="utf-8", newline="\n")
    lock_before = (wiki / "drift.lock").read_bytes()

    apply2 = migrate_wiki(wiki, dry_run=False)
    assert "## Changes (0)" in apply2
    assert idx_path.read_text(encoding="utf-8") == old_idx
    assert (wiki / "drift.lock").read_bytes() == lock_before

    # Verify ci-check catches preserved drift on drifted-with-man.md & drifted-no-man.md
    from brain79.core.ci_check import run_ci_check

    ci_rep = run_ci_check(project_root=proj, wiki_root=wiki, enforcement="strict")
    assert ci_rep.exit_code == 1
    drifted_articles = {d["article_path"] for d in ci_rep.drifted_articles}
    assert {"features/drifted-with-man.md", "features/drifted-no-man.md"}.issubset(drifted_articles)


def test_ac7_lint_emits_info_legacy_frontmatter_digest_without_failing(tmp_path: Path) -> None:
    proj = tmp_path / "lintrepo"
    proj.mkdir()
    _init_git_repo(proj)
    init_project(proj, auto_git_init=False)
    wiki = proj / ".brain-79"
    (proj / "src").mkdir()
    (proj / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    dig, cnt, tgts = compute_applies_to_manifest(["src/a.py"], proj, wiki)
    assert dig is not None
    save_drift_lock(wiki, {"version": "2.0", "articles": {"features/a.md": {"digest": dig, "count": cnt, "targets": tgts}}})
    _write_md(
        wiki / "features" / "a.md",
        f"---\ntype: feature\nsummary: legacy digest\nstatus: shipped\nversion: 0.1.0\napplies_to:\n  - src/a.py\nlast_updated: 2026-11-27\napplies_to_digest: \"{dig}\"\napplies_to_count: {cnt}\n---\n\n# Feature — A\n\n## Overview\n\nText.\n\n[← Back to Index](../INDEX.md)\n",
    )
    from brain79.core.navigation import regenerate_index_navigation

    regenerate_index_navigation(wiki, rebuild=True)

    issues = lint_organizational(wiki)
    legacy_issues = [i for i in issues if i.rule == "legacy_frontmatter_digest"]
    assert len(legacy_issues) == 1
    assert legacy_issues[0].severity == "info"
    assert "brain79 migrate --apply" in legacy_issues[0].actionable

    with patch("brain79.config.get_wiki_root", return_value=wiki), patch(
        "brain79.config.get_project_root", return_value=proj
    ):
        assert run_cli("lint", ["--strict"]) == 0
        assert run_cli("lint", ["--fail-on-warnings"]) == 0


def test_ac7_migrate_corrupt_drift_lock_fails_closed(tmp_path: Path) -> None:
    proj = tmp_path / "corruptmig"
    proj.mkdir()
    init_project(proj, auto_git_init=False)
    wiki = proj / ".brain-79"
    (wiki / "drift.lock").write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        migrate_wiki(wiki, dry_run=False)
    assert exc_info.value.issues[0]["rule"] == "corrupt_drift_lock"
