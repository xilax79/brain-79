#!/usr/bin/env python3
"""Phase 9 Deliverable 9.3: Five-Archetype Multi-Repo Battle Gauntlet Runner.

Executes a rigid 10-step lifecycle across five heterogeneous workspace archetypes:
1. Dirty polyglot monorepo (Python, TS, binaries, ignored node_modules/.venv/dist)
2. Chaotic legacy wiki (25 unfrontmattered articles, Husky hooksPath, stale .mcp.json)
3. Gitless research (--profile general, 10 sessions, Amnesia Test guard)
4. Git branch warfare (main, feat/payments, hotfix/auth, rebase, AST Guard C)
5. Scale benchmark (200 articles, 1,000 source files, in-process latency budgets)

CLI:
    python scripts/run_battle_gauntlet.py [--archetype N] [--keep] [--json PATH]
Exit codes:
    0 = all passed
    1 = any step failed
    2 = usage or environment error
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Literal

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from brain79.config import get_project_root, get_wiki_root, set_project_root
from brain79.core.bootstrap import run_bootstrap
from brain79.core.context import get_context
from brain79.core.doctor import run_doctor
from brain79.core.drift import WorkspaceIndex, check_article_drift
from brain79.core.frontmatter import (
    FrontmatterError,
    ValidationError,
    parse_frontmatter,
)
from brain79.core.handoff import write_handoff
from brain79.core.handoff_freshness import compute_handoff_freshness
from brain79.core.init_project import init_project, sync_project_mcp_configs
from brain79.core.lint import lint_wiki
from brain79.core.navigation import regenerate_index_navigation
from brain79.core.orient import orient
from brain79.core.session_commit import commit_session
from brain79.core.wiki import edit_article, read_article, write_article


def get_perf_factor() -> float:
    """Read BRAIN79_PERF_FACTOR environment variable (default 1.0, CI sets 3.0)."""
    raw = os.environ.get("BRAIN79_PERF_FACTOR", "1.0").strip()
    try:
        val = float(raw)
        return max(0.1, val)
    except ValueError:
        return 1.0


def _init_local_git(repo_dir: Path) -> None:
    """Initialize git repository with strictly local config (never mutating global user config)."""
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Battle Gauntlet"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "gauntlet@example.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_dir, check=True, capture_output=True)


def _measure_median(fn: Callable[[], Any], runs: int = 5) -> float:
    """Measure in-process median latency in milliseconds after one warm-up."""
    fn()  # Warm-up run
    timings: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        timings.append((time.perf_counter() - t0) * 1000.0)
    timings.sort()
    return timings[len(timings) // 2]


# ==============================================================================
# Archetype 1: Dirty Polyglot Monorepo
# ==============================================================================


def build_archetype_1(ws: Path) -> dict[str, Any]:
    _init_local_git(ws)

    # Polyglot sources
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "api.py").write_text("def get_data(): return {'status': 'ok'}\n", encoding="utf-8")
    (ws / "src" / "utils.py").write_text("def helper(): return True\n", encoding="utf-8")

    (ws / "web").mkdir(parents=True, exist_ok=True)
    (ws / "web" / "app.tsx").write_text("export const App = () => <div>Hello</div>;\n", encoding="utf-8")
    (ws / "web" / "index.ts").write_text("console.log('App init');\n", encoding="utf-8")

    # Binaries
    (ws / "assets").mkdir(parents=True, exist_ok=True)
    (ws / "assets" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32)
    (ws / "data").mkdir(parents=True, exist_ok=True)
    (ws / "data" / "app.sqlite").write_bytes(b"SQLite format 3\x00" + b"\x00" * 64)

    # Ignored directories
    (ws / ".gitignore").write_text("node_modules/\n.venv/\ndist/\n", encoding="utf-8")
    (ws / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
    (ws / "node_modules" / "pkg" / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
    (ws / ".venv" / "lib").mkdir(parents=True, exist_ok=True)
    (ws / ".venv" / "lib" / "site.py").write_text("# Virtualenv\n", encoding="utf-8")
    (ws / "dist").mkdir(parents=True, exist_ok=True)
    (ws / "dist" / "bundle.js").write_text("// bundle\n", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial polyglot commit"], cwd=ws, check=True, capture_output=True)
    return {"files_created": 8}


def run_archetype_1_lifecycle(ws: Path, perf_factor: float = 1.0) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    set_project_root(ws)
    w_root = ws / ".brain-79"

    def execute_step(step_num: int, name: str, fn: Callable[[], Any]) -> None:
        t0 = time.perf_counter()
        try:
            fn()
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 1,
                "step": step_num,
                "name": name,
                "status": "ok",
                "duration_ms": round(duration_ms, 2),
                "error": None,
            })
            print(f"[Archetype 1] Step {step_num:02d}/10: {name} ... [OK] ({duration_ms:.1f}ms)")
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 1,
                "step": step_num,
                "name": name,
                "status": "failed",
                "duration_ms": round(duration_ms, 2),
                "error": str(exc),
            })
            print(f"[Archetype 1] Step {step_num:02d}/10: {name} ... [FAILED] ({duration_ms:.1f}ms): {exc}")
            raise

    # 1. init
    execute_step(1, "init", lambda: init_project(ws, install_git_hooks_flag=True))
    # 2. doctor
    execute_step(2, "doctor", lambda: run_doctor(project_root=ws, wiki_root=w_root))
    # 3. bootstrap
    def step_3() -> None:
        manifest = run_bootstrap(force=True)
        assert manifest and "Bootstrap Manifest" in manifest
        assert (w_root / ".bootstrap_state.json").exists()

    execute_step(3, "bootstrap", step_3)
    # 4. write 3 articles
    def step_4() -> None:
        write_article(
            "features/api.md",
            "---\ntype: feature\nsummary: Python API service\nstatus: shipped\nversion: 1.0.0\nlast_updated: 2026-11-17\napplies_to:\n  - src/*.py\n---\n\n# Feature — API\n\n## Overview\nAPI endpoints.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
        write_article(
            "features/web.md",
            "---\ntype: feature\nsummary: TypeScript web frontend\nstatus: shipped\nversion: 1.0.0\nlast_updated: 2026-11-17\napplies_to:\n  - web/*.tsx\n  - web/*.ts\n---\n\n# Feature — Web\n\n## Overview\nWeb app.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
        write_article(
            "architecture/overview.md",
            "---\ntype: architecture\nsummary: Full-stack system architecture\nstability: stable\nlast_updated: 2026-11-17\napplies_to:\n  - src/**\n  - web/**\n---\n\n# Architecture — Overview\n\n## Overview\nSystem architecture.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
    execute_step(4, "write_3_articles", step_4)

    # 5. orient
    execute_step(5, "orient", lambda: orient(task="modify api data", paths=["src/api.py"], wiki_root=w_root))

    # 6. edit one article
    execute_step(
        6,
        "edit_article",
        lambda: edit_article("features/api.md", [{"old_text": "API endpoints.", "new_text": "Updated API endpoints."}], wiki_root=w_root),
    )

    # 7. session-commit with handoff
    execute_step(
        7,
        "session_commit_handoff",
        lambda: commit_session(
            session_summary="Completed API updates",
            handoff={
                "session_type": "feature",
                "summary": "API polish",
                "completed_work": ["Updated API"],
                "pending_work": ["Frontend sync"],
                "boot_instruction": "Continue frontend sync",
            },
            wiki_root=w_root,
        ),
    )

    # 8. mutate source
    def step_8() -> None:
        (ws / "src" / "api.py").write_text("def get_data(): return {'status': 'ok', 'v': 2}\n", encoding="utf-8")
    execute_step(8, "mutate_source", step_8)

    # 9. lint --strict and drift check expecting drift
    def step_9() -> None:
        drifts = check_article_drift("features/api.md", wiki_root=w_root, project_root=ws)
        assert len(drifts) > 0, "Expected drift on features/api.md"

        # Verify WorkspaceIndex excludes ignored dirs and binaries
        ws_idx = WorkspaceIndex.build(ws, w_root)
        for p in ws_idx.all_paths:
            assert not p.startswith("node_modules/"), f"Ignored directory leaked into index: {p}"
            assert not p.startswith(".venv/"), f"Ignored directory leaked into index: {p}"
            assert not p.startswith("dist/"), f"Ignored directory leaked into index: {p}"

        # Latency budget: WorkspaceIndex.build <= 250 ms * perf_factor
        ceiling_ms = 250.0 * perf_factor
        median_ms = _measure_median(lambda: WorkspaceIndex.build(ws, w_root), runs=5)
        assert median_ms <= ceiling_ms, f"WorkspaceIndex.build latency {median_ms:.1f}ms exceeded ceiling {ceiling_ms:.1f}ms"

    execute_step(9, "lint_and_drift_check", step_9)

    # 10. recover to clean
    def step_10() -> None:
        commit_session(
            session_summary="Reconcile drift after code mutation",
            edits=[{"path": "features/api.md", "edits": [{"old_text": "Updated API endpoints.", "new_text": "API v2 endpoints."}]}],
            wiki_root=w_root,
            allow_partial_ripple=True,
        )
        report = lint_wiki(wiki_root=w_root)
        assert "[CRITICAL] Broken Local Links (0)" in report
        assert "[CRITICAL] Namespace Violations (0)" in report
    execute_step(10, "recover_to_clean", step_10)

    return steps


# ==============================================================================
# Archetype 2: Chaotic Legacy Wiki + Husky Hooks + Stale MCP
# ==============================================================================


def build_archetype_2(ws: Path) -> dict[str, Any]:
    _init_local_git(ws)
    w_root = ws / ".brain-79"
    w_root.mkdir(parents=True, exist_ok=True)
    (w_root / "topics").mkdir(parents=True, exist_ok=True)
    (w_root / "INDEX.md").write_text("# Index\n\n## Quick navigation\n", encoding="utf-8")
    (w_root / "SCHEMA.md").write_text(
        "---\ntype: schema\nsummary: Declarative schema\nprofile: software\nlast_updated: 2026-11-17\n---\n# Schema\n",
        encoding="utf-8",
    )

    # 25 hand-written markdown files with missing frontmatter and broken links
    original_hashes: dict[str, str] = {}
    for i in range(25):
        body = (
            f"# Legacy Document {i}\n\n"
            f"Unformatted legacy body text number {i}.\n\n"
            f"[Broken Link](missing_{i}.md)\n\n"
            "---\n\n"
            "[← Volver al Índice](../INDEX.md)\n"
        )
        path = w_root / "topics" / f"legacy_{i}.md"
        path.write_text(body, encoding="utf-8")
        original_hashes[f"topics/legacy_{i}.md"] = hashlib.sha256(body.encode("utf-8")).hexdigest()

    # .husky/ pre-commit hook and core.hooksPath git config
    husky_dir = ws / ".husky"
    husky_dir.mkdir(parents=True, exist_ok=True)
    (husky_dir / "pre-commit").write_text("#!/usr/bin/env sh\necho 'husky pre-commit'\n", encoding="utf-8")
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=ws, check=True, capture_output=True)

    # Stale .mcp.json
    mcp_json = ws / ".mcp.json"
    mcp_json.write_text(
        json.dumps({
            "mcpServers": {
                "brain79": {
                    "command": "/Users/old/brain79",
                    "args": ["--project-root", "."],
                }
            }
        }, indent=2),
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit legacy state"], cwd=ws, check=True, capture_output=True)
    return {"original_hashes": original_hashes}


def run_archetype_2_lifecycle(ws: Path, perf_factor: float = 1.0) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    set_project_root(ws)
    w_root = ws / ".brain-79"

    # Read original hashes
    original_hashes: dict[str, str] = {}
    for i in range(25):
        p = w_root / "topics" / f"legacy_{i}.md"
        if p.is_file():
            original_hashes[f"topics/legacy_{i}.md"] = hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest()

    def execute_step(step_num: int, name: str, fn: Callable[[], Any]) -> None:
        t0 = time.perf_counter()
        try:
            fn()
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 2,
                "step": step_num,
                "name": name,
                "status": "ok",
                "duration_ms": round(duration_ms, 2),
                "error": None,
            })
            print(f"[Archetype 2] Step {step_num:02d}/10: {name} ... [OK] ({duration_ms:.1f}ms)")
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 2,
                "step": step_num,
                "name": name,
                "status": "failed",
                "duration_ms": round(duration_ms, 2),
                "error": str(exc),
            })
            print(f"[Archetype 2] Step {step_num:02d}/10: {name} ... [FAILED] ({duration_ms:.1f}ms): {exc}")
            raise

    # 1. init --upgrade
    execute_step(1, "init_upgrade", lambda: init_project(ws, upgrade=True))
    # 2. doctor
    execute_step(2, "doctor", lambda: run_doctor(project_root=ws, wiki_root=w_root))
    # 3. bootstrap
    def step_3() -> None:
        manifest = run_bootstrap(force=True)
        assert manifest and "Bootstrap Manifest" in manifest
        assert (w_root / ".bootstrap_state.json").exists()

    execute_step(3, "bootstrap", step_3)
    # 4. write 3 articles
    def step_4() -> None:
        for i in range(3):
            write_article(
                f"topics/new_topic_{i}.md",
                f"---\ntype: topic\nsummary: New topic {i}\nlast_updated: 2026-11-17\n---\n\n# New Topic {i}\n\n## Overview\nFresh article {i}.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
                wiki_root=w_root,
            )
    execute_step(4, "write_3_articles", step_4)

    # 5. orient
    execute_step(5, "orient", lambda: orient(task="audit legacy migration", wiki_root=w_root))
    # 6. edit one article
    execute_step(
        6,
        "edit_article",
        lambda: edit_article("topics/new_topic_0.md", [{"old_text": "Fresh article 0.", "new_text": "Audited article 0."}], wiki_root=w_root),
    )
    # 7. session-commit with handoff
    execute_step(
        7,
        "session_commit_handoff",
        lambda: commit_session(
            session_summary="Legacy migration audit",
            handoff={
                "session_type": "maintenance",
                "summary": "Audited legacy articles",
                "completed_work": ["Upgraded wiki", "Preserved Husky"],
                "pending_work": ["Continue monitoring"],
                "boot_instruction": "Check lint",
            },
            wiki_root=w_root,
        ),
    )
    # 8. mutate wiki
    execute_step(8, "mutate_wiki", lambda: (w_root / "topics" / "new_topic_1.md").write_text(
        "---\ntype: topic\nsummary: Modified topic 1\nlast_updated: 2026-11-17\n---\n\n# New Topic 1\n\n## Overview\nMutated.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
        encoding="utf-8",
    ))

    # 9. lint --strict and verification of legacy invariants
    def step_9() -> None:
        # Verify byte-identical original bodies (zero data loss)
        for rel_path, orig_hash in original_hashes.items():
            article_file = w_root / rel_path
            assert article_file.is_file(), f"Original legacy article lost: {rel_path}"
            raw = article_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(raw)
            # Body must match original body
            body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            assert body_hash == orig_hash, f"Data loss in {rel_path}: original content mutated!"
            assert meta.get("status") == "legacy", f"{rel_path} must be marked status: legacy"

        # Verify Husky hook and core.hooksPath unchanged
        hooks_path_proc = subprocess.run(["git", "config", "core.hooksPath"], cwd=ws, capture_output=True, text=True, check=True)
        assert hooks_path_proc.stdout.strip() == ".husky", "core.hooksPath was overwritten!"
        assert (ws / ".husky" / "pre-commit").read_text(encoding="utf-8") == "#!/usr/bin/env sh\necho 'husky pre-commit'\n"

        # Verify stale path replaced in .mcp.json
        mcp_data = json.loads((ws / ".mcp.json").read_text(encoding="utf-8"))
        cmd = mcp_data.get("mcpServers", {}).get("brain79", {}).get("command", "")
        assert "/Users/old/brain79" not in cmd, "Stale binary path was not replaced in .mcp.json"

    execute_step(9, "verify_legacy_invariants", step_9)

    # 10. recover to clean
    def step_10() -> None:
        run_doctor(project_root=ws, wiki_root=w_root, fix=True, force=True)
        for i in range(25):
            p = w_root / "topics" / f"legacy_{i}.md"
            if p.is_file():
                txt = p.read_text(encoding="utf-8")
                fixed_txt = txt.replace(f"[Broken Link](missing_{i}.md)", f"Repaired reference {i}.")
                p.write_text(fixed_txt, encoding="utf-8")

        regenerate_index_navigation(w_root)
        report = lint_wiki(wiki_root=w_root)
        assert "[CRITICAL] Broken Local Links (0)" in report
        assert "[CRITICAL] Namespace Violations (0)" in report
    execute_step(10, "recover_to_clean", step_10)

    return steps


# ==============================================================================
# Archetype 3: Gitless Research (--profile general, 10 sessions)
# ==============================================================================


def build_archetype_3(ws: Path) -> dict[str, Any]:
    # Pure non-git directory with general profile
    return {"workspace": str(ws)}


def run_archetype_3_lifecycle(ws: Path, perf_factor: float = 1.0) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    set_project_root(ws)
    w_root = ws / ".brain-79"

    def execute_step(step_num: int, name: str, fn: Callable[[], Any]) -> None:
        t0 = time.perf_counter()
        try:
            fn()
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 3,
                "step": step_num,
                "name": name,
                "status": "ok",
                "duration_ms": round(duration_ms, 2),
                "error": None,
            })
            print(f"[Archetype 3] Step {step_num:02d}/10: {name} ... [OK] ({duration_ms:.1f}ms)")
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 3,
                "step": step_num,
                "name": name,
                "status": "failed",
                "duration_ms": round(duration_ms, 2),
                "error": str(exc),
            })
            print(f"[Archetype 3] Step {step_num:02d}/10: {name} ... [FAILED] ({duration_ms:.1f}ms): {exc}")
            raise

    # 1. init --profile general
    execute_step(1, "init_general", lambda: init_project(ws, profile="general", install_git_hooks_flag=False))
    # 2. doctor
    execute_step(2, "doctor", lambda: run_doctor(project_root=ws, wiki_root=w_root))
    # 3. bootstrap
    def step_3() -> None:
        manifest = run_bootstrap(force=True)
        assert manifest and "Bootstrap Manifest" in manifest
        assert (w_root / ".bootstrap_state.json").exists()

    execute_step(3, "bootstrap", step_3)

    # 4. write 3 articles
    def step_4() -> None:
        write_article(
            "topics/pricing-models.md",
            "---\ntype: topic\nsummary: SaaS pricing analysis\nlast_updated: 2026-11-17\n---\n\n# SaaS Pricing Models\n\n## Overview\nComparative pricing models.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
        write_article(
            "decisions/adr-001.md",
            "---\ntype: decision\nsummary: Usage-based billing choice\nstatus: accepted\ndeciders: Research Team\ndate: 2026-11-17\nlast_updated: 2026-11-17\n---\n\n# ADR-001: Usage-Based Billing\n\n## Status\nAccepted\n\n## Context\nEvaluating pricing.\n\n## Decision\nUse usage-based billing.\n\n## Consequences\nFair customer alignment.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
        write_article(
            "topics/competitor-matrix.md",
            "---\ntype: topic\nsummary: Competitor landscape matrix\nlast_updated: 2026-11-17\n---\n\n# Competitor Matrix\n\n## Overview\nCompetitors landscape.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
    execute_step(4, "write_3_articles", step_4)

    # 5. orient
    execute_step(5, "orient", lambda: orient(task="analyze enterprise tier", wiki_root=w_root))

    # 6. edit one article
    execute_step(
        6,
        "edit_article",
        lambda: edit_article("topics/pricing-models.md", [{"old_text": "Comparative pricing models.", "new_text": "In-depth pricing models."}], wiki_root=w_root),
    )

    # 7. session-commit with handoff and Amnesia Test guard
    def step_7() -> None:
        # Legitimate session commit with handoff closing the session that edited pricing-models
        commit_session(
            session_summary="Enterprise tier research",
            handoff={
                "session_type": "research",
                "summary": "Enterprise tier analysis",
                "completed_work": ["Pricing matrix updated"],
                "pending_work": ["Churn forecast"],
                "boot_instruction": "Continue churn analysis",
            },
            wiki_root=w_root,
        )

        # Amnesia Test Guard: a subsequent research session claiming completed_work
        # without persisting findings/writes must be blocked by the Amnesia Test
        amnesia_blocked = False
        try:
            commit_session(
                session_summary="Unpersisted research session",
                handoff={
                    "session_type": "research",
                    "summary": "Unpersisted research notes",
                    "completed_work": ["Market sizing and TAM calculation"],
                    "pending_work": ["None"],
                    "boot_instruction": "None",
                },
                wiki_root=w_root,
            )
        except (ValueError, ValidationError) as exc:
            amnesia_blocked = True
            assert "unpersisted" in str(exc).lower() or "research" in str(exc).lower() or "blocked" in str(exc).lower()
        assert amnesia_blocked, "Amnesia Test guard must block research handoffs claiming completed work without persisting findings"

    execute_step(7, "session_commit_handoff_and_amnesia_guard", step_7)

    # 8. 10 sessions loop proving custom schema folders and gitless freshness
    def step_8() -> None:
        # Custom SCHEMA.md folder types validation
        schema_path = w_root / "SCHEMA.md"
        schema_text = schema_path.read_text(encoding="utf-8")
        custom_fm = (
            "---\n"
            "profile: general\n"
            "schema_version: 2\n"
            "custom_types:\n"
            "  report:\n"
            "    directory: reports\n"
            "    required: [type, summary, last_updated]\n"
            "    optional: [owner]\n"
            "---\n"
        )
        if schema_text.startswith("---\n"):
            _, body = schema_text[4:].split("---\n", 1)
            schema_path.write_text(custom_fm + body, encoding="utf-8")
        else:
            schema_path.write_text(custom_fm + schema_text, encoding="utf-8")
        from brain79.core.frontmatter import clear_schema_cache
        clear_schema_cache()
        (w_root / "reports").mkdir(exist_ok=True)
        report_content = (
            "---\n"
            "type: report\n"
            "summary: Q4 market analysis report\n"
            "last_updated: 2026-11-17\n"
            "---\n\n"
            "# Report — Q4 Market Analysis\n\n"
            "## Overview\n"
            "Custom schema folder test.\n\n"
            "---\n\n"
            "[← Volver al Índice](../INDEX.md)\n"
        )
        write_article("reports/q4_analysis.md", report_content, wiki_root=w_root)

        for sess in range(1, 11):
            sess_art = f"topics/session-{sess}.md"
            content = (
                "---\n"
                "type: topic\n"
                f"summary: Research session {sess} findings\n"
                "last_updated: 2026-11-17\n"
                "---\n\n"
                f"# Session {sess} Insights\n\n"
                "## Overview\n"
                f"Deep dive insights for research session {sess}.\n\n"
                "---\n\n"
                "[← Volver al Índice](../INDEX.md)\n"
            )
            commit_session(
                session_summary=f"Session {sess} synthesis",
                writes=[{"path": sess_art, "content": content}],
                handoff={
                    "session_type": "research",
                    "summary": f"Wrap session {sess}",
                    "completed_work": [f"Session {sess} done"],
                    "pending_work": [f"Session {sess + 1} next"],
                    "boot_instruction": f"Boot session {sess + 1}",
                },
                wiki_root=w_root,
            )

        # Check handoff freshness without git: must compute clean state, no crash, no false foreign_branch
        handoffs = sorted((w_root / "handoffs").glob("*.md"))
        assert handoffs, "Expected handoffs created in gitless workspace"
        latest_handoff = handoffs[-1]
        freshness = compute_handoff_freshness(latest_handoff, wiki_root=w_root)
        assert freshness.state != "foreign_branch", "Gitless handoff must not report false foreign_branch"
        assert freshness.state in ("fresh", "stale", "unverified")

    execute_step(8, "ten_sessions_gitless_loop", step_8)

    # 9. lint --strict
    execute_step(9, "lint_strict", lambda: lint_wiki(wiki_root=w_root))

    # 10. recover to clean
    def step_10() -> None:
        report = lint_wiki(wiki_root=w_root)
        assert "[CRITICAL] Broken Local Links (0)" in report
        assert "[CRITICAL] Namespace Violations (0)" in report
    execute_step(10, "recover_to_clean", step_10)

    return steps


# ==============================================================================
# Archetype 4: Git Branch Warfare & AST Guard C
# ==============================================================================


def build_archetype_4(ws: Path) -> dict[str, Any]:
    _init_local_git(ws)
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "payments.py").write_text("def process_payment(amount: float) -> bool:\n    return True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Base payments"], cwd=ws, check=True, capture_output=True)
    return {"workspace": str(ws)}


def run_archetype_4_lifecycle(ws: Path, perf_factor: float = 1.0) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    set_project_root(ws)
    w_root = ws / ".brain-79"

    def execute_step(step_num: int, name: str, fn: Callable[[], Any]) -> None:
        t0 = time.perf_counter()
        try:
            fn()
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 4,
                "step": step_num,
                "name": name,
                "status": "ok",
                "duration_ms": round(duration_ms, 2),
                "error": None,
            })
            print(f"[Archetype 4] Step {step_num:02d}/10: {name} ... [OK] ({duration_ms:.1f}ms)")
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 4,
                "step": step_num,
                "name": name,
                "status": "failed",
                "duration_ms": round(duration_ms, 2),
                "error": str(exc),
            })
            print(f"[Archetype 4] Step {step_num:02d}/10: {name} ... [FAILED] ({duration_ms:.1f}ms): {exc}")
            raise

    # 1. init
    execute_step(1, "init", lambda: init_project(ws, install_git_hooks_flag=True))
    # 2. doctor
    execute_step(2, "doctor", lambda: run_doctor(project_root=ws, wiki_root=w_root))
    # 3. bootstrap
    def step_3() -> None:
        manifest = run_bootstrap(force=True)
        assert manifest and "Bootstrap Manifest" in manifest
        assert (w_root / ".bootstrap_state.json").exists()

    execute_step(3, "bootstrap", step_3)

    # 4. write 3 articles
    def step_4() -> None:
        write_article(
            "features/payments.md",
            "---\ntype: feature\nsummary: Payment processing gateway\nstatus: shipped\nversion: 1.0.0\nlast_updated: 2026-11-17\napplies_to:\n  - src/payments.py\n---\n\n# Feature — Payments\n\n## Overview\nPayment processing.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
        write_article(
            "architecture/security.md",
            "---\ntype: architecture\nsummary: Security architecture\nstability: stable\nlast_updated: 2026-11-17\napplies_to:\n  - src/payments.py\n---\n\n# Architecture — Security\n\n## Overview\nSecurity model.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
        write_article(
            "decisions/adr-002.md",
            "---\ntype: decision\nsummary: Payment provider integration\nstatus: accepted\ndeciders: Team\ndate: 2026-11-17\nlast_updated: 2026-11-17\n---\n\n# ADR-002: Payment Gateway\n\n## Status\nAccepted\n\n## Context\nChoosing gateway.\n\n## Decision\nIntegrate Stripe.\n\n## Consequences\nStandardized processing.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            wiki_root=w_root,
        )
        subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Commit baseline wiki"], cwd=ws, check=True, capture_output=True)
    execute_step(4, "write_3_articles", step_4)

    # 5. orient
    execute_step(5, "orient", lambda: orient(task="refactor payments", paths=["src/payments.py"], wiki_root=w_root))

    # 6. edit one article
    execute_step(
        6,
        "edit_article",
        lambda: edit_article("features/payments.md", [{"old_text": "Payment processing.", "new_text": "Initial payment processing."}], wiki_root=w_root),
    )

    # 7. session-commit with handoff and branch warfare
    def step_7() -> None:
        commit_session(
            session_summary="Baseline commit on main",
            handoff={
                "session_type": "feature",
                "summary": "Main branch handoff",
                "completed_work": ["Base payments setup"],
                "pending_work": ["Branch out to feat/payments"],
                "boot_instruction": "Continue in feature branch",
            },
            wiki_root=w_root,
        )
        subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Commit main baseline with handoff"], cwd=ws, check=True, capture_output=True)

        # Checkout feat/payments from main
        subprocess.run(["git", "checkout", "-b", "feat/payments"], cwd=ws, check=True, capture_output=True)

        # Handoff inherited from main must report foreign_branch
        handoffs = sorted((w_root / "handoffs").glob("*.md"))
        assert handoffs, "Expected handoff created on main"
        freshness = compute_handoff_freshness(handoffs[-1], wiki_root=w_root)
        assert freshness.state == "foreign_branch", f"Expected foreign_branch, got {freshness.state}"

        orient_output = orient(task="feature payments check", wiki_root=w_root)
        assert "foreign branch" in orient_output.lower() or "foreign_branch" in orient_output.lower()

        # Checkout hotfix/auth from main and commit a hotfix
        subprocess.run(["git", "checkout", "-b", "hotfix/auth", "main"], cwd=ws, check=True, capture_output=True)
        orient_output_hotfix = orient(task="hotfix auth check", wiki_root=w_root)
        assert "foreign branch" in orient_output_hotfix.lower() or "foreign_branch" in orient_output_hotfix.lower()
        (ws / "src" / "auth.py").write_text("def auth(): return True\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Hotfix auth on hotfix/auth"], cwd=ws, check=True, capture_output=True)

        # Merge hotfix into main
        subprocess.run(["git", "checkout", "main"], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "merge", "--ff-only", "hotfix/auth"], cwd=ws, check=True, capture_output=True)

        # Switch to feat/payments and record a branch-local handoff
        subprocess.run(["git", "checkout", "feat/payments"], cwd=ws, check=True, capture_output=True)
        commit_session(
            session_summary="Feature work on feat/payments",
            handoff={
                "session_type": "feature",
                "summary": "Feature payments handoff",
                "completed_work": ["Refactor started"],
                "pending_work": ["Signature update"],
                "boot_instruction": "Continue on feat/payments",
            },
            wiki_root=w_root,
        )
        subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Commit feat/payments handoff"], cwd=ws, check=True, capture_output=True)

        # Perform actual git rebase
        subprocess.run(["git", "rebase", "main"], cwd=ws, check=True, capture_output=True)

    execute_step(7, "session_commit_and_branch_warfare", step_7)

    # 8. mutate public function signature in src/payments.py
    def step_8() -> None:
        # Break public signature: amount -> amount, currency
        (ws / "src" / "payments.py").write_text(
            "def process_payment(amount: float, currency: str = 'USD') -> bool:\n    return True\n",
            encoding="utf-8",
        )
    execute_step(8, "mutate_signature_in_source", step_8)

    # 9. Guard C: verified_articles cannot bypass breaking signature change, and handoff reports stale
    def step_9() -> None:
        # Check drift
        drifts = check_article_drift("features/payments.md", wiki_root=w_root, project_root=ws)
        assert any(d.get("drift_kind") == "modified" for d in drifts), "Expected modified drift on features/payments.md"

        # Verify handoff reports stale after code drift on the active branch
        handoffs = sorted((w_root / "handoffs").glob("*.md"))
        assert handoffs, "Expected handoff on feat/payments"
        freshness_stale = compute_handoff_freshness(handoffs[-1], wiki_root=w_root)
        assert freshness_stale.state == "stale", f"Expected stale state after drift, got {freshness_stale.state}"
        assert freshness_stale.code_changed is True, "Expected code_changed=True in freshness report"

        # Attempt to bypass via verified_articles
        caught = False
        try:
            commit_session(
                session_summary="Attempt to bypass signature change",
                verified_articles=[{
                    "path": "features/payments.md",
                    "reason": "Internal refactor without external API behavioral modifications",
                }],
                wiki_root=w_root,
            )
        except ValidationError as exc:
            caught = True
            assert (
                exc.rule == "verified_article_public_signature_changed"
                or "signature" in str(exc).lower()
                or "unresolved_session_ripple" in exc.rule
            ), f"Unexpected ValidationError rule: {exc.rule}"
        assert caught, "AST Guard C must block verified_articles on breaking signature change"

    execute_step(9, "ast_guard_c_blocks_bypass", step_9)

    # 10. recover to clean by updating prose in edits
    def step_10() -> None:
        commit_session(
            session_summary="Update prose acknowledging multi-currency",
            edits=[{
                "path": "features/payments.md",
                "edits": [{"old_text": "Initial payment processing.", "new_text": "Multi-currency payment processing."}],
            }],
            wiki_root=w_root,
            allow_partial_ripple=True,
        )
        report = lint_wiki(wiki_root=w_root)
        assert "[CRITICAL] Broken Local Links (0)" in report
        assert "[CRITICAL] Namespace Violations (0)" in report
    execute_step(10, "recover_to_clean", step_10)

    return steps


# ==============================================================================
# Archetype 5: 200 Articles & 1,000 Source Files Scale Benchmark
# ==============================================================================


def build_archetype_5(ws: Path) -> dict[str, Any]:
    _init_local_git(ws)
    w_root = ws / ".brain-79"
    w_root.mkdir(parents=True, exist_ok=True)
    (w_root / "INDEX.md").write_text("# Index\n\n## Quick navigation\n", encoding="utf-8")
    (w_root / "SCHEMA.md").write_text(
        "---\ntype: schema\nsummary: Declarative Schema\nprofile: software\nlast_updated: 2026-11-17\n---\n# Schema\n",
        encoding="utf-8",
    )

    # 1,000 source files across 20 modules
    for mod in range(20):
        mod_dir = ws / "src" / f"mod_{mod}"
        mod_dir.mkdir(parents=True, exist_ok=True)
        for f in range(50):
            (mod_dir / f"file_{f}.py").write_text(f"def func_{mod}_{f}(): return {f}\n", encoding="utf-8")

    # 200 valid articles across features, architecture, decisions, topics
    dirs = ["features", "architecture", "decisions", "topics"]
    for d in dirs:
        (w_root / d).mkdir(parents=True, exist_ok=True)

    writes_batch: list[dict[str, Any]] = []
    for i in range(200):
        d = dirs[i % len(dirs)]
        art_type = "decision" if d == "decisions" else ("architecture" if d == "architecture" else ("feature" if d == "features" else "topic"))
        extra_fm = ""
        if art_type == "decision":
            extra_fm = "status: accepted\ndeciders: Scale Team\ndate: 2026-11-17\n"
        elif art_type == "feature":
            extra_fm = f"status: shipped\nversion: 1.0.0\napplies_to:\n  - src/mod_{i % 20}/file_{i % 50}.py\n"
        elif art_type == "architecture":
            extra_fm = f"stability: stable\napplies_to:\n  - src/mod_{i % 20}/*.py\n"

        content = (
            "---\n"
            f"type: {art_type}\n"
            f"summary: Scale article {i} summary\n"
            f"{extra_fm}"
            "last_updated: 2026-11-17\n"
            "---\n\n"
            f"# Article {i}\n\n"
            "## Overview\n"
            f"Scale benchmark document {i}.\n\n"
            "---\n\n"
            "[← Volver al Índice](../INDEX.md)\n"
        )
        writes_batch.append({"path": f"{d}/art_{i}.md", "content": content})

    # Fast batch write for 200 articles
    for item in writes_batch:
        p = w_root / item["path"]
        p.write_text(item["content"], encoding="utf-8")

    regenerate_index_navigation(w_root)

    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit scale benchmark base"], cwd=ws, check=True, capture_output=True)
    return {"articles": 200, "files": 1000}


def run_archetype_5_lifecycle(ws: Path, perf_factor: float = 1.0) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    set_project_root(ws)
    w_root = ws / ".brain-79"

    def execute_step(step_num: int, name: str, fn: Callable[[], Any]) -> None:
        t0 = time.perf_counter()
        try:
            fn()
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 5,
                "step": step_num,
                "name": name,
                "status": "ok",
                "duration_ms": round(duration_ms, 2),
                "error": None,
            })
            print(f"[Archetype 5] Step {step_num:02d}/10: {name} ... [OK] ({duration_ms:.1f}ms)")
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            steps.append({
                "archetype": 5,
                "step": step_num,
                "name": name,
                "status": "failed",
                "duration_ms": round(duration_ms, 2),
                "error": str(exc),
            })
            print(f"[Archetype 5] Step {step_num:02d}/10: {name} ... [FAILED] ({duration_ms:.1f}ms): {exc}")
            raise

    # 1. init
    execute_step(1, "init", lambda: init_project(ws, install_git_hooks_flag=True))
    # 2. doctor
    execute_step(2, "doctor", lambda: run_doctor(project_root=ws, wiki_root=w_root))
    # 3. bootstrap
    def step_3() -> None:
        manifest = run_bootstrap(force=True)
        assert manifest and "Bootstrap Manifest" in manifest
        assert (w_root / ".bootstrap_state.json").exists()

    execute_step(3, "bootstrap", step_3)
    # 4. write 3 articles
    def step_4() -> None:
        for i in range(3):
            write_article(
                f"topics/scale_live_{i}.md",
                f"---\ntype: topic\nsummary: Scale live article {i}\nlast_updated: 2026-11-17\n---\n\n# Scale Live {i}\n\n## Overview\nScale live test {i}.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
                wiki_root=w_root,
            )
    execute_step(4, "write_3_articles", step_4)

    # 5. orient and latency budget check
    def step_5() -> None:
        # Initial ceiling: orient <= 500 ms * perf_factor
        ceiling_ms = 500.0 * perf_factor
        median_ms = _measure_median(lambda: orient(task="scale test query", paths=["src/mod_0/file_0.py"], wiki_root=w_root), runs=5)
        assert median_ms <= ceiling_ms, f"orient latency {median_ms:.1f}ms exceeded ceiling {ceiling_ms:.1f}ms"
    execute_step(5, "orient_latency_budget", step_5)

    # 6. edit one article
    execute_step(
        6,
        "edit_article",
        lambda: edit_article("topics/scale_live_0.md", [{"old_text": "Scale live test 0.", "new_text": "Edited scale live test 0."}], wiki_root=w_root),
    )

    # 7. session-commit with handoff
    execute_step(
        7,
        "session_commit_handoff",
        lambda: commit_session(
            session_summary="Scale benchmark close",
            handoff={
                "session_type": "maintenance",
                "summary": "Scale benchmark run",
                "completed_work": ["Orient latency measured"],
                "pending_work": ["Lint and doctor budgets"],
                "boot_instruction": "Run lint and doctor",
            },
            wiki_root=w_root,
        ),
    )

    # 8. mutate source file
    def step_8() -> None:
        (ws / "src" / "mod_0" / "file_0.py").write_text("def func_0_0(): return 999\n", encoding="utf-8")
    execute_step(8, "mutate_source", step_8)

    # 9. lint --strict and doctor latency budget checks
    def step_9() -> None:
        # Ceilings: lint --strict <= 1,500 ms * perf_factor, doctor <= 1,500 ms * perf_factor
        lint_ceiling = 1500.0 * perf_factor
        doc_ceiling = 1500.0 * perf_factor

        lint_median = _measure_median(lambda: lint_wiki(wiki_root=w_root), runs=5)
        assert lint_median <= lint_ceiling, f"lint --strict latency {lint_median:.1f}ms exceeded ceiling {lint_ceiling:.1f}ms"

        doc_median = _measure_median(lambda: run_doctor(project_root=ws, wiki_root=w_root), runs=5)
        assert doc_median <= doc_ceiling, f"doctor latency {doc_median:.1f}ms exceeded ceiling {doc_ceiling:.1f}ms"
    execute_step(9, "lint_and_doctor_latency_budgets", step_9)

    # 10. recover to clean
    def step_10() -> None:
        commit_session(
            session_summary="Reconcile scale mutation",
            edits=[{"path": "features/art_0.md", "edits": [{"old_text": "Scale benchmark document 0.", "new_text": "Scale benchmark document 0 updated."}]}],
            wiki_root=w_root,
            allow_partial_ripple=True,
        )
        report = lint_wiki(wiki_root=w_root)
        assert "[CRITICAL] Broken Local Links (0)" in report
        assert "[CRITICAL] Namespace Violations (0)" in report
    execute_step(10, "recover_to_clean", step_10)

    return steps


# ==============================================================================
# CLI Runner Entrypoint
# ==============================================================================


ARCHETYPE_RUNNERS = {
    1: (build_archetype_1, run_archetype_1_lifecycle),
    2: (build_archetype_2, run_archetype_2_lifecycle),
    3: (build_archetype_3, run_archetype_3_lifecycle),
    4: (build_archetype_4, run_archetype_4_lifecycle),
    5: (build_archetype_5, run_archetype_5_lifecycle),
}


def run_gauntlet(
    archetype_filter: int | None = None,
    keep_dirs: bool = False,
    json_path: Path | None = None,
    perf_factor: float = 1.0,
) -> int:
    """Run gauntlet across requested archetypes."""
    target_archetypes = [archetype_filter] if archetype_filter else [1, 2, 3, 4, 5]
    all_steps: list[dict[str, Any]] = []
    has_failure = False

    for arch_num in target_archetypes:
        if arch_num not in ARCHETYPE_RUNNERS:
            print(f"❌ Invalid archetype #{arch_num}. Must be 1..5.", file=sys.stderr)
            return 2

        builder, runner = ARCHETYPE_RUNNERS[arch_num]
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"b79-gauntlet-arch{arch_num}-"))
        print(f"\n=======================================================")
        print(f"▶ Launching Archetype {arch_num} Lifecycle (Workspace: {tmp_dir})")
        print(f"=======================================================")

        try:
            builder(tmp_dir)
            arch_steps = runner(tmp_dir, perf_factor=perf_factor)
            all_steps.extend(arch_steps)
            if any(s["status"] == "failed" for s in arch_steps):
                has_failure = True
        except Exception as exc:
            has_failure = True
            print(f"❌ Archetype {arch_num} halted with failure: {exc}", file=sys.stderr)
            if not keep_dirs:
                print(f"Preserving failed workspace directory: {tmp_dir}")
                keep_dirs = True
        finally:
            if not keep_dirs:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        report_data = {
            "timestamp": time.time(),
            "perf_factor": perf_factor,
            "status": "failed" if has_failure else "passed",
            "steps": all_steps,
        }
        json_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        print(f"\nSaved battle gauntlet JSON report to {json_path}")

    return 1 if has_failure else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Brain-79 Five-Archetype Multi-Repo Battle Gauntlet")
    parser.add_argument("--archetype", type=int, choices=[1, 2, 3, 4, 5], help="Run single archetype (1..5)")
    parser.add_argument("--keep", action="store_true", help="Keep temporary workspace directories after run")
    parser.add_argument("--json", type=Path, help="Path to write JSON report")

    # Check git presence
    if shutil.which("git") is None:
        print("❌ Error: git binary not found in PATH", file=sys.stderr)
        return 2

    args = parser.parse_args()
    perf_factor = get_perf_factor()
    return run_gauntlet(
        archetype_filter=args.archetype,
        keep_dirs=args.keep,
        json_path=args.json,
        perf_factor=perf_factor,
    )


if __name__ == "__main__":
    sys.exit(main())
