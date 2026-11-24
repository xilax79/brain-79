"""Opt-in native lifecycle hook harness adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain79.core.locks import atomic_replace_with_retry

_HOOK_TIMEOUT_SECONDS = 15


def _expected_command(client: str, event_arg: str) -> str:
    """Return the canonical portable brain79 lifecycle hook command."""
    return f"brain79 ci-check --lifecycle-hook {event_arg} --client {client}"


def _is_brain79_hook_entry(entry: object) -> bool:
    """Return True when a hook entry dictionary invokes brain79."""
    if not isinstance(entry, dict):
        return False
    cmd = entry.get("command")
    if isinstance(cmd, str) and "brain79" in cmd:
        return True
    nested = entry.get("hooks")
    if isinstance(nested, list):
        return any(_is_brain79_hook_entry(sub) for sub in nested)
    return False


def _has_brain79_hook_in_mapping(hooks_obj: object) -> bool:
    """Return True when any list under a hooks mapping contains a brain79 entry."""
    if not isinstance(hooks_obj, dict):
        return False
    return any(
        isinstance(entries, list) and any(_is_brain79_hook_entry(item) for item in entries)
        for entries in hooks_obj.values()
    )


def _detect_hooks_file(target: Path) -> bool:
    """Detect whether target is a file containing brain79 hooks (or corrupt JSON referencing brain79)."""
    if not target.is_file():
        return False
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "brain79" in raw
    if isinstance(data, dict):
        return _has_brain79_hook_in_mapping(data.get("hooks"))
    return "brain79" in raw


def _load_json_dict_for_sync(
    target: Path,
    *,
    dry_run: bool,
) -> tuple[dict[str, Any], str | None, bool]:
    """Load an existing JSON object from target, backing up corrupt/non-object files to <name>.bak."""
    if not target.is_file():
        return {}, None, False

    try:
        old_raw = target.read_text(encoding="utf-8")
    except OSError:
        old_raw = None

    corrupt = False
    data: dict[str, Any] = {}
    if old_raw is None:
        corrupt = True
    else:
        try:
            parsed = json.loads(old_raw)
            if isinstance(parsed, dict):
                data = parsed
            else:
                corrupt = True
        except json.JSONDecodeError:
            corrupt = True

    if corrupt and not dry_run:
        bak_path = target.with_name(f"{target.name}.bak")
        atomic_replace_with_retry(target, bak_path)

    return data, old_raw, corrupt


def _write_json_if_changed(
    target: Path,
    rel_path: str,
    data: dict[str, Any],
    old_raw: str | None,
    corrupt_backed_up: bool,
    *,
    dry_run: bool,
) -> list[str]:
    """Serialize data as LF-terminated UTF-8 JSON and write if changed."""
    new_raw = json.dumps(data, indent=2) + "\n"
    if not corrupt_backed_up and old_raw == new_raw:
        return []
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_raw, encoding="utf-8", newline="\n")
    return [rel_path]


def _read_json_dict_for_diagnose(target: Path, rel_path: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Read and parse a JSON object for diagnose(), reporting corrupt JSON explicitly."""
    if not target.is_file():
        return None, []
    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [f"{rel_path} contains corrupt JSON: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{rel_path} contains corrupt JSON: expected a JSON object."]
    return data, []


def _merge_flat_hook_entries(existing: object, canonical_entry: dict[str, Any]) -> list[Any]:
    """Deduplicate brain79 entries from a flat hook list while preserving third-party hooks."""
    kept = [item for item in existing if not _is_brain79_hook_entry(item)] if isinstance(existing, list) else []
    kept.append(canonical_entry)
    return kept


