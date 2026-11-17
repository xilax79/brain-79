#!/usr/bin/env python3
"""End-to-end smoke test suite for Brain-79 using real AI agent (pi -p).

Executes 3 canonical pre-merge scenarios:
1. Zero-code research in non-git directory (--profile general) — SaaS pricing models.
2. Ephemeral consultation / read-only chat — True No-Op.
3. Software project with Git (--profile software) — SQLite WAL ADR.

Evaluates the 'Zero-Retry MCP Metric':
Every call to brain79 tools must succeed on the first attempt without schema rejection
or validation aborts.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

MODEL = "gemini-3.8-flash:low"


def find_agent_cli() -> str | None:
    """Detect available real agent CLI (pi or agy)."""
    if shutil.which("pi"):
        return "pi"
    if shutil.which("agy"):
        return "agy"
    return None


def get_agent_cmd(prompt: str) -> list[str]:
    """Build command line for running the agent non-interactively."""
    cli = find_agent_cli()
    if cli == "pi":
        return ["pi", "--mcp-project-servers", "allow", "--models", MODEL, "-p", prompt]
    if cli == "agy":
        return ["agy", "--model", MODEL, "-p", prompt]
    raise RuntimeError("No agent CLI found")


def find_latest_session_for_dir(target_dir: Path) -> Path | None:
    """Find the latest pi session .jsonl for the given working directory."""
    sessions_root = Path.home() / ".pi" / "agent" / "sessions"
    if not sessions_root.is_dir():
        return None

    matching_dirs = sorted(
        [d for d in sessions_root.iterdir() if target_dir.name in d.name and d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not matching_dirs:
        return None

    all_session_files: list[Path] = []
    for d in matching_dirs:
        all_session_files.extend(d.glob("*.jsonl"))

    if not all_session_files:
        return None

    all_session_files.sort(key=lambda p: p.stat().st_mtime)
    return all_session_files[-1]


def check_mcp_zero_retry(session_file: Path) -> list[str]:
    """Inspect session log and return any failed brain79 MCP tool calls."""
    failures: list[str] = []
    for line in session_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue

        if d.get("type") == "message" and d.get("message", {}).get("role") == "toolResult":
            tool_name = str(d["message"].get("toolName", ""))
            is_error = bool(d["message"].get("isError", False))
            content = d["message"].get("content", [])
            text = content[0].get("text", "") if content else ""

            # Check for brain79 tool failures across all server.py error patterns
            if "brain79" in tool_name or tool_name.startswith("brain79_"):
                error_markers = (
                    "Error:",
                    "Error reading",
                    "Validation Error:",
                    "Commit Validation Failed:",
                    "Commit Aborted:",
                    "Failed to call tool",
                    "Bootstrap Error:",
                    "Navigation Error:",
                    "Migration Error:",
                    "> ❌ Error:",
                )
                if is_error or any(marker in text for marker in error_markers):
                    failures.append(f"{tool_name}: {text[:140]}")
    return failures


def run_scenario_1() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 1: Zero-code research in --profile general (No Git)")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-research-"))
    try:
        # 1. Initialize general profile wiki
        subprocess.run(
            ["brain79", "init", "--profile", "general", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
        )

        prompt = (
            "Orient yourself in the project. We analyzed multi-tenant SaaS pricing models: "
            "tiered subscription with usage-based overage provides optimal margin compared to flat-rate. "
            "Document this research into the wiki and conclude the session with a handoff."
        )

        print(f"Running agent in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            ["pi", "--mcp-project-servers", "allow", "--models", MODEL, "-p", prompt],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")

        # 2. Check artifacts
        topics = list((tmp / ".brain-79" / "topics").glob("*.md"))
        handoffs = list((tmp / ".brain-79" / "handoffs").glob("*.md"))

        print(f"Artifacts: {len(topics)} topic(s), {len(handoffs)} handoff(s)")
        assert len(topics) >= 1, "Failed: Expected at least 1 topic article in topics/"
        assert len(handoffs) >= 1, "Failed: Expected at least 1 handoff in handoffs/"

        # 3. Check strict lint
        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert lint_res.returncode == 0, f"Lint failed:\n{lint_res.stdout}"
        print("Strict lint: [Status: OK]")

        # 4. Check zero-retry MCP metric
        session_file = find_latest_session_for_dir(tmp)
        if session_file:
            failures = check_mcp_zero_retry(session_file)
            assert not failures, "Zero-retry violation in brain79 MCP calls:\n" + "\n".join(failures)
            print("Zero-Retry MCP Metric: ✅ PASS (0 tool errors/retries)")
        else:
            print("Warning: Could not locate session file for zero-retry audit")

        # Scenario 2 uses the same directory to test No-Op on an existing project!
        run_scenario_2(tmp)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_scenario_2(tmp: Path) -> None:
    print("\n" + "=" * 70)
    print("▶ Scenario 2: Ephemeral consultation / read-only chat (True No-Op)")
    print("=" * 70)

    prior_topics = sorted(p.name for p in (tmp / ".brain-79" / "topics").glob("*.md"))

    prompt = (
        "Orient yourself in the project. Just checking in to see what articles are currently in the wiki. "
        "Update the wiki if needed."
    )

    print(f"Running consultative turn in {tmp.name}...")
    t0 = time.time()
    res = subprocess.run(
        ["pi", "--mcp-project-servers", "allow", "--models", MODEL, "-p", prompt],
        cwd=tmp,
        capture_output=True,
        text=True,
        timeout=60,
    )
    duration = time.time() - t0
    print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")

    post_topics = sorted(p.name for p in (tmp / ".brain-79" / "topics").glob("*.md"))

    assert prior_topics == post_topics, f"Failed: No-Op violated, synthetic topics created: {set(post_topics) - set(prior_topics)}"
    print("No-Op check: ✅ PASS (0 synthetic topics created)")

    lint_res = subprocess.run(
        ["brain79", "lint", "--strict", "--project-root", str(tmp)],
        capture_output=True,
        text=True,
    )
    assert lint_res.returncode == 0, f"Lint failed:\n{lint_res.stdout}"
    print("Strict lint: [Status: OK]")

    session_file = find_latest_session_for_dir(tmp)
    if session_file:
        failures = check_mcp_zero_retry(session_file)
        assert not failures, "Zero-retry violation in brain79 MCP calls:\n" + "\n".join(failures)
        print("Zero-Retry MCP Metric: ✅ PASS (0 tool errors/retries)")


def run_scenario_3() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 3: Software project with Git (--profile software)")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-software-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
        )

        prompt = (
            "Orient yourself. We decided to adopt SQLite with WAL mode for local concurrency and created the module src/db.py. "
            "Record this architectural decision and update the wiki, closing the session."
        )

        print(f"Running agent in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            ["pi", "--mcp-project-servers", "allow", "--models", MODEL, "-p", prompt],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")

        decisions = list((tmp / ".brain-79" / "decisions").glob("*.md"))
        print(f"Artifacts: {len(decisions)} decision ADR(s)")
        assert len(decisions) >= 1, "Failed: Expected at least 1 decision ADR in decisions/"

        index_text = (tmp / ".brain-79" / "INDEX.md").read_text(encoding="utf-8")
        assert "decisions/" in index_text, "Failed: ADR not registered in INDEX.md Quick navigation"
        print("INDEX.md navigation sync: ✅ PASS")

        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert lint_res.returncode == 0, f"Lint failed:\n{lint_res.stdout}"
        print("Strict lint: [Status: OK]")

        session_file = find_latest_session_for_dir(tmp)
        if session_file:
            failures = check_mcp_zero_retry(session_file)
            assert not failures, "Zero-retry violation in brain79 MCP calls:\n" + "\n".join(failures)
            print("Zero-Retry MCP Metric: ✅ PASS (0 tool errors/retries)")

        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_scenario_4() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 4: Holistic ripple and drift gate verification (--profile software)")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-ripple-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=tmp, check=True, capture_output=True)

        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
        )

        wiki = tmp / ".brain-79"
        src_core = tmp / "src" / "core"
        src_core.mkdir(parents=True, exist_ok=True)
        (src_core / "auth.py").write_text("def authenticate(): return True\n", encoding="utf-8")

        # Create leaf feature article
        (wiki / "features").mkdir(exist_ok=True)
        (wiki / "features" / "auth.md").write_text(
            "---\ntype: feature\nsummary: Authentication service\nstatus: shipped\nversion: 1.0.0\nlast_updated: 2026-11-12\napplies_to:\n  - src/core/auth.py\n---\n\n# Feature — Authentication\n\n## Overview\nAuth service details.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            encoding="utf-8",
        )

        # Create umbrella architecture article
        (wiki / "architecture").mkdir(exist_ok=True)
        (wiki / "architecture" / "overview.md").write_text(
            "---\ntype: architecture\nsummary: Core system architecture\nstability: stable\nlast_updated: 2026-11-12\napplies_to:\n  - .brain-79/features/*.md\n  - src/core/*.py\n---\n\n# Architecture — Overview\n\n## Overview\nSystem architecture details.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            encoding="utf-8",
        )

        from brain79.core.migration import migrate_wiki
        from brain79.core.navigation import regenerate_index_navigation
        regenerate_index_navigation(wiki)
        migrate_wiki(wiki, dry_run=False)

        subprocess.run(["git", "add", "."], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial baseline"], cwd=tmp, check=True, capture_output=True)

        # Modify governed code file
        (src_core / "auth.py").write_text(
            "def authenticate(): return True\ndef verify_token(token: str) -> bool: return True\n",
            encoding="utf-8",
        )

        prompt = (
            "Orient yourself. We added token verification to src/core/auth.py. "
            "Update the wiki and wrap up the session using session commit."
        )

        print(f"Running agent in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            ["pi", "--mcp-project-servers", "allow", "--models", MODEL, "-p", prompt],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")

        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert lint_res.returncode == 0, f"Lint failed:\n{lint_res.stdout}"
        print("Strict lint: [Status: OK]")

        # Check zero-retry MCP metric
        session_file = find_latest_session_for_dir(tmp)
        if session_file:
            failures = check_mcp_zero_retry(session_file)
            assert not failures, "Zero-retry violation in brain79 MCP calls:\n" + "\n".join(failures)
            print("Zero-Retry MCP Metric: ✅ PASS (0 tool errors/retries)")

        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_scenario_5() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 5: Live-Agent Recovery from unresolved_session_ripple")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-recovery-ripple-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=tmp, check=True, capture_output=True)

        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
        )

        wiki = tmp / ".brain-79"
        src_core = tmp / "src" / "core"
        src_core.mkdir(parents=True, exist_ok=True)
        (src_core / "auth.py").write_text("def authenticate(): return True\n", encoding="utf-8")

        # Create leaf feature article
        (wiki / "features").mkdir(exist_ok=True)
        (wiki / "features" / "auth.md").write_text(
            "---\ntype: feature\nsummary: Authentication service\nstatus: shipped\nversion: 1.0.0\nlast_updated: 2026-11-12\napplies_to:\n  - src/core/auth.py\n---\n\n# Feature — Authentication\n\n## Overview\nAuth service details.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            encoding="utf-8",
        )

        # Create umbrella architecture article
        (wiki / "architecture").mkdir(exist_ok=True)
        (wiki / "architecture" / "overview.md").write_text(
            "---\ntype: architecture\nsummary: Core system architecture\nstability: stable\nlast_updated: 2026-11-12\napplies_to:\n  - .brain-79/features/*.md\n  - src/core/*.py\n---\n\n# Architecture — Overview\n\n## Overview\nSystem architecture details.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            encoding="utf-8",
        )

        from brain79.core.migration import migrate_wiki
        from brain79.core.navigation import regenerate_index_navigation

        regenerate_index_navigation(wiki)
        migrate_wiki(wiki, dry_run=False)

        subprocess.run(["git", "add", "."], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial baseline"], cwd=tmp, check=True, capture_output=True)

        # Modify leaf file without updating umbrella article
        (src_core / "auth.py").write_text(
            "def authenticate(): return True\ndef revoke_token(token: str) -> bool: return True\n",
            encoding="utf-8",
        )

        # Prompt must NOT mention unresolved_session_ripple or the fix
        prompt = (
            "Orient yourself in the project. We refactored src/core/auth.py to add token revocation. "
            "Update the project documentation for this change and wrap up the session using session commit."
        )

        agent_cmd = get_agent_cmd(prompt)
        print(f"Running agent ({find_agent_cli()}) in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            agent_cmd,
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=180,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")

        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert lint_res.returncode == 0, f"Lint failed:\n{lint_res.stdout}"
        print("Strict lint: [Status: OK]")

        # Check recovery in session log
        session_file = find_latest_session_for_dir(tmp)
        if session_file:
            log_text = session_file.read_text(encoding="utf-8")
            if "unresolved_session_ripple" in log_text:
                print("Observed expected initial rejection 'unresolved_session_ripple' and subsequent recovery: ✅ PASS")
            else:
                print("Note: Agent completed cleanly without triggering ripple rejection or already resolved it upfront.")

        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_scenario_6() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 6: Live-Agent Recovery from duplicate_governance_target")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-recovery-duplicate-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=tmp, check=True, capture_output=True)

        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
        )

        wiki = tmp / ".brain-79"
        src_core = tmp / "src" / "core"
        src_core.mkdir(parents=True, exist_ok=True)
        (src_core / "auth.py").write_text("def authenticate(): return True\n", encoding="utf-8")
        (src_core / "user.py").write_text("def get_user(): return {}\n", encoding="utf-8")

        # Create existing feature article governing auth.py
        (wiki / "features").mkdir(exist_ok=True)
        (wiki / "features" / "auth.md").write_text(
            "---\ntype: feature\nsummary: Authentication service\nstatus: shipped\nversion: 1.0.0\nlast_updated: 2026-11-12\napplies_to:\n  - src/core/auth.py\n---\n\n# Feature — Authentication\n\n## Overview\nAuth service details.\n\n---\n\n[← Volver al Índice](../INDEX.md)\n",
            encoding="utf-8",
        )

        from brain79.core.migration import migrate_wiki
        from brain79.core.navigation import regenerate_index_navigation

        regenerate_index_navigation(wiki)
        migrate_wiki(wiki, dry_run=False)

        subprocess.run(["git", "add", "."], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial baseline"], cwd=tmp, check=True, capture_output=True)

        # Prompt must NOT mention duplicate_governance_target or the fix
        prompt = (
            "Orient yourself in the project. We created authentication helpers and need a new article "
            "features/auth_helpers.md governing src/core/auth.py. Document it and wrap up the session using session commit."
        )

        agent_cmd = get_agent_cmd(prompt)
        print(f"Running agent ({find_agent_cli()}) in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            agent_cmd,
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=180,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")

        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
        )
        assert lint_res.returncode == 0, f"Lint failed:\n{lint_res.stdout}"
        print("Strict lint: [Status: OK]")

        # Check recovery in session log
        session_file = find_latest_session_for_dir(tmp)
        if session_file:
            log_text = session_file.read_text(encoding="utf-8")
            if "duplicate_governance_target" in log_text:
                print("Observed expected initial rejection 'duplicate_governance_target' and subsequent recovery: ✅ PASS")
            else:
                print("Note: Agent resolved target disambiguation cleanly.")

        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    cli = find_agent_cli()
    if not cli:
        print("❌ SKIPPED (exit 77): Neither 'pi' nor 'agy' agent CLI was found in PATH.")
        return 77

    print("=" * 70)
    print(f"🚀 Brain-79 Pre-Merge E2E Smoke Suite (Agent: {cli} | Model: {MODEL})")
    print("=" * 70)

    import argparse

    parser = argparse.ArgumentParser(description="Brain-79 E2E Live-Agent Smoke Suite")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3, 4, 5, 6], help="Run specific scenario")
    args = parser.parse_args()

    scenarios = {
        1: run_scenario_1,
        3: run_scenario_3,
        4: run_scenario_4,
        5: run_scenario_5,
        6: run_scenario_6,
    }

    try:
        if args.scenario:
            if args.scenario == 2:
                print("Scenario 2 runs as part of Scenario 1.")
                scenarios[1]()
            else:
                scenarios[args.scenario]()
        else:
            run_scenario_1()
            run_scenario_3()
            run_scenario_4()
            run_scenario_5()
            run_scenario_6()

        print("\n" + "=" * 70)
        print("🎉 ALL TESTED E2E SCENARIOS PASSED WITH LIVE-AGENT VERIFICATION!")
        print("=" * 70)
        return 0
    except Exception as exc:
        print(f"\n❌ E2E SMOKE SUITE FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
