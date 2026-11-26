"""Phase 15 Stage 1 tests: Language-agnostic Guard C orchestrator and AST registry (AC-1, AC-2)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from brain79.core.ast_guards import (
    MAX_AST_SOURCE_BYTES,
    POLYGLOT_LANGUAGES,
    LanguageInspector,
    PythonInspector,
    SignatureDiff,
    get_ast_guard_capabilities,
    get_inspector_for_path,
    has_public_api_changes,
    has_public_python_api_changes,
    list_registered_extensions,
    register_inspector,
    unregister_extensions,
)
from brain79.core.drift import (
    MAX_AST_SOURCE_BYTES as DRIFT_MAX_AST_SOURCE_BYTES,
    WorkspaceIndex,
    has_public_api_changes as drift_has_public_api_changes,
)
from brain79.core.frontmatter import ValidationError
from brain79.core.git_ops import GitSessionCache, GitTimeoutError, NotAGitRepoError
from brain79.core.init_project import init_project
from brain79.core.session_commit import commit_session


class _CustomInspector:
    """Minimal custom LanguageInspector for '.custom' files."""

    extensions: tuple[str, ...] = (".custom",)
    language: str = "custom"

    def extract_signatures(self, source_code: str) -> dict[str, Any]:
        sigs: dict[str, Any] = {}
        for line in source_code.splitlines():
            stripped = line.strip()
            if stripped.startswith("pub "):
                # Format: "pub name(args)"
                header = stripped[4:].split("{", 1)[0].strip()
                name = header.split("(", 1)[0].strip()
                sigs[name] = header
        return sigs

    def compare_sources(
        self,
        base_source: str,
        current_source: str,
        rel_path: str,
    ) -> SignatureDiff:
        base_sigs = self.extract_signatures(base_source)
        curr_sigs = self.extract_signatures(current_source)
        added = sorted(set(curr_sigs) - set(base_sigs))
        if added:
            return SignatureDiff(True, f"added public symbol '{added[0]}' in {rel_path}")
        removed = sorted(set(base_sigs) - set(curr_sigs))
        if removed:
            return SignatureDiff(True, f"removed public symbol '{removed[0]}' in {rel_path}")
        for sym in sorted(curr_sigs):
            if base_sigs.get(sym) != curr_sigs[sym]:
                return SignatureDiff(True, f"changed public signature for '{sym}' in {rel_path}")
        return SignatureDiff(False, "")


class _NoLanguageAttrInspector:
    """Custom LanguageInspector omitting the optional .language attribute."""

    extensions: tuple[str, ...] = (".nolang",)

    def extract_signatures(self, source_code: str) -> dict[str, Any]:
        return {}

    def compare_sources(
        self,
        base_source: str,
        current_source: str,
        rel_path: str,
    ) -> SignatureDiff:
        return SignatureDiff(False, "")


@pytest.fixture
def custom_inspector() -> Any:
    """Register _CustomInspector for '.custom' and restore registry state on teardown."""
    inspector = _CustomInspector()
    register_inspector(inspector)
    try:
        yield inspector
    finally:
        unregister_extensions((".custom",))
        register_inspector(PythonInspector())


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _init_git_wiki_repo(tmp_path: Path, enforcement: str = "strict") -> tuple[Path, Path]:
    p_root = tmp_path / "repo"
    p_root.mkdir()
    _git(p_root, "init")
    _git(p_root, "config", "user.email", "test@example.com")
    _git(p_root, "config", "user.name", "Test User")

    init_project(
        p_root,
        install_git_hooks_flag=False,
        auto_git_init=False,
        install_merge_driver=False,
        enforcement=enforcement,
    )
    w_root = p_root / ".brain-79"

    src_dir = p_root / "src"
    src_dir.mkdir()
    target = src_dir / "payments.custom"
    target.write_text("pub charge(amount) {\n  return amount;\n}\n", encoding="utf-8")

    article_content = (
        "---\n"
        "type: feature\n"
        "status: shipped\n"
        "summary: Documents payment charge API\n"
        "applies_to:\n"
        "  - src/payments.custom\n"
        "---\n\n"
        "# Payments service\n\n"
        "Documents `charge(amount)`.\n\n"
        "[← Back to Index](../INDEX.md)\n"
    )
    commit_session(
        writes=[{"path": "features/payments.md", "content": article_content}],
        wiki_root=w_root,
    )

    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "initial commit")
    return p_root, w_root


# ---------------------------------------------------------------------------
# AC-1: Language-agnostic Guard C orchestrator, size guard, and registry
# ---------------------------------------------------------------------------


def test_unregistered_extension_zero_disk_and_git_calls(tmp_path: Path) -> None:
    """R-1.1(1): Unregistered extensions return (False, '') with zero disk reads or Git calls."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "readme.txt").write_bytes(b"\xff\xfe\x00\x00invalid utf-8")

    with (
        patch.object(Path, "read_text", side_effect=AssertionError("unexpected disk read")),
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path") as mock_log,
        patch("brain79.core.ast_guards.orchestrator.git_rev_parse_head") as mock_head,
        patch("brain79.core.ast_guards.orchestrator.git_show_blob") as mock_show,
    ):
        changed, desc = has_public_api_changes(
            tmp_path, "notes/readme.txt", "features/readme.md"
        )
        assert changed is False
        assert desc == ""
        mock_log.assert_not_called()
        mock_head.assert_not_called()
        mock_show.assert_not_called()


