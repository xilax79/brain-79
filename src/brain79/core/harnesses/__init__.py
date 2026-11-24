"""Declarative harness adapter registry (Phase 10 Stage 4: R-4.2; Phase 11 Stage 2: R-2.2)."""

from __future__ import annotations

from pathlib import Path

from brain79.core.harnesses.agents_md import AgentsMdAdapter
from brain79.core.harnesses.antigravity import AntigravityAdapter
from brain79.core.harnesses.base import HarnessAdapter
from brain79.core.harnesses.claude_code import ClaudeCodeAdapter
from brain79.core.harnesses.copilot import CopilotAdapter
from brain79.core.harnesses.cursor import CursorAdapter
from brain79.core.harnesses.cursor_rules import CursorRulesAdapter
from brain79.core.harnesses.lifecycle_hooks import (
    AntigravityHooksAdapter,
    ClaudeHooksAdapter,
    CursorHooksAdapter,
)
from brain79.core.harnesses.mcp_json import McpJsonAdapter

_HARNESS_ADAPTERS: list[HarnessAdapter] = [
    AgentsMdAdapter(),
    ClaudeCodeAdapter(),
    CursorRulesAdapter(),
    CopilotAdapter(),
    McpJsonAdapter(),
    AntigravityAdapter(),
    CursorAdapter(),
]

_LIFECYCLE_HOOK_ADAPTERS: list[HarnessAdapter] = [
    ClaudeHooksAdapter(),
    AntigravityHooksAdapter(),
    CursorHooksAdapter(),
]

_HARNESS_ALIASES: dict[str, tuple[str, ...]] = {
    "agents": ("agents_md",),
    "agents_md": ("agents_md",),
    "claude": ("claude_code",),
    "claude_code": ("claude_code",),
    "cursor": ("cursor", "cursor_rules"),
    "cursor_mcp": ("cursor",),
    "cursor_rules": ("cursor_rules",),
    "copilot": ("copilot",),
    "agy": ("antigravity",),
    "antigravity": ("antigravity",),
    "mcp": ("mcp_json",),
    "mcp_json": ("mcp_json",),
    "hooks": ("claude_hooks", "agy_hooks", "cursor_hooks"),
    "claude_hooks": ("claude_hooks",),
    "agy_hooks": ("agy_hooks",),
    "cursor_hooks": ("cursor_hooks",),
}


def resolve_harness_selection(harnesses: list[str] | str | None) -> list[HarnessAdapter]:
    """Resolve user-supplied harness names/aliases to registered HarnessAdapter instances."""
    if harnesses is None:
        return list(_HARNESS_ADAPTERS)

    raw_items: list[str] = (
        [part.strip().lower() for part in harnesses.split(",") if part.strip()]
        if isinstance(harnesses, str)
        else [part.strip().lower() for item in harnesses for part in item.split(",") if part.strip()]
    )
    if not raw_items or raw_items == ["all"]:
        return list(_HARNESS_ADAPTERS)

    by_name = {adapter.name: adapter for adapter in (*_HARNESS_ADAPTERS, *_LIFECYCLE_HOOK_ADAPTERS)}
    selected_names: list[str] = []
    for token in raw_items:
        if token == "all":
            for adapter in _HARNESS_ADAPTERS:
                if adapter.name not in selected_names:
                    selected_names.append(adapter.name)
            continue
        mapped = _HARNESS_ALIASES.get(token)
        if mapped is None:
            if token in by_name:
                mapped = (token,)
            else:
                valid = sorted(set(_HARNESS_ALIASES.keys()) | set(by_name.keys()) | {"all"})
                raise ValueError(f"Unknown harness '{token}'. Valid options: {', '.join(valid)}")
        for target_name in mapped:
            if target_name not in selected_names and target_name in by_name:
                selected_names.append(target_name)

    return [by_name[n] for n in selected_names]


def register_harness_adapter(adapter: HarnessAdapter) -> None:
    """Register a custom HarnessAdapter (replaces existing adapter with the same name)."""
    for idx, existing in enumerate(_HARNESS_ADAPTERS):
        if existing.name == adapter.name:
            _HARNESS_ADAPTERS[idx] = adapter
            return
    _HARNESS_ADAPTERS.append(adapter)


def get_harness_adapters() -> tuple[HarnessAdapter, ...]:
    """Return all registered Tier 1 harness adapters in deterministic order."""
    return tuple(_HARNESS_ADAPTERS)


def get_lifecycle_hook_adapters() -> tuple[HarnessAdapter, ...]:
    """Return all opt-in lifecycle hook harness adapters in deterministic order."""
    return tuple(_LIFECYCLE_HOOK_ADAPTERS)


def sync_all_harnesses(project_root: Path) -> list[str]:
    """Synchronize all registered harness adapters for project_root."""
    touched: list[str] = []
    for adapter in _HARNESS_ADAPTERS:
        touched.extend(adapter.sync(project_root))
    return touched


def diagnose_all_harnesses(project_root: Path) -> dict[str, list[str]]:
    """Run diagnostics across all registered Tier 1 and installed lifecycle hook adapters."""
    results: dict[str, list[str]] = {
        adapter.name: adapter.diagnose(project_root) for adapter in _HARNESS_ADAPTERS
    }
    for hook_adapter in _LIFECYCLE_HOOK_ADAPTERS:
        if hook_adapter.detect(project_root):
            results[hook_adapter.name] = hook_adapter.diagnose(project_root)
    return results


__all__ = [
    "AgentsMdAdapter",
    "AntigravityAdapter",
    "AntigravityHooksAdapter",
    "ClaudeCodeAdapter",
    "ClaudeHooksAdapter",
    "CopilotAdapter",
    "CursorAdapter",
    "CursorHooksAdapter",
    "CursorRulesAdapter",
    "HarnessAdapter",
    "McpJsonAdapter",
    "diagnose_all_harnesses",
    "get_harness_adapters",
    "get_lifecycle_hook_adapters",
    "register_harness_adapter",
    "resolve_harness_selection",
    "sync_all_harnesses",
]
