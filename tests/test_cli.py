from io import BytesIO
from pathlib import Path
import subprocess
import sys
from unittest import mock

import pytest

from brain79.__main__ import parse_global_flags
from brain79.cli.dispatch import map_exception_to_exit_code, run_cli
from brain79.config import get_wiki_root, set_project_root
from brain79.core.init_project import init_project


@pytest.fixture(autouse=True)
def setup_cli_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


def test_dual_position_project_root(tmp_path: Path) -> None:
    p1 = tmp_path / "proj1"
    p1.mkdir()
    init_project(p1)

    p2 = tmp_path / "proj2"
    p2.mkdir()
    init_project(p2)

    root1, debug1, filtered1 = parse_global_flags(
        ["--project-root", str(p1), "read", "INDEX.md"]
    )
    assert root1 == p1.resolve()
    assert filtered1 == ["read", "INDEX.md"]

    root2, debug2, filtered2 = parse_global_flags(
        ["read", "--project-root", str(p2), "INDEX.md"]
    )
    assert root2 == p2.resolve()
    assert filtered2 == ["read", "INDEX.md"]


def test_debug_flag_hoisting() -> None:
    root, debug, filtered = parse_global_flags(["read", "--debug", "INDEX.md"])
    assert debug is True
    assert filtered == ["read", "INDEX.md"]


