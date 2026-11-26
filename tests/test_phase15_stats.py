"""Tests for Phase 15 Stage 3: read-only context budget telemetry (`stats.py`) and CLI (`brain79 stats`)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, cast

import pytest

from brain79.core.frontmatter import ValidationError
from brain79.core.orient import MAX_ORIENT_INLINE_CHARS
from brain79.core.validation import MAX_ARTICLE_BYTES, MAX_ARTICLE_LINES


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _build_sample_wiki(root: Path) -> None:
    """Create a minimal deterministic .brain-79/ wiki and workspace files."""
    wiki = root / ".brain-79"
    wiki.mkdir(parents=True, exist_ok=True)

    _write_file(
        wiki / "SCHEMA.md",
        "---\nprofile: software\nenforcement: strict\nschema_version: 2\n---\n\n# Schema\n",
    )
    _write_file(
        wiki / "INDEX.md",
        "---\ntype: navigation\nlast_updated: 2026-01-01\n---\n\n# Project index\n",
    )
    # Active feature governing src/a.py and src/b.py
    _write_file(
        wiki / "features" / "auth.md",
        (
            "---\n"
            "type: feature\n"
            "status: active\n"
            "summary: Auth module\n"
            "last_updated: 2026-01-01\n"
            "applies_to:\n"
            "  - src/a.py\n"
            "  - src/b.py\n"
            "---\n\n"
            "# Auth\n\nAuth details.\n\n[<- Back to Index](../INDEX.md)\n"
        ),
    )
    # Inactive (superseded) and pre-implementation (draft) + stability: archived/deprecated
    _write_file(
        wiki / "features" / "old.md",
        (
            "---\n"
            "type: feature\n"
            "status: superseded\n"
            "summary: Old feature\n"
            "last_updated: 2026-01-01\n"
            "applies_to:\n"
            "  - src/ungoverned.py\n"
            "---\n\n"
            "# Old\n"
        ),
    )
    _write_file(
        wiki / "features" / "draft_feat.md",
        (
            "---\n"
            "type: feature\n"
            "status: draft\n"
            "summary: Draft feature\n"
            "last_updated: 2026-01-01\n"
            "applies_to:\n"
            "  - src/ungoverned.py\n"
            "---\n\n"
            "# Draft\n"
        ),
    )
    _write_file(
        wiki / "features" / "archived_stab.md",
        (
            "---\n"
            "type: feature\n"
            "status: active\n"
            "stability: archived\n"
            "summary: Archived stability\n"
            "last_updated: 2026-01-01\n"
            "applies_to:\n"
            "  - src/ungoverned.py\n"
            "---\n\n"
            "# Archived\n"
        ),
    )
    _write_file(
        wiki / "features" / "deprecated_stab.md",
        (
            "---\n"
            "type: feature\n"
            "status: active\n"
            "stability: deprecated\n"
            "summary: Deprecated stability\n"
            "last_updated: 2026-01-01\n"
            "applies_to:\n"
            "  - src/ungoverned.py\n"
            "---\n\n"
            "# Deprecated\n"
        ),
    )
    # Missing frontmatter type -> grouped under "unknown"
    _write_file(
        wiki / "topics" / "no_type.md",
        "# No frontmatter topic\n\nPlain markdown without frontmatter.\n",
    )
    # Oversized living manual (> MAX_ARTICLE_BYTES) -> over_limit=True
    oversized_body = "x" * (MAX_ARTICLE_BYTES + 200)
    _write_file(
        wiki / "architecture" / "huge_arch.md",
        (
            "---\n"
            "type: architecture\n"
            "status: active\n"
            "summary: Huge architecture\n"
            "last_updated: 2026-01-01\n"
            "---\n\n"
            f"# Huge\n\n{oversized_body}\n"
        ),
    )
    # Large immutable decision (> MAX_ARTICLE_LINES) -> over_limit=False
    many_lines = "\n".join(f"Line {i}" for i in range(MAX_ARTICLE_LINES + 30))
    _write_file(
        wiki / "decisions" / "adr-001.md",
        (
            "---\n"
            "type: decision\n"
            "status: accepted\n"
            "summary: Big ADR\n"
            "last_updated: 2026-01-01\n"
            "---\n\n"
            f"# ADR-001\n\n{many_lines}\n"
        ),
    )
    # Large changelog -> over_limit=False
    _write_file(
        wiki / "changelog" / "v0-1-0.md",
        (
            "---\n"
            "type: changelog\n"
            "status: active\n"
            "summary: Big changelog\n"
            "last_updated: 2026-01-01\n"
            "---\n\n"
            f"# v0.1.0\n\n{many_lines}\n"
        ),
    )
    # Handoff
    _write_file(
        wiki / "handoffs" / "2026-01-01T00-00-00Z.md",
        (
            "---\n"
            "type: handoff\n"
            "session_type: feature\n"
            "previous_ref: none\n"
            "last_updated: 2026-01-01\n"
            "---\n\n"
            "## Completed work\n\n- Setup\n"
        ),
    )
    # Workspace files
    _write_file(root / "AGENTS.md", "# Agent instructions\n\nRead INDEX.md.\n")
    _write_file(root / "CLAUDE.md", "# Claude instructions\n")
    _write_file(root / "src" / "a.py", "def a() -> int:\n    return 1\n")
    _write_file(root / "src" / "b.py", "def b() -> int:\n    return 2\n")
    _write_file(root / "src" / "ungoverned.py", "def u() -> int:\n    return 3\n")


def test_estimate_tokens_edge_cases() -> None:
    """R-3.1(1): estimate_tokens handles empty, 4-char boundaries, and CRLF==LF parity."""
    from brain79.core.stats import estimate_tokens

    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("a\r\nb\r\nc") == estimate_tokens("a\nb\nc")


def test_compute_stats_accuracy_and_edge_cases(tmp_path: Path) -> None:
    """AC-10 / R-3.1..R-3.3: verify wiki, context_budget, coverage, ast_guards, tie-breaks, and format_text."""
    from brain79.core.stats import compute_stats, estimate_tokens

    repo = tmp_path / "repo"
    _build_sample_wiki(repo)

    # Create two equal-byte articles to test largest_articles tie-breaking ascending by path
    equal_content = "---\ntype: topic\nstatus: active\nsummary: Tie\nlast_updated: 2026-01-01\n---\n\n# Tie\n"
    _write_file(repo / ".brain-79" / "topics" / "z_tie.md", equal_content)
    _write_file(repo / ".brain-79" / "topics" / "a_tie.md", equal_content)

    report = compute_stats(repo, repo / ".brain-79", task="auth", paths=["src/a.py"], max_articles=4)
    data = report.to_dict()

    wiki = data["wiki"]
    assert wiki["profile"] == "software"
    assert wiki["enforcement"] == "strict"
    # 11 governed articles: auth, old, draft_feat, archived_stab, deprecated_stab, no_type, huge_arch, adr-001, v0-1-0, z_tie, a_tie
    assert wiki["total_articles"] == 11
    # Active: auth, no_type, huge_arch, adr-001, v0-1-0, z_tie, a_tie => 7
    assert wiki["active_articles"] == 7
    assert wiki["articles_by_type"] == {
        "architecture": 1,
        "changelog": 1,
        "decision": 1,
        "feature": 5,
        "topic": 2,
        "unknown": 1,
    }
    assert wiki["handoff_count"] == 1
    assert wiki["index_lines"] > 0
    assert wiki["index_estimated_tokens"] == estimate_tokens(
        (repo / ".brain-79" / "INDEX.md").read_text(encoding="utf-8")
    )

    largest = wiki["largest_articles"]
    assert len(largest) == 5
    # Verify descending by bytes, tie-broken ascending by path
    for prev, curr in zip(largest, largest[1:]):
        assert (prev["bytes"], curr["path"]) >= (curr["bytes"], prev["path"]) or prev["bytes"] > curr["bytes"]
    by_path = {item["path"]: item for item in largest}
    assert by_path["architecture/huge_arch.md"]["over_limit"] is True
    assert by_path["decisions/adr-001.md"]["over_limit"] is False
    assert by_path["changelog/v0-1-0.md"]["over_limit"] is False

    # Context budget
    cb = data["context_budget"]
    assert cb["token_estimator"] == "chars_div_4_ceil"
    assert cb["orient_budget_chars"] == MAX_ORIENT_INLINE_CHARS
    assert cb["full_wiki_chars"] == wiki["total_chars"] + wiki["index_chars"]
    assert cb["full_wiki_estimated_tokens"] == wiki["estimated_tokens"] + wiki["index_estimated_tokens"]
    assert cb["orient_budget_utilization_pct"] == round(
        (cb["orient_chars"] / MAX_ORIENT_INLINE_CHARS) * 100.0, 1
    )
    inst_paths = [item["path"] for item in cb["instruction_files"]]
    assert inst_paths == ["AGENTS.md", "CLAUDE.md"]
    assert cb["instruction_files_estimated_tokens"] == sum(
        item["estimated_tokens"] for item in cb["instruction_files"]
    )

    # Coverage: workspace has AGENTS.md, CLAUDE.md, src/a.py, src/b.py, src/ungoverned.py => 5 files
    cov = data["coverage"]
    assert cov["total_workspace_files"] == 5
    # Only active auth.md governs src/a.py and src/b.py; inactive/archived/deprecated articles excluded
    assert cov["governed_workspace_files"] == 2
    assert cov["ungoverned_workspace_files"] == 3
    assert cov["coverage_pct"] == 40.0
    # auth.md has no drift manifest yet -> drifted
    assert cov["drifted_articles_count"] >= 1
    assert "features/auth.md" in cov["drifted_articles"]

    # AST guards
    ast_g = data["ast_guards"]
    for key in (
        "built_in",
        "polyglot_runtime_available",
        "polyglot_installed",
        "active_languages",
        "missing_grammars",
        "broken_grammars",
        "registered_extensions",
    ):
        assert key in ast_g
    assert ast_g["governed_files_ast_covered"] == 2
    assert ast_g["governed_files_ast_coverage_pct"] == 100.0

    # format_text()
    rendered = report.format_text()
    assert "# Brain-79 — Context and Governance Statistics" in rendered
    assert "architecture/huge_arch.md" in rendered
    assert "OVER LIMIT" in rendered.upper()


def test_compute_stats_unclamped_utilization_and_tie_break(tmp_path: Path) -> None:
    """R-3.2(1)-(2): unclamped orient_budget_utilization_pct (>100%) and ascending path tie-break."""
    from brain79.core.stats import compute_stats

    repo = tmp_path / "repo"
    wiki = repo / ".brain-79"
    _write_file(wiki / "SCHEMA.md", "---\nprofile: software\nenforcement: strict\n---\n\n# Schema\n")
    # Make INDEX.md > 64,000 chars so orient_budget_utilization_pct exceeds 100.0
    huge_index = "---\ntype: navigation\nlast_updated: 2026-01-01\n---\n\n" + ("a" * (MAX_ORIENT_INLINE_CHARS + 500)) + "\n"
    _write_file(wiki / "INDEX.md", huge_index)

    same = "---\ntype: topic\nstatus: active\nsummary: Tie\nlast_updated: 2026-01-01\n---\n\n# Tie\n"
    for name in ("d.md", "b.md", "a.md", "c.md", "e.md", "f.md"):
        _write_file(wiki / "topics" / name, same)

    report = compute_stats(repo, wiki)
    data = report.to_dict()
    assert data["context_budget"]["orient_budget_utilization_pct"] > 100.0
    largest_paths = [item["path"] for item in data["wiki"]["largest_articles"]]
    assert largest_paths == [
        "topics/a.md",
        "topics/b.md",
        "topics/c.md",
        "topics/d.md",
        "topics/e.md",
    ]


def test_compute_stats_single_workspace_index_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-10 / R-3.1(2),(4): WorkspaceIndex.build called once and zero disk mutations occur."""
    from brain79.core.drift import WorkspaceIndex
    from brain79.core.stats import compute_stats

    repo = tmp_path / "repo"
    _build_sample_wiki(repo)

    build_calls = 0
    orig_build = WorkspaceIndex.build.__func__  # type: ignore[attr-defined]

    def spy_build(cls: type[WorkspaceIndex], *args: Any, **kwargs: Any) -> WorkspaceIndex:
        nonlocal build_calls
        build_calls += 1
        return cast(WorkspaceIndex, orig_build(cls, *args, **kwargs))

    monkeypatch.setattr(WorkspaceIndex, "build", classmethod(spy_build))

    def _snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
        snap: dict[str, tuple[int, int]] = {}
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if rel == ".git" or rel.startswith(".git/"):
                continue
            if p.is_file():
                st = p.stat()
                snap[rel] = (st.st_mtime_ns, st.st_size)
        return snap

    before = _snapshot_tree(repo)
    compute_stats(repo, repo / ".brain-79", task="auth", paths=["src/a.py"])
    after = _snapshot_tree(repo)

    assert build_calls == 1
    assert before == after
    assert not (repo / ".brain-79" / ".drift_manifest.json").exists()
    assert not (repo / ".brain-79" / ".navigation_registry.json").exists()
    assert not (repo / ".brain-79" / ".locks").exists()


