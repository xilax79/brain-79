from collections.abc import Iterator
import json
from pathlib import Path
import threading
from unittest.mock import patch

import pytest

from brain79.config import get_wiki_root, set_project_root
from brain79.core.bootstrap import (
    _TOTAL_CONTENT_BUDGET_BYTES,
    _TREE_MAX_ENTRIES,
    _detect_project_type,
    _load_bootstrap_state,
    _resolve_scope_paths,
    _save_bootstrap_state,
    _truncate_file,
    run_bootstrap,
)
from brain79.core.init_project import init_project
import brain79.server as server_module


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Initialized project with empty wiki (no user files)."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)
    return project_dir


# Group A — Idempotency guard


def test_second_run_returns_warning(project: Path) -> None:
    run_bootstrap()
    result = run_bootstrap()
    assert "already been run" in result.lower()


def test_second_run_warning_contains_previous_timestamp(project: Path) -> None:
    run_bootstrap()
    state = _load_bootstrap_state(get_wiki_root())
    result = run_bootstrap()
    assert state["last_run_iso"] in result


def test_second_run_warning_contains_force_instruction(project: Path) -> None:
    run_bootstrap()
    result = run_bootstrap()
    assert "force=True" in result


def test_force_overrides_guard(project: Path) -> None:
    run_bootstrap()
    result = run_bootstrap(force=True)
    assert "already been run" not in result.lower()
    assert "Bootstrap Error" not in result


def test_state_file_created_with_schema(project: Path) -> None:
    run_bootstrap()
    state_path = get_wiki_root() / ".bootstrap_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert isinstance(state, dict)
    required_keys = {
        "last_run_iso",
        "scope",
        "project_type",
        "files_scanned",
        "bytes_consumed",
        "existing_articles_count",
    }
    assert required_keys.issubset(state.keys())
    assert "in_progress" not in state


def test_state_corrupt_json_treated_as_missing(project: Path) -> None:
    state_path = get_wiki_root() / ".bootstrap_state.json"
    state_path.write_text("{not valid json")
    result = run_bootstrap()
    assert "Bootstrap Error" not in result
    new_state = json.loads(state_path.read_text())
    assert isinstance(new_state, dict)
    assert "last_run_iso" in new_state


def test_state_not_dict_treated_as_missing(project: Path) -> None:
    state_path = get_wiki_root() / ".bootstrap_state.json"
    state_path.write_text("[]")
    result = run_bootstrap()
    assert "Bootstrap Error" not in result
    new_state = json.loads(state_path.read_text())
    assert isinstance(new_state, dict)
    assert "last_run_iso" in new_state


# Group B — Empty / minimal project


def test_empty_project_no_error(project: Path) -> None:
    result = run_bootstrap()
    assert "Bootstrap Error" not in result


def test_empty_project_manifest_has_instructions(project: Path) -> None:
    result = run_bootstrap()
    assert "Bootstrap Instructions" in result


def test_empty_project_type_unknown(project: Path) -> None:
    result = run_bootstrap()
    assert "Project type: unknown" in result


# Group C — Project type detection


@pytest.mark.parametrize(
    "filename,expected_type",
    [
        ("pyproject.toml", "python-package"),
        ("setup.py", "python-package"),
        ("package.json", "node-package"),
        ("Cargo.toml", "rust-crate"),
        ("go.mod", "go-module"),
        ("pom.xml", "java-maven"),
        ("build.gradle", "java-gradle"),
        ("Gemfile", "ruby-gem"),
    ],
)
def test_detect_project_type_via_file(
    project: Path, filename: str, expected_type: str
) -> None:
    (project / filename).write_text("# signal")
    result = run_bootstrap()
    assert f"Project type: {expected_type}" in result


def test_detect_docker_service(project: Path) -> None:
    (project / "Dockerfile").write_text("FROM python:3.12")
    result = run_bootstrap()
    assert "Project type: docker-service" in result


def test_detect_research_paper(project: Path) -> None:
    (project / "paper.tex").write_text("\\documentclass{article}")
    result = run_bootstrap()
    assert "Project type: research-paper" in result


def test_detect_documentation(project: Path) -> None:
    (project / "mkdocs.yml").write_text("site_name: Docs")
    result = run_bootstrap()
    assert "Project type: documentation" in result


def test_detect_unknown(project: Path) -> None:
    result = run_bootstrap()
    assert "Project type: unknown" in result


