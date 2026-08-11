from pathlib import Path
from unittest.mock import patch


from brain79 import config
from brain79.core.lint import lint_wiki




def test_lint_read_only_contract(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    features_dir = wiki_dir / "features"
    features_dir.mkdir(parents=True)

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Main Index\n\n[Doc](features/doc.md)\n", encoding="utf-8")
    doc = features_dir / "doc.md"
    doc.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Document\n", encoding="utf-8")

    mtime_before = {p: p.stat().st_mtime_ns for p in wiki_dir.rglob("*")}

    report = lint_wiki()

    assert "[Status: OK]" in report

    mtime_after = {p: p.stat().st_mtime_ns for p in wiki_dir.rglob("*")}
    assert mtime_before == mtime_after


def test_lint_vacios_absolutos(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    raw_dir = wiki_dir / "_raw" / "sessions"
    raw_dir.mkdir(parents=True)
    (raw_dir / "session1.md").write_text("# Session 1\n", encoding="utf-8")

    handoff_dir = wiki_dir / "handoffs"
    handoff_dir.mkdir(parents=True)
    (handoff_dir / "handoff-1.md").write_text(
        "---\ntype: handoff\nsession_type: interactive\nprevious_ref: none\nlast_updated: 2026-08-11\n---\n\n"
        "# Handoff\nNo index link.\n", encoding="utf-8"
    )

    report = lint_wiki()
    assert "Brain-79 Lint Report" in report
    assert "[Status: OK]" in report  # handoffs are excluded from orphan analysis
    assert "## [INFO] Orphans (0)" in report


def test_lint_unicode_resilience(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    sub_dir = wiki_dir / "features" / "路径"
    sub_dir.mkdir(parents=True)
    target_file = sub_dir / "文件.md"
    target_file.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Target\n", encoding="utf-8")

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Index\n\n[Exotic](features/路径/文件.md)\n", encoding="utf-8")

    report = lint_wiki()
    assert "[Status: OK]" in report
    assert "## [CRITICAL] Broken Local Links (0)" in report


def test_lint_reference_titles(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    features_dir = wiki_dir / "features"
    features_dir.mkdir(parents=True)

    target = features_dir / "target.md"
    target.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Target Document\n", encoding="utf-8")

    idx = wiki_dir / "INDEX.md"
    idx.write_text(
        '# Index\n\n[Ref link][ref]\n\n[ref]: features/target.md "Some Title"\n',
        encoding="utf-8",
    )

    report = lint_wiki()
    assert "[Status: OK]" in report
    assert "## [CRITICAL] Broken Local Links (0)" in report


def test_lint_space_resilience(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    space_dir = wiki_dir / "features" / "path with spaces"
    space_dir.mkdir(parents=True)
    space_file = space_dir / "file.md"
    space_file.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Spaced File\n", encoding="utf-8")

    idx = wiki_dir / "INDEX.md"
    idx.write_text(
        "# Index\n\n[Space Link](features/path with spaces/file.md)\n",
        encoding="utf-8",
    )

    report = lint_wiki()
    assert "[Status: OK]" in report
    assert "## [CRITICAL] Broken Local Links (0)" in report


def test_lint_broken_links_and_namespace_violations(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    raw_dir = wiki_dir / "_raw" / "sessions"
    raw_dir.mkdir(parents=True)
    raw_file = raw_dir / "s1.md"
    raw_file.write_text("# Raw Session 1\n", encoding="utf-8")

    idx = wiki_dir / "INDEX.md"
    idx.write_text(
        "# Index\n\n[Broken](missing.md)\n[Violation](_raw/sessions/s1.md)\n",
        encoding="utf-8",
    )

    report = lint_wiki()
    assert "[Status: CRITICAL]" in report
    assert "## [CRITICAL] Broken Local Links (1)" in report
    assert "- INDEX.md → `missing.md`: target not found" in report
    assert "## [CRITICAL] Namespace Violations (1)" in report
    assert "- INDEX.md → `_raw/sessions/s1.md`: invalid namespace" in report


def test_lint_structural_errors_and_truncation(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    features_dir = wiki_dir / "features"
    features_dir.mkdir(parents=True)

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Index\n\nLinks to missing H1 files.\n", encoding="utf-8")

    # Empty file
    (features_dir / "empty.md").write_text("", encoding="utf-8")

    # Missing H1 header
    (features_dir / "no_h1.md").write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\nNo header here.\n", encoding="utf-8")

    # Create 55 missing H1 files to test truncation
    for i in range(55):
        file_name = f"no_h1_{i:02d}.md"
        (features_dir / file_name).write_text(f"---\ntype: feature\nlast_updated: 2026-08-11\n---\n\nLine {i}\n", encoding="utf-8")
        idx.write_text(
            idx.read_text(encoding="utf-8") + f"[{file_name}](features/{file_name})\n",
            encoding="utf-8",
        )

    # File too large
    huge = features_dir / "huge.md"
    huge.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Huge Header\n" + "x" * (1024 * 1024 + 10), encoding="utf-8")
    idx.write_text(
        idx.read_text(encoding="utf-8") + "[Huge](features/huge.md)\n", encoding="utf-8"
    )

    report = lint_wiki()
    assert "[Status: WARNING]" in report
    assert "## [WARNING] Structural Errors & Warnings (58)" in report
    assert "- features/empty.md: empty (0 bytes)" in report
    assert "- features/huge.md: file_too_large (skipped)" in report
    assert "... y 8 más ocultos" in report


def test_lint_orphans_bfs_analysis(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    features_dir = wiki_dir / "features"
    features_dir.mkdir(parents=True)

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Index\n\n[Article 1](features/art1.md)\n", encoding="utf-8")

    art1 = features_dir / "art1.md"
    art1.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Article 1\n\n[Article 2](art2.md)\n", encoding="utf-8")

    art2 = features_dir / "art2.md"
    art2.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Article 2\n", encoding="utf-8")

    orphan = features_dir / "orphan.md"
    orphan.write_text("---\ntype: feature\nlast_updated: 2026-08-11\n---\n\n# Lonely Article\n", encoding="utf-8")

    report = lint_wiki()
    assert "[Status: WARNING]" in report
    assert "## [INFO] Orphans (1)" in report
    assert "- features/orphan.md" in report


def test_lint_timeout_simulation(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Index\n", encoding="utf-8")

    start_time = 100.0
    times = [start_time, start_time + 20.0]  # Simulates > 15s elapsed immediately

    def mock_time() -> float:
        if times:
            return times.pop(0)
        return 200.0

    with patch("time.time", side_effect=mock_time):
        report = lint_wiki()

    assert "[timeout_reached: true]" in report


def test_lint_non_existent_wiki_dir(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    # .brain-79 directory does not exist
    report = lint_wiki()
    assert "# Brain-79 Lint Report" in report
    assert "[Status: OK] [timeout_reached: false]" in report


def test_lint_inline_code_strip(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Index\n\nUse `[link](file.md)` syntax.\n", encoding="utf-8")

    report = lint_wiki()
    assert "## [CRITICAL] Broken Local Links (0)" in report


def test_lint_locked_file_skipped(tmp_path: Path) -> None:
    import filelock

    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Index\n", encoding="utf-8")

    locked_file = wiki_dir / "locked.md"
    locked_file.write_text("# Locked Document\n", encoding="utf-8")
    lock_file = wiki_dir / "locked.md.lock"

    flock = filelock.FileLock(str(lock_file), timeout=0)
    flock.acquire()
    try:
        report = lint_wiki()
    finally:
        flock.release()

    assert "## [WARNING] Structural Errors & Warnings (1)" in report
    assert "- locked.md: locked (skipped)" in report


def test_lint_strict_h1_header(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    idx = wiki_dir / "INDEX.md"
    idx.write_text("# Index\n", encoding="utf-8")

    bad_h1 = wiki_dir / "bad_h1.md"
    bad_h1.write_text("#Title Without Space\n", encoding="utf-8")

    report = lint_wiki()
    assert "## [WARNING] Structural Errors & Warnings (1)" in report
    assert "- bad_h1.md: missing H1 header" in report


def test_lint_double_backtick_code_strip(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    idx = wiki_dir / "INDEX.md"
    idx.write_text(
        "# Index\n\nUse ``code with `[link](file.md)` inside`` syntax.\n",
        encoding="utf-8",
    )

    report = lint_wiki()
    assert "## [CRITICAL] Broken Local Links (0)" in report


def test_lint_url_encoded_paths(tmp_path: Path) -> None:
    config.set_project_root(tmp_path)
    wiki_dir = tmp_path / ".brain-79"
    wiki_dir.mkdir()

    space_dir = wiki_dir / "path with spaces"
    space_dir.mkdir()
    (space_dir / "file.md").write_text("# File\n", encoding="utf-8")

    idx = wiki_dir / "INDEX.md"
    idx.write_text(
        "# Index\n\n[Link](path%20with%20spaces/file.md)\n",
        encoding="utf-8",
    )

    report = lint_wiki()
    assert "## [CRITICAL] Broken Local Links (0)" in report
