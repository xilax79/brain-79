"""Unit tests for scripts/run_e2e_smoke.py (CLI builder, parser, and recovery verifier)."""

import json
from pathlib import Path
import pytest

from scripts.run_e2e_smoke import (
    check_mcp_zero_retry,
    find_agent_cli,
    find_latest_session_for_dir,
    get_agent_cmd,
    verify_recovery_in_session,
)


def test_find_agent_cli_prefers_agy_and_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. BRAIN79_SMOKE_CLI override
    monkeypatch.setenv("BRAIN79_SMOKE_CLI", "custom-cli")
    assert find_agent_cli() == "custom-cli"

    monkeypatch.delenv("BRAIN79_SMOKE_CLI", raising=False)

    # 2. Both agy and pi in PATH -> prefers agy
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/local/bin/{cmd}" if cmd in ("agy", "pi") else None)
    assert find_agent_cli() == "agy"

    # 3. Only pi in PATH -> falls back to pi
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/local/bin/{cmd}" if cmd == "pi" else None)
    assert find_agent_cli() == "pi"

    # 4. Neither in PATH -> None
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert find_agent_cli() is None


def test_get_agent_cmd_agy_and_pi(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test agy with thinking effort
    monkeypatch.setattr("scripts.run_e2e_smoke.find_agent_cli", lambda: "agy")
    monkeypatch.setattr("scripts.run_e2e_smoke.MODEL", "gemini-3.8-flash:low")
    cmd_agy = get_agent_cmd("Test prompt")
    assert cmd_agy == [
        "agy",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--model",
        "gemini-3.8-flash",
        "--effort",
        "low",
        "-p",
        "Test prompt",
    ]

    # Test agy without thinking effort
    monkeypatch.setattr("scripts.run_e2e_smoke.MODEL", "gemini-3.8-flash")
    cmd_agy_no_effort = get_agent_cmd("Test prompt")
    assert cmd_agy_no_effort == [
        "agy",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--model",
        "gemini-3.8-flash",
        "-p",
        "Test prompt",
    ]

    # Test pi with thinking effort
    monkeypatch.setattr("scripts.run_e2e_smoke.find_agent_cli", lambda: "pi")
    monkeypatch.setattr("scripts.run_e2e_smoke.MODEL", "gemini-3.8-flash:low")
    cmd_pi = get_agent_cmd("Test prompt")
    assert cmd_pi == [
        "pi",
        "--mcp-project-servers",
        "allow",
        "--model",
        "gemini-3.8-flash",
        "--thinking",
        "low",
        "-p",
        "Test prompt",
    ]


def test_check_mcp_zero_retry_with_agy_stream_json(tmp_path: Path) -> None:
    session_file = tmp_path / "agent_session.jsonl"
    events = [
        {"event": "init", "conversation_id": "test-1"},
        {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "state": "ACTIVE",
                "tool_name": "call_mcp_tool",
                "tool_info": {
                    "name": "call_mcp_tool",
                    "parameters": {"ServerName": "brain79", "ToolName": "brain79_orient"},
                },
            },
        },
        {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "state": "DONE",
                "tool_name": "call_mcp_tool",
                "tool_info": {
                    "name": "call_mcp_tool",
                    "parameters": {"ServerName": "brain79", "ToolName": "brain79_orient"},
                    "output": "# Brain-79 Orientation OK",
                },
            },
        },
        {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "state": "DONE",
                "tool_name": "call_mcp_tool",
                "tool_info": {
                    "name": "call_mcp_tool",
                    "parameters": {"ServerName": "brain79", "ToolName": "brain79_session_commit"},
                    "output": "Successfully committed session",
                },
            },
        },
    ]
    session_file.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    failures = check_mcp_zero_retry(session_file)
    assert failures == []

    # Inject failure
    fail_event = {
        "event": "step_update",
        "step_update": {
            "step_type": "tool",
            "state": "DONE",
            "tool_name": "call_mcp_tool",
            "tool_info": {
                "name": "call_mcp_tool",
                "parameters": {"ServerName": "brain79", "ToolName": "brain79_session_commit"},
                "output": "Commit Validation Failed: schema error",
            },
        },
    }
    events.append(fail_event)
    session_file.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    failures = check_mcp_zero_retry(session_file)
    assert len(failures) == 1
    assert "brain79_session_commit" in failures[0]
    assert "Commit Validation Failed:" in failures[0]


