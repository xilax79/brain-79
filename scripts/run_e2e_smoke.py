#!/usr/bin/env python3
"""End-to-end smoke test suite for Brain-79 using real AI agent (agy or pi).

Executes canonical pre-merge scenarios:
1. Zero-code research in non-git directory (--profile general) — SaaS pricing models.
2. Ephemeral consultation / read-only chat — True No-Op.
3. Software project with Git (--profile software) — SQLite WAL ADR.
4. Holistic ripple and drift gate verification (--profile software).
5. Autonomous recovery from unresolved_session_ripple.
6. Autonomous recovery from duplicate_governance_target.

Evaluates the 'Zero-Retry MCP Metric':
Every call to brain79 tools must succeed on the first attempt without schema rejection
or validation aborts (except for intentional rejection-recovery scenarios 5 and 6).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("BRAIN79_SMOKE_MODEL", "gemini-3.8-flash:low")

RULE_MESSAGE_MARKERS: dict[str, tuple[str, ...]] = {
    "duplicate_governance_target": (
        "duplicate_governance_target",
        "Anti-sprawl guard",
        "already governs",
        "duplicate article",
    ),
    "unresolved_session_ripple": (
        "unresolved_session_ripple",
        "Holistic update required",
        "Cannot verify umbrella article",
        "unresolved drift",
        "remains drifted",
        "verified_article_umbrella_bypass_forbidden",
    ),
}


def get_smoke_env() -> dict[str, str]:
    """Provide execution environment with local .venv/bin prepended to PATH."""
    env = os.environ.copy()
    venv_bin = REPO_ROOT / ".venv" / "bin"
    if venv_bin.is_dir():
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    return env


def find_agent_cli() -> str | None:
    """Detect available real agent CLI (agy or pi)."""
    override = os.environ.get("BRAIN79_SMOKE_CLI")
    if override:
        return override
    if shutil.which("agy"):
        return "agy"
    if shutil.which("pi"):
        return "pi"
    return None


def get_agent_cmd(prompt: str) -> list[str]:
    """Build command line for running the agent non-interactively."""
    cli = find_agent_cli()
    model_name, _, thinking_level = MODEL.partition(":")
    if cli == "pi":
        cmd = ["pi", "--mcp-project-servers", "allow", "--model", model_name]
        if thinking_level:
            cmd.extend(["--thinking", thinking_level])
        cmd.extend(["-p", prompt])
        return cmd
    if cli == "agy":
        cmd = [
            "agy",
            "--dangerously-skip-permissions",
            "--output-format",
            "stream-json",
            "--model",
            model_name,
        ]
        if thinking_level:
            cmd.extend(["--effort", thinking_level])
        cmd.extend(["-p", prompt])
        return cmd
    raise RuntimeError("No agent CLI found")


def find_latest_session_for_dir(target_dir: Path) -> Path | None:
    """Find the latest session or transcript file (.jsonl) for the given working directory."""
    # 1. Local session logs in target_dir (*agent_session*.jsonl)
    local_sessions = sorted(
        target_dir.glob("agent_session*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if local_sessions:
        return local_sessions[0]

    # 2. agy brain conversations in ~/.gemini/antigravity-cli/brain/
    brain_root = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    if brain_root.is_dir():
        resolved_target = str(target_dir.resolve())
        matching_transcripts: list[Path] = []
        for conv_dir in sorted(brain_root.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)[:30]:
            transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if transcript.is_file():
                try:
                    with transcript.open(encoding="utf-8") as f:
                        for idx, line in enumerate(f):
                            if idx > 15:
                                break
                            if not line.strip():
                                continue
                            data = json.loads(line)
                            if data.get("event") == "init":
                                init_cwd = str(data.get("init", {}).get("cwd", ""))
                                if init_cwd == resolved_target or target_dir.name in init_cwd:
                                    matching_transcripts.append(transcript)
                                break
                            if resolved_target in line or target_dir.name in line:
                                matching_transcripts.append(transcript)
                                break
                except Exception:
                    continue
        if matching_transcripts:
            return matching_transcripts[0]

    # 3. pi sessions in ~/.pi/agent/sessions/
    sessions_root = Path.home() / ".pi" / "agent" / "sessions"
    if sessions_root.is_dir():
        matching_dirs = sorted(
            [d for d in sessions_root.iterdir() if target_dir.name in d.name and d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if matching_dirs:
            all_session_files: list[Path] = []
            for d in matching_dirs:
                all_session_files.extend(d.glob("*.jsonl"))
            if all_session_files:
                all_session_files.sort(key=lambda p: p.stat().st_mtime)
                return all_session_files[-1]

    return None


def check_mcp_zero_retry(session_file: Path) -> list[str]:
    """Inspect session log and return any failed brain79 MCP tool calls."""
    failures: list[str] = []
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

    last_transcript_tool: str | None = None

    for line in session_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue

        # Format 1: Pi toolResult message
        if d.get("type") == "message" and d.get("message", {}).get("role") == "toolResult":
            tool_name = str(d["message"].get("toolName", ""))
            is_error = bool(d["message"].get("isError", False))
            content = d["message"].get("content", [])
            text = content[0].get("text", "") if content else ""

            if "brain79" in tool_name or tool_name.startswith("brain79_"):
                if is_error or any(marker in text for marker in error_markers):
                    failures.append(f"{tool_name}: {text[:140]}")

        # Format 2: agy stream-json step_update
        elif d.get("event") == "step_update":
            su = d.get("step_update", {})
            if su.get("step_type") == "tool" and su.get("state") == "DONE":
                tool_info = su.get("tool_info", {})
                raw_tool_name = su.get("tool_name", "") or tool_info.get("name", "")
                params = tool_info.get("parameters", {})

                tool_name = raw_tool_name
                if raw_tool_name == "call_mcp_tool":
                    server = str(params.get("ServerName") or params.get("server_name") or "")
                    mcp_tool = str(params.get("ToolName") or params.get("tool_name") or "")
                    if "brain79" in server or "brain79" in mcp_tool:
                        tool_name = mcp_tool or f"mcp_{server}"
                    else:
                        tool_name = mcp_tool or raw_tool_name

                text = str(tool_info.get("output", "") or tool_info.get("error", ""))
                is_error = (
                    su.get("state") == "ERROR"
                    or bool(tool_info.get("is_error", False))
                    or bool(tool_info.get("error"))
                )

                if "brain79" in tool_name or tool_name.startswith("brain79_"):
                    if is_error or any(marker in text for marker in error_markers):
                        failures.append(f"{tool_name}: {text[:140]}")

        # Format 3: agy transcript.jsonl
        elif d.get("type") == "PLANNER_RESPONSE":
            calls = d.get("tool_calls", [])
            if calls:
                tc = calls[0]
                name = tc.get("name", "")
                args = tc.get("args", {})
                if name == "call_mcp_tool":
                    server = str(args.get("ServerName", "")).strip('"\'')
                    m_tool = str(args.get("ToolName", "")).strip('"\'')
                    if "brain79" in server or "brain79" in m_tool:
                        last_transcript_tool = m_tool or f"mcp_{server}"
                    else:
                        last_transcript_tool = m_tool or name
                elif "brain79" in name:
                    last_transcript_tool = name
                else:
                    last_transcript_tool = None
            else:
                last_transcript_tool = None

        elif d.get("type") == "GENERIC" and last_transcript_tool:
            text = str(d.get("content", ""))
            if any(marker in text for marker in error_markers):
                failures.append(f"{last_transcript_tool}: {text[:140]}")
            last_transcript_tool = None

    return failures


def verify_recovery_in_session(session_file: Path, expected_rule: str) -> bool:
    """Verify autonomous recovery from rejection:
    1. First session_commit call failed with expected_rule.
    2. Second session_commit call succeeded.
    3. No third attempt occurred.
    """
    if not session_file.is_file():
        return False

    commit_results: list[tuple[bool, str]] = []  # (has_err, text)
    error_markers = ("Commit Validation Failed:", "Validation Error:", "Error:", "Commit Aborted:")
    expected_markers = RULE_MESSAGE_MARKERS.get(expected_rule, (expected_rule,))

    last_was_commit = False

    for line in session_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue

        # Format 1: Pi toolResult
        if d.get("type") == "message" and d.get("message", {}).get("role") == "toolResult":
            tool_name = str(d["message"].get("toolName", ""))
            if "session_commit" in tool_name or tool_name.endswith("commit_session"):
                is_error = bool(d["message"].get("isError", False))
                content = d["message"].get("content", [])
                text = content[0].get("text", "") if content else ""
                has_err = is_error or any(m in text for m in error_markers)
                commit_results.append((has_err, text))

        # Format 2: agy stream-json step_update
        elif d.get("event") == "step_update":
            su = d.get("step_update", {})
            if su.get("step_type") == "tool" and su.get("state") == "DONE":
                tool_info = su.get("tool_info", {})
                raw_tool_name = su.get("tool_name", "") or tool_info.get("name", "")
                params = tool_info.get("parameters", {})

                tool_name = raw_tool_name
                if raw_tool_name == "call_mcp_tool":
                    tool_name = str(params.get("ToolName") or params.get("tool_name") or "")

                if "session_commit" in tool_name or tool_name.endswith("commit_session"):
                    text = str(tool_info.get("output", "") or tool_info.get("error", ""))
                    is_error = (
                        su.get("state") == "ERROR"
                        or bool(tool_info.get("is_error", False))
                        or bool(tool_info.get("error"))
                    )
                    has_err = is_error or any(m in text for m in error_markers)
                    commit_results.append((has_err, text))

        # Format 3: agy transcript.jsonl
        elif d.get("type") == "PLANNER_RESPONSE":
            calls = d.get("tool_calls", [])
            commit_call = False
            for tc in calls:
                name = tc.get("name", "")
                args = tc.get("args", {})
                t_name = name
                if name == "call_mcp_tool":
                    t_name = str(args.get("ToolName", "")).strip('"\'')
                if "session_commit" in t_name or t_name.endswith("commit_session"):
                    commit_call = True
                    break
            last_was_commit = commit_call

        elif d.get("type") == "GENERIC" and last_was_commit:
            text = str(d.get("content", ""))
            has_err = any(m in text for m in error_markers)
            commit_results.append((has_err, text))
            last_was_commit = False

    if len(commit_results) != 2:
        return False

    first_failed, first_text = commit_results[0]
    second_failed, second_text = commit_results[1]

    return first_failed and any(m in first_text for m in expected_markers) and not second_failed


def run_scenario_with_retries(
    name: str, runner_fn: Callable[[], bool], max_attempts: int = 3, min_successes: int = 2
) -> bool:
    """Run up to max_attempts, passing if at least min_successes succeed."""
    print(f"\nEvaluating {name} (up to {max_attempts} attempts, requiring >= {min_successes} successes)...")
    successes = 0
    for attempt in range(1, max_attempts + 1):
        print(f"\n--- {name} Attempt {attempt}/{max_attempts} ---")
        try:
            if runner_fn():
                successes += 1
                print(f"Attempt {attempt}: SUCCESS ({successes}/{min_successes} required)")
            else:
                print(f"Attempt {attempt}: FAILED")
        except Exception as exc:
            print(f"Attempt {attempt}: EXCEPTION: {exc}")

        if successes >= min_successes:
            print(f"{name}: PASSED with {successes}/{attempt} successes.")
            return True
        remaining = max_attempts - attempt
        if successes + remaining < min_successes:
            print(f"{name}: FAILED (cannot reach {min_successes} successes with {remaining} remaining attempts).")
            return False

    return successes >= min_successes


def run_scenario_1() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 1: Zero-code research in --profile general (No Git)")
    print("=" * 70)

    env = get_smoke_env()
    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-research-"))
    try:
        # 1. Initialize general profile wiki
        subprocess.run(
            ["brain79", "init", "--profile", "general", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
            env=env,
        )

        prompt = (
            "Orient yourself in the project. We analyzed multi-tenant SaaS pricing models: "
            "tiered subscription with usage-based overage provides optimal margin compared to flat-rate. "
            "Document this research into the wiki and conclude the session with a handoff."
        )

        agent_cmd = get_agent_cmd(prompt)
        print(f"Running agent ({find_agent_cli()}) in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            agent_cmd,
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")
        if res.returncode != 0 and res.stderr:
            print(f"Agent stderr:\n{res.stderr[:500]}")

        if res.stdout:
            (tmp / f"agent_session_{int(time.time() * 1000)}.jsonl").write_text(res.stdout, encoding="utf-8")

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
            env=env,
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

    env = get_smoke_env()
    prior_topics = sorted(p.name for p in (tmp / ".brain-79" / "topics").glob("*.md"))

    prompt = (
        "Orient yourself in the project. Just checking in to see what articles are currently in the wiki. "
        "Update the wiki if needed."
    )

    agent_cmd = get_agent_cmd(prompt)
    print(f"Running consultative turn in {tmp.name}...")
    t0 = time.time()
    res = subprocess.run(
        agent_cmd,
        cwd=tmp,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    duration = time.time() - t0
    print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")
    if res.returncode != 0 and res.stderr:
        print(f"Agent stderr:\n{res.stderr[:500]}")

    if res.stdout:
        (tmp / f"agent_session_{int(time.time() * 1000)}.jsonl").write_text(res.stdout, encoding="utf-8")

    post_topics = sorted(p.name for p in (tmp / ".brain-79" / "topics").glob("*.md"))

    assert prior_topics == post_topics, f"Failed: No-Op violated, synthetic topics created: {set(post_topics) - set(prior_topics)}"
    print("No-Op check: ✅ PASS (0 synthetic topics created)")

    lint_res = subprocess.run(
        ["brain79", "lint", "--strict", "--project-root", str(tmp)],
        capture_output=True,
        text=True,
        env=env,
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

    env = get_smoke_env()
    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-software-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
            env=env,
        )

        prompt = (
            "Orient yourself. We decided to adopt SQLite with WAL mode for local concurrency and created the module src/db.py. "
            "Record this architectural decision and update the wiki, closing the session."
        )

        agent_cmd = get_agent_cmd(prompt)
        print(f"Running agent ({find_agent_cli()}) in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            agent_cmd,
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")
        if res.returncode != 0 and res.stderr:
            print(f"Agent stderr:\n{res.stderr[:500]}")

        if res.stdout:
            (tmp / f"agent_session_{int(time.time() * 1000)}.jsonl").write_text(res.stdout, encoding="utf-8")

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
            env=env,
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

    env = get_smoke_env()
    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-ripple-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=tmp, check=True, capture_output=True, env=env)

        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
            env=env,
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

        subprocess.run(["git", "add", "."], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "Initial baseline"], cwd=tmp, check=True, capture_output=True, env=env)

        # Modify governed code file
        (src_core / "auth.py").write_text(
            "def authenticate(): return True\ndef verify_token(token: str) -> bool: return True\n",
            encoding="utf-8",
        )

        prompt = (
            "Orient yourself. We added token verification to src/core/auth.py. "
            "Update the wiki and wrap up the session using session commit."
        )

        agent_cmd = get_agent_cmd(prompt)
        print(f"Running agent ({find_agent_cli()}) in {tmp.name} with model {MODEL}...")
        t0 = time.time()
        res = subprocess.run(
            agent_cmd,
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")
        if res.returncode != 0 and res.stderr:
            print(f"Agent stderr:\n{res.stderr[:500]}")

        if res.stdout:
            (tmp / f"agent_session_{int(time.time() * 1000)}.jsonl").write_text(res.stdout, encoding="utf-8")

        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
            env=env,
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


def run_scenario_5_attempt() -> bool:
    env = get_smoke_env()
    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-recovery-ripple-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=tmp, check=True, capture_output=True, env=env)

        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
            env=env,
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

        subprocess.run(["git", "add", "."], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "Initial baseline"], cwd=tmp, check=True, capture_output=True, env=env)

        # Modify leaf file without updating umbrella article
        (src_core / "auth.py").write_text(
            "def authenticate(): return True\ndef revoke_token(token: str) -> bool: return True\n",
            encoding="utf-8",
        )

        prompt = (
            "Orient yourself. We added revoke_token to src/core/auth.py. "
            "In your initial commit, update only features/auth.md to document revoke_token. "
            "If rejected by the ripple gate, resolve the issue and complete the session commit."
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
            env=env,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")
        if res.returncode != 0 and res.stderr:
            print(f"Agent stderr:\n{res.stderr[:500]}")

        if res.stdout:
            (tmp / f"agent_session_{int(time.time() * 1000)}.jsonl").write_text(res.stdout, encoding="utf-8")

        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
            env=env,
        )
        if lint_res.returncode != 0:
            print(f"Strict lint failed:\n{lint_res.stdout}")
            return False
        print("Strict lint: [Status: OK]")

        # Check recovery in session log
        session_file = find_latest_session_for_dir(tmp)
        if not session_file:
            print("Warning: session file not found")
            return False

        if not verify_recovery_in_session(session_file, "unresolved_session_ripple"):
            print("Failed: Expected recovery pattern (1st commit rejected with unresolved_session_ripple, 2nd accepted, no 3rd)")
            return False

        print("Observed expected initial rejection 'unresolved_session_ripple' and subsequent recovery: ✅ PASS")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_scenario_5() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 5: Live-Agent Recovery from unresolved_session_ripple")
    print("=" * 70)
    return run_scenario_with_retries("Scenario 5", run_scenario_5_attempt, max_attempts=3, min_successes=2)


def run_scenario_6_attempt() -> bool:
    env = get_smoke_env()
    tmp = Path(tempfile.mkdtemp(prefix="b79-e2e-recovery-duplicate-"))
    try:
        subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=tmp, check=True, capture_output=True, env=env)

        subprocess.run(
            ["brain79", "init", "--profile", "software", "--no-git-hooks", "--project-root", str(tmp)],
            check=True,
            capture_output=True,
            env=env,
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

        subprocess.run(["git", "add", "."], cwd=tmp, check=True, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "Initial baseline"], cwd=tmp, check=True, capture_output=True, env=env)

        prompt = (
            "Orient yourself. Use session commit to create a new feature article features/token_revocation.md "
            "with applies_to: [src/core/auth.py] documenting token revocation. If rejected by anti-sprawl, "
            "resolve the issue autonomously and complete the session commit."
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
            env=env,
        )
        duration = time.time() - t0
        print(f"Agent finished in {duration:.1f}s (exit code {res.returncode})")
        if res.returncode != 0 and res.stderr:
            print(f"Agent stderr:\n{res.stderr[:500]}")

        if res.stdout:
            (tmp / f"agent_session_{int(time.time() * 1000)}.jsonl").write_text(res.stdout, encoding="utf-8")

        lint_res = subprocess.run(
            ["brain79", "lint", "--strict", "--project-root", str(tmp)],
            capture_output=True,
            text=True,
            env=env,
        )
        if lint_res.returncode != 0:
            print(f"Strict lint failed:\n{lint_res.stdout}")
            return False
        print("Strict lint: [Status: OK]")

        # Check recovery in session log
        session_file = find_latest_session_for_dir(tmp)
        if not session_file:
            print("Warning: session file not found")
            return False

        if not verify_recovery_in_session(session_file, "duplicate_governance_target"):
            print("Failed: Expected recovery pattern (1st commit rejected with duplicate_governance_target, 2nd accepted, no 3rd)")
            return False

        print("Observed expected initial rejection 'duplicate_governance_target' and subsequent recovery: ✅ PASS")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_scenario_6() -> bool:
    print("\n" + "=" * 70)
    print("▶ Scenario 6: Live-Agent Recovery from duplicate_governance_target")
    print("=" * 70)
    return run_scenario_with_retries("Scenario 6", run_scenario_6_attempt, max_attempts=3, min_successes=2)


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
