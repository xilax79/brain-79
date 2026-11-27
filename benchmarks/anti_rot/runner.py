"""12-session longitudinal cold-start runner and telemetry collector (SPEC-016 Capability 2)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from benchmarks.anti_rot import resolve_git_bin
from benchmarks.anti_rot.contracts.runner import run_session_contract
from benchmarks.anti_rot.scenarios import SCENARIOS, SessionScenario, prompt_sha256
from benchmarks.anti_rot.workspace import DualArmWorkspace

DEFAULT_MODEL: str = "gemini-4-hydrogen-low"
DEFAULT_EFFORT: str = "low"
DEFAULT_TIMEOUT_SECONDS: int = 300
MAX_TRANSIENT_RETRIES: int = 1

_TRANSIENT_ERROR_PATTERNS: tuple[str, ...] = (
    "429",
    "502",
    "503",
    "504",
    "rate limit",
    "connection reset",
    "temporarily unavailable",
    "network error",
)

_FORBIDDEN_COLD_START_FLAGS: frozenset[str] = frozenset(
    {"--continue", "-c", "--resume", "-r", "--conversation"}
)

_REQUIRED_RECORD_FIELDS: tuple[str, ...] = (
    "arm",
    "session_id",
    "title",
    "triage_type",
    "prompt_sha256",
    "exit_code",
    "timed_out",
    "retries",
    "duration_seconds",
    "changed_paths",
    "commit_sha",
    "git_diff_stat",
    "pytest_passed",
    "node_tests_passed",
    "contract_passed",
    "contract_errors",
    "clean_completion",
    "conversation_id",
    "input_tokens",
    "output_tokens",
    "tool_calls",
    "doc_read_tokens",
    "src_read_paths",
)


class TelemetryError(RuntimeError):
    """Raised when session JSONL telemetry is missing, corrupt, or incomplete."""


@dataclass(frozen=True)
class AgyRunResult:
    """Raw subprocess outcome from a single `agy` invocation."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class StreamTelemetry:
    """Parsed token, tool-call, and file-read telemetry from `agy` stream-json."""

    conversation_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    doc_read_tokens: int = 0
    src_read_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SessionRecord:
    """Structured per-session telemetry record persisted to `sessions.jsonl`."""

    arm: str
    session_id: str
    title: str
    triage_type: str
    prompt_sha256: str
    exit_code: int
    timed_out: bool
    retries: int
    duration_seconds: float
    changed_paths: list[str]
    commit_sha: str
    git_diff_stat: str
    pytest_passed: bool
    node_tests_passed: bool
    contract_passed: bool
    contract_errors: list[str]
    clean_completion: bool
    conversation_id: str | None
    input_tokens: int
    output_tokens: int
    tool_calls: int
    doc_read_tokens: int
    src_read_paths: list[str]
    brain79_stats: dict[str, Any] | None = None
    brain79_ci_check: dict[str, Any] | None = None
    brain79_ci_check_exit_code: int | None = None
    brain79_lint_exit_code: int | None = None
    error: str | None = None


SessionAgyRunner = Callable[[list[str], Path, int], AgyRunResult]