def test_project_root_missing_value(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_global_flags(["--project-root"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "requires a path argument" in captured.err


def test_cli_init(tmp_path: Path) -> None:
    new_proj = tmp_path / "new_proj"
    code = run_cli("init", ["--project-root", str(new_proj)])
    assert code == 0
    assert (new_proj / ".brain-79").exists()


def test_cli_update_branch_flag_parsed() -> None:
    with mock.patch("brain79.core.update.update_project", return_value=0) as m:
        code = run_cli("update", ["--branch", "develop"])
        assert code == 0
        m.assert_called_once_with(branch_override="develop")


def test_cli_index(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("index", [])
    assert code == 0
    captured = capsys.readouterr()
    assert "# Project index" in captured.out or "INDEX.md" in captured.out


def test_cli_read(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("read", ["INDEX.md"])
    assert code == 0
    captured = capsys.readouterr()
    assert len(captured.out) > 0


def test_cli_read_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("read", ["nonexistent.md"])
    assert code == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_cli_write_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    content_file = tmp_path / "content.md"
    content_file.write_text(
        "---\ntype: feature\nstatus: planned\nversion: 0.1.0\nlast_updated: 2026-08-11\n---\n\n# Test Title\n\nTest content",
        encoding="utf-8",
    )

    code = run_cli(
        "write", ["features/new.md", "--content-file", str(content_file)]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "features/new.md"

    wiki_root = get_wiki_root()
    article_path = wiki_root / "features/new.md"
    assert article_path.exists()
    assert "# Test Title" in article_path.read_text(encoding="utf-8")


class DummyStdin:
    def __init__(self, raw_bytes: bytes):
        self.buffer = BytesIO(raw_bytes)

    def fileno(self) -> int:
        raise OSError("Not a tty")


def test_cli_write_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    test_data = (
        "---\ntype: decision\nstatus: accepted\ndate: 2026-08-11\ndeciders: [test]\nlast_updated: 2026-08-11\n---\n\n# Stdin Title\nContent from stdin"
    ).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", DummyStdin(test_data))

    code = run_cli("write", ["decisions/stdin_test.md", "--content-stdin"])
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "decisions/stdin_test.md"


def test_cli_list(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("list", [])
    assert code == 0
    captured = capsys.readouterr()
    assert "INDEX.md" in captured.out
    assert "SCHEMA.md" in captured.out


def test_cli_list_nonexistent_section(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("list", ["--section", "nonexistent"])
    assert code == 0
    captured = capsys.readouterr()
    assert "No articles found in 'nonexistent'." in captured.out


def test_cli_search(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("search", ["Index"])
    assert code == 0
    captured = capsys.readouterr()
    assert "INDEX.md" in captured.out


def test_cli_ingest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sum_file = tmp_path / "summary.txt"
    sum_file.write_text("Implemented hybrid CLI interface.", encoding="utf-8")

    code = run_cli("ingest", ["--summary-file", str(sum_file)])
    assert code == 0
    captured = capsys.readouterr()
    saved_path = captured.out.strip()
    assert saved_path.startswith("_raw/sessions/session-")
    assert saved_path.endswith(".md")


def test_cli_handoff_write_and_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sum_file = tmp_path / "summary.txt"
    sum_file.write_text("Completed hybrid CLI feature.", encoding="utf-8")

    boot_file = tmp_path / "boot.txt"
    boot_file.write_text("No hay tareas pendientes por hacer.", encoding="utf-8")

    code_w = run_cli(
        "handoff-write",
        [
            "--session-type",
            "feature",
            "--summary-file",
            str(sum_file),
            "--boot-instruction-file",
            str(boot_file),
            "--completed-work",
            "CLI subcommands",
            "Tests",
        ],
    )
    assert code_w == 0
    captured_w = capsys.readouterr()
    saved_rel = captured_w.out.strip()
    assert saved_rel.startswith("handoffs/handoff-")

    code_r = run_cli("handoff-read", ["latest"])
    assert code_r == 0
    captured_r = capsys.readouterr()
    assert "=== Handoff:" in captured_r.out
    assert "Completed hybrid CLI feature." in captured_r.out
    assert "ATENCIÓN:" not in captured_r.out


def test_cli_lint(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("lint", [])
    assert code == 0
    captured = capsys.readouterr()
    assert len(captured.out) > 0


def test_cli_context(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("context", ["architecture"])
    assert code == 0
    captured = capsys.readouterr()
    assert len(captured.out) > 0


def test_cli_bootstrap(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("bootstrap", [])
    assert code == 0
    captured = capsys.readouterr()
    assert len(captured.out) > 0


def test_cli_bootstrap_wiki_not_initialized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    no_wiki = tmp_path / "no_wiki"
    no_wiki.mkdir()
    set_project_root(no_wiki)
    code = run_cli("bootstrap", [])
    assert code == 2
    captured = capsys.readouterr()
    assert "wiki not initialized" in captured.err


def test_cli_bootstrap_idempotent_warning(capsys: pytest.CaptureFixture[str]) -> None:
    code1 = run_cli("bootstrap", [])
    assert code1 == 0
    code2 = run_cli("bootstrap", [])
    assert code2 == 1
    captured = capsys.readouterr()
    assert "force=True" in captured.err or "already been run" in captured.err


def test_1mb_limit_exceeded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"A" * (1_048_576 + 10))

    code = run_cli("write", ["features/large.md", "--content-file", str(large_file)])
    assert code == 1
    captured = capsys.readouterr()
    assert "exceeds maximum allowed size of 1MB" in captured.err


def test_invalid_utf8_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_file = tmp_path / "bad.bin"
    bad_file.write_bytes(b"\x80\x81\x82")

    code = run_cli("write", ["features/bad.md", "--content-file", str(bad_file)])
    assert code == 1
    captured = capsys.readouterr()
    assert "invalid UTF-8 encoding" in captured.err


def test_map_exception_to_exit_code() -> None:
    assert map_exception_to_exit_code(KeyboardInterrupt()) == 130
    assert map_exception_to_exit_code(FileNotFoundError()) == 2
    assert map_exception_to_exit_code(ValueError()) == 1
    assert map_exception_to_exit_code(OSError()) == 3
    assert map_exception_to_exit_code(PermissionError()) == 3


def test_subprocess_smoke_init_and_read(tmp_path: Path) -> None:
    proj = tmp_path / "sub_proj"
    res_init = subprocess.run(
        [sys.executable, "-m", "brain79", "init", "--project-root", str(proj)],
        capture_output=True,
        text=True,
    )
    assert res_init.returncode == 0
    assert (proj / ".brain-79").exists()

    res_read = subprocess.run(
        [
            sys.executable,
            "-m",
            "brain79",
            "--project-root",
            str(proj),
            "read",
            "INDEX.md",
        ],
        capture_output=True,
        text=True,
    )
    assert res_read.returncode == 0
    assert "# Project index" in res_read.stdout


def test_cli_all_enforcement_flags(tmp_path: Path) -> None:
    c_file = tmp_path / "draft.md"
    c_file.write_text("# Draft\n- Decision: bypass\n", encoding="utf-8")
    code_write_skip = run_cli(
        "write",
        ["features/draft1.md", "--content-file", str(c_file), "--force-validation-skip"],
    )
    assert code_write_skip == 0

    code_write_alias = run_cli(
        "write", ["features/draft2.md", "--content-file", str(c_file), "--force-skip"]
    )
    assert code_write_alias == 0

    code_lint_suggest = run_cli("lint", ["--suggest-extract"])
    assert code_lint_suggest == 0

    code_lint_json = run_cli("lint", ["--format", "json"])
    assert code_lint_json == 0

    code_nav = run_cli("navigate", ["--regenerate"])
    assert code_nav == 0

    code_mig_dry = run_cli("migrate", ["--dry-run"])
    assert code_mig_dry == 0

    code_mig_reloc = run_cli("migrate", ["--suggest-relocations"])
    assert code_mig_reloc == 0


def test_migrate_defaults_to_dry_run(setup_cli_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """BUG-1: CLI `brain79 migrate` defaults to dry-run for MCP symmetry."""
    features_dir = setup_cli_project / ".brain-79" / "features"
    features_dir.mkdir(exist_ok=True)
    bad_file = features_dir / "no-frontmatter.md"
    bad_file.write_text("# No frontmatter\n", encoding="utf-8")

    code = run_cli("migrate", [])
    assert code == 0
    content_after = bad_file.read_text(encoding="utf-8")
    assert not content_after.startswith("---\n")
    captured = capsys.readouterr()
    assert "DRY RUN" in captured.out


def test_migrate_apply_explicit(setup_cli_project: Path) -> None:
    """BUG-1: CLI `brain79 migrate --apply` actually mutates."""
    features_dir = setup_cli_project / ".brain-79" / "features"
    features_dir.mkdir(exist_ok=True)
    bad_file = features_dir / "no-frontmatter.md"
    bad_file.write_text("# No frontmatter\n", encoding="utf-8")

    code = run_cli("migrate", ["--apply"])
    assert code == 0
    content_after = bad_file.read_text(encoding="utf-8")
    assert content_after.startswith("---\n")


def test_mcp_migrate_defaults_to_dry_run(setup_cli_project: Path) -> None:
    """BUG-1: MCP `brain79_migrate()` defaults to dry-run (safe)."""
    from brain79.server import brain79_migrate

    features_dir = setup_cli_project / ".brain-79" / "features"
    features_dir.mkdir(exist_ok=True)
    bad_file = features_dir / "no-frontmatter.md"
    bad_file.write_text("# No frontmatter\n", encoding="utf-8")

    result = brain79_migrate()
    assert "DRY RUN" in result
    content_after = bad_file.read_text(encoding="utf-8")
    assert not content_after.startswith("---\n")


def test_cli_handoff_purge_dry_run_default(
    setup_cli_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI default = dry-run."""
    handoffs_dir = setup_cli_project / ".brain-79" / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-X.md").write_text("# X", encoding="utf-8")

    code = run_cli("handoff-purge", [])
    assert code == 0
    captured = capsys.readouterr()
    assert "DRY RUN" in captured.out
    assert (handoffs_dir / "handoff-X.md").exists()


def test_cli_handoff_purge_apply(setup_cli_project: Path) -> None:
    """CLI --apply actually deletes."""
    handoffs_dir = setup_cli_project / ".brain-79" / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-X.md").write_text("# X", encoding="utf-8")

    code = run_cli("handoff-purge", ["--apply"])
    assert code == 0
    assert not (handoffs_dir / "handoff-X.md").exists()


def test_mcp_handoff_purge_default_dry_run(setup_cli_project: Path) -> None:
    """MCP brain79_handoff_purge() defaults to dry-run (safe)."""
    from brain79.server import brain79_handoff_purge

    handoffs_dir = setup_cli_project / ".brain-79" / "handoffs"
    handoffs_dir.mkdir(exist_ok=True)
    (handoffs_dir / "handoff-X.md").write_text("# X", encoding="utf-8")

    result = brain79_handoff_purge()  # no args = apply=False default
    assert "DRY RUN" in result
    assert (handoffs_dir / "handoff-X.md").exists()  # not deleted