def _diagnose_flat_hook_list(
    rel_path: str,
    entries: object,
    event_key: str,
    expected_cmd: str,
) -> list[str]:
    """Validate flat hook list entries for a single lifecycle event."""
    if not isinstance(entries, list):
        return [f"{rel_path} is missing '{event_key}' brain79 lifecycle hook."]
    brain79_entries = [item for item in entries if _is_brain79_hook_entry(item)]
    if not brain79_entries:
        return [f"{rel_path} is missing '{event_key}' brain79 lifecycle hook."]
    issues: list[str] = []
    for item in brain79_entries:
        cmd = str(item.get("command", ""))
        if cmd != expected_cmd:
            issues.append(f"{rel_path} '{event_key}' uses non-portable or misconfigured command '{cmd}'.")
    return issues


class ClaudeHooksAdapter:
    """Opt-in HarnessAdapter for Claude Code (.claude/settings.json) lifecycle hooks."""

    name: str = "claude_hooks"
    _rel_path: str = ".claude/settings.json"

    def detect(self, project_root: Path) -> bool:
        return _detect_hooks_file(project_root / self._rel_path)

    def sync(self, project_root: Path, dry_run: bool = False) -> list[str]:
        target = project_root / self._rel_path
        if target.is_dir():
            return []

        data, old_raw, corrupt = _load_json_dict_for_sync(target, dry_run=dry_run)
        hooks_obj = data.get("hooks")
        if not isinstance(hooks_obj, dict):
            hooks_obj = {}
            data["hooks"] = hooks_obj

        for event_key, event_arg in (("SessionStart", "session-start"), ("Stop", "stop")):
            expected_handler = {
                "type": "command",
                "command": _expected_command("claude", event_arg),
                "timeout": _HOOK_TIMEOUT_SECONDS,
            }
            existing_groups = hooks_obj.get(event_key)
            cleaned_groups: list[Any] = []
            if isinstance(existing_groups, list):
                for group in existing_groups:
                    if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                        kept_sub = [h for h in group["hooks"] if not _is_brain79_hook_entry(h)]
                        if kept_sub:
                            cleaned_groups.append({**group, "hooks": kept_sub})
                    elif not _is_brain79_hook_entry(group):
                        cleaned_groups.append(group)
            cleaned_groups.append({"matcher": "", "hooks": [expected_handler]})
            hooks_obj[event_key] = cleaned_groups

        return _write_json_if_changed(target, self._rel_path, data, old_raw, corrupt, dry_run=dry_run)

    def diagnose(self, project_root: Path) -> list[str]:
        data, parse_issues = _read_json_dict_for_diagnose(project_root / self._rel_path, self._rel_path)
        if data is None:
            return parse_issues

        hooks_obj = data.get("hooks")
        if not isinstance(hooks_obj, dict):
            return [f"{self._rel_path} is missing 'hooks' object."]

        issues: list[str] = []
        for event_key, event_arg in (("SessionStart", "session-start"), ("Stop", "stop")):
            expected_cmd = _expected_command("claude", event_arg)
            groups = hooks_obj.get(event_key)
            found_cmds: list[str] = []
            has_flat_entry = False
            if isinstance(groups, list):
                for group in groups:
                    if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                        for sub in group["hooks"]:
                            if _is_brain79_hook_entry(sub):
                                found_cmds.append(str(sub.get("command", "")))
                    elif _is_brain79_hook_entry(group):
                        has_flat_entry = True
                        issues.append(
                            f"{self._rel_path} '{event_key}' contains flat brain79 hook entry; "
                            "expected grouped '{matcher, hooks}' object."
                        )

            if not found_cmds and not has_flat_entry:
                issues.append(f"{self._rel_path} is missing '{event_key}' brain79 lifecycle hook.")
            else:
                for cmd in found_cmds:
                    if cmd != expected_cmd:
                        issues.append(
                            f"{self._rel_path} '{event_key}' uses non-portable or misconfigured command '{cmd}'."
                        )
        return issues