def test_custom_inspector_routing_and_unregister_normalization(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.1 / R-1.4: Custom inspector routes via has_public_api_changes and unregisters cleanly."""
    assert drift_has_public_api_changes is has_public_api_changes
    assert DRIFT_MAX_AST_SOURCE_BYTES == MAX_AST_SOURCE_BYTES == 2_097_152
    assert isinstance(custom_inspector, LanguageInspector)
    assert get_inspector_for_path("src/mod.CUSTOM") is custom_inspector

    target = tmp_path / "mod.custom"
    target.write_text("pub alpha(x) {\n  return x + 1;\n}\n", encoding="utf-8")

    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value="abc123"),
        patch(
            "brain79.core.ast_guards.orchestrator.git_show_blob",
            return_value="pub alpha(x) {\n  return x;\n}\n",
        ),
    ):
        changed, desc = has_public_api_changes(tmp_path, "mod.custom", "features/mod.md")
        assert changed is False
        assert desc == ""

    target.write_text("pub alpha(x, y) {\n  return x + y;\n}\n", encoding="utf-8")
    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value="abc123"),
        patch(
            "brain79.core.ast_guards.orchestrator.git_show_blob",
            return_value="pub alpha(x) {\n  return x;\n}\n",
        ),
    ):
        changed, desc = has_public_api_changes(tmp_path, "mod.custom", "features/mod.md")
        assert changed is True
        assert "alpha" in desc

    # Added and removed symbols on .custom
    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value="abc123"),
        patch(
            "brain79.core.ast_guards.orchestrator.git_show_blob",
            return_value="pub alpha(x) {\n  return x;\n}\n",
        ),
    ):
        changed_add, desc_add = has_public_api_changes(
            tmp_path,
            "mod.custom",
            "features/mod.md",
            current_content="pub alpha(x) {\n  return x;\n}\npub beta() {}\n",
        )
        assert changed_add is True
        assert "added public symbol 'beta'" in desc_add

        changed_rem, desc_rem = has_public_api_changes(
            tmp_path,
            "mod.custom",
            "features/mod.md",
            current_content="// empty\n",
        )
        assert changed_rem is True
        assert "removed public symbol 'alpha'" in desc_rem

    # Direct .py routing + >2 MB .py size guard through orchestrator
    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value="abc123"),
        patch("brain79.core.ast_guards.orchestrator.git_show_blob", return_value="def foo() -> int:\n    return 1\n"),
    ):
        py_changed, py_desc = has_public_api_changes(
            tmp_path,
            "mod.py",
            "features/mod.md",
            current_content="def foo(x: int) -> int:\n    return x\n",
        )
        assert py_changed is True
        assert "def foo" in py_desc

    assert has_public_api_changes(
        tmp_path,
        "big.py",
        "features/big.md",
        current_content="x = 1\n" + (" " * MAX_AST_SOURCE_BYTES),
    ) == (False, "")

    # unregister_extensions normalizes missing leading dot and uppercase
    unregister_extensions(["CUSTOM"])
    assert get_inspector_for_path("src/mod.custom") is None
    assert ".custom" not in list_registered_extensions()


def test_has_public_api_changes_rejects_symlink_and_traversal(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.1(2): Both escaping symlinks and '..' traversals raise path_outside_project_root."""
    outside = tmp_path / "outside.custom"
    outside.write_text("pub secret() {}\n", encoding="utf-8")
    p_root = tmp_path / "repo"
    p_root.mkdir()
    (p_root / "link.custom").symlink_to(outside)

    with pytest.raises(ValidationError) as exc_sym:
        has_public_api_changes(p_root, "link.custom", "features/link.md")
    assert exc_sym.value.rule == "path_outside_project_root"

    with pytest.raises(ValidationError) as exc_dot:
        has_public_api_changes(p_root, "../outside.custom", "features/link.md")
    assert exc_dot.value.rule == "path_outside_project_root"


def test_has_public_api_changes_missing_and_unreadable_file(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.1(3): Missing file returns (False, ''); invalid UTF-8 raises ast_verification_failed."""
    changed, desc = has_public_api_changes(tmp_path, "missing.custom", "features/m.md")
    assert changed is False
    assert desc == ""

    bad = tmp_path / "bad.custom"
    bad.write_bytes(b"\xff\xfe\x00\x00invalid")
    with pytest.raises(ValidationError) as exc_info:
        has_public_api_changes(tmp_path, "bad.custom", "features/bad.md")
    assert exc_info.value.rule == "ast_verification_failed"


def test_has_public_api_changes_size_guard_both_directions(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.1(4, 6): >2 MB on either current or base returns (False, '') without false blocks."""
    oversized = "x" * (MAX_AST_SOURCE_BYTES + 1)
    under_limit = "pub ok() {}\n" + (" " * 1_900_000)

    # Direction 1: current > 2 MB -> returns (False, "") BEFORE any Git call
    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path") as mock_log,
        patch("brain79.core.ast_guards.orchestrator.git_show_blob") as mock_show,
    ):
        changed, desc = has_public_api_changes(
            tmp_path, "big.custom", "features/big.md", current_content=oversized
        )
        assert changed is False
        assert desc == ""
        mock_log.assert_not_called()
        mock_show.assert_not_called()

    # Direction 2: base > 2 MB vs current < 2 MB -> returns (False, "") without inspector diff
    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value="abc123"),
        patch("brain79.core.ast_guards.orchestrator.git_show_blob", return_value=oversized),
        patch.object(custom_inspector, "compare_sources") as mock_cmp,
    ):
        changed2, desc2 = has_public_api_changes(
            tmp_path, "big.custom", "features/big.md", current_content=under_limit
        )
        assert changed2 is False
        assert desc2 == ""
        mock_cmp.assert_not_called()


