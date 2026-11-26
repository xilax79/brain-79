"""Tests for Stage 2: Ergonomic brain79_read_batch normalization and CLI/MCP parity (AC-3)."""

from __future__ import annotations

from collections.abc import Generator
import inspect
import io
import json
from pathlib import Path
from typing import Any

import pytest

from brain79.cli.dispatch import WHITELIST, run_cli
from brain79.config import set_project_root
from brain79.core.frontmatter import clear_schema_cache
from brain79.core.init_project import init_project
from brain79.core.wiki import read_batch_articles, write_article
from brain79.server import MCP_TOOLS, brain79_read_batch, mcp


@pytest.fixture(autouse=True)
def isolated_wiki(tmp_path: Path) -> Generator[Path, None, None]:
    """Create an isolated temporary project wiki for each test."""
    (tmp_path / "README.md").write_text("# Temp Repo\n", encoding="utf-8")
    set_project_root(tmp_path)
    clear_schema_cache()
    init_project(tmp_path, profile="software")
    yield tmp_path
    set_project_root(None)
    clear_schema_cache()


def _seed_wiki() -> None:
    """Create 3 sample articles for batch-read parity tests."""
    write_article(
        "architecture/overview.md",
        """---
type: architecture
summary: System overview
stability: stable
applies_to:
  - README.md
last_updated: 2026-11-26
---

# System Overview

## Boundaries
Boundary details.
""",
    )
    write_article(
        "features/auth.md",
        """---
type: feature
summary: Authentication flow
status: planned
version: 1.0.0
last_updated: 2026-11-26
---

# Authentication

## Overview
Auth overview content.

## Endpoints
Login and logout endpoints.
""",
    )
    write_article(
        "topics/notes.md",
        """---
type: topic
summary: Domain notes
status: active
last_updated: 2026-11-26
---

# Domain Notes

## Summary
Topic summary content.
""",
    )


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    """Capture relative file paths and contents under root for zero-mutation checks."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.endswith(".lock")
    }


def _collect_array_items(schema: Any) -> list[dict[str, Any]]:
    """Collect all `items` sub-schemas inside a JSON schema property."""
    items_list: list[dict[str, Any]] = []
    if isinstance(schema, dict):
        if "items" in schema and isinstance(schema["items"], dict):
            items_list.append(schema["items"])
        for val in schema.values():
            items_list.extend(_collect_array_items(val))
    elif isinstance(schema, list):
        for elem in schema:
            items_list.extend(_collect_array_items(elem))
    return items_list


def test_mcp_read_batch_paths_and_nested_args_parity() -> None:
    """R-2.1: brain79_read_batch(paths=...) top-level & nested args normalize prefixes and match requests output."""
    _seed_wiki()

    via_requests = brain79_read_batch(
        requests=[
            {"path": "architecture/overview.md"},
            {"path": "features/auth.md"},
        ]
    )
    via_paths = brain79_read_batch(
        paths=[".brain-79/architecture/overview.md", "./.brain-79/features/auth.md"]
    )
    via_nested_args = brain79_read_batch(
        args={"paths": ["/.brain-79/architecture/overview.md", "features/auth.md"]}
    )

    assert via_paths == via_requests
    assert via_nested_args == via_requests
    assert "## === Article: architecture/overview.md ===" in via_paths
    assert "## === Article: features/auth.md ===" in via_paths
    assert "Boundary details." in via_paths
    assert "Auth overview content." in via_paths


def test_read_batch_string_requests_and_deterministic_dedup() -> None:
    """R-2.2: String items in requests, dict backward-compat, and first-seen deduplication."""
    _seed_wiki()

    # Mixed string and dict requests + overlapping paths
    out = brain79_read_batch(
        requests=[
            ".brain-79/architecture/overview.md",
            {"path": "features/auth.md", "sections": ["Endpoints"]},
            {"path": "features/auth.md", "sections": ["Endpoints"]},
            {"path": "architecture/overview.md", "sections": []},
        ],
        paths=[
            "architecture/overview.md",
            "features/auth.md",
            "topics/notes.md",
        ],
    )

    # First-seen order:
    # 1. architecture/overview.md (None)
    # 2. features/auth.md (["Endpoints"])
    # 3. features/auth.md (None) - distinct from ("features/auth.md", ("Endpoints",))
    # 4. topics/notes.md (None)
    assert out.count("## === Article: architecture/overview.md ===") == 1
    assert out.count("## === Article: features/auth.md ===") == 2
    assert out.count("## === Article: topics/notes.md ===") == 1

    idx_arch = out.index("## === Article: architecture/overview.md ===")
    idx_auth = out.index("## === Article: features/auth.md ===")
    idx_notes = out.index("## === Article: topics/notes.md ===")
    assert idx_arch < idx_auth < idx_notes

    # Core read_batch_articles returns structured list with normalized paths
    core_res = read_batch_articles(
        requests=[".brain-79/architecture/overview.md", {"path": "features/auth.md", "sections": ["Endpoints"]}],
        paths=["architecture/overview.md", "topics/notes.md"],
    )
    assert [item["path"] for item in core_res] == [
        "architecture/overview.md",
        "features/auth.md",
        "topics/notes.md",
    ]
    assert "## Endpoints" in core_res[1]["content"]
    assert "## Overview" not in core_res[1]["content"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"paths": []},
        {"requests": []},
        {"paths": [], "requests": []},
        {"paths": ["  "]},
        {"requests": [{"path": "  "}]},
        {"args": {"paths": "architecture/overview.md"}},
        {"args": {"requests": "architecture/overview.md"}},
        {"paths": [123]},
        {"requests": [123]},
        {"requests": [{}]},
        {"requests": [{"path": 42}]},
        {"requests": [{"path": "features/auth.md", "sections": "Overview"}]},
        {"requests": [{"path": "features/auth.md", "sections": [123]}]},
        {"requests": [{"path": "features/auth.md", "sections": ["  "]}]},
    ],
)
def test_mcp_read_batch_invalid_and_empty_inputs_return_actionable_error(kwargs: dict[str, Any]) -> None:
    """R-2.3: Empty or malformed inputs return actionable 'Error: ...' showing both forms without raising."""
    _seed_wiki()
    resp = brain79_read_batch(**kwargs)
    assert resp.startswith("Error:")
    assert "paths=[" in resp
    assert "requests=[" in resp


@pytest.mark.asyncio
async def test_mcp_read_batch_wire_schema_no_nested_anyof() -> None:
    """R-2.2: await mcp.list_tools() exposes paths & requests with zero nested anyOf in array items."""
    tools = await mcp.list_tools()
    by_name = {t.name: t for t in tools}
    assert "brain79_read_batch" in by_name

    schema = by_name["brain79_read_batch"].to_mcp_tool().inputSchema
    props = schema.get("properties", {})
    assert "paths" in props
    assert "requests" in props

    for field in ("paths", "requests"):
        for item_schema in _collect_array_items(props[field]):
            assert "anyOf" not in item_schema, f"{field}.items must not contain anyOf: {item_schema}"


def test_read_batch_symmetry_and_surface_invariants() -> None:
    """Verify read_batch_articles/brain79_read_batch parameter parity, 9 MCP tools, and 26 CLI subcommands."""
    assert len(MCP_TOOLS) == 9
    assert len(WHITELIST) == 26
    assert "read-batch" in WHITELIST

    mcp_sig = inspect.signature(brain79_read_batch)
    core_sig = inspect.signature(read_batch_articles)
    assert "requests" in mcp_sig.parameters and "requests" in core_sig.parameters
    assert "paths" in mcp_sig.parameters and "paths" in core_sig.parameters
    assert mcp_sig.parameters["requests"].default is None
    assert mcp_sig.parameters["paths"].default is None
    assert core_sig.parameters["requests"].default is None
    assert core_sig.parameters["paths"].default is None


def test_cli_read_batch_paths_stdin_file_and_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """R-2.5: CLI read-batch supports --paths, --stdin, --file (strings & dicts), exit 2/1, zero disk mutations."""
    _seed_wiki()
    wiki_dir = tmp_path / ".brain-79"
    before = _snapshot_tree(wiki_dir)

    # 1. --paths with .brain-79/ prefix normalization and deduplication
    rc_paths = run_cli(
        "read-batch",
        ["--paths", ".brain-79/architecture/overview.md", "features/auth.md", "architecture/overview.md"],
    )
    assert rc_paths == 0
    out_paths = capsys.readouterr().out
    assert out_paths.count("## === Article: architecture/overview.md ===") == 1
    assert "## === Article: features/auth.md ===" in out_paths
    assert "Boundary details." in out_paths

    # 2. --stdin with JSON array of strings & dicts
    stdin_payload = json.dumps(["architecture/overview.md", {"path": "features/auth.md", "sections": ["Endpoints"]}])
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin_payload.encode("utf-8")), encoding="utf-8"))
    rc_stdin = run_cli("read-batch", ["--stdin"])
    assert rc_stdin == 0
    out_stdin = capsys.readouterr().out
    assert "## Endpoints" in out_stdin
    assert "## Overview" not in out_stdin

    # 3. --file with JSON array of strings
    batch_file = tmp_path / "paths.json"
    batch_file.write_text(json.dumps(["topics/notes.md"]), encoding="utf-8")
    rc_file = run_cli("read-batch", ["--file", str(batch_file)])
    assert rc_file == 0
    assert "Topic summary content." in capsys.readouterr().out

    # 4. Missing required arguments -> exit 2
    rc_missing = run_cli("read-batch", [])
    assert rc_missing == 2
    capsys.readouterr()

    # 5. Invalid JSON payload -> exit 1 with actionable stderr
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{bad json"), encoding="utf-8"))
    rc_bad_json = run_cli("read-batch", ["--stdin"])
    assert rc_bad_json == 1
    assert "Error:" in capsys.readouterr().err

    # 6. Invalid item type in JSON payload -> exit 1 with actionable stderr
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"[123]"), encoding="utf-8"))
    rc_bad_item = run_cli("read-batch", ["--stdin"])
    assert rc_bad_item == 1
    err_bad_item = capsys.readouterr().err
    assert "Error:" in err_bad_item
    assert "paths=[" in err_bad_item

    after = _snapshot_tree(wiki_dir)
    assert after == before
