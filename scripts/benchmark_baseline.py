"""Benchmark script for brain-79 performance baseline and regression testing."""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from brain79.config import get_project_root, get_wiki_root, set_project_root
from brain79.core.curate import prepare_curation_guide
from brain79.core.handoff import write_handoff
from brain79.core.lint import lint_wiki
from brain79.core.lint_organizational import lint_organizational
from brain79.core.navigation import (
    load_registry,
    regenerate_index_navigation,
)
from brain79.core.wiki import read_article, write_article
from brain79.server import mcp


def benchmark_current_wiki() -> dict:
    original_root = get_project_root()
    wiki_dir = get_wiki_root()

    # Index read time
    t0 = time.perf_counter()
    index_content = read_article("INDEX.md")
    t_index = (time.perf_counter() - t0) * 1000

    # Lint strict time
    t0 = time.perf_counter()
    lint_report = lint_wiki()
    t_lint = (time.perf_counter() - t0) * 1000

    # Lint organizational time
    t0 = time.perf_counter()
    org_issues = lint_organizational(wiki_dir)
    t_lint_org = (time.perf_counter() - t0) * 1000

    # Ingest / Curation guide time
    t0 = time.perf_counter()
    guide = prepare_curation_guide(wiki_dir, "Benchmarking session close performance.")
    t_ingest = (time.perf_counter() - t0) * 1000

    # Navigate regenerate time (on tmp copy to avoid mutating actual INDEX.md)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_project = Path(tmp_dir)
        tmp_wiki = tmp_project / ".brain-79"
        shutil.copytree(wiki_dir, tmp_wiki)
        t0 = time.perf_counter()
        regenerate_index_navigation(tmp_wiki)
        t_nav = (time.perf_counter() - t0) * 1000

    return {
        "index_read_ms": round(t_index, 2),
        "lint_strict_ms": round(t_lint, 2),
        "lint_org_ms": round(t_lint_org, 2),
        "curation_guide_ms": round(t_ingest, 2),
        "nav_regenerate_ms": round(t_nav, 2),
    }


def check_handoff_navigation_pollution() -> bool:
    """Check if handoffs get added to navigation registry / INDEX.md."""
    orig_root = get_project_root()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_project = Path(tmp_dir)
        tmp_wiki = tmp_project / ".brain-79"
        shutil.copytree(get_wiki_root(), tmp_wiki)
        set_project_root(tmp_project)

        try:
            # Write a handoff
            write_handoff(
                session_type="feature",
                previous_handoff_ref="none",
                summary="Handoff test",
                completed_work=["Task 1"],
                pending_work=["Task 2"],
                knowledge_pending_promotion=["Knowledge 1"],
                resources=["Doc 1"],
                gotchas=["Gotcha 1"],
                boot_instruction="Boot test Task 2",
            )

            reg = load_registry(tmp_wiki)
            handoff_in_reg = any(k.startswith("handoffs/") for k in reg.keys())

            # Also check index navigation
            regenerate_index_navigation(tmp_wiki)
            idx_text = (tmp_wiki / "INDEX.md").read_text()
            handoff_in_index = "handoff" in idx_text.lower() and "### Handoffs" in idx_text

            return handoff_in_reg or handoff_in_index
        finally:
            set_project_root(orig_root)


def check_validation_error_behavior() -> dict:
    """Check how validation errors are reported currently."""
    from brain79.core.frontmatter import validate_frontmatter

    # Content missing status, version, last_updated
    bad_fm = {"type": "feature", "unknown_key": "bar"}
    try:
        validate_frontmatter(bad_fm, "features/test.md")
        error_count = 0
        error_msg = ""
    except Exception as e:
        error_msg = str(e)
        # Check if error mentions all missing fields or just the first one
        has_status = "status" in error_msg
        has_version = "version" in error_msg
        has_last_updated = "last_updated" in error_msg
        has_unknown = "unknown_key" in error_msg
        error_count = sum([has_status, has_version, has_last_updated, has_unknown])

    return {
        "error_msg": error_msg,
        "violations_detected_in_single_error": error_count,
    }


def benchmark_synthetic(num_articles: int) -> dict:
    orig_root = get_project_root()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_project = Path(tmp_dir)
        tmp_wiki = tmp_project / ".brain-79"
        tmp_wiki.mkdir(parents=True)
        (tmp_wiki / "features").mkdir()
        (tmp_wiki / "INDEX.md").write_text("---\ntype: navigation\nlast_updated: 2026-08-11\n---\n# Index\n")
        (tmp_wiki / "SCHEMA.md").write_text((get_wiki_root() / "SCHEMA.md").read_text())

        for i in range(num_articles):
            links = "\n".join([f"- [Link {j}](features/feature-{j}.md)" for j in range(min(10, num_articles))])
            content = f"""---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# Feature {i}

Description of feature {i}.

{links}
"""
            (tmp_wiki / "features" / f"feature-{i}.md").write_text(content)

        set_project_root(tmp_project)
        try:
            # Measure lint_wiki
            t0 = time.perf_counter()
            lint_wiki()
            t_lint = (time.perf_counter() - t0) * 1000

            # Measure lint_organizational
            t0 = time.perf_counter()
            lint_organizational(tmp_wiki)
            t_org = (time.perf_counter() - t0) * 1000

            # Measure prepare_curation_guide
            t0 = time.perf_counter()
            prepare_curation_guide(tmp_wiki, "Summary")
            t_ingest = (time.perf_counter() - t0) * 1000

            # Measure single write_article
            t0 = time.perf_counter()
            write_article(
                "features/new-feature.md",
                """---
type: feature
status: planned
version: 1.0.0
last_updated: 2026-10-29
---

# New Feature
Content
""",
            )
            t_write = (time.perf_counter() - t0) * 1000

            return {
                f"synthetic_{num_articles}_lint_ms": round(t_lint, 2),
                f"synthetic_{num_articles}_org_ms": round(t_org, 2),
                f"synthetic_{num_articles}_ingest_ms": round(t_ingest, 2),
                f"synthetic_{num_articles}_write_ms": round(t_write, 2),
            }
        finally:
            set_project_root(orig_root)


def main():
    print("=== Running Baseline Profiling ===")
    current = benchmark_current_wiki()
    print("Current wiki timings (ms):", json.dumps(current, indent=2))

    pollution = check_handoff_navigation_pollution()
    print(f"Handoff pollutes navigation/registry: {pollution}")

    val_behavior = check_validation_error_behavior()
    print("Validation error behavior:", json.dumps(val_behavior, indent=2))

    synth_50 = benchmark_synthetic(50)
    print("Synthetic 50 timings (ms):", json.dumps(synth_50, indent=2))

    synth_300 = benchmark_synthetic(300)
    print("Synthetic 300 timings (ms):", json.dumps(synth_300, indent=2))

    # FastMCP tool inspection
    print("\nFastMCP tools output_schema check:")
    import asyncio
    tools = asyncio.run(mcp.list_tools())
    tool_schemas = {t.name: getattr(t, "output_schema", None) for t in tools}
    print(f"Tool count: {len(tool_schemas)}, sample schemas: {list(tool_schemas.items())[:3]}")

    results = {
        "current_wiki": current,
        "handoff_pollutes_nav": pollution,
        "validation_error_behavior": val_behavior,
        "synth_50": synth_50,
        "synth_300": synth_300,
        "tool_schemas": {k: str(v) for k, v in tool_schemas.items()},
    }
    with open("reports/baseline_measurements.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved baseline to reports/baseline_measurements.json")


if __name__ == "__main__":
    main()