def test_has_public_api_changes_non_git_and_empty_base_rev(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.1(5): Non-Git workspace and empty base_rev degrade cleanly to (False, '')."""
    with patch(
        "brain79.core.ast_guards.orchestrator.git_last_commit_for_path",
        side_effect=NotAGitRepoError("not a git repo"),
    ):
        assert has_public_api_changes(
            tmp_path, "mod.custom", "features/mod.md", current_content="pub a() {}"
        ) == (False, "")

    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value=""),
        patch("brain79.core.ast_guards.orchestrator.git_rev_parse_head", return_value=""),
    ):
        assert has_public_api_changes(
            tmp_path, "mod.custom", "features/mod.md", current_content="pub a() {}"
        ) == (False, "")


def test_has_public_api_changes_git_timeout_and_inspector_crash(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.1(5, 9): GitTimeoutError and unexpected inspector exceptions fail closed."""
    with patch(
        "brain79.core.ast_guards.orchestrator.git_last_commit_for_path",
        side_effect=GitTimeoutError("timed out"),
    ):
        with pytest.raises(ValidationError) as exc_git:
            has_public_api_changes(
                tmp_path, "mod.custom", "features/mod.md", current_content="pub a() {}"
            )
        assert exc_git.value.rule == "ast_verification_failed"

    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value="abc123"),
        patch("brain79.core.ast_guards.orchestrator.git_show_blob", return_value="pub a() {}"),
        patch.object(custom_inspector, "compare_sources", side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(ValidationError) as exc_crash:
            has_public_api_changes(
                tmp_path, "mod.custom", "features/mod.md", current_content="pub b() {}"
            )
        assert exc_crash.value.rule == "ast_verification_failed"


def test_has_public_api_changes_new_file_base_content_none(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.1(7): base_content=None reports sorted first public symbol or (False, '') if none."""
    with (
        patch("brain79.core.ast_guards.orchestrator.git_last_commit_for_path", return_value="abc123"),
        patch("brain79.core.ast_guards.orchestrator.git_show_blob", return_value=None),
    ):
        changed, desc = has_public_api_changes(
            tmp_path,
            "new.custom",
            "features/new.md",
            current_content="pub zeta() {}\npub alpha() {}\n",
        )
        assert changed is True
        assert desc == "new public symbol 'alpha' in new.custom"

        changed_empty, desc_empty = has_public_api_changes(
            tmp_path,
            "empty.custom",
            "features/empty.md",
            current_content="// private only\n",
        )
        assert changed_empty is False
        assert desc_empty == ""


def test_has_public_python_api_changes_backward_compatibility(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """R-1.2: Frozen Python Guard C ignores .custom and PythonInspector sorts changed keys."""
    assert PythonInspector.language == "python"
    assert has_public_python_api_changes(tmp_path, "mod.custom", "features/mod.md") == (False, "")

    py_insp = PythonInspector()
    diff = py_insp.compare_sources(
        "def zeta(a: int) -> int:\n    return a\n\ndef alpha(a: int) -> int:\n    return a\n",
        "def zeta(a: int) -> str:\n    return ''\n\ndef alpha(a: int) -> str:\n    return ''\n",
        "mod.py",
    )
    assert diff.has_changes is True
    assert diff.description == "changed public signature for 'def alpha' in mod.py"


def test_polyglot_languages_and_capabilities_determinism() -> None:
    """R-1.4: POLYGLOT_LANGUAGES and get_ast_guard_capabilities() return deterministic Stage 1 state."""
    assert POLYGLOT_LANGUAGES == (
        "bash",
        "c_sharp",
        "go",
        "java",
        "javascript",
        "php",
        "ruby",
        "rust",
        "tsx",
        "typescript",
    )
    assert len(POLYGLOT_LANGUAGES) == 10
    assert list(POLYGLOT_LANGUAGES) == sorted(POLYGLOT_LANGUAGES)

    caps = get_ast_guard_capabilities()
    expected_keys = {
        "built_in",
        "polyglot_runtime_available",
        "polyglot_installed",
        "active_languages",
        "missing_grammars",
        "broken_grammars",
        "registered_extensions",
    }
    assert set(caps.keys()) == expected_keys
    assert caps["built_in"] == ["python"]
    assert isinstance(caps["polyglot_installed"], bool)
    expected_poly = bool(
        caps["polyglot_runtime_available"]
        and (set(POLYGLOT_LANGUAGES) & set(caps["active_languages"]))
    )
    assert caps["polyglot_installed"] is expected_poly
    assert "python" in caps["active_languages"]
    assert ".py" in caps["registered_extensions"]

    no_lang = _NoLanguageAttrInspector()
    register_inspector(no_lang)
    try:
        caps_with_custom = get_ast_guard_capabilities()
        assert "_nolanguageattrinspector" in caps_with_custom["active_languages"]
        assert ".nolang" in caps_with_custom["registered_extensions"]
    finally:
        unregister_extensions((".nolang",))
        register_inspector(PythonInspector())


# ---------------------------------------------------------------------------
# AC-2: session_commit Guard C enforcement and GitSessionCache reuse
# ---------------------------------------------------------------------------


def test_session_commit_guard_c_git_cache_populated_and_reused(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """AC-2 / R-1.3(1): GitSessionCache is populated and reused across multiple Guard C targets."""
    p_root = tmp_path / "repo"
    p_root.mkdir()
    _git(p_root, "init")
    _git(p_root, "config", "user.email", "test@example.com")
    _git(p_root, "config", "user.name", "Test User")
    init_project(
        p_root,
        install_git_hooks_flag=False,
        auto_git_init=False,
        install_merge_driver=False,
        enforcement="strict",
    )
    w_root = p_root / ".brain-79"
    src_dir = p_root / "src"
    src_dir.mkdir()
    t1 = src_dir / "payments.custom"
    t2 = src_dir / "refunds.custom"
    t1.write_text("pub charge(amount) {\n  return amount;\n}\n", encoding="utf-8")
    t2.write_text("pub refund(tx_id) {\n  return tx_id;\n}\n", encoding="utf-8")

    article_content = (
        "---\n"
        "type: feature\n"
        "status: shipped\n"
        "summary: Documents payments and refunds API\n"
        "applies_to:\n"
        "  - src/*.custom\n"
        "---\n\n"
        "# Payments service\n\n"
        "Documents `charge(amount)` and `refund(tx_id)`.\n\n"
        "[← Back to Index](../INDEX.md)\n"
    )
    commit_session(
        writes=[{"path": "features/payments.md", "content": article_content}],
        wiki_root=w_root,
    )
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "initial commit")

    # Modify internal bodies of BOTH governed .custom files
    t1.write_text("pub charge(amount) {\n  return amount + 1;\n}\n", encoding="utf-8")
    t2.write_text("pub refund(tx_id) {\n  return tx_id + 1;\n}\n", encoding="utf-8")

    captured_caches: list[GitSessionCache] = []
    orig_build = WorkspaceIndex.build

    def _spy_build(*args: Any, **kwargs: Any) -> WorkspaceIndex:
        ws = orig_build(*args, **kwargs)
        assert isinstance(ws.git_cache, GitSessionCache)
        captured_caches.append(ws.git_cache)
        return ws

    from brain79.core import git_ops as git_ops_mod

    log_calls_for_article = 0
    orig_run_git = git_ops_mod.run_git

    def _counting_run_git(args: Any, cwd: Path, **kwargs: Any) -> Any:
        nonlocal log_calls_for_article
        args_list = list(args)
        if args_list[:2] == ["log", "-1"] and any("payments.md" in str(a) for a in args_list):
            log_calls_for_article += 1
        return orig_run_git(args, cwd, **kwargs)

    with (
        patch.object(WorkspaceIndex, "build", side_effect=_spy_build),
        patch.object(git_ops_mod, "run_git", side_effect=_counting_run_git),
    ):
        res = commit_session(
            verified_articles=[
                {
                    "path": "features/payments.md",
                    "reason": "Verified internal body edits only across both custom files.",
                }
            ],
            wiki_root=w_root,
        )

    assert res["success"] is True
    assert len(captured_caches) == 1
    cache = captured_caches[0]
    assert len(cache.last_commit_by_key) >= 1
    assert len(cache.blob_by_key) >= 2
    assert log_calls_for_article == 1


def test_session_commit_guard_c_non_python_tiers_and_git_cache(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """AC-2: session_commit reuses GitSessionCache and enforces strict/balanced/advisory for non-.py."""
    p_root, w_root = _init_git_wiki_repo(tmp_path, enforcement="strict")
    target = p_root / "src" / "payments.custom"

    # 1. Body-only edit under strict -> passes cleanly and populates WorkspaceIndex.git_cache
    target.write_text("pub charge(amount) {\n  return amount * 2;\n}\n", encoding="utf-8")
    captured_caches: list[Any] = []
    orig_build = WorkspaceIndex.build

    def _spy_build(*args: Any, **kwargs: Any) -> WorkspaceIndex:
        ws = orig_build(*args, **kwargs)
        captured_caches.append(ws.git_cache)
        return ws

    with patch.object(WorkspaceIndex, "build", side_effect=_spy_build):
        res_body = commit_session(
            verified_articles=[
                {
                    "path": "features/payments.md",
                    "reason": "Verified internal body edit only, public API unchanged.",
                }
            ],
            wiki_root=w_root,
        )
    assert res_body["success"] is True
    assert len(captured_caches) == 1
    assert isinstance(captured_caches[0], GitSessionCache)

    # 2. Public signature change under strict -> raises verified_article_public_signature_changed
    target.write_text("pub charge(amount, currency) {\n  return amount;\n}\n", encoding="utf-8")
    with pytest.raises(ValidationError) as exc_strict:
        commit_session(
            verified_articles=[
                {
                    "path": "features/payments.md",
                    "reason": "Verified signature change under strict tier test.",
                }
            ],
            wiki_root=w_root,
        )
    assert exc_strict.value.rule == "verified_article_public_signature_changed"

    # 3. Under balanced and advisory -> succeeds with downgraded warning
    for tier in ("balanced", "advisory"):
        target.write_text(
            f"pub charge(amount, currency, {tier}_flag) {{\n  return amount;\n}}\n",
            encoding="utf-8",
        )
        schema_path = w_root / "SCHEMA.md"
        lines = [
            f"enforcement: {tier}" if ln.startswith("enforcement:") else ln
            for ln in schema_path.read_text(encoding="utf-8").splitlines()
        ]
        schema_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        res_tier = commit_session(
            verified_articles=[
                {
                    "path": "features/payments.md",
                    "reason": f"Verified signature change under {tier} tier test.",
                }
            ],
            wiki_root=w_root,
        )
        assert res_tier["success"] is True
        warnings = res_tier.get("warnings", [])
        assert any("verified_article_public_signature_changed" in w for w in warnings)


def test_session_commit_guard_c_fail_closed_tiers(
    tmp_path: Path, custom_inspector: _CustomInspector
) -> None:
    """AC-2 / R-1.3(3): ast_verification_failed raises under strict/balanced, warns under advisory."""
    p_root, w_root = _init_git_wiki_repo(tmp_path, enforcement="strict")
    target = p_root / "src" / "payments.custom"
    target.write_bytes(b"\xff\xfe\x00\x00unreadable")

    for tier in ("strict", "balanced"):
        schema_path = w_root / "SCHEMA.md"
        lines = [
            f"enforcement: {tier}" if ln.startswith("enforcement:") else ln
            for ln in schema_path.read_text(encoding="utf-8").splitlines()
        ]
        schema_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(ValidationError) as exc_info:
            commit_session(
                verified_articles=[
                    {
                        "path": "features/payments.md",
                        "reason": "Verified unreadable file handling under fail-closed tier.",
                    }
                ],
                wiki_root=w_root,
            )
        assert exc_info.value.rule == "ast_verification_failed"

    schema_path = w_root / "SCHEMA.md"
    lines = [
        "enforcement: advisory" if ln.startswith("enforcement:") else ln
        for ln in schema_path.read_text(encoding="utf-8").splitlines()
    ]
    schema_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    res_adv = commit_session(
        verified_articles=[
            {
                "path": "features/payments.md",
                "reason": "Verified unreadable file handling under advisory tier.",
            }
        ],
        wiki_root=w_root,
    )
    assert res_adv["success"] is True
    assert any("ast_verification_failed" in w for w in res_adv.get("warnings", []))


# ===========================================================================
# Stage 2: Optional brain79[polyglot] Tree-sitter engine & 10 parsers (AC-3..AC-9)
# ===========================================================================

import importlib
import importlib.util
import os
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor

from brain79.core.ast_guards import TreeSitterInspector, discover_polyglot_inspectors


_REQUIRE_POLYGLOT = os.environ.get("BRAIN79_REQUIRE_POLYGLOT") == "1"


def _polyglot_available() -> bool:
    caps = get_ast_guard_capabilities()
    return bool(caps["polyglot_installed"] and not caps["missing_grammars"] and not caps["broken_grammars"])


POLYGLOT_AVAILABLE = _polyglot_available()


@pytest.fixture
def restore_polyglot_registry() -> Any:
    """Restore global AST inspector registry after tests that mutate discovery state."""
    try:
        yield
    finally:
        register_inspector(PythonInspector())
        discover_polyglot_inspectors(reset=True)


# ---------------------------------------------------------------------------
# AC-3: pyproject.toml audit, metadata-only lazy discovery, partial/broken resilience
# ---------------------------------------------------------------------------


def test_pyproject_polyglot_and_mypy_overrides_audit() -> None:
    """AC-3 / R-2.1: Core dependencies remain minimal; polyglot extra and mypy overrides match spec."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    core_deps = data["project"]["dependencies"]
    core_names = {d.split(">=")[0].split("<")[0].split("==")[0].strip() for d in core_deps}
    assert core_names == {"fastmcp", "filelock", "pyyaml"}

    polyglot_deps = data["project"]["optional-dependencies"]["polyglot"]
    assert any(d.startswith("tree-sitter>=0.25,<0.26") for d in polyglot_deps)
    expected_grammars = {
        "tree-sitter-bash",
        "tree-sitter-c-sharp",
        "tree-sitter-go",
        "tree-sitter-java",
        "tree-sitter-javascript",
        "tree-sitter-php",
        "tree-sitter-ruby",
        "tree-sitter-rust",
        "tree-sitter-typescript",
    }
    poly_names = {d.split(">=")[0].split("<")[0].split("==")[0].strip() for d in polyglot_deps}
    assert expected_grammars.issubset(poly_names)

    overrides = data["tool"]["mypy"]["overrides"]
    ts_override = next(
        (ov for ov in overrides if "tree_sitter" in ov.get("module", [])),
        None,
    )
    assert ts_override is not None
    expected_ts_modules = {
        "tree_sitter",
        "tree_sitter_bash",
        "tree_sitter_c_sharp",
        "tree_sitter_go",
        "tree_sitter_java",
        "tree_sitter_javascript",
        "tree_sitter_php",
        "tree_sitter_ruby",
        "tree_sitter_rust",
        "tree_sitter_typescript",
    }
    assert expected_ts_modules.issubset(set(ts_override["module"]))
    assert ts_override["ignore_missing_imports"] is True
    assert ts_override["follow_untyped_imports"] is False


def test_metadata_only_lazy_discovery_does_not_import_tree_sitter() -> None:
    """R-2.4: Importing brain79.core.ast_guards uses find_spec only without importing tree_sitter."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import brain79.core.ast_guards as ag; "
                "assert 'tree_sitter' not in sys.modules; "
                "assert ag.get_inspector_for_path('app.py') is not None; "
                "assert 'tree_sitter' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"


def test_absent_tree_sitter_degrades_gracefully(
    restore_polyglot_registry: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 / R-2.4(1): Absent tree_sitter leaves only Python active and all 10 in missing_grammars."""
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    discover_polyglot_inspectors(reset=True)

    caps = get_ast_guard_capabilities()
    assert caps["built_in"] == ["python"]
    assert caps["polyglot_runtime_available"] is False
    assert caps["polyglot_installed"] is False
    assert caps["active_languages"] == ["python"]
    assert caps["missing_grammars"] == sorted(POLYGLOT_LANGUAGES)
    assert caps["broken_grammars"] == {}
    assert get_inspector_for_path("main.go") is None
    assert get_inspector_for_path("app.py") is not None


def test_partial_grammar_install_reports_missing_including_tsx_and_typescript(
    restore_polyglot_registry: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 / R-2.4(2): Partial install activates available grammars; missing tree_sitter_typescript marks both tsx and typescript missing."""
    real_find_spec = importlib.util.find_spec

    def _partial_find_spec(name: str, package: str | None = None) -> Any:
        if name in ("tree_sitter", "tree_sitter_go"):
            return real_find_spec("ast")  # non-None dummy spec
        return None

    monkeypatch.setattr(importlib.util, "find_spec", _partial_find_spec)
    discover_polyglot_inspectors(reset=True)

    assert "go" in {
        getattr(get_inspector_for_path("main.go"), "language", None)
    } or not POLYGLOT_AVAILABLE
    # If tree_sitter_go is actually installed, go becomes active; otherwise validate via caps
    caps = get_ast_guard_capabilities()
    assert "typescript" in caps["missing_grammars"]
    assert "tsx" in caps["missing_grammars"]
    assert get_inspector_for_path("index.ts") is None
    assert get_inspector_for_path("App.tsx") is None


def test_broken_grammar_lazy_init_failure_isolated(
    restore_polyglot_registry: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3 / R-2.5(2): Broken grammar Language() init unregisters its extensions and surfaces in broken_grammars."""
    real_find_spec = importlib.util.find_spec
    real_import = importlib.import_module

    class _DummyTS:
        class Language:
            def __init__(self, ptr: Any) -> None:
                if ptr == "BROKEN_RUST_PTR":
                    raise RuntimeError("Incompatible Language version 15")
                self.ptr = ptr

        class Parser:
            def __init__(self, lang: Any) -> None:
                self.lang = lang

    class _BrokenRustMod:
        @staticmethod
        def language() -> str:
            return "BROKEN_RUST_PTR"

    class _HealthyGoMod:
        @staticmethod
        def language() -> str:
            return "HEALTHY_GO_PTR"

    def _fake_find_spec(name: str, package: str | None = None) -> Any:
        if name in ("tree_sitter", "tree_sitter_rust", "tree_sitter_go"):
            return real_find_spec("ast")
        return None

    def _fake_import(name: str, package: str | None = None) -> Any:
        if name == "tree_sitter":
            return _DummyTS
        if name == "tree_sitter_rust":
            return _BrokenRustMod
        if name == "tree_sitter_go":
            return _HealthyGoMod
        return real_import(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    monkeypatch.setattr(importlib, "import_module", _fake_import)
    discover_polyglot_inspectors(reset=True)

    # Healthy Go works, broken Rust unregisters .rs and returns None
    assert get_inspector_for_path("main.go") is not None
    assert get_inspector_for_path("lib.rs") is None

    caps = get_ast_guard_capabilities()
    assert "go" in caps["active_languages"]
    assert "rust" in caps["broken_grammars"]
    assert "Incompatible Language version 15" in caps["broken_grammars"]["rust"]
    assert ".rs" not in caps["registered_extensions"]


# ---------------------------------------------------------------------------
# Live Tree-sitter tests (AC-4 through AC-9)
# ---------------------------------------------------------------------------


def test_polyglot_strict_ci_gate() -> None:
    """Strict gate enforced in CI polyglot job when BRAIN79_REQUIRE_POLYGLOT=1."""
    if not _REQUIRE_POLYGLOT:
        pytest.skip("BRAIN79_REQUIRE_POLYGLOT is not set to 1")
    caps = get_ast_guard_capabilities()
    assert caps["polyglot_installed"] is True
    assert caps["missing_grammars"] == []
    assert caps["broken_grammars"] == {}
    assert set(POLYGLOT_LANGUAGES).issubset(set(caps["active_languages"]))


@pytest.mark.skipif(not POLYGLOT_AVAILABLE, reason="brain79[polyglot] not installed")
def test_treesitter_inspector_resilience_url_literals_size_syntax_and_threads() -> None:
    """AC-4 / R-2.2, R-2.6: URL literal safety, >2 MB guard, syntax-error 3-branch semantics, partial error, 8 threads."""
    ts_insp = get_inspector_for_path("api.ts")
    assert isinstance(ts_insp, TreeSitterInspector)

    # (a) URL string literal preserved while real comments/whitespace ignored
    base_ts = 'export function fetchUrl(url: string = "http://example.com/*not-a-comment*/"): string { return url; }\n'
    curr_ts = (
        "// leading comment\n"
        'export   function   fetchUrl(url: string = "http://example.com/*not-a-comment*/" /* inline */): string {\n'
        "  return url;\n"
        "}\n"
    )
    assert ts_insp.compare_sources(base_ts, curr_ts, "api.ts") == SignatureDiff(False, "")

    # (b) > 2 MB guard returns {}
    oversized = base_ts + ("// " + ("x" * 1000) + "\n") * 2200
    assert len(oversized.encode("utf-8")) > MAX_AST_SOURCE_BYTES
    assert ts_insp.extract_signatures(oversized) == {}
    assert ts_insp.compare_sources(base_ts, oversized, "api.ts") == SignatureDiff(False, "")

    # (c) Syntax-error 3-branch semantics (R-2.2(6))
    broken_src = "export function ((( {\n"
    diff_curr_bad = ts_insp.compare_sources(base_ts, broken_src, "api.ts")
    assert diff_curr_bad == SignatureDiff(True, "unparseable source in api.ts")

    diff_base_bad = ts_insp.compare_sources(broken_src, base_ts, "api.ts")
    assert diff_base_bad == SignatureDiff(True, "added public symbol 'function fetchUrl' in api.ts")

    assert ts_insp.compare_sources(broken_src, broken_src, "api.ts") == SignatureDiff(False, "")
    assert ts_insp.compare_sources("", "", "api.ts") == SignatureDiff(False, "")

    # Partial syntax error: malformed header skipped, valid sibling preserved
    partial_src = "export function validOne(a: number): void {}\nexport function ((( {\n"
    sigs_partial = ts_insp.extract_signatures(partial_src)
    assert "function validOne" in sigs_partial

    # (d) 8-thread concurrency
    expected = ts_insp.extract_signatures(base_ts)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: ts_insp.extract_signatures(base_ts), range(32)))
    assert all(r == expected for r in results)


# Parametrized 10-language matrix (AC-5..AC-8)
_LANGUAGE_MATRIX: list[tuple[str, str, str, str, str, str, str, str]] = [
    (
        "typescript",
        "mod.ts",
        "export function greet(name: string): string { return name; }\nfunction _priv(): void {}\n",
        "export function greet(name: string): string { return name; }\nexport function extra(): void {}\nfunction _priv(): void {}\n",
        "function _priv(): void {}\n",
        "export function greet(name: string, loud: boolean): string { return name; }\nfunction _priv(): void {}\n",
        'export function greet(name: string): string { const u = "http://example.com"; return u + name; }\nfunction _priv(): void {}\n',
        "// comment\nexport  function  greet(name: string): string { return name; }\nfunction _priv(x: number): void {}\n",
    ),
    (
        "tsx",
        "Comp.tsx",
        "export function Button(label: string): any { return <button>{label}</button>; }\nfunction helper() {}\n",
        "export function Button(label: string): any { return <button>{label}</button>; }\nexport const VERSION: number = 1;\n",
        "function helper() {}\n",
        "export function Button(label: string, disabled: boolean): any { return <button>{label}</button>; }\n",
        'export function Button(label: string): any { const u = "http://example.com"; return <span>{u}{label}</span>; }\n',
        "/* c */\nexport function Button(label: string): any { return <button>{label}</button>; }\nfunction helper(a: number) { return a; }\n",
    ),
    (
        "javascript",
        "mod.js",
        "export function greet(name) { return name; }\nfunction priv() {}\n",
        "export function greet(name) { return name; }\nexport function extra() {}\n",
        "function priv() {}\n",
        "export function greet(name, loud) { return name; }\n",
        'export function greet(name) { const u = "http://example.com"; return u + name; }\n',
        "// c\nexport function greet(name) { return name; }\nfunction priv(x) { return x; }\n",
    ),
    (
        "go",
        "mod.go",
        "package p\nfunc Greet(name string) string { return name }\nfunc priv() {}\n",
        "package p\nfunc Greet(name string) string { return name }\nfunc Extra() {}\nfunc priv() {}\n",
        "package p\nfunc priv() {}\n",
        "package p\nfunc Greet(name string, loud bool) string { return name }\nfunc priv() {}\n",
        'package p\nfunc Greet(name string) string { u := "http://example.com"; return u + name }\nfunc priv() {}\n',
        "// c\npackage p\nfunc Greet(name string) string { return name }\nfunc priv(x int) int { return x }\n",
    ),
    (
        "rust",
        "lib.rs",
        "pub fn greet(name: &str) -> usize { name.len() }\nfn priv_fn() {}\n",
        "pub fn greet(name: &str) -> usize { name.len() }\npub fn extra() {}\nfn priv_fn() {}\n",
        "fn priv_fn() {}\n",
        "pub fn greet(name: &str, loud: bool) -> usize { name.len() }\nfn priv_fn() {}\n",
        'pub fn greet(name: &str) -> usize { let _u = "http://example.com"; name.len() }\nfn priv_fn() {}\n',
        "// c\npub fn greet(name: &str) -> usize { name.len() }\npub(crate) fn crate_fn() {}\n",
    ),
    (
        "java",
        "Mod.java",
        "public class Mod { public int greet(String s) { return 1; } private void priv() {} }\n",
        "public class Mod { public int greet(String s) { return 1; } public void extra() {} private void priv() {} }\n",
        "public class Mod { private void priv() {} }\n",
        "public class Mod { public String greet(String s) { return s; } private void priv() {} }\n",
        'public class Mod { public int greet(String s) { String u = "http://example.com"; return u.length(); } private void priv() {} }\n',
        "// c\npublic class Mod { public int greet(String s) { return 1; } private void priv(int x) {} }\n",
    ),
    (
        "c_sharp",
        "Mod.cs",
        "namespace App;\npublic class Mod { public int Greet(string s) { return 1; } private void Priv() {} }\n",
        "namespace App;\npublic class Mod { public int Greet(string s) { return 1; } public void Extra() {} private void Priv() {} }\n",
        "namespace App;\npublic class Mod { private void Priv() {} }\n",
        "namespace App;\npublic class Mod { public string Greet(string s) { return s; } private void Priv() {} }\n",
        'namespace App;\npublic class Mod { public int Greet(string s) { var u = "http://example.com"; return u.Length; } private void Priv() {} }\n',
        "// c\nnamespace App;\npublic class Mod { public int Greet(string s) { return 1; } internal void IntFn() {} }\n",
    ),
    (
        "php",
        "mod.php",
        "<?php\nclass Mod { public function greet(string $s): int { return 1; } private function priv(): void {} }\n",
        "<?php\nclass Mod { public function greet(string $s): int { return 1; } public function extra(): void {} }\n",
        "<?php\nclass Mod { private function priv(): void {} }\n",
        "<?php\nclass Mod { public function greet(string $s, bool $loud): int { return 1; } }\n",
        '<?php\nclass Mod { public function greet(string $s): int { $u = "http://example.com"; return strlen($u); } private function priv(): void {} }\n',
        "<?php\n// c\nclass Mod { public function greet(string $s): int { return 1; } protected function prot(): void {} }\n",
    ),
    (
        "ruby",
        "mod.rb",
        "class Mod\n  def greet(name)\n    name\n  end\n  private\n  def priv\n  end\nend\n",
        "class Mod\n  def greet(name)\n    name\n  end\n  def extra\n  end\n  private\n  def priv\n  end\nend\n",
        "class Mod\n  private\n  def priv\n  end\nend\n",
        "class Mod\n  def greet(name, loud = false)\n    name\n  end\n  private\n  def priv\n  end\nend\n",
        "class Mod\n  def greet(name)\n    u = \"http://example.com\"\n    u + name\n  end\n  private\n  def priv\n  end\nend\n",
        "# c\nclass Mod\n  def greet(name)\n    name\n  end\n  private\n  def priv(x)\n    x\n  end\nend\n",
    ),
    (
        "bash",
        "mod.sh",
        "greet() { echo \"$1\"; }\n_priv() { echo no; }\n",
        "greet() { echo \"$1\"; }\nextra() { echo ok; }\n_priv() { echo no; }\n",
        "_priv() { echo no; }\n",
        "greet_v2() { echo \"$1\"; }\n_priv() { echo no; }\n",
        "greet() { local u=\"http://example.com\"; echo \"$u\"; }\n_priv() { echo no; }\n",
        "# comment\ngreet() { echo \"$1\"; }\n_priv() { echo changed; }\nLOCAL_ONLY=1\n",
    ),
]


@pytest.mark.skipif(not POLYGLOT_AVAILABLE, reason="brain79[polyglot] not installed")
@pytest.mark.parametrize(
    ("lang", "filename", "base", "added", "removed", "changed", "body_edit", "comment_priv_edit"),
    _LANGUAGE_MATRIX,
    ids=[row[0] for row in _LANGUAGE_MATRIX],
)
def test_polyglot_10_language_matrix(
    lang: str,
    filename: str,
    base: str,
    added: str,
    removed: str,
    changed: str,
    body_edit: str,
    comment_priv_edit: str,
) -> None:
    """AC-5..AC-8: 6-scenario matrix across all 10 POLYGLOT_LANGUAGES."""
    insp = get_inspector_for_path(filename)
    assert insp is not None
    assert getattr(insp, "language", None) == lang

    assert insp.compare_sources(base, added, filename).has_changes is True
    assert insp.compare_sources(base, removed, filename).has_changes is True
    assert insp.compare_sources(base, changed, filename).has_changes is True
    assert insp.compare_sources(base, body_edit, filename) == SignatureDiff(False, "")
    assert insp.compare_sources(base, comment_priv_edit, filename) == SignatureDiff(False, "")


@pytest.mark.skipif(not POLYGLOT_AVAILABLE, reason="brain79[polyglot] not installed")
def test_polyglot_language_specific_edge_cases() -> None:
    """AC-5..AC-8: Re-exports, CommonJS, Go receivers, Rust visibility/impl, Java/C# overloads, PHP/Ruby/Bash specifics."""
    # TS re-exports, namespace, export =
    ts = get_inspector_for_path("index.ts")
    assert ts is not None
    ts_base = "export { a, b as c } from './m';\nexport * as ns from './m';\nexport namespace N { export function f(): void {} }\n"
    ts_chg = "export { a, b as d } from './m';\nexport * as ns from './m';\nexport namespace N { export function f(): void {} }\n"
    assert ts.compare_sources(ts_base, ts_chg, "index.ts").has_changes is True

    # JS CommonJS
    js = get_inspector_for_path("cjs.cjs")
    assert js is not None
    js_base = "exports.foo = function(a) { return a; };\nmodule.exports.bar = 1;\n"
    js_sig = "exports.foo = function(a, b) { return a; };\nmodule.exports.bar = 1;\n"
    assert js.compare_sources(js_base, js_sig, "cjs.cjs").has_changes is True

    # Go same-named methods on distinct receivers
    go = get_inspector_for_path("recv.go")
    assert go is not None
    go_base = "package p\ntype A struct{}\ntype B struct{}\nfunc (a *A) Run() {}\nfunc (b *B) Run() {}\n"
    go_rem = "package p\ntype A struct{}\ntype B struct{}\nfunc (a *A) Run() {}\n"
    assert go.compare_sources(go_base, go_rem, "recv.go").has_changes is True

    # Rust pub(crate), private mod, trait impl
    rs = get_inspector_for_path("lib.rs")
    assert rs is not None
    rs_base = "pub struct S;\npub trait T { fn m(&self); }\nimpl S { pub fn a(&self) {} }\nimpl T for S { fn m(&self) {} }\nmod priv_mod { pub fn hidden() {} }\n"
    rs_priv_edit = "pub struct S;\npub trait T { fn m(&self); }\nimpl S { pub fn a(&self) {} }\nimpl T for S { fn m(&self) {} }\nmod priv_mod { pub fn hidden(x: i32) {} }\npub(crate) fn c() {}\n"
    assert rs.compare_sources(rs_base, rs_priv_edit, "lib.rs") == SignatureDiff(False, "")

    # Java & C# overloads + nested types
    java = get_inspector_for_path("Over.java")
    assert java is not None
    j_base = "public class Over { public static class Inner { public void m(String a) {} } }\n"
    j_add_overload = "public class Over { public static class Inner { public void m(String a) {} public void m(int a) {} } }\n"
    assert java.compare_sources(j_base, j_add_overload, "Over.java").has_changes is True

    cs = get_inspector_for_path("Over.cs")
    assert cs is not None
    cs_base = "namespace N;\npublic class Over { public int Prop { get; set; } public void M(string a) {} }\n"
    cs_overload = "namespace N;\npublic class Over { public int Prop { get; set; } public void M(string a) {} public void M(int a) {} }\n"
    assert cs.compare_sources(cs_base, cs_overload, "Over.cs").has_changes is True

    # PHP implicit public
    php = get_inspector_for_path("svc.php")
    assert php is not None
    php_base = "<?php\nclass Svc { function run($a) {} }\n"
    php_chg = "<?php\nclass Svc { function run($a, $b) {} }\n"
    assert php.compare_sources(php_base, php_chg, "svc.php").has_changes is True

    # Ruby attr_accessor, class << self, private :sym, module_function
    rb = get_inspector_for_path("svc.rb")
    assert rb is not None
    rb_base = "class Svc\n  attr_accessor :token\n  def self.build; end\n  class << self\n    def eigen; end\n  end\n  def hidden; end\n  private :hidden\nend\n"
    rb_priv_chg = "class Svc\n  attr_accessor :token\n  def self.build; end\n  class << self\n    def eigen; end\n  end\n  def hidden(x); end\n  private :hidden\nend\n"
    assert rb.compare_sources(rb_base, rb_priv_chg, "svc.rb") == SignatureDiff(False, "")
    rb_attr_chg = rb_base.replace("attr_accessor :token", "attr_accessor :token, :secret")
    assert rb.compare_sources(rb_base, rb_attr_chg, "svc.rb").has_changes is True

    # Bash export -f & value-change immunity
    sh = get_inspector_for_path("env.sh")
    assert sh is not None
    sh_base = "export API_PORT=8080\ndeclare -x MODE=prod\nhelper_fn() { :; }\nexport -f helper_fn\n"
    sh_val_chg = "export API_PORT=9090\ndeclare -x MODE=dev\nhelper_fn() { echo hi; }\nexport -f helper_fn\n"
    assert sh.compare_sources(sh_base, sh_val_chg, "env.sh") == SignatureDiff(False, "")
    sh_var_add = sh_base + "export NEW_FLAG=1\n"
    assert sh.compare_sources(sh_base, sh_var_add, "env.sh").has_changes is True


@pytest.mark.skipif(not POLYGLOT_AVAILABLE, reason="brain79[polyglot] not installed")
@pytest.mark.parametrize(
    ("rel_path", "base_code", "sig_code", "body_code"),
    [
        (
            "src/app.ts",
            "export function run(x: number): number { return x; }\n",
            "export function run(x: number, y: number): number { return x + y; }\n",
            "export function run(x: number): number { return x * 2; }\n",
        ),
        (
            "src/app.go",
            "package main\nfunc Run(x int) int { return x }\n",
            "package main\nfunc Run(x int, y int) int { return x + y }\n",
            "package main\nfunc Run(x int) int { return x * 2 }\n",
        ),
        (
            "src/lib.rs",
            "pub fn run(x: i32) -> i32 { x }\n",
            "pub fn run(x: i32, y: i32) -> i32 { x + y }\n",
            "pub fn run(x: i32) -> i32 { x * 2 }\n",
        ),
        (
            "src/run.sh",
            "run_task() { echo 1; }\n",
            "run_task_v2() { echo 1; }\n",
            "run_task() { echo 2; }\n",
        ),
    ],
    ids=["ts", "go", "rs", "sh"],
)
def test_session_commit_polyglot_e2e_guard_c(
    tmp_path: Path,
    rel_path: str,
    base_code: str,
    sig_code: str,
    body_code: str,
) -> None:
    """AC-9: Real Git commit_session(verified_articles=...) blocks public sig changes and allows body edits."""
    p_root = tmp_path / "repo"
    p_root.mkdir()
    _git(p_root, "init")
    _git(p_root, "config", "user.email", "test@example.com")
    _git(p_root, "config", "user.name", "Test")

    init_project(p_root, profile="software", enforcement="strict")
    w_root = p_root / ".brain-79"
    target = p_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(base_code, encoding="utf-8")

    commit_session(
        writes=[
            {
                "path": "features/poly.md",
                "content": (
                    "---\n"
                    'title: "Feature — Polyglot module"\n'
                    "type: feature\n"
                    "status: shipped\n"
                    "version: 0.1.0\n"
                    'summary: "Governs polyglot source file."\n'
                    "applies_to:\n"
                    f'  - "{rel_path}"\n'
                    "---\n\n"
                    "# Feature — Polyglot module\n\n"
                    "## Overview\n\n"
                    "Governs polyglot module.\n\n"
                    "[← Back to Index](../INDEX.md)\n"
                ),
            }
        ],
        wiki_root=w_root,
    )
    _git(p_root, "add", ".")
    _git(p_root, "commit", "-m", "initial polyglot")

    # 1. Public signature change -> blocked under strict
    target.write_text(sig_code, encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        commit_session(
            verified_articles=[
                {"path": "features/poly.md", "reason": "Verified polyglot signature change."}
            ],
            wiki_root=w_root,
        )
    assert exc_info.value.rule == "verified_article_public_signature_changed"

    # 2. Revert to body-only edit -> succeeds
    target.write_text(body_code, encoding="utf-8")
    res = commit_session(
        verified_articles=[
            {"path": "features/poly.md", "reason": "Verified body-only edit."}
        ],
        wiki_root=w_root,
    )
    assert res["success"] is True


@pytest.mark.skipif(not POLYGLOT_AVAILABLE, reason="brain79[polyglot] not installed")
def test_polyglot_cycle1_regression_fixes() -> None:
    """Regression tests for Cycle 1 findings F-1 through F-7."""
    # F-1: TS declare module & non-exported members inside export namespace
    ts = get_inspector_for_path("ambient.ts")
    assert ts is not None
    assert "function pkg.f" in ts.extract_signatures(
        'declare module "pkg" { export function f(a: string): void; }\n'
    )
    ns_base = "export namespace NS { export function pub(): void {} function priv(): void {} }\n"
    ns_priv = "export namespace NS { export function pub(): void {} function priv(x: number): void {} }\n"
    assert ts.compare_sources(ns_base, ns_priv, "ambient.ts") == SignatureDiff(False, "")

    # F-2: C# private property accessor & expression-bodied property
    cs = get_inspector_for_path("Props.cs")
    assert cs is not None
    cs_prop_base = "public class C { public int Id { get; set; } public int Count => 1; }\n"
    cs_prop_priv_set = "public class C { public int Id { get; private set; } public int Count => 1; }\n"
    cs_prop_expr_body = "public class C { public int Id { get; set; } public int Count => 2; }\n"
    assert cs.compare_sources(cs_prop_base, cs_prop_priv_set, "Props.cs").has_changes is True
    assert cs.compare_sources(cs_prop_base, cs_prop_expr_body, "Props.cs") == SignatureDiff(False, "")

    # F-3: Java enum constants & enum_body_declarations methods
    java = get_inspector_for_path("Status.java")
    assert java is not None
    j_enum_base = "public enum S { OK, ERR; public int code() { return 1; } }\n"
    j_enum_chg = "public enum S { OK, ERR; public long code() { return 1L; } }\n"
    j_enum_const = "public enum S { OK, ERR, WARN; public int code() { return 1; } }\n"
    assert java.compare_sources(j_enum_base, j_enum_chg, "Status.java").has_changes is True
    assert java.compare_sources(j_enum_base, j_enum_const, "Status.java").has_changes is True

    # F-4: Ruby section-mode module_function
    rb = get_inspector_for_path("helpers.rb")
    assert rb is not None
    rb_mf_base = "module Helpers\n  module_function\n  def helper(a)\n    a\n  end\nend\n"
    rb_mf_chg = "module Helpers\n  module_function\n  def helper(a, b)\n    a\n  end\nend\n"
    assert "def Helpers.self.helper" in rb.extract_signatures(rb_mf_base)
    assert rb.compare_sources(rb_mf_base, rb_mf_chg, "helpers.rb").has_changes is True

    # F-5: Go grouped var ( ... ) blocks
    go = get_inspector_for_path("vars.go")
    assert go is not None
    go_var_base = "package p\nvar (\n  Global string\n  local int\n)\n"
    go_var_chg = "package p\nvar (\n  Global int\n  local string\n)\n"
    go_var_local_only = "package p\nvar (\n  Global string\n  local string\n)\n"
    assert go.compare_sources(go_var_base, go_var_chg, "vars.go").has_changes is True
    assert go.compare_sources(go_var_base, go_var_local_only, "vars.go") == SignatureDiff(False, "")

    # F-6: JS CommonJS module.exports = class & object method shorthand
    js = get_inspector_for_path("cjs2.js")
    assert js is not None
    js_cls_base = "module.exports = class Foo { run(a) { return a; } };\n"
    js_cls_chg = "module.exports = class Foo { run(a, b) { return a; } };\n"
    assert js.compare_sources(js_cls_base, js_cls_chg, "cjs2.js").has_changes is True

    js_obj_base = "module.exports = { foo(a) { return a; } };\n"
    js_obj_chg = "module.exports = { foo(a, b) { return a; } };\n"
    assert js.compare_sources(js_obj_base, js_obj_chg, "cjs2.js").has_changes is True

    # F-7: Bash export VAR="hello -f" value containing -f is not misclassified as export -f
    sh = get_inspector_for_path("flags.sh")
    assert sh is not None
    sh_sigs = sh.extract_signatures('export MSG="hello -f"\n')
    assert "export MSG" in sh_sigs
