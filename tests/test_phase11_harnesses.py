"""Tests for Phase 11 Stage 2: Native multi-harness instruction adapters."""

from pathlib import Path

import pytest

from brain79 import __version__
from brain79.cli.dispatch import dispatch_cmd
from brain79.core.doctor import run_doctor
from brain79.core.harnesses import (
    ClaudeCodeAdapter,
    CopilotAdapter,
    CursorRulesAdapter,
    diagnose_all_harnesses,
    get_harness_adapters,
)
from brain79.core.harnesses._delimited import (
    diagnose_delimited_file,
    sync_delimited_file,
)
from brain79.core.init_project import init_project, update_project


# ==============================================================================
# R-2.1: Shared delimited block engine (_delimited.py)
# ==============================================================================


def test_sync_delimited_file_create_update_append_dry_run_and_corrupted(tmp_path: Path) -> None:
    """sync_delimited_file handles create, idempotent no-op, update, append, dry_run, and corrupted markers."""
    target = tmp_path / "SUB" / "GUIDE.md"
    block_v1 = "<!-- brain79:start v0.10.0 -->\nProtocol v1\n<!-- brain79:end -->"
    block_v2 = f"<!-- brain79:start v{__version__} -->\nProtocol v2\n<!-- brain79:end -->"

    # 1. dry_run on missing file does not write
    changed, msg = sync_delimited_file(target, block_v1, dry_run=True, version="0.10.0")
    assert changed is True
    assert not target.exists()

    # 2. Create missing file
    changed, _ = sync_delimited_file(target, block_v1, version="0.10.0")
    assert changed is True
    assert target.is_file()
    assert "Protocol v1" in target.read_text(encoding="utf-8")

    # 3. Idempotent no-op
    changed, _ = sync_delimited_file(target, block_v1, version="0.10.0")
    assert changed is False

    # 4. Update in-place preserving surrounding user text
    target.write_text(f"# Custom Header\n\n{block_v1}\n\n## Custom Footer\n", encoding="utf-8")
    changed, _ = sync_delimited_file(target, block_v2, version=__version__)
    assert changed is True
    updated = target.read_text(encoding="utf-8")
    assert updated.startswith("# Custom Header\n\n")
    assert "Protocol v2" in updated
    assert updated.endswith("\n\n## Custom Footer\n")

    # 5. Append to existing file without markers
    plain = tmp_path / "PLAIN.md"
    plain.write_text("# My Existing Rules\nKeep this.\n", encoding="utf-8")
    changed, _ = sync_delimited_file(plain, block_v2, version=__version__)
    assert changed is True
    plain_text = plain.read_text(encoding="utf-8")
    assert "# My Existing Rules\nKeep this." in plain_text
    assert "Protocol v2" in plain_text

    # 6. Corrupted delimiters raise ValueError("corrupted_harness_delimiters: ...")
    corrupt = tmp_path / "CORRUPT.md"
    corrupt.write_text("<!-- brain79:start v0.10.0 -->\nMissing end\n", encoding="utf-8")
    with pytest.raises(ValueError, match="corrupted_harness_delimiters"):
        sync_delimited_file(corrupt, block_v2, version=__version__)


def test_diagnose_delimited_file_checks_missing_stale_and_corrupted(tmp_path: Path) -> None:
    """diagnose_delimited_file detects missing (when required), unmarked, stale, and corrupted files."""
    missing = tmp_path / "MISSING.md"
    assert diagnose_delimited_file(missing, required=False) == []
    assert len(diagnose_delimited_file(missing, required=True)) == 1

    stale = tmp_path / "STALE.md"
    stale.write_text("<!-- brain79:start v0.1.0 -->\nold\n<!-- brain79:end -->\n", encoding="utf-8")
    issues = diagnose_delimited_file(stale, expected_version=__version__)
    assert any("lags behind" in i for i in issues)

    corrupt = tmp_path / "CORRUPT.md"
    corrupt.write_text("<!-- brain79:end -->\n<!-- brain79:start v0.1.0 -->\n", encoding="utf-8")
    c_issues = diagnose_delimited_file(corrupt, expected_version=__version__)
    assert any("corrupted_harness_delimiters" in i for i in c_issues)


# ==============================================================================
# R-2.2 & AC-11.4: Native adapters registered and created by init_project
# ==============================================================================


def test_native_adapters_registered_in_registry() -> None:
    """ClaudeCodeAdapter, CursorRulesAdapter, and CopilotAdapter are registered."""
    names = [a.name for a in get_harness_adapters()]
    assert "claude_code" in names
    assert "cursor_rules" in names
    assert "copilot" in names
    assert any(isinstance(a, ClaudeCodeAdapter) for a in get_harness_adapters())
    assert any(isinstance(a, CursorRulesAdapter) for a in get_harness_adapters())
    assert any(isinstance(a, CopilotAdapter) for a in get_harness_adapters())


def test_init_project_creates_all_native_instruction_harnesses(tmp_path: Path) -> None:
    """AC-11.4: brain79 init creates delimited blocks in CLAUDE.md, .cursor/rules/brain79.mdc, and .github/copilot-instructions.md."""
    init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)

    claude_md = tmp_path / "CLAUDE.md"
    cursor_mdc = tmp_path / ".cursor" / "rules" / "brain79.mdc"
    copilot_md = tmp_path / ".github" / "copilot-instructions.md"

    assert claude_md.is_file()
    assert cursor_mdc.is_file()
    assert copilot_md.is_file()

    for f in (claude_md, cursor_mdc, copilot_md):
        text = f.read_text(encoding="utf-8")
        assert f"<!-- brain79:start v{__version__} -->" in text
        assert "<!-- brain79:end -->" in text
        assert "brain79_orient" in text
        assert "brain79_session_commit" in text

    mdc_text = cursor_mdc.read_text(encoding="utf-8")
    assert mdc_text.startswith("---\n")
    assert "alwaysApply: true" in mdc_text