def test_detect_project_type_function_returns_valid_enum() -> None:
    valid = {
        "python-package",
        "python-script",
        "node-package",
        "rust-crate",
        "go-module",
        "java-maven",
        "java-gradle",
        "ruby-gem",
        "docker-service",
        "research-paper",
        "documentation",
        "unknown",
    }
    assert _detect_project_type({}, []) in valid
    assert _detect_project_type({"pyproject.toml": ""}, []) in valid


# Group D — Scope handling


def test_scope_none_produces_auto_label(project: Path) -> None:
    result = run_bootstrap(scope=None)
    assert "Scope: auto" in result


def test_scope_dot_treated_as_auto(project: Path) -> None:
    result_none = run_bootstrap(scope=None)
    result_dot = run_bootstrap(scope=".", force=True)
    for section in (
        "Bootstrap Instructions",
        "Project Structure",
        "Project type:",
    ):
        assert section in result_none
        assert section in result_dot


def test_scope_empty_string_treated_as_auto(project: Path) -> None:
    result = run_bootstrap(scope="")
    assert "Scope: auto" in result


def test_scope_valid_path_included(project: Path) -> None:
    auth_dir = project / "src" / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "login.py").write_text("def login(): pass")
    (auth_dir / "logout.py").write_text("def logout(): pass")
    result = run_bootstrap(scope="src/auth")
    assert "Scope Analysis" in result
    assert "src/auth" in result


def test_scope_nonexistent_path_warning(project: Path) -> None:
    result = run_bootstrap(scope="nonexistent/path")
    assert "Warnings" in result


def test_scope_outside_project_root_silently_dropped(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    init_project(project_dir)

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("SECRET CONTENT")

    result = run_bootstrap(scope="../outside")

    assert "SECRET CONTENT" not in result
    if "## Scope Analysis" in result:
        scope_section = result.split("## Scope Analysis")[1].split("---")[0]
        assert "outside" not in scope_section
        assert "secret" not in scope_section.lower()
    if "## Warnings" in result:
        warnings_section = result.split("## Warnings")[-1]
        assert "outside" not in warnings_section


def test_scope_multiple_paths(project: Path) -> None:
    for name in ("auth", "payments"):
        d = project / "src" / name
        d.mkdir(parents=True)
        (d / "main.py").write_text(f"# {name}")
    result = run_bootstrap(scope="src/auth,src/payments")
    assert "src/auth" in result
    assert "src/payments" in result


def test_scope_with_spaces_parsed_correctly(project: Path) -> None:
    auth_dir = project / "src" / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "main.py").write_text("# auth")
    result = run_bootstrap(scope=" src/auth ")
    assert "Scope Analysis" in result


def test_scope_duplicates_deduplicated(project: Path) -> None:
    auth_dir = project / "src" / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "main.py").write_text("# auth")
    result = run_bootstrap(scope="src/auth,src/auth")
    assert result.count("### src/auth\n") <= 1


# Group E — File budget and content limits


def test_large_file_truncated(project: Path) -> None:
    readme = project / "README.md"
    readme.write_text("A" * 20_000)
    result = run_bootstrap()
    assert "[truncated at" in result
    assert "full file is" in result


def test_total_budget_not_exceeded(project: Path) -> None:
    src = project / "src"
    src.mkdir()
    for i in range(100):
        (src / f"file_{i}.py").write_text("x" * 2_000)
    result = run_bootstrap()
    assert len(result.encode()) <= _TOTAL_CONTENT_BUDGET_BYTES * 1.5


def test_binary_files_not_in_key_files(project: Path) -> None:
    (project / "image.png").write_bytes(bytes(100))
    result = run_bootstrap()
    if "## Key Files" in result:
        key_files_section = result.split("## Key Files")[1].split("---")[0]
        assert "image.png" not in key_files_section


def test_presence_only_files_have_no_content_in_manifest(project: Path) -> None:
    lock_file = project / "uv.lock"
    lock_file.write_text("THIS SHOULD NOT APPEAR IN MANIFEST")
    result = run_bootstrap()
    assert "THIS SHOULD NOT APPEAR IN MANIFEST" not in result


def test_excluded_dirs_not_walked(project: Path) -> None:
    nm = project / "node_modules"
    nm.mkdir()
    (nm / "secret.js").write_text("SHOULD NOT APPEAR")
    result = run_bootstrap()
    assert "SHOULD NOT APPEAR" not in result


