"""Comprehensive unit and integration tests for Phase 6.6:
Handoff freshness, provenance, and authority decay.
"""

import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import pytest


from brain79.core.frontmatter import parse_frontmatter
from brain79.core.handoff import (
    HANDOFF_ESCALATION_AGE_DAYS,
    read_handoff,
    write_handoff,
)
from brain79.core.handoff_freshness import (
    HandoffFreshness,
    compute_code_digest,
    compute_handoff_freshness,
)
from brain79.core.orient import orient_session
from brain79.core.session_commit import commit_session
from brain79.core.wiki import write_article


def _setup_git_repo(path: Path) -> None:
    """Initialize a git repo with user configuration."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    # Create initial commit so HEAD exists
    dummy_file = path / "README.md"
    dummy_file.write_text("# Project\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_1_fresh_handoff_no_later_changes(tmp_path: Path) -> None:
    """Case 1: Write a handoff with no later changes -> fresh; orient shows Active handoff state."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    write_article(
        "product/overview.md",
        "---\ntype: product\nsummary: product overview\n---\n# Product overview\n",
        wiki_root=wiki_root,
    )

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Completed initial setup.",
        completed_work=["Configured base repo"],
        pending_work=["Add integration tests"],
        boot_instruction="Implement integration tests for API.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    handoff_path = wiki_root / handoff_rel
    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "fresh"

    rendered, _ = read_handoff("latest", wiki_root=wiki_root)
    assert "Active handoff state" in rendered
    assert "Fresh: written" in rendered
    assert "no wiki or code changes since" in rendered
    assert "## Boot instruction\nImplement integration tests for API." in rendered


def test_2_wiki_change_after_handoff_renders_stale(tmp_path: Path) -> None:
    """Case 2: Wiki change after handoff -> stale; changed article listed; boot instruction relabeled; file byte-identical."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    write_article(
        "product/overview.md",
        "---\ntype: product\nsummary: overview\n---\n# Overview\n",
        wiki_root=wiki_root,
    )

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Done feature.",
        completed_work=["Step 1"],
        pending_work=["Step 2"],
        boot_instruction="Execute step 2 immediately.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel
    content_before = handoff_path.read_bytes()

    # Modify a wiki article after handoff
    time.sleep(0.01)
    write_article(
        "product/overview.md",
        "---\ntype: product\nsummary: overview updated\n---\n# Overview\nUpdated content.\n",
        wiki_root=wiki_root,
    )

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "stale"
    assert "product/overview.md" in freshness.changed_wiki_articles

    rendered, _ = read_handoff("latest", wiki_root=wiki_root)
    assert "Last handoff (stale: verify before acting)" in rendered
    assert "product/overview.md" in rendered
    assert "## Boot instruction (historical: verify against current state)" in rendered
    assert "Execute step 2 immediately." in rendered

    # Verify handoff file on disk was NOT mutated
    assert handoff_path.read_bytes() == content_before


def test_3_same_transaction_session_commit_is_fresh(tmp_path: Path) -> None:
    """Case 3: session_commit with writes and handoff in same transaction -> fresh immediately after."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    result = commit_session(
        payload={
            "writes": [
                {
                    "path": "features/auth.md",
                    "content": "---\ntype: feature\nsummary: auth flow\n---\n# Auth flow\n",
                }
            ],
            "handoff": {
                "session_type": "feature",
                "summary": "Implemented auth flow.",
                "completed_work": ["Auth middleware"],
                "pending_work": ["OAuth refresh"],
                "boot_instruction": "Add OAuth refresh endpoint.",
            },
        },
        wiki_root=wiki_root,
    )

    handoff_rel = result["handoff_path"]
    assert handoff_rel is not None
    handoff_path = wiki_root / handoff_rel

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "fresh"

    rendered, _ = read_handoff("latest", wiki_root=wiki_root)
    assert "Active handoff state" in rendered
    assert "Fresh: written" in rendered