def test_compute_stats_error_contracts(tmp_path: Path) -> None:
    """R-3.1(5): ValueError on max_articles<1, FileNotFoundError on missing wiki/INDEX.md, ValidationError on corrupt SCHEMA.md."""
    from brain79.core.stats import compute_stats

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    with pytest.raises(ValueError, match="max_articles"):
        compute_stats(empty_dir, empty_dir / ".brain-79", max_articles=0)

    with pytest.raises(FileNotFoundError, match="brain79 init"):
        compute_stats(empty_dir, empty_dir / ".brain-79")

    # .brain-79 exists, but INDEX.md is missing
    partial_wiki = tmp_path / "partial"
    (partial_wiki / ".brain-79").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="brain79 init"):
        compute_stats(partial_wiki, partial_wiki / ".brain-79")

    # Corrupt SCHEMA.md -> ValidationError
    corrupt_dir = tmp_path / "corrupt"
    _build_sample_wiki(corrupt_dir)
    _write_file(corrupt_dir / ".brain-79" / "SCHEMA.md", "---\nprofile: [broken\n---\n")
    with pytest.raises(ValidationError):
        compute_stats(corrupt_dir, corrupt_dir / ".brain-79")


def test_cli_brain79_stats_and_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-11 / R-3.4: CLI brain79 stats arguments, JSON parity, and exit codes 0, 1, 2, 3."""
    from brain79.__main__ import ROOT_HELP, main
    from brain79.cli.dispatch import WHITELIST, run_cli
    from brain79.config import set_project_root
    from brain79.core.stats import compute_stats

    assert "stats" in WHITELIST
    assert "stats" in ROOT_HELP

    assert run_cli("stats", ["--help"]) == 0
    help_out = capsys.readouterr().out
    assert "brain79 stats" in help_out

    repo = tmp_path / "repo"
    _build_sample_wiki(repo)
    monkeypatch.chdir(repo)

    # Text format -> exit 0
    assert run_cli("stats", []) == 0
    text_out = capsys.readouterr().out
    assert "# Brain-79 — Context and Governance Statistics" in text_out

    # JSON format with --task, space-separated --paths, --max-articles -> exit 0
    assert (
        run_cli(
            "stats",
            ["--format", "json", "--task", "auth", "--paths", "src/a.py", "src/b.py", "--max-articles", "2"],
        )
        == 0
    )
    json_out = capsys.readouterr().out
    parsed = json.loads(json_out)
    expected = compute_stats(
        repo, repo / ".brain-79", task="auth", paths=["src/a.py", "src/b.py"], max_articles=2
    ).to_dict()
    assert parsed == expected

    # Comma-separated --paths -> exit 0
    assert run_cli("stats", ["--format", "json", "--paths", "src/a.py,src/b.py"]) == 0
    capsys.readouterr()

    # Invalid args -> exit 2
    assert run_cli("stats", ["--max-articles", "0"]) == 2
    capsys.readouterr()
    assert run_cli("stats", ["--format", "invalid"]) == 2
    capsys.readouterr()

    try:
        # Missing .brain-79/ -> exit 2 with actionable stderr
        no_wiki = tmp_path / "no_wiki"
        no_wiki.mkdir()
        with pytest.raises(SystemExit) as exc_missing:
            main(["--project-root", str(no_wiki), "stats"])
        assert exc_missing.value.code == 2
        assert "brain79 init" in capsys.readouterr().err

        # Missing INDEX.md when .brain-79/ exists -> exit 2
        missing_idx = tmp_path / "missing_idx"
        (missing_idx / ".brain-79").mkdir(parents=True)
        with pytest.raises(SystemExit) as exc_idx:
            main(["--project-root", str(missing_idx), "stats"])
        assert exc_idx.value.code == 2
        assert "brain79 init" in capsys.readouterr().err

        # Corrupt SCHEMA.md -> exit 1
        corrupt_dir = tmp_path / "corrupt_cli"
        _build_sample_wiki(corrupt_dir)
        _write_file(corrupt_dir / ".brain-79" / "SCHEMA.md", "---\nprofile: [unclosed\n---\n")
        with pytest.raises(SystemExit) as exc_corrupt:
            main(["--project-root", str(corrupt_dir), "stats"])
        assert exc_corrupt.value.code == 1
        capsys.readouterr()

        # Unreadable wiki file -> exit 3 (Unix non-root)
        if sys.platform != "win32" and getattr(os, "geteuid", lambda: 1)() != 0:
            unreadable_dir = tmp_path / "unreadable"
            _build_sample_wiki(unreadable_dir)
            target_article = unreadable_dir / ".brain-79" / "features" / "auth.md"
            target_article.chmod(0o000)
            try:
                with pytest.raises(SystemExit) as exc_perm:
                    main(["--project-root", str(unreadable_dir), "stats"])
                assert exc_perm.value.code == 3
                capsys.readouterr()
            finally:
                target_article.chmod(0o644)
    finally:
        set_project_root(None)


def _init_clean_doctor_repo(tmp_path: Path) -> Path:
    """Create a clean initialized git repository that passes all 9 canonical doctor checks."""
    import subprocess

    from brain79.core.init_project import init_project

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True)
    init_project(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial", "--no-verify"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path / ".brain-79"


def test_doctor_ast_guard_capabilities_and_broken_grammars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-12: run_doctor() reports AST guard capabilities in 9 checks and warns on broken grammars."""
    from brain79.core.ast_guards import POLYGLOT_LANGUAGES
    from brain79.core.doctor import run_doctor

    w_root = _init_clean_doctor_repo(tmp_path)
    monkeypatch.setattr("brain79.core.doctor.shutil.which", lambda _: "/usr/local/bin/brain79")

    # (a) Core-only install (no polyglot) -> 9 checks, exit_code == 0
    core_caps: dict[str, Any] = {
        "built_in": ["python"],
        "polyglot_runtime_available": False,
        "polyglot_installed": False,
        "active_languages": ["python"],
        "missing_grammars": list(POLYGLOT_LANGUAGES),
        "broken_grammars": {},
        "registered_extensions": [".py"],
    }
    monkeypatch.setattr("brain79.core.ast_guards.get_ast_guard_capabilities", lambda: core_caps)

    core_report = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert core_report.exit_code == 0
    assert core_report.status == "ok"
    assert len(core_report.checks) == 9
    bin_check_core = next(c for c in core_report.checks if c.category == "binary_and_environment")
    assert (
        f"AST guards: python (built-in); install brain79[polyglot] for {len(POLYGLOT_LANGUAGES)} more language parsers"
        in bin_check_core.message
    )

    # (b) Healthy polyglot install -> 9 checks, exit_code == 0, custom inspectors excluded from polyglot count
    poly_caps: dict[str, Any] = {
        "built_in": ["python"],
        "polyglot_runtime_available": True,
        "polyglot_installed": True,
        "active_languages": ["custom_lang", "python", *POLYGLOT_LANGUAGES],
        "missing_grammars": [],
        "broken_grammars": {},
        "registered_extensions": [".custom", ".py"],
    }
    monkeypatch.setattr("brain79.core.ast_guards.get_ast_guard_capabilities", lambda: poly_caps)

    poly_report = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert poly_report.exit_code == 0
    assert poly_report.status == "ok"
    assert len(poly_report.checks) == 9
    bin_check_poly = next(c for c in poly_report.checks if c.category == "binary_and_environment")
    expected_list = ", ".join(sorted(POLYGLOT_LANGUAGES))
    assert (
        f"AST guards: python + {len(POLYGLOT_LANGUAGES)} polyglot parsers ({expected_list})"
        in bin_check_poly.message
    )

    # (c) Simulated broken_grammars={"go": "ABI mismatch"} -> ast_guards warning, exit_code == 2
    broken_caps: dict[str, Any] = {
        "built_in": ["python"],
        "polyglot_runtime_available": True,
        "polyglot_installed": True,
        "active_languages": ["python", *(lang for lang in POLYGLOT_LANGUAGES if lang != "go")],
        "missing_grammars": [],
        "broken_grammars": {"go": "ABI mismatch"},
        "registered_extensions": [".py"],
    }
    monkeypatch.setattr("brain79.core.ast_guards.get_ast_guard_capabilities", lambda: broken_caps)

    broken_report = run_doctor(project_root=tmp_path, wiki_root=w_root)
    assert broken_report.exit_code == 2
    assert broken_report.status == "warning"
    ast_check = next(c for c in broken_report.checks if c.category == "ast_guards")
    assert ast_check.status == "warning"
    assert "go" in ast_check.message
    assert "ABI mismatch" in ast_check.message
    assert 'uv tool install --reinstall "brain79[polyglot]"' in (ast_check.actionable or "")