def test_verify_recovery_in_session_with_agy_stream_json(tmp_path: Path) -> None:
    session_file = tmp_path / "agent_session.jsonl"
    events = [
        {"event": "init", "conversation_id": "test-rec"},
        {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "state": "DONE",
                "tool_name": "call_mcp_tool",
                "tool_info": {
                    "name": "call_mcp_tool",
                    "parameters": {"ServerName": "brain79", "ToolName": "brain79_orient"},
                    "output": "# Orientation",
                },
            },
        },
        # 1st commit: rejected with unresolved_session_ripple
        {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "state": "DONE",
                "tool_name": "call_mcp_tool",
                "tool_info": {
                    "name": "call_mcp_tool",
                    "parameters": {"ServerName": "brain79", "ToolName": "brain79_session_commit"},
                    "output": "Commit Validation Failed:\n- unresolved_session_ripple: architecture/overview.md needs update",
                },
            },
        },
        # 2nd commit: successful
        {
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "state": "DONE",
                "tool_name": "call_mcp_tool",
                "tool_info": {
                    "name": "call_mcp_tool",
                    "parameters": {"ServerName": "brain79", "ToolName": "brain79_session_commit"},
                    "output": "Successfully committed session with 2 writes.",
                },
            },
        },
    ]
    session_file.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")

    assert verify_recovery_in_session(session_file, "unresolved_session_ripple") is True
    # Checking for wrong rule fails
    assert verify_recovery_in_session(session_file, "duplicate_governance_target") is False


def test_verify_recovery_in_session_with_transcript(tmp_path: Path) -> None:
    session_file = tmp_path / "transcript.jsonl"
    steps = [
        {"step_index": 0, "type": "USER_INPUT", "content": "Prompt"},
        {
            "step_index": 1,
            "type": "PLANNER_RESPONSE",
            "tool_calls": [
                {
                    "name": "call_mcp_tool",
                    "args": {"ServerName": '"brain79"', "ToolName": '"brain79_session_commit"'},
                }
            ],
        },
        {
            "step_index": 2,
            "type": "GENERIC",
            "content": "Commit Validation Failed:\n- duplicate_governance_target: already governed",
        },
        {
            "step_index": 3,
            "type": "PLANNER_RESPONSE",
            "tool_calls": [
                {
                    "name": "call_mcp_tool",
                    "args": {"ServerName": '"brain79"', "ToolName": '"brain79_session_commit"'},
                }
            ],
        },
        {
            "step_index": 4,
            "type": "GENERIC",
            "content": "Successfully committed session.",
        },
    ]
    session_file.write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

    assert verify_recovery_in_session(session_file, "duplicate_governance_target") is True


def test_find_latest_session_for_dir_finds_local_session(tmp_path: Path) -> None:
    session_file = tmp_path / "agent_session_12345.jsonl"
    session_file.write_text('{"event": "init"}\n', encoding="utf-8")

    found = find_latest_session_for_dir(tmp_path)
    assert found == session_file


def test_verify_recovery_in_session_user_message_markers(tmp_path: Path) -> None:
    session_file = tmp_path / "transcript_anti_sprawl.jsonl"
    steps = [
        {"step_index": 0, "type": "USER_INPUT", "content": "Prompt"},
        {
            "step_index": 1,
            "type": "PLANNER_RESPONSE",
            "tool_calls": [
                {
                    "name": "call_mcp_tool",
                    "args": {"ServerName": '"brain79"', "ToolName": '"brain79_session_commit"'},
                }
            ],
        },
        {
            "step_index": 2,
            "type": "GENERIC",
            "content": "Commit Validation Failed:\nAnti-sprawl guard: existing active article 'features/auth.md' of type 'feature' already governs src/core/auth.py.",
        },
        {
            "step_index": 3,
            "type": "PLANNER_RESPONSE",
            "tool_calls": [
                {
                    "name": "call_mcp_tool",
                    "args": {"ServerName": '"brain79"', "ToolName": '"brain79_session_commit"'},
                }
            ],
        },
        {
            "step_index": 4,
            "type": "GENERIC",
            "content": "# Brain-79 — Session Commit Receipt",
        },
    ]
    session_file.write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

    assert verify_recovery_in_session(session_file, "duplicate_governance_target") is True

    # Also test umbrella ripple bypass message
    session_ripple = tmp_path / "transcript_ripple.jsonl"
    steps[2]["content"] = (
        "Commit Validation Failed:\nCannot verify umbrella article 'architecture/overview.md': it has unresolved drift targeting intra-wiki articles."
    )
    session_ripple.write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")
    assert verify_recovery_in_session(session_ripple, "unresolved_session_ripple") is True
