"""Offline deterministic unit tests for Stage 2 longitudinal runner (SPEC-016 AC-2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.anti_rot.contracts.specs import SESSION_CONTRACTS
from benchmarks.anti_rot.runner import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TRANSIENT_RETRIES,
    AgyRunResult,
    SessionRecord,
    TelemetryError,
    build_agy_session_cmd,
    create_dry_run_runner,
    load_session_records,
    parse_stream_json_telemetry,
    run_benchmark_sessions,
    run_single_session,
)
from benchmarks.anti_rot.scenarios import (
    FORBIDDEN_PROMPT_TERMS,
    SCENARIOS,
    SessionScenario,
    prompt_sha256,
)
from benchmarks.anti_rot.workspace import initialize_arms


def test_scenarios_order_parity_and_forbidden_terms() -> None:
    expected_ids = [f"S{i}" for i in range(1, 13)]
    assert [s.session_id for s in SCENARIOS] == expected_ids
    assert SCENARIOS[0].triage_type == "bootstrap"
    assert SCENARIOS[8].triage_type == "type_a"
    assert SCENARIOS[9].triage_type == "type_b"

    for scenario in SCENARIOS:
        assert isinstance(scenario, SessionScenario)
        assert scenario.prompt.strip()
        lowered = scenario.prompt.lower()
        for forbidden in FORBIDDEN_PROMPT_TERMS:
            assert forbidden not in lowered, (
                f"{scenario.session_id} prompt must not mention '{forbidden}'"
            )
        digest = prompt_sha256(scenario.prompt)
        assert len(digest) == 64
        assert digest == prompt_sha256(scenario)


def test_scenarios_cover_all_pinned_contracts() -> None:
    by_id = {s.session_id: s for s in SCENARIOS}
    for sid, contract in SESSION_CONTRACTS.items():
        prompt = by_id[sid].prompt
        for req_file in contract.required_files:
            assert req_file in prompt, f"{sid} prompt missing required_file {req_file}"
        for forb_file in contract.forbidden_files:
            assert forb_file in prompt, f"{sid} prompt missing forbidden_file {forb_file}"
        for py_sym in contract.py_symbols:
            assert py_sym.symbol_name in prompt, f"{sid} prompt missing py symbol {py_sym.symbol_name}"
            for param in py_sym.params:
                assert param in prompt, f"{sid} prompt missing param {param} for {py_sym.symbol_name}"
        for _, forb_sym in contract.forbidden_py_symbols:
            assert forb_sym in prompt, f"{sid} prompt missing forbidden symbol {forb_sym}"
        for _, consts in contract.py_constants.items():
            for const_name, const_val in consts.items():
                assert const_name in prompt, f"{sid} prompt missing constant {const_name}"
                assert str(const_val) in prompt, f"{sid} prompt missing value {const_val}"
        for js_sym in contract.js_symbols:
            assert js_sym.symbol_name in prompt, f"{sid} prompt missing js symbol {js_sym.symbol_name}"
            for param in js_sym.params:
                assert param in prompt, f"{sid} prompt missing js param {param} for {js_sym.symbol_name}"


def test_build_agy_session_cmd_enforces_cold_start() -> None:
    cmd = build_agy_session_cmd("Implement feature X")
    assert cmd[0] == "agy"
    assert "-p" in cmd and cmd[cmd.index("-p") + 1] == "Implement feature X"
    assert "--model" in cmd and cmd[cmd.index("--model") + 1] == DEFAULT_MODEL
    assert "--effort" in cmd and cmd[cmd.index("--effort") + 1] == DEFAULT_EFFORT
    assert "--output-format" in cmd and cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--dangerously-skip-permissions" in cmd
    assert "--print-timeout" in cmd and cmd[cmd.index("--print-timeout") + 1] == f"{DEFAULT_TIMEOUT_SECONDS}s"

    forbidden_flags = {"--continue", "-c", "--resume", "-r", "--conversation"}
    assert not (forbidden_flags & set(cmd))


def test_parse_stream_json_telemetry_extracts_tokens_and_paths() -> None:
    stream = "\n".join(
        [
            json.dumps({"type": "init", "conversation_id": "conv-abc-123"}),
            json.dumps(
                {
                    "type": "tool_use",
                    "name": "read_file",
                    "input": {"path": ".brain-79/INDEX.md"},
                    "content": "x" * 400,
                }
            ),
            json.dumps(
                {
                    "type": "tool_use",
                    "name": "read_file",
                    "input": {"path": "src/ledgerpulse/pricing.py"},
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "usage": {"input_tokens": 1200, "output_tokens": 350},
                }
            ),
        ]
    )
    telemetry = parse_stream_json_telemetry(stream)
    assert telemetry.conversation_id == "conv-abc-123"
    assert telemetry.input_tokens == 1200
    assert telemetry.output_tokens == 350
    assert telemetry.tool_calls == 2
    assert telemetry.doc_read_tokens == 100
    assert telemetry.src_read_paths == ["src/ledgerpulse/pricing.py"]


def test_parse_stream_json_telemetry_split_tool_result_and_search_cmd_paths() -> None:
    stream = "\n".join(
        [
            json.dumps({"type": "init", "conversation_id": "conv-split-1"}),
            json.dumps(
                {
                    "type": "tool_use",
                    "id": "call-doc-1",
                    "name": "read_file",
                    "input": {"path": "docs/architecture.md"},
                }
            ),
            json.dumps(
                {
                    "type": "tool_result",
                    "tool_use_id": "call-doc-1",
                    "content": [{"type": "text", "text": "a" * 200}],
                }
            ),
            json.dumps(
                {
                    "type": "tool_use",
                    "id": "call-orient-2",
                    "name": "mcp__brain79__brain79_orient",
                    "input": {"task": "S5"},
                }
            ),
            json.dumps(
                {
                    "type": "tool_result",
                    "tool_use_id": "call-orient-2",
                    "output": "b" * 400,
                }
            ),
            json.dumps(
                {
                    "type": "tool_use",
                    "id": "call-grep-3",
                    "name": "grep_search",
                    "input": {"SearchPath": "src/ledgerpulse", "Query": "tax"},
                }
            ),
            json.dumps(
                {
                    "type": "tool_use",
                    "id": "call-sh-4",
                    "name": "run_command",
                    "input": {"CommandLine": "cat src/reporter/schema.mjs"},
                }
            ),
        ]
    )
    telemetry = parse_stream_json_telemetry(stream)
    assert telemetry.conversation_id == "conv-split-1"
    assert telemetry.tool_calls == 4
    assert telemetry.doc_read_tokens == 150
    assert telemetry.src_read_paths == ["src/ledgerpulse", "src/reporter/schema.mjs"]


def test_parse_stream_json_telemetry_real_agy_nested_events() -> None:
    stream = "\n".join(
        [
            json.dumps(
                {
                    "event": "init",
                    "conversation_id": "a775826c-real-1",
                    "init": {"model": "gemini-4-hydrogen-low", "cwd": "/tmp/ws", "tools": ["read_file"]},
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "a775826c-real-1",
                        "step_index": 1,
                        "state": "DONE",
                        "step_type": "agent_response",
                        "usage": {"input_tokens": 11930, "output_tokens": 210},
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "a775826c-real-1",
                        "step_index": 2,
                        "state": "ACTIVE",
                        "step_type": "tool",
                        "tool_name": "read_file",
                        "tool_info": {
                            "name": "read_file",
                            "parameters": {"Path": "/tmp/ws/AGENTS.md", "StartLine": 1, "EndLine": 20},
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "a775826c-real-1",
                        "step_index": 2,
                        "state": "DONE",
                        "step_type": "tool",
                        "tool_name": "read_file",
                        "tool_info": {
                            "name": "read_file",
                            "parameters": {"Path": "/tmp/ws/AGENTS.md", "StartLine": 1, "EndLine": 20},
                            "output": "20 lines, 2023 bytes",
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "a775826c-real-1",
                        "step_index": 3,
                        "state": "ACTIVE",
                        "step_type": "tool",
                        "tool_name": "call_mcp_tool",
                        "tool_info": {
                            "name": "call_mcp_tool",
                            "parameters": {"ServerName": "brain79", "ToolName": "brain79_orient"},
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "a775826c-real-1",
                        "step_index": 3,
                        "state": "DONE",
                        "step_type": "tool",
                        "tool_name": "call_mcp_tool",
                        "tool_info": {
                            "name": "call_mcp_tool",
                            "parameters": {"ServerName": "brain79", "ToolName": "brain79_orient"},
                            "output": "x" * 400,
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "a775826c-real-1",
                        "step_index": 4,
                        "state": "ACTIVE",
                        "step_type": "tool",
                        "tool_name": "read_file",
                        "tool_info": {
                            "name": "read_file",
                            "parameters": {"Path": "/tmp/ws/src/ledgerpulse/models.py"},
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "event": "result",
                    "result": {
                        "conversation_id": "a775826c-real-1",
                        "status": "SUCCESS",
                        "usage": {"input_tokens": 14776, "output_tokens": 326},
                    },
                }
            ),
        ]
    )
    telemetry = parse_stream_json_telemetry(stream)
    assert telemetry.conversation_id == "a775826c-real-1"
    assert telemetry.input_tokens == 14776
    assert telemetry.output_tokens == 326
    assert telemetry.tool_calls == 2
    assert telemetry.doc_read_tokens == 505 + 100
    assert telemetry.src_read_paths == ["src/ledgerpulse/models.py"]


def test_parse_stream_json_telemetry_timeout_fallback_to_step_usage() -> None:
    stream = "\n".join(
        [
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "conv-timeout-1",
                        "step_index": 1,
                        "state": "DONE",
                        "step_type": "agent_response",
                        "usage": {"input_tokens": 1000, "output_tokens": 50},
                    },
                }
            ),
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": "conv-timeout-1",
                        "step_index": 2,
                        "state": "DONE",
                        "step_type": "agent_response",
                        "usage": {"input_tokens": 2000, "output_tokens": 80},
                    },
                }
            ),
        ]
    )
    telemetry = parse_stream_json_telemetry(stream)
    assert telemetry.conversation_id == "conv-timeout-1"
    assert telemetry.input_tokens == 3000
    assert telemetry.output_tokens == 130


def test_retry_policy_transient_vs_timeout(tmp_path: Path) -> None:
    ws = initialize_arms(tmp_path / "ws")
    dry_runner = create_dry_run_runner(
        transient_fail_once_sessions={("arm_a", "S1")},
        timeout_sessions={("arm_b", "S1")},
    )
    calls: dict[str, int] = {"arm_a": 0, "arm_b": 0}

    def counting_runner(cmd: list[str], cwd: Path, timeout_seconds: int) -> AgyRunResult:
        arm_key = "arm_a" if cwd.name == "arm_a" else "arm_b"
        calls[arm_key] += 1
        return dry_runner(cmd, cwd, timeout_seconds)

    s1 = SCENARIOS[0]
    rec_a = run_single_session("arm_a", ws.arm_a, s1, agy_runner=counting_runner)
    rec_b = run_single_session("arm_b", ws.arm_b, s1, agy_runner=counting_runner)

    assert calls["arm_a"] == 1 + MAX_TRANSIENT_RETRIES
    assert rec_a.retries == 1
    assert rec_a.clean_completion is True

    assert calls["arm_b"] == 1
    assert rec_b.retries == 0
    assert rec_b.timed_out is True
    assert rec_b.clean_completion is False


def test_load_session_records_fail_closed_on_corrupt_or_duplicate(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    with pytest.raises(TelemetryError):
        load_session_records(missing)

    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text("{not valid json\n", encoding="utf-8")
    with pytest.raises(TelemetryError):
        load_session_records(corrupt)

    incomplete = tmp_path / "incomplete.jsonl"
    incomplete.write_text(json.dumps({"arm": "arm_a", "session_id": "S1"}) + "\n", encoding="utf-8")
    with pytest.raises(TelemetryError):
        load_session_records(incomplete)


def test_dry_run_12_sessions_end_to_end_with_simulated_timeout(tmp_path: Path) -> None:
    ws = initialize_arms(tmp_path / "ws")
    out_dir = tmp_path / "out"
    seen_prompts: dict[str, list[str]] = {"arm_a": [], "arm_b": []}
    base_runner = create_dry_run_runner(timeout_sessions={("arm_b", "S9")})

    def spy_runner(cmd: list[str], cwd: Path, timeout_seconds: int) -> AgyRunResult:
        arm = "arm_a" if cwd.name == "arm_a" else "arm_b"
        prompt = cmd[cmd.index("-p") + 1]
        seen_prompts[arm].append(prompt)
        return base_runner(cmd, cwd, timeout_seconds)

    records = run_benchmark_sessions(ws, out_dir, agy_runner=spy_runner)
    assert len(records) == 24
    assert seen_prompts["arm_a"] == seen_prompts["arm_b"]

    arm_a_records = [r for r in records if r.arm == "arm_a"]
    arm_b_records = [r for r in records if r.arm == "arm_b"]
    assert all(r.clean_completion for r in arm_a_records)
    conv_ids = [r.conversation_id for r in records if r.conversation_id is not None]
    assert len(conv_ids) == 23
    assert len(set(conv_ids)) == 23

    # S9 in Arm A produces zero permanent doc mutations & clean git tree
    s9_a = next(r for r in arm_a_records if r.session_id == "S9")
    assert s9_a.changed_paths == []
    assert s9_a.contract_passed is True

    # S9 timeout in Arm B is explicitly logged without fabricating a pass
    s9_b = next(r for r in arm_b_records if r.session_id == "S9")
    assert s9_b.timed_out is True
    assert s9_b.clean_completion is False

    # Arm A records include brain79 stats, ci-check (with exit code), and lint telemetry
    assert all(r.brain79_ci_check_exit_code is not None for r in arm_a_records)
    s12_a = next(r for r in arm_a_records if r.session_id == "S12")
    assert isinstance(s12_a.brain79_stats, dict)
    assert isinstance(s12_a.brain79_ci_check, dict)
    assert s12_a.brain79_ci_check_exit_code == 0
    assert s12_a.brain79_lint_exit_code == 0

    # JSONL persisted and reloadable; duplicate check works
    jsonl_path = out_dir / "sessions.jsonl"
    assert jsonl_path.is_file()
    loaded = load_session_records(jsonl_path)
    assert len(loaded) == 24
    assert all(isinstance(r, SessionRecord) for r in loaded)

    # Appending duplicate entry triggers TelemetryError
    with jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write(jsonl_path.read_text(encoding="utf-8").splitlines()[0] + "\n")
    with pytest.raises(TelemetryError):
        load_session_records(jsonl_path)
