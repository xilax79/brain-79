"""PreToolUse hook script that denies any tool call referencing `src/` during blind recall."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

_PATH_KEYS: tuple[str, ...] = (
    "path",
    "Path",
    "file_path",
    "target_file",
    "SearchPath",
    "DirectoryPath",
    "AbsolutePath",
)
_CMD_KEYS: tuple[str, ...] = ("CommandLine", "command", "cmd")
_CMD_SRC_RE = re.compile(r"(?:^|[\s\"'=/])src(?:/|$|[\s\"'])")


def _references_src(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False

    containers: list[dict[str, Any]] = [payload]
    tool_call = payload.get("toolCall")
    if isinstance(tool_call, dict):
        containers.append(tool_call)
        if isinstance(tool_call.get("args"), dict):
            containers.append(tool_call["args"])
    for key in ("tool_input", "input", "arguments", "args"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            containers.append(nested)

    for container in containers:
        for pkey in _PATH_KEYS:
            val = container.get(pkey)
            if isinstance(val, str) and val.strip():
                norm = val.strip().replace("\\", "/")
                if norm == "src" or norm.startswith("src/") or "/src/" in norm or norm.endswith("/src"):
                    return True
        for ckey in _CMD_KEYS:
            cmd_val = container.get(ckey)
            if isinstance(cmd_val, str):
                norm_cmd = cmd_val.replace("\\", "/")
                if _CMD_SRC_RE.search(norm_cmd) or "/src/" in norm_cmd:
                    return True
    return False


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"decision": "allow"}))
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))
        return 0

    if _references_src(payload):
        print(
            json.dumps(
                {
                    "decision": "deny",
                    "reason": "Blind recall probe: reading files under src/ is prohibited.",
                }
            )
        )
        return 0

    print(json.dumps({"decision": "allow"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