def build_agy_session_cmd(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> list[str]:
    """Build a strict cold-start `agy` CLI command with zero session-resume flags."""
    cmd = [
        "agy",
        "-p",
        prompt,
        "--model",
        model,
        "--effort",
        effort,
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        "--print-timeout",
        f"{timeout_seconds}s",
    ]
    if _FORBIDDEN_COLD_START_FLAGS & set(cmd):
        raise ValueError("Cold-start command must never include conversation resume flags")
    return cmd


def default_live_agy_runner(cmd: list[str], cwd: Path, timeout_seconds: int) -> AgyRunResult:
    """Execute `agy` via Popen with timeout enforcement and clean SIGINT termination."""
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        return AgyRunResult(
            exit_code=proc.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            timed_out=False,
            duration_seconds=round(time.monotonic() - start, 4),
        )
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        return AgyRunResult(
            exit_code=124,
            stdout=stdout or "",
            stderr=(stderr or "") + f"\nTimed out after {timeout_seconds}s",
            timed_out=True,
            duration_seconds=round(time.monotonic() - start, 4),
        )
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        raise


def is_transient_error(result: AgyRunResult) -> bool:
    """Return True strictly for transient API/network failures (never timeouts/logic)."""
    if result.timed_out or result.exit_code == 0:
        return False
    combined = f"{result.stderr}\n{result.stdout}".lower()
    return any(pattern in combined for pattern in _TRANSIENT_ERROR_PATTERNS)


def _normalize_rel_path(raw: str) -> str:
    norm = raw.strip().replace("\\", "/")
    for marker in ("/src/", "/.brain-79/", "/docs/"):
        if marker in norm:
            return norm[norm.index(marker) + 1 :]
    for root_doc in ("AGENTS.md", "README.md"):
        if norm == root_doc or norm.endswith(f"/{root_doc}"):
            return root_doc
    if norm.startswith("./"):
        return norm[2:]
    return norm


def _is_doc_path(rel_path: str) -> bool:
    return (
        rel_path.startswith(".brain-79/")
        or rel_path.startswith("docs/")
        or rel_path in {"AGENTS.md", "README.md"}
    )


_BRAIN79_DOC_TOOLS: tuple[str, ...] = (
    "brain79_orient",
    "brain79_read",
    "brain79_read_batch",
    "brain79_context",
    "brain79_search",
)
_CMD_SRC_PATH_RE = re.compile(r"(?:^|[\s\"'=/])(src(?:/[A-Za-z0-9_.-]+)*/?)")
_BYTES_OUTPUT_RE = re.compile(r"(\d+)\s+bytes\b")


def _is_brain79_doc_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return any(tok in lowered for tok in _BRAIN79_DOC_TOOLS)


def _iter_param_containers(ev: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = [ev]
    for key in ("input", "arguments", "args", "parameters", "tool_info"):
        sub = ev.get(key)
        if isinstance(sub, dict):
            containers.append(sub)
            for nested_key in ("parameters", "args", "input", "arguments"):
                nested = sub.get(nested_key)
                if isinstance(nested, dict):
                    containers.append(nested)
    return containers


def _extract_src_paths_from_event(ev: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for container in _iter_param_containers(ev):
        for key in ("path", "file_path", "Path", "target_file", "SearchPath", "DirectoryPath", "AbsolutePath"):
            val = container.get(key)
            if isinstance(val, str) and val.strip():
                norm = _normalize_rel_path(val)
                if (norm == "src" or norm.startswith("src/")) and norm not in found:
                    found.append(norm)
        for cmd_key in ("CommandLine", "command", "cmd"):
            cmd_val = container.get(cmd_key)
            if isinstance(cmd_val, str) and "src/" in cmd_val.replace("\\", "/"):
                norm_cmd = cmd_val.replace("\\", "/")
                for m in _CMD_SRC_PATH_RE.finditer(norm_cmd):
                    candidate = m.group(1).rstrip("/")
                    if candidate and candidate not in found:
                        found.append(candidate)
    return found


def _extract_path_from_event(ev: dict[str, Any]) -> str | None:
    for container in _iter_param_containers(ev):
        for key in ("path", "file_path", "Path", "target_file", "SearchPath", "DirectoryPath", "AbsolutePath"):
            val = container.get(key)
            if isinstance(val, str) and val.strip():
                return _normalize_rel_path(val)
    return None


def _extract_result_text(ev: dict[str, Any]) -> str:
    raw = ev.get("content")
    if raw is None:
        raw = ev.get("output")
    if raw is None:
        raw = ev.get("result")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    if isinstance(raw, dict):
        return json.dumps(raw)
    return ""


def _estimate_output_tokens(raw_out: object) -> int:
    if isinstance(raw_out, str):
        m = _BYTES_OUTPUT_RE.search(raw_out)
        if m:
            return max(1, int(m.group(1)) // 4)
        return max(1, len(raw_out) // 4) if raw_out else 0
    if isinstance(raw_out, (dict, list)) and raw_out:
        return max(1, len(json.dumps(raw_out)) // 4)
    return 0


def _extract_conv_id(ev: dict[str, Any]) -> str | None:
    containers: list[dict[str, Any]] = [ev]
    for sub_key in ("result", "step_update", "init"):
        sub = ev.get(sub_key)
        if isinstance(sub, dict):
            containers.append(sub)
    for container in containers:
        for key in ("conversation_id", "conversationId", "session_id", "thread_id"):
            val = container.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def parse_stream_json_telemetry(stdout: str) -> StreamTelemetry:
    """Extract conversation ID, token usage, tool calls, and doc/src reads from stream-json."""
    conversation_id: str | None = None
    result_usage: tuple[int, int] | None = None
    step_input_tokens = 0
    step_output_tokens = 0
    flat_input_tokens = 0
    flat_output_tokens = 0
    tool_calls = 0
    doc_read_tokens = 0
    src_reads: list[str] = []
    pending_calls: dict[str, tuple[str, str | None]] = {}

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue

        if conversation_id is None:
            conversation_id = _extract_conv_id(ev)

        nested_event = ev.get("event")
        if nested_event == "result":
            res_obj = ev.get("result")
            if isinstance(res_obj, dict) and isinstance(res_obj.get("usage"), dict):
                u = res_obj["usage"]
                in_t = u.get("input_tokens") or u.get("prompt_tokens")
                out_t = u.get("output_tokens") or u.get("completion_tokens")
                result_usage = (
                    in_t if isinstance(in_t, int) else 0,
                    out_t if isinstance(out_t, int) else 0,
                )
            continue

        if nested_event == "step_update":
            step = ev.get("step_update")
            if not isinstance(step, dict):
                continue
            state = step.get("state")
            if state == "DONE" and isinstance(step.get("usage"), dict):
                u = step["usage"]
                in_t = u.get("input_tokens") or u.get("prompt_tokens")
                out_t = u.get("output_tokens") or u.get("completion_tokens")
                if isinstance(in_t, int):
                    step_input_tokens += in_t
                if isinstance(out_t, int):
                    step_output_tokens += out_t

            if step.get("step_type") == "tool":
                tool_info = step.get("tool_info")
                tool_info_dict = tool_info if isinstance(tool_info, dict) else {}
                for src_p in _extract_src_paths_from_event(step):
                    if src_p not in src_reads:
                        src_reads.append(src_p)
                if state == "DONE":
                    tool_calls += 1
                    t_name = str(step.get("tool_name") or tool_info_dict.get("name") or "")
                    rel_path = _extract_path_from_event(step)
                    params = tool_info_dict.get("parameters")
                    mcp_tool = params.get("ToolName") if isinstance(params, dict) else None
                    is_doc_read = (
                        (rel_path is not None and _is_doc_path(rel_path))
                        or _is_brain79_doc_tool(t_name)
                        or (
                            t_name == "call_mcp_tool"
                            and isinstance(mcp_tool, str)
                            and _is_brain79_doc_tool(mcp_tool)
                        )
                    )
                    if is_doc_read:
                        doc_read_tokens += _estimate_output_tokens(tool_info_dict.get("output"))
            continue

        # Legacy flat stream-json events
        usage = ev.get("usage")
        usage_dict = usage if isinstance(usage, dict) else ev
        in_tok = usage_dict.get("input_tokens") or usage_dict.get("prompt_tokens")
        out_tok = usage_dict.get("output_tokens") or usage_dict.get("completion_tokens")
        if isinstance(in_tok, int):
            flat_input_tokens += in_tok
        if isinstance(out_tok, int):
            flat_output_tokens += out_tok

        ev_type = ev.get("type")
        tool_name = ev.get("name") or ev.get("tool_name") or ev.get("tool")
        if ev_type == "tool_result":
            call_id = ev.get("tool_use_id") or ev.get("call_id") or ev.get("id")
            linked_tool, linked_path = pending_calls.get(str(call_id), ("", None))
            is_doc_read = (linked_path is not None and _is_doc_path(linked_path)) or (
                bool(linked_tool) and _is_brain79_doc_tool(linked_tool)
            )
            if is_doc_read:
                explicit_tok = ev.get("doc_read_tokens")
                if isinstance(explicit_tok, int):
                    doc_read_tokens += explicit_tok
                else:
                    text = _extract_result_text(ev)
                    if text:
                        doc_read_tokens += max(1, len(text) // 4)
            continue

        if ev_type in {"tool_use", "tool_call"} or (isinstance(tool_name, str) and ev_type != "result"):
            if isinstance(tool_name, str) and tool_name.strip():
                tool_calls += 1
                rel_path = _extract_path_from_event(ev)
                for src_p in _extract_src_paths_from_event(ev):
                    if src_p not in src_reads:
                        src_reads.append(src_p)
                call_id = ev.get("id") or ev.get("tool_use_id") or ev.get("call_id")
                if isinstance(call_id, str) and call_id.strip():
                    pending_calls[call_id.strip()] = (tool_name.strip(), rel_path)
                is_doc_read = (rel_path is not None and _is_doc_path(rel_path)) or _is_brain79_doc_tool(
                    tool_name
                )
                if is_doc_read:
                    explicit_tok = ev.get("doc_read_tokens")
                    if isinstance(explicit_tok, int):
                        doc_read_tokens += explicit_tok
                    else:
                        text = _extract_result_text(ev)
                        if text:
                            doc_read_tokens += max(1, len(text) // 4)

    if result_usage is not None:
        final_in, final_out = result_usage
    elif step_input_tokens > 0 or step_output_tokens > 0:
        final_in, final_out = step_input_tokens, step_output_tokens
    else:
        final_in, final_out = flat_input_tokens, flat_output_tokens

    return StreamTelemetry(
        conversation_id=conversation_id,
        input_tokens=final_in,
        output_tokens=final_out,
        tool_calls=tool_calls,
        doc_read_tokens=doc_read_tokens,
        src_read_paths=src_reads,
    )


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [resolve_git_bin(), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _is_ignored_artifact(path: str) -> bool:
    parts = path.split("/")
    return "__pycache__" in parts or ".pytest_cache" in parts or path.endswith(".pyc")


def capture_changed_paths(workspace: Path) -> list[str]:
    """Capture modified/untracked relative POSIX paths via `git status --porcelain -uall`."""
    proc = _run_git(["status", "--porcelain", "-uall"], workspace)
    if proc.returncode != 0:
        return []
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) <= 3:
            continue
        raw = line[3:].strip()
        if " -> " in raw:
            old_path, new_path = raw.split(" -> ", 1)
            for candidate in (old_path, new_path):
                norm = candidate.strip().strip('"').replace("\\", "/")
                if norm and not _is_ignored_artifact(norm) and norm not in paths:
                    paths.append(norm)
        else:
            norm = raw.strip('"').replace("\\", "/")
            if norm and not _is_ignored_artifact(norm) and norm not in paths:
                paths.append(norm)
    return paths


def commit_session_changes(workspace: Path, session_id: str, title: str) -> tuple[str, str]:
    """Commit dirty working tree after a session; preserve clean tree if unchanged."""
    status = _run_git(["status", "--porcelain", "-uall"], workspace)
    committed = False
    if status.returncode == 0 and status.stdout.strip():
        _run_git(["add", "-A"], workspace)
        commit_proc = _run_git(["commit", "-m", f"session({session_id}): {title}"], workspace)
        committed = commit_proc.returncode == 0

    head_proc = _run_git(["rev-parse", "HEAD"], workspace)
    commit_sha = head_proc.stdout.strip() if head_proc.returncode == 0 else ""

    diff_stat = ""
    if committed:
        stat_proc = _run_git(["diff", "--stat", "HEAD~1", "HEAD"], workspace)
        if stat_proc.returncode == 0:
            diff_stat = stat_proc.stdout.strip()
    return commit_sha, diff_stat


def _run_pytest(workspace: Path) -> bool:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _run_node_tests(workspace: Path) -> bool:
    proc = subprocess.run(
        ["node", "--test"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _run_brain79_json(arm_a: Path, args: list[str]) -> tuple[dict[str, Any] | None, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "brain79", "--project-root", str(arm_a), *args],
        cwd=arm_a,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        return None, proc.returncode
    try:
        parsed = json.loads(proc.stdout)
        return (parsed if isinstance(parsed, dict) else None), proc.returncode
    except json.JSONDecodeError:
        return None, proc.returncode


def _collect_arm_a_brain79_telemetry(
    arm_a: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int, int]:
    stats, _ = _run_brain79_json(arm_a, ["stats", "--format", "json"])
    ci_check, ci_check_exit_code = _run_brain79_json(
        arm_a, ["ci-check", "--format", "json", "--enforcement", "strict"]
    )
    lint_proc = subprocess.run(
        [sys.executable, "-m", "brain79", "--project-root", str(arm_a), "lint", "--strict"],
        cwd=arm_a,
        capture_output=True,
        text=True,
    )
    return stats, ci_check, ci_check_exit_code, lint_proc.returncode


def run_single_session(
    arm: str,
    workspace: Path,
    scenario: SessionScenario,
    *,
    agy_runner: SessionAgyRunner | None = None,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> SessionRecord:
    """Execute one cold-start session, commit changes, run tests/contracts, and collect telemetry."""
    runner = agy_runner or default_live_agy_runner
    cmd = build_agy_session_cmd(
        scenario.prompt,
        model=model,
        effort=effort,
        timeout_seconds=timeout_seconds,
    )

    retries = 0
    result = runner(cmd, workspace, timeout_seconds)
    while retries < MAX_TRANSIENT_RETRIES and is_transient_error(result):
        retries += 1
        result = runner(cmd, workspace, timeout_seconds)

    changed_paths = capture_changed_paths(workspace)
    commit_sha, git_diff_stat = commit_session_changes(
        workspace, scenario.session_id, scenario.title
    )

    pytest_passed = _run_pytest(workspace)
    node_tests_passed = _run_node_tests(workspace)

    if scenario.session_id == "S1":
        contract_passed = True
        contract_errors: list[str] = []
    else:
        contract = run_session_contract(
            scenario.session_id, workspace, changed_paths=changed_paths
        )
        contract_passed = contract.passed
        contract_errors = list(contract.errors)

    telemetry = parse_stream_json_telemetry(result.stdout)

    brain79_stats: dict[str, Any] | None = None
    brain79_ci_check: dict[str, Any] | None = None
    brain79_ci_check_exit_code: int | None = None
    brain79_lint_exit_code: int | None = None
    if arm == "arm_a":
        brain79_stats, brain79_ci_check, brain79_ci_check_exit_code, brain79_lint_exit_code = (
            _collect_arm_a_brain79_telemetry(workspace)
        )

    clean_completion = (
        result.exit_code == 0
        and not result.timed_out
        and pytest_passed
        and node_tests_passed
        and contract_passed
    )
    error_msg: str | None = None
    if not clean_completion:
        reasons: list[str] = []
        if result.timed_out:
            reasons.append("timeout")
        elif result.exit_code != 0:
            reasons.append(f"exit_code={result.exit_code}")
        if not pytest_passed:
            reasons.append("pytest_failed")
        if not node_tests_passed:
            reasons.append("node_tests_failed")
        if not contract_passed:
            reasons.append(f"contract_failed: {'; '.join(contract_errors)}")
        error_msg = "; ".join(reasons)

    return SessionRecord(
        arm=arm,
        session_id=scenario.session_id,
        title=scenario.title,
        triage_type=scenario.triage_type,
        prompt_sha256=prompt_sha256(scenario.prompt),
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        retries=retries,
        duration_seconds=result.duration_seconds,
        changed_paths=changed_paths,
        commit_sha=commit_sha,
        git_diff_stat=git_diff_stat,
        pytest_passed=pytest_passed,
        node_tests_passed=node_tests_passed,
        contract_passed=contract_passed,
        contract_errors=contract_errors,
        clean_completion=clean_completion,
        conversation_id=telemetry.conversation_id,
        input_tokens=telemetry.input_tokens,
        output_tokens=telemetry.output_tokens,
        tool_calls=telemetry.tool_calls,
        doc_read_tokens=telemetry.doc_read_tokens,
        src_read_paths=telemetry.src_read_paths,
        brain79_stats=brain79_stats,
        brain79_ci_check=brain79_ci_check,
        brain79_ci_check_exit_code=brain79_ci_check_exit_code,
        brain79_lint_exit_code=brain79_lint_exit_code,
        error=error_msg,
    )


def run_benchmark_sessions(
    workspace: DualArmWorkspace,
    output_dir: Path,
    *,
    agy_runner: SessionAgyRunner | None = None,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    scenarios: Sequence[SessionScenario] = SCENARIOS,
) -> list[SessionRecord]:
    """Execute `S1`-`S12` on Arm A and Arm B, flushing each record to `sessions.jsonl`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "sessions.jsonl"
    records: list[SessionRecord] = []

    with jsonl_path.open("w", encoding="utf-8", newline="\n") as fh:
        for scenario in scenarios:
            for arm, arm_dir in (("arm_a", workspace.arm_a), ("arm_b", workspace.arm_b)):
                record = run_single_session(
                    arm,
                    arm_dir,
                    scenario,
                    agy_runner=agy_runner,
                    model=model,
                    effort=effort,
                    timeout_seconds=timeout_seconds,
                )
                records.append(record)
                fh.write(json.dumps(asdict(record), sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
    return records


def load_session_records(jsonl_path: Path) -> list[SessionRecord]:
    """Load and validate `sessions.jsonl`, failing closed on corrupt/incomplete/duplicate data."""
    if not jsonl_path.is_file():
        raise TelemetryError(f"Session log does not exist: {jsonl_path}")

    raw_lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    non_empty = [line for line in raw_lines if line.strip()]
    if not non_empty:
        raise TelemetryError(f"Session log is empty: {jsonl_path}")

    records: list[SessionRecord] = []
    seen_keys: set[tuple[str, str]] = set()
    for idx, line in enumerate(non_empty, start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TelemetryError(f"Corrupt JSON at line {idx} in {jsonl_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise TelemetryError(f"Expected JSON object at line {idx} in {jsonl_path}")

        missing = [k for k in _REQUIRED_RECORD_FIELDS if k not in payload]
        if missing:
            raise TelemetryError(
                f"Incomplete record at line {idx} in {jsonl_path}; missing: {missing}"
            )

        key = (str(payload["arm"]), str(payload["session_id"]))
        if key in seen_keys:
            raise TelemetryError(
                f"Duplicate session record for {key} at line {idx} in {jsonl_path}"
            )
        seen_keys.add(key)

        try:
            records.append(SessionRecord(**payload))
        except TypeError as exc:
            raise TelemetryError(f"Invalid record schema at line {idx}: {exc}") from exc

    return records


def _write_arm_doc(workspace: Path, arm: str, rel_doc: str, content: str) -> str:
    target = workspace / rel_doc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if arm == "arm_a":
        subprocess.run(
            [
                sys.executable,
                "-m",
                "brain79",
                "--project-root",
                str(workspace),
                "navigate",
                "--regenerate",
                "--rebuild",
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
    return rel_doc


def _apply_dry_run_mutations(workspace: Path, arm: str, session_id: str) -> str:
    """Apply deterministic valid code/doc mutations for dry-run verification."""
    if session_id == "S1":
        doc_path = (
            ".brain-79/architecture/ledgerpulse-core.md"
            if arm == "arm_a"
            else "docs/architecture.md"
        )
        content = (
            "---\n"
            "title: LedgerPulse core architecture\n"
            "type: architecture\n"
            "stability: stable\n"
            f"last_updated: {date.today().isoformat()}\n"
            "summary: Architecture overview for LedgerPulse pricing, ledger, tax, and reporter.\n"
            "applies_to:\n"
            "  - src/ledgerpulse/pricing.py\n"
            "  - src/ledgerpulse/ledger.py\n"
            "  - src/ledgerpulse/tax.py\n"
            "  - src/reporter/schema.mjs\n"
            "---\n\n"
            "# LedgerPulse core architecture\n\n"
            "## Overview\n\n"
            "Core modules live in `src/ledgerpulse/pricing.py` and `src/reporter/schema.mjs`.\n\n"
            "[← Back to Index](../INDEX.md)\n"
        )
        return _write_arm_doc(workspace, arm, doc_path, content)

    if session_id == "S2":
        pricing = workspace / "src/ledgerpulse/pricing.py"
        text = pricing.read_text(encoding="utf-8")
        text += (
            "\n\nTIERED_BULK_THRESHOLD: int = 10\n"
            "TIERED_BULK_DISCOUNT_BPS: int = 500\n\n\n"
            "def calculate_bulk_discount(items: list[LineItem]) -> int:\n"
            '    """Return bulk discount basis points when total quantity >= 10."""\n'
            "    total_qty = sum(item.quantity for item in items)\n"
            "    return TIERED_BULK_DISCOUNT_BPS if total_qty >= TIERED_BULK_THRESHOLD else 0\n"
        )
        pricing.write_text(text, encoding="utf-8")
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S3":
        ledger = workspace / "src/ledgerpulse/ledger.py"
        text = ledger.read_text(encoding="utf-8")
        anchor = "from .validation import ValidationError, require_valid_invoice\n"
        text = text.replace(anchor, anchor + "\nVOID_REASON_MAX_LEN: int = 200\n", 1)
        text += (
            "\n\n    def void_invoice(self, invoice_id: str, reason: str) -> None:\n"
            '        """Void an existing invoice with a bounded reason."""\n'
            "        if not reason.strip() or len(reason) > VOID_REASON_MAX_LEN:\n"
            '            raise ValidationError("invalid void reason")\n'
            "        self._invoices[invoice_id].status = InvoiceStatus.VOID\n"
        )
        ledger.write_text(text, encoding="utf-8")
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S4":
        tax = workspace / "src/ledgerpulse/tax.py"
        text = tax.read_text(encoding="utf-8")
        text += (
            "\n\nLATE_FEE_BPS: int = 250\n"
            "LATE_FEE_GRACE_DAYS: int = 15\n\n\n"
            "def calculate_late_fee(amount_cents: int, days_overdue: int) -> int:\n"
            '    """Compute late fee in cents after grace period."""\n'
            "    if days_overdue <= LATE_FEE_GRACE_DAYS:\n"
            "        return 0\n"
            "    return round_half_even((amount_cents * LATE_FEE_BPS) / 10_000)\n"
        )
        tax.write_text(text, encoding="utf-8")
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S5":
        for rel in (
            "src/ledgerpulse/pricing.py",
            "src/ledgerpulse/ledger.py",
            "src/ledgerpulse/export.py",
            "src/ledgerpulse/__init__.py",
            "tests/test_ledgerpulse.py",
        ):
            p = workspace / rel
            content = p.read_text(encoding="utf-8")
            if rel == "src/ledgerpulse/pricing.py":
                content = content.replace(
                    "def compute_invoice_total(invoice: Invoice) -> int:",
                    "def calculate_invoice_grand_total(invoice: Invoice, include_tax: bool = True) -> int:",
                ).replace(
                    "return discounted + calculate_invoice_tax(invoice)",
                    "return discounted + (calculate_invoice_tax(invoice) if include_tax else 0)",
                )
            else:
                content = content.replace("compute_invoice_total", "calculate_invoice_grand_total")
            p.write_text(content, encoding="utf-8")
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S6":
        schema = workspace / "src/reporter/schema.mjs"
        schema.write_text(
            schema.read_text(encoding="utf-8")
            + "\nexport function validateSummaryDocument(payload, options = {}) {\n"
            "  return validateReportPayload(payload);\n"
            "}\n",
            encoding="utf-8",
        )
        idx = workspace / "src/reporter/index.mjs"
        idx.write_text(
            idx.read_text(encoding="utf-8").replace(
                "validateReportPayload }",
                "validateReportPayload, validateSummaryDocument }",
            ),
            encoding="utf-8",
        )
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S7":
        tax = workspace / "src/ledgerpulse/tax.py"
        text = tax.read_text(encoding="utf-8")
        text = text.replace("LATE_FEE_BPS: int = 250", "LATE_FEE_BPS: int = 500")
        text = text.replace("LATE_FEE_GRACE_DAYS: int = 15", "LATE_FEE_GRACE_DAYS: int = 7")
        text = text.replace(
            "def calculate_late_fee(amount_cents: int, days_overdue: int) -> int:",
            "def calculate_late_fee(amount_cents: int, days_overdue: int, compound: bool = False) -> int:",
        )
        tax.write_text(text, encoding="utf-8")
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S8":
        exp = workspace / "src/ledgerpulse/export.py"
        text = exp.read_text(encoding="utf-8")
        text = text.replace('SCHEMA_VERSION: str = "1.0"', 'SCHEMA_VERSION: str = "2.0"')
        text = text.replace(
            '"schema_version": SCHEMA_VERSION,',
            '"schema_version": "1.0",',
        )
        text += (
            "\n\ndef export_audit_bundle(ledger: Ledger, include_void: bool = False) -> dict[str, object]:\n"
            '    """Export an audit bundle with schema v2.0."""\n'
            '    return {"schema_version": SCHEMA_VERSION, "include_void": include_void, "count": len(ledger.invoices)}\n'
        )
        exp.write_text(text, encoding="utf-8")
        fmt = workspace / "src/reporter/formatter.mjs"
        fmt.write_text(
            fmt.read_text(encoding="utf-8")
            + "\nexport function formatAuditBanner(bundle) {\n"
            "  return `audit:${bundle?.schema_version ?? '2.0'}`;\n"
            "}\n",
            encoding="utf-8",
        )
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S9":
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S10":
        if arm == "arm_a":
            return _write_arm_doc(
                workspace,
                arm,
                ".brain-79/topics/multi-currency-rounding-drift.md",
                (
                    "---\n"
                    "title: Multi-currency rounding drift analysis\n"
                    "type: topic\n"
                    f"last_updated: {date.today().isoformat()}\n"
                    "summary: Research findings on rounding drift across USD, EUR, and GBP.\n"
                    "---\n\n"
                    "# Multi-currency rounding drift analysis\n\n"
                    "## Overview\n\n"
                    "Half-even rounding prevents systematic bias across currencies.\n\n"
                    "[← Back to Index](../INDEX.md)\n"
                ),
            )
        return _write_arm_doc(
            workspace,
            arm,
            "docs/research/multi-currency-rounding-drift.md",
            "# Multi-currency rounding drift analysis\n\nHalf-even rounding prevents systematic bias.\n",
        )

    if session_id == "S11":
        old_file = workspace / "src/ledgerpulse/reconcile.py"
        pkg_dir = workspace / "src/ledgerpulse/reconciliation"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        matcher_text = old_file.read_text(encoding="utf-8").replace(
            "from .ledger import Ledger", "from ..ledger import Ledger"
        )
        (pkg_dir / "matcher.py").write_text(matcher_text, encoding="utf-8")
        (pkg_dir / "__init__.py").write_text(
            '"""Reconciliation package."""\n\n'
            "from .matcher import ReconciliationReport, reconcile_payments\n\n"
            '__all__ = ["ReconciliationReport", "reconcile_payments"]\n',
            encoding="utf-8",
        )
        old_file.unlink()
        init_py = workspace / "src/ledgerpulse/__init__.py"
        init_py.write_text(
            init_py.read_text(encoding="utf-8").replace("from .reconcile import", "from .reconciliation import"),
            encoding="utf-8",
        )
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    if session_id == "S12":
        val_py = workspace / "src/ledgerpulse/validation.py"
        val_py.write_text(
            val_py.read_text(encoding="utf-8")
            + '\n\nAUDIT_FREEZE_TAG: str = "v1-audit-ready"\n\n\n'
            "def verify_audit_readiness(ledger: object) -> bool:\n"
            '    """Return True when ledger passes pre-audit readiness checks."""\n'
            "    return ledger is not None\n",
            encoding="utf-8",
        )
        cli_mjs = workspace / "src/reporter/cli.mjs"
        cli_mjs.write_text(
            cli_mjs.read_text(encoding="utf-8")
            + "\nexport function verifyBundleCli(bundle) {\n"
            "  return { ok: Boolean(bundle) };\n"
            "}\n",
            encoding="utf-8",
        )
        return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"

    return ".brain-79/INDEX.md" if arm == "arm_a" else "docs/architecture.md"


def create_dry_run_runner(
    *,
    timeout_sessions: set[tuple[str, str]] | None = None,
    transient_fail_once_sessions: set[tuple[str, str]] | None = None,
) -> SessionAgyRunner:
    """Create a deterministic offline `SessionAgyRunner` for `--mode dry-run` & tests."""
    timeouts = timeout_sessions or set()
    transient_once = transient_fail_once_sessions or set()
    seen_transient: set[tuple[str, str]] = set()
    prompt_to_id = {s.prompt: s.session_id for s in SCENARIOS}

    def _runner(cmd: list[str], cwd: Path, timeout_seconds: int) -> AgyRunResult:
        arm = "arm_a" if cwd.name == "arm_a" else "arm_b"
        prompt = cmd[cmd.index("-p") + 1] if "-p" in cmd else ""
        session_id = prompt_to_id.get(prompt, "S1")
        key = (arm, session_id)

        if key in transient_once and key not in seen_transient:
            seen_transient.add(key)
            return AgyRunResult(
                exit_code=1,
                stdout="",
                stderr="HTTP 429 rate limit exceeded",
                timed_out=False,
                duration_seconds=0.01,
            )

        if key in timeouts:
            return AgyRunResult(
                exit_code=124,
                stdout="",
                stderr=f"Simulated timeout after {timeout_seconds}s",
                timed_out=True,
                duration_seconds=float(timeout_seconds),
            )

        doc_read_path = _apply_dry_run_mutations(cwd, arm, session_id)
        conv_id = f"dry-{arm}-{session_id}"
        stream_lines = [
            json.dumps({"type": "init", "conversation_id": conv_id}),
            json.dumps(
                {
                    "type": "tool_use",
                    "name": "read_file",
                    "input": {"path": doc_read_path},
                    "content": "dry-run doc read " * 20,
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "usage": {"input_tokens": 250, "output_tokens": 120},
                }
            ),
        ]
        return AgyRunResult(
            exit_code=0,
            stdout="\n".join(stream_lines) + "\n",
            stderr="",
            timed_out=False,
            duration_seconds=0.05,
        )

    return _runner


__all__ = [
    "AgyRunResult",
    "DEFAULT_EFFORT",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_TRANSIENT_RETRIES",
    "SessionAgyRunner",
    "SessionRecord",
    "StreamTelemetry",
    "TelemetryError",
    "build_agy_session_cmd",
    "capture_changed_paths",
    "commit_session_changes",
    "create_dry_run_runner",
    "default_live_agy_runner",
    "is_transient_error",
    "load_session_records",
    "parse_stream_json_telemetry",
    "run_benchmark_sessions",
    "run_single_session",
]