def test_4_commit_independence_in_git(tmp_path: Path) -> None:
    """Case 4: Handoff written with uncommitted changes, then git commit -am -> still fresh, commits_since == 1."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    # Modify code outside wiki
    src_file = tmp_path / "app.py"
    src_file.write_text("print('hello')\n", encoding="utf-8")

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Added app.py.",
        completed_work=["app.py created"],
        pending_work=["tests"],
        boot_instruction="Write tests.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    # Commit uncommitted code
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "commit app.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    # Tree contents did not change, only git commit occurred
    assert freshness.state == "fresh"
    assert freshness.commits_since == 1


def test_5_code_change_after_handoff_renders_stale(tmp_path: Path) -> None:
    """Case 5: Code change outside .brain-79 after handoff -> stale, code_changed is True."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Initial code state.",
        completed_work=["Init"],
        pending_work=["More code"],
        boot_instruction="Add code.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    # Change code
    new_code = tmp_path / "service.py"
    new_code.write_text("def run(): pass\n", encoding="utf-8")

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "stale"
    assert freshness.code_changed is True

    rendered, _ = read_handoff("latest", wiki_root=wiki_root)
    assert "Last handoff (stale: verify before acting)" in rendered


def test_6_mtime_touch_clone_safety(tmp_path: Path) -> None:
    """Case 6: Touching article mtime without changing content -> still fresh (content hash safety)."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    art_rel = "features/feature1.md"
    write_article(
        art_rel,
        "---\ntype: feature\nsummary: feature 1\n---\n# Feature 1\n",
        wiki_root=wiki_root,
    )

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Done.",
        completed_work=["F1"],
        pending_work=["F2"],
        boot_instruction="Do F2.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    # Simulate git checkout/clone altering mtime by setting mtime to future
    future_time = time.time() + 1000
    os.utime(wiki_root / art_rel, (future_time, future_time))

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "fresh"


def test_7_foreign_branch_rendering(tmp_path: Path) -> None:
    """Case 7: Handoff written on main, checkout feature branch -> foreign_branch; orient omits pending work; read_handoff full."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Main branch handoff.",
        completed_work=["Finished on main"],
        pending_work=["Pending on main"],
        boot_instruction="Instruction for main.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    # Switch branch
    subprocess.run(
        ["git", "checkout", "-b", "feat-experiment"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "foreign_branch"

    rendered_orient = orient_session(wiki_root=wiki_root)
    assert "Last handoff (from branch" in rendered_orient
    assert "Main branch handoff." in rendered_orient
    assert "Pending on main" not in rendered_orient
    assert "Instruction for main." not in rendered_orient
    assert "brain79_handoff_read" in rendered_orient

    # read_handoff must return full content
    rendered_read, _ = read_handoff(handoff_rel, wiki_root=wiki_root)
    assert "Pending on main" in rendered_read
    assert "Instruction for main." in rendered_read


def test_8_branch_aware_latest_resolution(tmp_path: Path) -> None:
    """Case 8: Older handoff on main, newer handoff on feature branch; on main, latest resolves to main handoff."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    # Handoff 1 on main
    write_handoff(
        session_type="feature",
        summary="Handoff 1 on main branch.",
        completed_work=["H1"],
        pending_work=["H1 next"],
        boot_instruction="H1 boot.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    # Switch to feature branch and write Handoff 2
    subprocess.run(
        ["git", "checkout", "-b", "feat-branch"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    time.sleep(0.01)
    write_handoff(
        session_type="feature",
        summary="Handoff 2 on feat branch.",
        completed_work=["H2"],
        pending_work=["H2 next"],
        boot_instruction="H2 boot.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    # On feat-branch, latest is h2
    rendered_feat, _ = read_handoff("latest", wiki_root=wiki_root)
    assert "Handoff 2 on feat branch." in rendered_feat

    # Switch back to main; latest should resolve to h1
    subprocess.run(["git", "checkout", "main"], cwd=tmp_path, check=True, capture_output=True)
    rendered_main, _ = read_handoff("latest", wiki_root=wiki_root)
    assert "Handoff 1 on main branch." in rendered_main
    assert "Handoff 2 on feat branch." not in rendered_main


def test_9_non_git_workspace_general_profile(tmp_path: Path) -> None:
    """Case 9: Non-git workspace (general profile): git fields are none; freshness relies on wiki_digest."""
    # Do NOT init git
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    write_article(
        "topics/market-analysis.md",
        "---\ntype: topic\nsummary: analysis\n---\n# Market analysis\n",
        wiki_root=wiki_root,
    )

    handoff_rel = write_handoff(
        session_type="research",
        summary="Analyzed pricing.",
        completed_work=["SaaS tiering"],
        pending_work=["Enterprise SLA"],
        boot_instruction="Research enterprise SLAs.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel
    frontmatter, _ = parse_frontmatter(handoff_path.read_text(encoding="utf-8"))
    assert frontmatter["git_branch"] == "none"
    assert frontmatter["git_head"] == "none"
    assert frontmatter["code_digest"] == "none"
    assert len(frontmatter["wiki_digest"]) == 64

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "fresh"

    # Modify wiki article
    time.sleep(0.01)
    write_article(
        "topics/market-analysis.md",
        "---\ntype: topic\nsummary: analysis updated\n---\n# Market analysis\nUpdated.",
        wiki_root=wiki_root,
    )
    freshness2 = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness2.state == "stale"


def test_10_legacy_handoff_without_provenance(tmp_path: Path) -> None:
    """Case 10: Legacy handoff without digests or git fields -> unverified; promotion warning detected; age from filename."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    handoffs_dir = wiki_root / "handoffs"
    handoffs_dir.mkdir()

    legacy_filename = "handoff-2024-01-01-120000-000.md"
    legacy_content = (
        "---\n"
        "type: handoff\n"
        "session_type: feature\n"
        "previous_ref: none\n"
        "last_updated: 2024-01-01\n"
        "schema_version: 1\n"
        "---\n\n"
        "# Handoff — 2024-01-01-120000-000 (UTC)\n"
        "**Tipo de sesión:** feature\n"
        "**Referencia anterior:** none\n\n"
        "## Contexto inmediato\n"
        "Legacy context.\n\n"
        "## Conocimiento pendiente de promoción (a wiki)\n"
        "- Critical insight to promote\n\n"
        "## Instrucción de arranque\n"
        "Legacy boot instruction.\n"
    )
    legacy_path = handoffs_dir / legacy_filename
    legacy_path.write_text(legacy_content, encoding="utf-8")

    freshness = compute_handoff_freshness(legacy_path, wiki_root=wiki_root)
    assert freshness.state == "unverified"
    assert freshness.age_seconds > 86400 * 30  # Over 30 days old

    rendered, has_promo = read_handoff("latest", wiki_root=wiki_root)
    assert "Last handoff (stale: verify before acting)" in rendered
    assert has_promo is True
    assert "Legacy boot instruction." in rendered


def test_11_git_failure_tolerance(tmp_path: Path) -> None:
    """Case 11: Git command failure or timeout -> unknown, no exception, unverified rendering."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Normal handoff.",
        completed_work=["Step A"],
        pending_work=["Step B"],
        boot_instruction="Step B boot.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    with patch(
        "brain79.core.handoff_freshness._run_git",
        side_effect=subprocess.SubprocessError("git timeout"),
    ):
        freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
        assert freshness.state in ("unverified", "stale")

    rendered, _ = read_handoff("latest", wiki_root=wiki_root)
    assert rendered  # Never crashes


def test_12_escalation_of_aging_pending_work(tmp_path: Path) -> None:
    """Case 12: Escalation banner appears when state is not fresh, pending work exists, and thresholds crossed."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    write_handoff(
        session_type="feature",
        summary="Feature with pending work.",
        completed_work=["Done 1"],
        pending_work=["Unfinished long-term task"],
        boot_instruction="Work on task.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    # Make handoff stale
    new_code = tmp_path / "extra.py"
    new_code.write_text("x = 1\n", encoding="utf-8")

    # When age and commits are low, no escalation banner
    rendered_orient = orient_session(wiki_root=wiki_root)
    assert "Pending work in this handoff is aging" not in rendered_orient

    # Simulate aged handoff (crossing age threshold)
    aged_freshness = HandoffFreshness(
        state="stale",
        reasons=["wiki changed"],
        age_seconds=86400 * (HANDOFF_ESCALATION_AGE_DAYS + 1),
        commits_since=2,
        handoff_branch="main",
        current_branch="main",
        changed_wiki_articles=["features/something.md"],
        code_changed=False,
    )
    with patch(
        "brain79.core.orient.compute_handoff_freshness",
        return_value=aged_freshness,
    ), patch(
        "brain79.core.handoff.compute_handoff_freshness",
        return_value=aged_freshness,
    ):
        rendered_aged = orient_session(wiki_root=wiki_root)
        assert "Pending work in this handoff is aging" in rendered_aged
        assert "handoff-purge" in rendered_aged


def test_13_english_handoff_template_and_colon_formatting(tmp_path: Path) -> None:
    """Case 13: New handoffs use English headings and colons outside bold; no Spanish headings."""
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    handoff_rel = write_handoff(
        session_type="feature",
        summary="English handoff test.",
        completed_work=["Feature A"],
        pending_work=["Feature B"],
        knowledge_pending_promotion=["Promotion point"],
        resources=["Doc link"],
        gotchas=["Watch out for cache"],
        boot_instruction="Start Feature B.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    handoff_text = (wiki_root / handoff_rel).read_text(encoding="utf-8")
    # Colon outside bold
    assert "**Session type**: feature" in handoff_text
    assert "**Previous ref**:" in handoff_text
    # English headings
    assert "## Immediate context" in handoff_text
    assert "## Completed work" in handoff_text
    assert "## Pending work" in handoff_text
    assert "## Knowledge pending promotion" in handoff_text
    assert "## Resources" in handoff_text
    assert "## Gotchas" in handoff_text
    assert "## Boot instruction" in handoff_text

    # No Spanish headings
    assert "Trabajo completado" not in handoff_text
    assert "Trabajo pendiente" not in handoff_text
    assert "Instrucción de arranque" not in handoff_text
    assert "Contexto inmediato" not in handoff_text
    assert "**Tipo de sesión:**" not in handoff_text


def test_14_orient_idempotence_no_filesystem_mutation(tmp_path: Path) -> None:
    """Case 14: Two consecutive orient calls produce identical handoff sections and zero filesystem changes."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    write_handoff(
        session_type="feature",
        summary="Idempotence test.",
        completed_work=["Step 1"],
        pending_work=["Step 2"],
        boot_instruction="Run step 2.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    def _snapshot_fs(root: Path) -> dict[str, tuple[int, int]]:
        return {
            str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*")
            if p.is_file()
        }

    snapshot1 = _snapshot_fs(wiki_root)
    orient1 = orient_session(wiki_root=wiki_root)

    time.sleep(0.01)
    snapshot2 = _snapshot_fs(wiki_root)
    orient2 = orient_session(wiki_root=wiki_root)

    # Ignore age indicator ticking in banner ("written Xs ago")
    import re
    norm_orient1 = re.sub(r"written \d+s ago", "written Xs ago", orient1)
    norm_orient2 = re.sub(r"written \d+s ago", "written Xs ago", orient2)

    assert norm_orient1 == norm_orient2
    assert snapshot1 == snapshot2


def test_adversarial_1_deleted_file_in_working_tree_does_not_crash_code_digest(tmp_path: Path) -> None:
    """Finding 1: Tracked file deleted uncommitted in working tree must not crash git hash-object with 128."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    # Track app.py in git
    app_file = tmp_path / "app.py"
    app_file.write_text("print('test')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add app.py"], cwd=tmp_path, check=True, capture_output=True)

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Initial handoff with app.py tracked.",
        completed_work=["app.py"],
        pending_work=["Refactor"],
        boot_instruction="Refactor app.py.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    # Delete app.py from disk (uncommitted deletion)
    app_file.unlink()

    # compute_code_digest must not return "unknown"
    code_digest = compute_code_digest(tmp_path)
    assert code_digest != "unknown"
    assert len(code_digest) == 64

    # Freshness must correctly detect codebase modification (stale), NOT unverified
    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "stale"
    assert freshness.code_changed is True

    # Writing a handoff while a file is deleted must also succeed with valid 64-char digest
    h2_rel = write_handoff(
        session_type="feature",
        summary="Handoff after deleting app.py.",
        completed_work=["Deleted app.py"],
        pending_work=["cleanup"],
        boot_instruction="cleanup.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    fm, _ = parse_frontmatter((wiki_root / h2_rel).read_text(encoding="utf-8"))
    assert fm["code_digest"] != "unknown"
    assert len(fm["code_digest"]) == 64


def test_adversarial_2_detached_head_in_ci_not_flagged_as_foreign_branch(tmp_path: Path) -> None:
    """Finding 2: In CI detached HEAD, handoff must not falsely trigger foreign_branch."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Handoff on main branch.",
        completed_work=["Task 1"],
        pending_work=["Task 2"],
        boot_instruction="Execute task 2.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    # Detach HEAD (e.g. CI checkout)
    subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=tmp_path, check=True, capture_output=True)

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state != "foreign_branch"
    assert freshness.state == "fresh"

    # Pending work and boot instruction must NOT be suppressed
    rendered = orient_session(wiki_root=wiki_root)
    assert "Task 2" in rendered
    assert "Execute task 2." in rendered
    assert "Last handoff (from branch" not in rendered


def test_adversarial_3_orient_avoids_double_freshness_computation(tmp_path: Path) -> None:
    """Finding 3: orient() must compute freshness exactly once per invocation, not twice."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    write_handoff(
        session_type="feature",
        summary="Testing single computation.",
        completed_work=["Done"],
        pending_work=["Next"],
        boot_instruction="Go.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    with patch(
        "brain79.core.orient.compute_handoff_freshness",
        wraps=compute_handoff_freshness,
    ) as mock_freshness:
        orient_session(wiki_root=wiki_root)
        assert mock_freshness.call_count == 1


def test_adversarial_4_quoted_paths_with_non_ascii_or_spaces_do_not_leak_into_code_digest(tmp_path: Path) -> None:
    """Finding 4: Wiki paths with accents/spaces must not leak into code_digest due to git quotepath."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    # Track a normal code file
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add main.py"], cwd=tmp_path, check=True, capture_output=True)

    initial_code_digest = compute_code_digest(tmp_path)

    # Create a wiki file with non-ASCII and space: .brain-79/decisions/decisión técnica.md
    dec_dir = wiki_root / "decisions"
    dec_dir.mkdir()
    wiki_file = dec_dir / "decisión técnica.md"
    wiki_file.write_text("# Decisión\n", encoding="utf-8")

    # Code digest must NOT change even if untracked wiki file has non-ASCII characters or spaces
    digest_after_wiki_file = compute_code_digest(tmp_path)
    assert digest_after_wiki_file == initial_code_digest


def test_adversarial_5_dormant_repo_escalation_triggers_on_age_alone(tmp_path: Path) -> None:
    """Finding 5: Escalation banner must appear on dormant repos where age threshold is crossed even if state is fresh."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    write_handoff(
        session_type="feature",
        summary="Dormant repo handoff.",
        completed_work=["Old work"],
        pending_work=["Unfinished task from long ago"],
        boot_instruction="Finish task.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )

    dormant_freshness = HandoffFreshness(
        state="fresh",
        reasons=["all content digests match exactly"],
        age_seconds=86400 * (HANDOFF_ESCALATION_AGE_DAYS + 5),
        commits_since=0,
        handoff_branch="main",
        current_branch="main",
        changed_wiki_articles=[],
        code_changed=False,
    )

    with patch(
        "brain79.core.orient.compute_handoff_freshness",
        return_value=dormant_freshness,
    ):
        rendered = orient_session(wiki_root=wiki_root)
        assert "Pending work in this handoff is aging" in rendered
        assert "handoff-purge" in rendered


def test_adversarial_round2_1_broken_symlink_recorded_as_symlink_not_deleted(tmp_path: Path) -> None:
    """Finding 1 (Round 2): Broken symlinks must be evaluated as symlinks, not misclassified as deleted files."""
    _setup_git_repo(tmp_path)

    # Create a broken symlink in working tree
    broken_symlink = tmp_path / "broken_link.txt"
    try:
        broken_symlink.symlink_to(tmp_path / "nonexistent_target.txt")
    except OSError:
        pytest.skip("Symlinks not supported on this OS/filesystem")

    # The digest must be computable and stable
    digest1 = compute_code_digest(tmp_path)
    assert digest1 != "unknown"
    assert len(digest1) == 64

    # If broken symlink target changes, the digest must change
    broken_symlink.unlink()
    broken_symlink.symlink_to(tmp_path / "other_nonexistent_target.txt")
    digest2 = compute_code_digest(tmp_path)
    # Target path changed, so digest must reflect the symlink target change, not just a static 'deleted' token!
    assert digest2 != digest1


def test_adversarial_round2_2_monorepo_subfolder_diff_with_relative(tmp_path: Path) -> None:
    """Finding 2 (Round 2): In monorepos/subdirectories, git diff must use --relative to report changed wiki articles."""
    _setup_git_repo(tmp_path)

    # Subdirectory project: packages/service
    service_root = tmp_path / "packages" / "service"
    service_root.mkdir(parents=True)
    wiki_root = service_root / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    art_file = wiki_root / "features" / "auth.md"
    art_file.parent.mkdir(parents=True)
    art_file.write_text("---\ntype: feature\nsummary: auth\n---\n# Auth\n", encoding="utf-8")

    # Initial commit of entire repo
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init monorepo"], cwd=tmp_path, check=True, capture_output=True)

    handoff_rel = write_handoff(
        session_type="feature",
        summary="Service handoff.",
        completed_work=["Auth"],
        pending_work=["Tokens"],
        boot_instruction="Tokens.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    # Modify wiki article
    art_file.write_text("---\ntype: feature\nsummary: auth updated\n---\n# Auth updated\n", encoding="utf-8")

    # Evaluate freshness from the subproject directory
    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    assert freshness.state == "stale"
    assert "features/auth.md" in freshness.changed_wiki_articles


def test_adversarial_round2_3_git_repo_with_zero_commits_is_fresh(tmp_path: Path) -> None:
    """Finding 3 (Round 2): A git repo with git init but zero commits must not falsely degrade to unverified."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    # Track an initial file in working tree without committing
    (tmp_path / "code.py").write_text("print(1)\n", encoding="utf-8")

    handoff_rel = write_handoff(
        session_type="feature",
        summary="First session in zero-commit repo.",
        completed_work=["Init"],
        pending_work=["First commit"],
        boot_instruction="Make first commit.",
        _has_session_writes=True,
        wiki_root=wiki_root,
    )
    handoff_path = wiki_root / handoff_rel

    freshness = compute_handoff_freshness(handoff_path, wiki_root=wiki_root)
    # Must be fresh because zero changes occurred since handoff was written!
    assert freshness.state == "fresh"


def test_adversarial_round2_4_argument_injection_via_git_head_is_defended(tmp_path: Path) -> None:
    """Finding 4 (Round 2): Malformed or flag-injected git_head in frontmatter must be rejected as invalid SHA."""
    _setup_git_repo(tmp_path)
    wiki_root = tmp_path / ".brain-79"
    wiki_root.mkdir()
    (wiki_root / "handoffs").mkdir()

    # Write a handoff with malicious git_head injected into frontmatter
    handoff_file = wiki_root / "handoffs" / "handoff-2026-11-05-235959-999.md"
    handoff_content = (
        "---\n"
        "type: handoff\n"
        "session_type: feature\n"
        "previous_ref: none\n"
        "created_at: 2026-11-05T23:59:59Z\n"
        "last_updated: 2026-11-05\n"
        "git_branch: main\n"
        "git_head: '--all'\n"
        "wiki_digest: '0000000000000000000000000000000000000000000000000000000000000000'\n"
        "code_digest: '0000000000000000000000000000000000000000000000000000000000000000'\n"
        "schema_version: 1\n"
        "---\n\n"
        "# Handoff — 2026-11-05-235959-999 (UTC)\n\n"
        "## Immediate context\n"
        "Injection test.\n\n"
        "## Boot instruction\n"
        "Run.\n"
    )
    handoff_file.write_text(handoff_content, encoding="utf-8")

    # Calling compute_handoff_freshness must not pass '--all' to git rev-list or git diff
    freshness = compute_handoff_freshness(handoff_file, wiki_root=wiki_root)
    assert freshness.commits_since is None  # Handled safely as invalid SHA


