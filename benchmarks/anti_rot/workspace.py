"""Dual-arm isolated workspace initializer and fail-closed pre-flight probes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from benchmarks.anti_rot import CONTROL_AGENTS_PATH, FIXTURE_DIR, resolve_git_bin

AgyRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]

_DETERMINISTIC_GIT_DATE = "2026-01-01T00:00:00Z"
_IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".git")


class IsolationError(RuntimeError):
    """Raised when Arm A/Arm B isolation or pre-flight probe verification fails."""


class FixtureError(RuntimeError):
    """Raised when the LedgerPulse fixture or control baseline is missing or invalid."""


@dataclass(frozen=True)
class DualArmWorkspace:
    """Paths and shared commit-0 SHA for an isolated dual-arm benchmark run."""

    base_dir: Path
    arm_a: Path
    arm_b: Path
    commit_zero_sha: str


@dataclass(frozen=True)
class PreflightReport:
    """Result of fail-closed pre-flight isolation and hook verification."""

    passed: bool
    arm_a_hooks_verified: bool
    arm_a_tools: list[str] = field(default_factory=list)
    arm_b_tools: list[str] = field(default_factory=list)
    arm_b_brain79_tools: list[str] = field(default_factory=list)
    arm_a_mcp_servers: list[str] = field(default_factory=list)
    arm_b_mcp_servers: list[str] = field(default_factory=list)


def _run_git(args: list[str], cwd: Path, *, deterministic_time: bool = False) -> str:
    git_bin = resolve_git_bin()
    env = os.environ.copy()
    if deterministic_time:
        env["GIT_AUTHOR_DATE"] = _DETERMINISTIC_GIT_DATE
        env["GIT_COMMITTER_DATE"] = _DETERMINISTIC_GIT_DATE
    proc = subprocess.run(
        [git_bin, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise IsolationError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _init_commit_zero(repo_dir: Path, fixture_dir: Path) -> str:
    shutil.copytree(fixture_dir, repo_dir, ignore=_IGNORE_PATTERNS)
    _run_git(["init", "-b", "main"], repo_dir)
    _run_git(["config", "user.name", "LedgerPulse Bot"], repo_dir)
    _run_git(["config", "user.email", "bot@ledgerpulse.local"], repo_dir)
    _run_git(["add", "-A"], repo_dir)
    _run_git(["commit", "-m", "chore: initial LedgerPulse fixture"], repo_dir, deterministic_time=True)
    return _run_git(["rev-parse", "HEAD"], repo_dir)


def _set_schema_enforcement_strict(schema_path: Path) -> None:
    if not schema_path.is_file():
        raise IsolationError(f"Missing Arm A SCHEMA.md at {schema_path}")
    content = schema_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = content.splitlines()
    replaced = False
    for idx, line in enumerate(lines):
        if line.startswith("enforcement:"):
            lines[idx] = "enforcement: strict"
            replaced = True
            break
    if not replaced:
        for idx, line in enumerate(lines):
            if line.startswith("schema_version:"):
                lines.insert(idx + 1, "enforcement: strict")
                replaced = True
                break
    if not replaced:
        raise IsolationError("Unable to set enforcement: strict in Arm A SCHEMA.md")
    schema_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def initialize_arms(
    base_dir: Path | None = None,
    *,
    fixture_dir: Path = FIXTURE_DIR,
    control_agents_path: Path = CONTROL_AGENTS_PATH,
) -> DualArmWorkspace:
    """Create isolated Arm A (brain79) and Arm B (control) Git repos from identical commit 0."""
    if not fixture_dir.is_dir():
        raise FixtureError(f"Fixture directory does not exist: {fixture_dir}")
    if not control_agents_path.is_file():
        raise FixtureError(f"Control AGENTS.md baseline does not exist: {control_agents_path}")

    root = base_dir if base_dir is not None else Path(tempfile.mkdtemp(prefix="brain79_anti_rot_"))
    root.mkdir(parents=True, exist_ok=True)
    arm_a = root / "arm_a"
    arm_b = root / "arm_b"
    if arm_a.exists() or arm_b.exists():
        raise IsolationError(f"Target arm directories already exist under {root}")

    sha_a = _init_commit_zero(arm_a, fixture_dir)
    sha_b = _init_commit_zero(arm_b, fixture_dir)
    if sha_a != sha_b:
        raise IsolationError(f"Commit 0 SHA mismatch between arms: {sha_a} != {sha_b}")

    # Arm A: initialize brain79 with native agy plugin & lifecycle hooks, no git hooks
    init_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "brain79",
            "--project-root",
            str(arm_a),
            "init",
            "--profile",
            "software",
            "--harnesses",
            "agents,agy,agy_hooks",
            "--no-git-hooks",
        ],
        cwd=arm_a,
        capture_output=True,
        text=True,
    )
    if init_proc.returncode != 0:
        raise IsolationError(f"Arm A brain79 init failed: {init_proc.stderr.strip() or init_proc.stdout.strip()}")

    _set_schema_enforcement_strict(arm_a / ".brain-79" / "SCHEMA.md")
    _run_git(["add", "-A"], arm_a)
    _run_git(["commit", "-m", "chore: initialize brain79 treatment arm"], arm_a)

    # Arm B: install realistic control AGENTS.md with zero brain79 artifacts
    shutil.copyfile(control_agents_path, arm_b / "AGENTS.md")
    if (arm_b / ".brain-79").exists() or (arm_b / ".agents").exists():
        raise IsolationError("Arm B contains forbidden .brain-79/ or .agents/ directory")
    _run_git(["add", "-A"], arm_b)
    _run_git(["commit", "-m", "chore: initialize control arm AGENTS.md"], arm_b)

    return DualArmWorkspace(
        base_dir=root,
        arm_a=arm_a,
        arm_b=arm_b,
        commit_zero_sha=sha_a,
    )


def _default_agy_runner(
    cmd: list[str],
    cwd: Path,
    *,
    timeout_seconds: int = 60,
) -> subprocess.CompletedProcess[str]:
    if shutil.which("agy") is None:
        raise IsolationError("agy CLI binary not found on PATH")
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise IsolationError(
            f"agy pre-flight probe timed out after {timeout_seconds}s in {cwd}"
        ) from exc


def _parse_stream_json_events(stdout: str, *, arm_label: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    if not events:
        raise IsolationError(f"{arm_label}: agy stream-json probe produced zero parseable JSON events")
    return events


_PREFLIGHT_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "mcp_servers": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["mcp_servers"],
    },
    separators=(",", ":"),
)


def _extract_tool_names(events: list[dict[str, object]]) -> list[str]:
    tools: list[str] = []
    for ev in events:
        candidate_lists: list[object] = [ev.get("tools")]
        init_obj = ev.get("init")
        if isinstance(init_obj, dict):
            candidate_lists.append(init_obj.get("tools"))
        for raw_tools in candidate_lists:
            if isinstance(raw_tools, list):
                for item in raw_tools:
                    if isinstance(item, str) and item.strip():
                        tools.append(item.strip())
                    elif isinstance(item, dict) and isinstance(item.get("name"), str):
                        tools.append(str(item["name"]).strip())
        for key in ("tool", "tool_name", "name"):
            val = ev.get(key)
            if ev.get("type") in {"tool_use", "tool_call"} and isinstance(val, str) and val.strip():
                tools.append(val.strip())
        step_upd = ev.get("step_update")
        if isinstance(step_upd, dict) and step_upd.get("step_type") == "tool":
            tname = step_upd.get("tool_name")
            if isinstance(tname, str) and tname.strip():
                tools.append(tname.strip())
    return sorted(set(tools))


def _extract_mcp_servers(events: list[dict[str, object]]) -> list[str]:
    servers: list[str] = []

    def _collect_from_obj(obj: object) -> None:
        if not isinstance(obj, dict):
            return
        raw = obj.get("mcp_servers")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    servers.append(item.strip())

    for ev in events:
        _collect_from_obj(ev.get("structured_output"))
        res_obj = ev.get("result")
        if isinstance(res_obj, dict):
            _collect_from_obj(res_obj.get("structured_output"))
            resp = res_obj.get("response")
            if isinstance(resp, str) and resp.strip():
                try:
                    _collect_from_obj(json.loads(resp))
                except json.JSONDecodeError:
                    pass
    return sorted(set(servers))


def _has_hook_evidence(events: list[dict[str, object]]) -> bool:
    for ev in events:
        if ev.get("type") == "hook":
            return True
        if ev.get("hookEventName") in {"SessionStart", "Stop"}:
            return True
        if "hooks" in ev or "hook_results" in ev:
            return True
        if ev.get("event") == "step_update":
            step_upd = ev.get("step_update")
            if isinstance(step_upd, dict) and step_upd.get("step_type") == "system_message":
                return True
    return False


def run_preflight_checks(
    workspace: DualArmWorkspace,
    *,
    agy_runner: AgyRunner | None = None,
    model: str = "gemini-4-hydrogen-low",
    effort: str = "low",
    timeout_seconds: int = 60,
) -> PreflightReport:
    """Verify Arm B has zero brain79* MCP leakage and Arm A has active plugin + hooks."""
    runner: AgyRunner = (
        agy_runner
        if agy_runner is not None
        else lambda cmd, cwd: _default_agy_runner(cmd, cwd, timeout_seconds=timeout_seconds)
    )
    probe_cmd = [
        "agy",
        "-p",
        "List all MCP servers available to you. Return JSON with field mcp_servers (array of server name strings).",
        "--model",
        model,
        "--effort",
        effort,
        "--output-format",
        "stream-json",
        "--json-schema",
        _PREFLIGHT_JSON_SCHEMA,
        "--dangerously-skip-permissions",
        "--print-timeout",
        f"{timeout_seconds}s",
    ]

    # 1. Arm B disk & probe check (fail-closed)
    if (workspace.arm_b / ".brain-79").exists() or (workspace.arm_b / ".agents").exists():
        raise IsolationError("Arm B isolation failure: .brain-79/ or .agents/ exists on disk")

    proc_b = runner(probe_cmd, workspace.arm_b)
    if proc_b.returncode != 0:
        raise IsolationError(f"Arm B pre-flight probe failed with exit code {proc_b.returncode}")
    events_b = _parse_stream_json_events(proc_b.stdout, arm_label="Arm B")
    tools_b = _extract_tool_names(events_b)
    mcp_servers_b = _extract_mcp_servers(events_b)
    if not tools_b:
        raise IsolationError("Arm B pre-flight probe failed: no tool inventory found in stream-json output")
    leaked = sorted({t for t in (*tools_b, *mcp_servers_b) if "brain79" in t.lower()})
    if leaked:
        raise IsolationError(f"Arm B isolation failure: leaked brain79 MCP tools: {leaked}")

    # 2. Arm A disk & probe hook check (Q-1c)
    plugin_dir = workspace.arm_a / ".agents" / "plugins" / "brain79"
    mcp_cfg = plugin_dir / "mcp_config.json"
    hooks_cfg = plugin_dir / "hooks.json"
    if not mcp_cfg.is_file() or not hooks_cfg.is_file():
        raise IsolationError("Arm A pre-flight failure: missing .agents/plugins/brain79/ mcp_config.json or hooks.json")
    hooks_text = hooks_cfg.read_text(encoding="utf-8")
    if "SessionStart" not in hooks_text or "Stop" not in hooks_text:
        raise IsolationError("Arm A pre-flight failure: hooks.json missing SessionStart or Stop hook")

    proc_a = runner(probe_cmd, workspace.arm_a)
    if proc_a.returncode != 0:
        raise IsolationError(f"Arm A pre-flight probe failed with exit code {proc_a.returncode}")
    events_a = _parse_stream_json_events(proc_a.stdout, arm_label="Arm A")
    tools_a = _extract_tool_names(events_a)
    mcp_servers_a = _extract_mcp_servers(events_a)
    if not any("brain79" in t.lower() for t in (*tools_a, *mcp_servers_a)):
        raise IsolationError("Arm A pre-flight failure: no brain79 MCP tools loaded in stream-json output")
    hooks_verified = _has_hook_evidence(events_a)
    if not hooks_verified:
        raise IsolationError("Arm A pre-flight failure: agy -p probe output showed no lifecycle hook execution")

    return PreflightReport(
        passed=True,
        arm_a_hooks_verified=hooks_verified,
        arm_a_tools=tools_a,
        arm_b_tools=tools_b,
        arm_b_brain79_tools=leaked,
        arm_a_mcp_servers=mcp_servers_a,
        arm_b_mcp_servers=mcp_servers_b,
    )