def test_brain79_dir_not_scanned(project: Path) -> None:
    secret = project / ".brain-79" / "product" / "secret.md"
    secret.write_text("WIKI SECRET")
    result = run_bootstrap()
    assert "WIKI SECRET" not in result


# Group F — Tree listing


def test_tree_lists_depth1_only(project: Path) -> None:
    deep = project / "src" / "deep" / "nested"
    deep.mkdir(parents=True)
    (deep / "file.py").write_text("# deep")
    result = run_bootstrap()
    tree_section = result.split("## Project Structure")[1].split("---")[0]
    assert "nested" not in tree_section


def test_tree_max_entries_respected(project: Path) -> None:
    for i in range(70):
        (project / f"file_{i}.txt").write_text("x")
    result = run_bootstrap()
    tree_section = result.split("## Project Structure (depth 1)\n")[1].split("---")[0]
    entries = [line for line in tree_section.splitlines() if line.strip()]
    assert len(entries) <= _TREE_MAX_ENTRIES


def test_tree_excludes_git_and_cache(project: Path) -> None:
    (project / ".git").mkdir()
    (project / "__pycache__").mkdir()
    result = run_bootstrap()
    tree_section = result.split("## Project Structure")[1].split("---")[0]
    assert ".git" not in tree_section
    assert "__pycache__" not in tree_section


# Group G — Manifest structure


def test_manifest_has_required_sections(project: Path) -> None:
    result = run_bootstrap()
    for section in (
        "## Project Structure",
        "## Key Files",
        "## Bootstrap Instructions",
    ):
        assert section in result


def test_manifest_generated_timestamp_is_valid_iso(project: Path) -> None:
    import re
    from datetime import datetime as dt

    result = run_bootstrap()
    match = re.search(
        r"Generated: (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+\d{2}:\d{2}|Z))",
        result,
    )
    assert match is not None, "No valid ISO timestamp found in manifest"
    dt.fromisoformat(match.group(1))


def test_manifest_project_root_present(project: Path) -> None:
    result = run_bootstrap()
    assert "Project root:" in result


def test_manifest_instructions_reference_required_articles(project: Path) -> None:
    import re

    result = run_bootstrap()
    assert re.search(r"`architecture/overview\.md`", result)
    assert re.search(r"`INDEX\.md`", result)


def test_manifest_instructions_contain_frontmatter_template(project: Path) -> None:
    result = run_bootstrap()
    assert "bootstrap: true" in result
    assert "generated_by: brain79_bootstrap" in result


def test_manifest_domain_article_not_required_when_no_signals(
    project: Path,
) -> None:
    result = run_bootstrap()
    instructions = result.split("## Bootstrap Instructions")[1]
    assert "product/domain.md" not in instructions.split("**Conditional")[0]


def test_manifest_stack_article_required_when_pyproject_present(
    project: Path,
) -> None:
    (project / "pyproject.toml").write_text("[project]\nname='test'")
    result = run_bootstrap()
    assert "architecture/stack.md" in result


def test_manifest_scope_article_in_instructions_when_scope_given(
    project: Path,
) -> None:
    auth = project / "src" / "auth"
    auth.mkdir(parents=True)
    (auth / "main.py").write_text("# auth")
    result = run_bootstrap(scope="src/auth")
    assert "features/" in result


# Group H — Error resilience


def test_wiki_not_initialized_returns_error(tmp_path: Path) -> None:
    project_dir = tmp_path / "fresh"
    project_dir.mkdir()
    set_project_root(project_dir)
    result = run_bootstrap()
    assert "Bootstrap Error" in result