# ==============================================================================
# AC-11.5: Non-destructive preservation & corrupted delimiter error reporting
# ==============================================================================


def test_init_and_update_preserve_custom_user_content_in_native_harnesses(tmp_path: Path) -> None:
    """AC-11.5: Pre-existing custom content in CLAUDE.md, brain79.mdc, and copilot-instructions.md is preserved 100%."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Claude Rules\nAlways use pytest.\n", encoding="utf-8")

    cursor_mdc = tmp_path / ".cursor" / "rules" / "brain79.mdc"
    cursor_mdc.parent.mkdir(parents=True, exist_ok=True)
    cursor_mdc.write_text(
        "---\ndescription: Custom cursor rule\nalwaysApply: true\n---\n\n# Custom Cursor Notes\nKeep this.\n",
        encoding="utf-8",
    )

    copilot_md = tmp_path / ".github" / "copilot-instructions.md"
    copilot_md.parent.mkdir(parents=True, exist_ok=True)
    copilot_md.write_text("# Team Copilot Guidelines\nDo not delete.\n", encoding="utf-8")

    init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)

    assert "# My Claude Rules\nAlways use pytest." in claude_md.read_text(encoding="utf-8")
    assert "# Custom Cursor Notes\nKeep this." in cursor_mdc.read_text(encoding="utf-8")
    assert "# Team Copilot Guidelines\nDo not delete." in copilot_md.read_text(encoding="utf-8")

    # Running update_project again preserves custom content and is idempotent
    res = update_project(tmp_path)
    assert res["status"] == "ok"
    assert "# My Claude Rules\nAlways use pytest." in claude_md.read_text(encoding="utf-8")
    assert "# Custom Cursor Notes\nKeep this." in cursor_mdc.read_text(encoding="utf-8")
    assert "# Team Copilot Guidelines\nDo not delete." in copilot_md.read_text(encoding="utf-8")


def test_corrupted_native_harness_delimiters_raise_and_doctor_reports_error(tmp_path: Path) -> None:
    """AC-11.5: Corrupted delimiters raise ValueError on update and are reported as error by doctor."""
    init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("<!-- brain79:start v0.11.0 -->\nBroken block without end\n", encoding="utf-8")

    with pytest.raises(ValueError, match="corrupted_harness_delimiters"):
        update_project(tmp_path)

    diag = diagnose_all_harnesses(tmp_path)
    assert any("corrupted_harness_delimiters" in m for m in diag["claude_code"])

    report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
    assert report.status == "error"
    assert report.exit_code == 1


# ==============================================================================
# R-2.3 & AC-11.6: Selective --harnesses control and doctor --fix repair
# ==============================================================================


def test_init_selective_harnesses_cli_and_unknown_rejection(tmp_path: Path) -> None:
    """AC-11.6: brain79 init --harnesses agents,claude installs only requested adapters; unknown names error."""
    proj = tmp_path / "selective"
    proj.mkdir()
    rc = dispatch_cmd(
        "init",
        ["--project-root", str(proj), "--no-git", "--no-git-hooks", "--harnesses", "agents,claude"],
    )
    assert rc == 0
    assert (proj / "AGENTS.md").is_file()
    assert (proj / "CLAUDE.md").is_file()
    assert not (proj / ".github" / "copilot-instructions.md").exists()
    assert not (proj / ".cursor" / "rules" / "brain79.mdc").exists()
    assert not (proj / ".mcp.json").exists()

    bad_proj = tmp_path / "bad"
    bad_proj.mkdir()
    with pytest.raises(ValueError, match="Unknown harness"):
        init_project(bad_proj, auto_git_init=False, install_git_hooks_flag=False, harnesses=["nonexistent"])


def test_init_selective_cursor_does_not_leak_other_harnesses(tmp_path: Path) -> None:
    """AC-11.6: init_project(harnesses=['cursor']) only writes .cursor/mcp.json and .cursor/rules/brain79.mdc."""
    proj = tmp_path / "cursor_only"
    proj.mkdir()
    init_project(proj, auto_git_init=False, install_git_hooks_flag=False, harnesses=["cursor"])

    assert (proj / ".cursor" / "mcp.json").is_file()
    assert (proj / ".cursor" / "rules" / "brain79.mdc").is_file()
    assert not (proj / ".mcp.json").exists()
    assert not (proj / ".agents").exists()
    assert not (proj / "AGENTS.md").exists()
    assert not (proj / "CLAUDE.md").exists()
    assert not (proj / ".github" / "copilot-instructions.md").exists()


def test_doctor_diagnoses_and_fixes_stale_native_harness_blocks(tmp_path: Path) -> None:
    """AC-11.6: doctor diagnoses stale native harness blocks and doctor --fix repairs them."""
    init_project(tmp_path, auto_git_init=False, install_git_hooks_flag=False)

    # Make CLAUDE.md stale
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# User Header\n\n<!-- brain79:start v0.9.0 -->\nOld instructions\n<!-- brain79:end -->\n",
        encoding="utf-8",
    )

    pre_report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79")
    assert any("CLAUDE.md" in c.message and c.status == "warning" for c in pre_report.checks)

    fix_report = run_doctor(project_root=tmp_path, wiki_root=tmp_path / ".brain-79", fix=True, force=True)
    assert f"<!-- brain79:start v{__version__} -->" in claude_md.read_text(encoding="utf-8")
    assert "# User Header" in claude_md.read_text(encoding="utf-8")
    assert not any("CLAUDE.md" in c.message and c.status in ("warning", "error") for c in fix_report.checks)