class AntigravityHooksAdapter:
    """Opt-in HarnessAdapter for Antigravity (.agents/plugins/brain79/hooks.json) lifecycle hooks."""

    name: str = "agy_hooks"
    _rel_path: str = ".agents/plugins/brain79/hooks.json"

    def detect(self, project_root: Path) -> bool:
        return (project_root / self._rel_path).is_file()

    def sync(self, project_root: Path, dry_run: bool = False) -> list[str]:
        target = project_root / self._rel_path
        if target.is_dir():
            return []

        data, old_raw, corrupt = _load_json_dict_for_sync(target, dry_run=dry_run)
        existing_lifecycle = data.get("brain79-lifecycle")
        lifecycle_obj: dict[str, Any] = dict(existing_lifecycle) if isinstance(existing_lifecycle, dict) else {}
        if lifecycle_obj.get("enabled") is not False:
            lifecycle_obj["enabled"] = True

        for event_key, event_arg in (("SessionStart", "session-start"), ("Stop", "stop")):
            canonical_entry = {
                "type": "command",
                "command": _expected_command("agy", event_arg),
                "timeout": _HOOK_TIMEOUT_SECONDS,
            }
            lifecycle_obj[event_key] = _merge_flat_hook_entries(lifecycle_obj.get(event_key), canonical_entry)

        data["brain79-lifecycle"] = lifecycle_obj
        return _write_json_if_changed(target, self._rel_path, data, old_raw, corrupt, dry_run=dry_run)

    def diagnose(self, project_root: Path) -> list[str]:
        data, parse_issues = _read_json_dict_for_diagnose(project_root / self._rel_path, self._rel_path)
        if data is None:
            return parse_issues

        lifecycle_obj = data.get("brain79-lifecycle")
        if not isinstance(lifecycle_obj, dict):
            return [f"{self._rel_path} is missing 'brain79-lifecycle' configuration."]

        issues: list[str] = []
        for event_key, event_arg in (("SessionStart", "session-start"), ("Stop", "stop")):
            issues.extend(
                _diagnose_flat_hook_list(
                    self._rel_path,
                    lifecycle_obj.get(event_key),
                    event_key,
                    _expected_command("agy", event_arg),
                )
            )
        return issues


class CursorHooksAdapter:
    """Opt-in HarnessAdapter for Cursor (.cursor/hooks.json) lifecycle hooks."""

    name: str = "cursor_hooks"
    _rel_path: str = ".cursor/hooks.json"

    def detect(self, project_root: Path) -> bool:
        return _detect_hooks_file(project_root / self._rel_path)

    def sync(self, project_root: Path, dry_run: bool = False) -> list[str]:
        target = project_root / self._rel_path
        if target.is_dir():
            return []

        data, old_raw, corrupt = _load_json_dict_for_sync(target, dry_run=dry_run)
        if type(data.get("version")) is not int or data.get("version") != 1:
            data["version"] = 1

        hooks_obj = data.get("hooks")
        if not isinstance(hooks_obj, dict):
            hooks_obj = {}
            data["hooks"] = hooks_obj

        for event_key, event_arg in (("sessionStart", "session-start"), ("stop", "stop")):
            canonical_entry = {
                "command": _expected_command("cursor", event_arg),
                "timeout": _HOOK_TIMEOUT_SECONDS,
            }
            hooks_obj[event_key] = _merge_flat_hook_entries(hooks_obj.get(event_key), canonical_entry)

        return _write_json_if_changed(target, self._rel_path, data, old_raw, corrupt, dry_run=dry_run)

    def diagnose(self, project_root: Path) -> list[str]:
        data, parse_issues = _read_json_dict_for_diagnose(project_root / self._rel_path, self._rel_path)
        if data is None:
            return parse_issues

        issues: list[str] = []
        if type(data.get("version")) is not int or data.get("version") != 1:
            issues.append(f"{self._rel_path} is missing valid 'version': 1.")

        hooks_obj = data.get("hooks")
        if not isinstance(hooks_obj, dict):
            issues.append(f"{self._rel_path} is missing 'hooks' object.")
            return issues

        for event_key, event_arg in (("sessionStart", "session-start"), ("stop", "stop")):
            issues.extend(
                _diagnose_flat_hook_list(
                    self._rel_path,
                    hooks_obj.get(event_key),
                    event_key,
                    _expected_command("cursor", event_arg),
                )
            )
        return issues