def test_wiki_root_is_file_returns_error(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    set_project_root(project_dir)
    wiki_root = project_dir / ".brain-79"
    wiki_root.write_text("not a directory")
    result = run_bootstrap()
    assert "Bootstrap Error" in result


@pytest.fixture
def unreadable_readme(project: Path) -> Iterator[Path]:
    readme = project / "README.md"
    readme.write_text("Hello")
    readme.chmod(0o000)
    yield readme
    readme.chmod(0o644)


def test_unreadable_file_skipped(project: Path, unreadable_readme: Path) -> None:
    result = run_bootstrap()
    assert "Bootstrap Error" not in result


def test_concurrent_state_write_atomic(project: Path) -> None:
    wiki_root = get_wiki_root()
    errors: list[Exception] = []

    def write_state(i: int) -> None:
        try:
            _save_bootstrap_state(wiki_root, {"id": i, "last_run_iso": "2026-01-01"})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_state, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    final = json.loads((wiki_root / ".bootstrap_state.json").read_text())
    assert isinstance(final, dict)
    assert "id" in final


def test_concurrent_run_bootstrap_no_corruption(project: Path) -> None:
    results: list[str] = []
    barrier = threading.Barrier(2)

    def call() -> None:
        barrier.wait()
        results.append(run_bootstrap())

    threads = [threading.Thread(target=call) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 2
    for r in results:
        assert "Bootstrap Error" not in r
    state = _load_bootstrap_state(get_wiki_root())
    assert isinstance(state, dict)
    assert "in_progress" not in state


def test_scope_all_paths_invalid_still_returns_manifest(project: Path) -> None:
    result = run_bootstrap(scope="does/not/exist,also/missing")
    assert "Bootstrap Instructions" in result
    assert "Warnings" in result


# Group I — _truncate_file unit tests


def test_truncate_file_small_file_not_truncated(tmp_path: Path) -> None:
    f = tmp_path / "small.txt"
    f.write_text("hello")
    content, truncated = _truncate_file(f, 8_000)
    assert content == "hello"
    assert truncated is False


def test_truncate_file_large_file_truncated(tmp_path: Path) -> None:
    f = tmp_path / "large.txt"
    f.write_text("A" * 20_000)
    content, truncated = _truncate_file(f, 8_000)
    assert truncated is True
    assert "[truncated at 8k — full file is" in content
    assert "k]" in content
    assert len(content.encode()) < 20_000


def test_truncate_file_large_file_marker_has_correct_sizes(
    tmp_path: Path,
) -> None:
    f = tmp_path / "large.txt"
    f.write_text("A" * 20_000)
    content, _ = _truncate_file(f, 8_000)
    assert "[truncated at 8k — full file is 20k]" in content


def test_truncate_file_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    f.write_text("")
    content, truncated = _truncate_file(f, 8_000)
    assert content == ""
    assert truncated is False


def test_truncate_file_missing_file(tmp_path: Path) -> None:
    content, truncated = _truncate_file(tmp_path / "missing.txt", 8_000)
    assert content == ""
    assert truncated is False


# Group K — _resolve_scope_paths unit tests


def test_resolve_scope_paths_dedup(project: Path) -> None:
    (project / "src" / "auth").mkdir(parents=True)
    paths, _ = _resolve_scope_paths(project, "src/auth,src/auth")
    assert len(paths) == 1


def test_resolve_scope_paths_strips_whitespace(project: Path) -> None:
    (project / "src" / "auth").mkdir(parents=True)
    paths, _ = _resolve_scope_paths(project, "  src/auth  ,  src/auth  ")
    assert len(paths) == 1


def test_resolve_scope_paths_absolute_path_dropped(project: Path) -> None:
    paths, warnings = _resolve_scope_paths(project, "/etc/passwd")
    assert paths == []
    assert warnings == []


def test_resolve_scope_paths_traversal_dropped(project: Path) -> None:
    paths, warnings = _resolve_scope_paths(project, "../../../etc")
    assert paths == []
    assert warnings == []


def test_resolve_scope_paths_mixed_valid_and_invalid(project: Path) -> None:
    (project / "src").mkdir()
    paths, _ = _resolve_scope_paths(project, "src,../outside")
    assert len(paths) == 1
    assert paths[0] == (project / "src").resolve(strict=False)


def test_resolve_scope_paths_nonexistent_returns_warning(project: Path) -> None:
    paths, warnings = _resolve_scope_paths(project, "nonexistent/path")
    assert paths == []
    assert len(warnings) == 1
    assert "Scope path does not exist: nonexistent/path" in warnings[0]


# Group L — MCP tool integration


def test_mcp_tool_registered() -> None:
    import asyncio

    tools = asyncio.run(server_module.mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "brain79_bootstrap" in tool_names


def test_mcp_tool_returns_string(project: Path) -> None:
    result = run_bootstrap()
    assert isinstance(result, str)
    assert len(result) > 0


def test_mcp_tool_exception_caught_in_server(project: Path) -> None:
    with patch(
        "brain79.core.bootstrap.run_bootstrap", side_effect=OSError("disk full")
    ):
        result = server_module.brain79_bootstrap()
    assert result.startswith("Bootstrap Error:")
