from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Literal

from brain79 import __version__
from brain79.config import get_project_root, get_wiki_root
from brain79.core.frontmatter import load_active_schema, parse_frontmatter
from brain79.core.handoff_freshness import compute_handoff_freshness, is_git_workspace
from brain79.core.init_project import (
    AGENTS_END_REGEX,
    AGENTS_START_REGEX,
    update_project,
)
from brain79.core.locks import acquire_wiki_lock
from brain79.core.migration import migrate_wiki


@dataclass
class DoctorCheck:
    category: str
    status: Literal["ok", "warning", "error", "info"]
    message: str
    actionable: str | None = None


@dataclass
class DoctorReport:
    status: Literal["ok", "warning", "error"]
    exit_code: int
    checks: list[DoctorCheck]
    fixed: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "checks": [asdict(c) for c in self.checks],
            "fixed": self.fixed,
        }

    def format_text(self) -> str:
        lines = [
            "# Brain-79 Doctor Diagnostic Report",
            f"[Status: {self.status.upper()}] [Exit code: {self.exit_code}]",
            "",
        ]
        status_icons = {
            "ok": "[✓]",
            "info": "[i]",
            "warning": "[!]",
            "error": "[✗]",
        }
        for c in self.checks:
            icon = status_icons.get(c.status, "[?]")
            lines.append(f"{icon} {c.category}: {c.message}")
            if c.actionable:
                lines.append(f"    Action: {c.actionable}")

        if self.fixed:
            lines.append("")
            lines.append(f"## Repaired items ({len(self.fixed)})")
            for item in self.fixed:
                lines.append(f"- {item}")

        return "\n".join(lines)


def _format_ast_guard_summary(caps: dict[str, Any], polyglot_languages: tuple[str, ...]) -> str:
    """Format a concise one-line AST Guard C capability summary for doctor output."""
    if not caps.get("polyglot_installed"):
        return (
            f"AST guards: python (built-in); install brain79[polyglot] "
            f"for {len(polyglot_languages)} more language parsers."
        )

    active_polyglot = sorted(lang for lang in caps.get("active_languages", []) if lang in polyglot_languages)
    missing = sorted(caps.get("missing_grammars", []))
    active_list = ", ".join(active_polyglot) if active_polyglot else "none"
    summary = f"AST guards: python + {len(active_polyglot)} polyglot parsers ({active_list})"
    if missing:
        summary += f"; {len(missing)} missing ({', '.join(missing)})"
    return f"{summary}."


def run_doctor(
    project_root: Path | None = None,
    wiki_root: Path | None = None,
    fix: bool = False,
    force: bool = False,
    include_desktop: bool = False,
    format: str = "text",
) -> DoctorReport:
    """Run 7-point operational diagnostic checks and optionally auto-repair defects."""
    if wiki_root is not None:
        w_root = wiki_root.resolve()
    elif project_root is not None:
        w_root = (project_root / ".brain-79").resolve()
    else:
        w_root = get_wiki_root().resolve()
    p_root = (project_root or (w_root.parent if w_root.parent.exists() else get_project_root())).resolve()

    fixed: list[str] = []

    if fix:
        if not force and is_git_workspace(p_root):
            try:
                from brain79.core.git_ops import git_status_porcelain

                proc = git_status_porcelain(
                    p_root,
                    paths=[
                        "AGENTS.md",
                        "CLAUDE.md",
                        ".cursor/rules/brain79.mdc",
                        ".github/copilot-instructions.md",
                        ".brain-79",
                        ".mcp.json",
                        ".agents/mcp_config.json",
                        ".agents/plugins/brain79",
                        ".cursor/mcp.json",
                        ".claude/settings.json",
                        ".cursor/hooks.json",
                    ],
                    check_repo=False,
                )
                if proc.stdout.strip():
                    dirty_check = DoctorCheck(
                        category="dirty_working_tree",
                        status="error",
                        message="Uncommitted changes detected in project protocol files.",
                        actionable="Commit or stash changes before running --fix, or use --force.",
                    )
                    return DoctorReport(
                        status="error",
                        exit_code=1,
                        checks=[dirty_check],
                        fixed=[],
                    )
            except Exception:
                pass

        # Execute repairs
        try:
            up_res = update_project(p_root, include_desktop=include_desktop)
            if up_res.get("manifest_updated"):
                fixed.append("Synchronized AGENTS.md protocol block")
            if up_res.get("schema_updated"):
                fixed.append("Synchronized SCHEMA.md to schema_version 2")
            if up_res.get("gitignore_updated"):
                fixed.append("Synchronized .brain-79/.gitignore derived-state exclusions")
            if up_res.get("mcp_configs"):
                fixed.append(f"Configured MCP harnesses: {', '.join(up_res['mcp_configs'])}")
            if up_res.get("instruction_harnesses"):
                fixed.append(f"Synchronized native instruction harnesses: {', '.join(up_res['instruction_harnesses'])}")
            if up_res.get("lifecycle_hooks"):
                fixed.append(f"Synchronized lifecycle hooks: {', '.join(up_res['lifecycle_hooks'])}")
            if up_res.get("git_hook") and "updated" in str(up_res["git_hook"]):
                fixed.append("Installed/updated git pre-commit hook")
            if up_res.get("merge_driver_updated"):
                fixed.append("Configured Git merge drivers (INDEX.md & drift.lock) in .gitattributes & .git/config")
            mig_rep = up_res.get("migration_report")
            if mig_rep and "Changes (0)" not in str(mig_rep):
                fixed.append("Reconditioned legacy wiki articles via migrate_wiki")
        except Exception as exc:
            err_check = DoctorCheck(
                category="repair_failure",
                status="error",
                message=f"Failed to execute automatic repair: {exc}",
                actionable="Review project permissions or run repair commands manually.",
            )
            return DoctorReport(
                status="error",
                exit_code=1,
                checks=[err_check],
                fixed=fixed,
            )

    checks: list[DoctorCheck] = []

    from brain79.core.ast_guards import POLYGLOT_LANGUAGES, get_ast_guard_capabilities

    ast_caps = get_ast_guard_capabilities()
    ast_summary = _format_ast_guard_summary(ast_caps, POLYGLOT_LANGUAGES)

    # 1. binary_and_environment
    binary_path = shutil.which("brain79")
    py_ver = sys.version_info
    if py_ver < (3, 11):
        checks.append(
            DoctorCheck(
                category="binary_and_environment",
                status="error",
                message=f"Python runtime {py_ver[0]}.{py_ver[1]} is below minimum requirement 3.11. {ast_summary}",
                actionable="Upgrade Python to version 3.11 or higher.",
            )
        )
    elif not binary_path:
        checks.append(
            DoctorCheck(
                category="binary_and_environment",
                status="warning",
                message=f"Executable 'brain79' not found in system PATH. {ast_summary}",
                actionable="Run 'uv tool install git+https://github.com/xilax79/brain-79.git' or 'uv tool ensurepath'.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                category="binary_and_environment",
                status="ok",
                message=f"Binary located at {binary_path} (Python {py_ver[0]}.{py_ver[1]}.{py_ver[2]}). {ast_summary}",
            )
        )

    broken_grammars = ast_caps.get("broken_grammars") or {}
    if broken_grammars:
        broken_details = "; ".join(f"{lang} ({err})" for lang, err in sorted(broken_grammars.items()))
        checks.append(
            DoctorCheck(
                category="ast_guards",
                status="warning",
                message=f"Broken AST grammar package(s) detected: {broken_details}.",
                actionable='Reinstall polyglot grammars with: uv tool install --reinstall "brain79[polyglot]"',
            )
        )

    # 2. protocol_sync
    agents_file = p_root / "AGENTS.md"
    schema_file = w_root / "SCHEMA.md"
    protocol_status: Literal["ok", "warning", "error"] = "ok"
    protocol_msg = []
    protocol_act = None

    if not agents_file.is_file():
        protocol_status = "warning"
        protocol_msg.append("AGENTS.md is missing")
        protocol_act = "Run 'brain79 update-project' to generate AGENTS.md."
    else:
        try:
            a_content = agents_file.read_text(encoding="utf-8")
            starts = list(AGENTS_START_REGEX.finditer(a_content))
            ends = list(AGENTS_END_REGEX.finditer(a_content))
            if (
                len(starts) > 1
                or len(ends) > 1
                or len(starts) != len(ends)
                or (starts and ends and starts[0].start() > ends[0].start())
            ):
                protocol_status = "error"
                protocol_msg.append("AGENTS.md contains corrupted delimiters")
                protocol_act = "Restore delimiters or run 'brain79 update-project --force'."
            elif not starts or not ends:
                protocol_status = "warning"
                protocol_msg.append("AGENTS.md lacks delimited protocol markers")
                protocol_act = "Run 'brain79 update-project' to wrap instructions in delimited markers."
            else:
                v_block = starts[0].group(1)
                if not v_block or v_block != __version__:
                    protocol_status = "warning"
                    protocol_msg.append(f"AGENTS.md protocol (v{v_block or 'unknown'}) lags behind v{__version__}")
                    protocol_act = "Run 'brain79 update-project' to sync AGENTS.md."
        except Exception as e:
            protocol_status = "error"
            protocol_msg.append(f"Could not read AGENTS.md: {e}")

    if not schema_file.is_file():
        if protocol_status != "error":
            protocol_status = "warning"
        protocol_msg.append("SCHEMA.md is missing")
        protocol_act = "Run 'brain79 update-project' to sync SCHEMA.md."
    else:
        try:
            s_meta, _ = parse_frontmatter(schema_file.read_text(encoding="utf-8"))
            s_ver = int(s_meta.get("schema_version", 1))
            if s_ver < 2:
                if protocol_status != "error":
                    protocol_status = "warning"
                protocol_msg.append(f"SCHEMA.md is at schema_version {s_ver} (latest: 2)")
                protocol_act = "Run 'brain79 update-project' to upgrade SCHEMA.md."
        except Exception as e:
            protocol_status = "error"
            protocol_msg.append(f"Could not parse SCHEMA.md: {e}")

    # Also diagnose active native instruction harnesses (CLAUDE.md, .cursor/rules/brain79.mdc, .github/copilot-instructions.md)
    from brain79.core.harnesses import diagnose_all_harnesses

    all_harness_diags = diagnose_all_harnesses(p_root)
    for h_name in ("claude_code", "cursor_rules", "copilot"):
        for h_issue in all_harness_diags.get(h_name, []):
            if "corrupted_harness_delimiters" in h_issue:
                protocol_status = "error"
                protocol_act = "Restore delimiters or repair the corrupted harness file."
            elif protocol_status != "error":
                protocol_status = "warning"
                if not protocol_act:
                    protocol_act = "Run 'brain79 update-project' or 'brain79 doctor --fix' to sync native harness blocks."
            protocol_msg.append(h_issue.rstrip("."))

    # Check active enforcement tier and any schema warnings (R-4.1 / R-4.3)
    active_enforcement = "strict"
    try:
        schema_for_proto = load_active_schema(w_root)
        active_enforcement = schema_for_proto.enforcement
        for sw in schema_for_proto.schema_warnings:
            if protocol_status != "error":
                protocol_status = "warning"
            protocol_msg.append(sw.rstrip("."))
            if not protocol_act:
                protocol_act = "Set 'enforcement' in .brain-79/SCHEMA.md to 'strict', 'balanced', or 'advisory'."
    except Exception:
        pass

    if not protocol_msg:
        checks.append(
            DoctorCheck(
                category="protocol_sync",
                status="ok",
                message=f"AGENTS.md and SCHEMA.md synchronized with brain79 v{__version__} (enforcement: {active_enforcement}).",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                category="protocol_sync",
                status=protocol_status,
                message="; ".join(protocol_msg) + f" (enforcement: {active_enforcement}).",
                actionable=protocol_act,
            )
        )

    # 3. wiki_structure
    try:
        active_s = load_active_schema(w_root)
        index_file = w_root / "INDEX.md"
        if not index_file.is_file():
            checks.append(
                DoctorCheck(
                    category="wiki_structure",
                    status="error",
                    message="INDEX.md routing table is missing.",
                    actionable="Run 'brain79 init' or 'brain79 update-project' to initialize wiki index.",
                )
            )
        else:
            missing_dirs = []
            for loc in active_s.location_to_type.keys():
                if loc not in ("INDEX.md", "SCHEMA.md") and not (w_root / loc).is_dir():
                    missing_dirs.append(loc)

            # Check unmigrated articles
            unmigrated = []
            for f in w_root.rglob("*.md"):
                rel = f.relative_to(w_root).as_posix()
                if rel in ("INDEX.md", "SCHEMA.md") or rel.startswith(("_raw/", ".locks/")):
                    continue
                try:
                    f_meta, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
                    if not f_meta.get("type"):
                        unmigrated.append(rel)
                except Exception:
                    unmigrated.append(rel)

            if missing_dirs or unmigrated:
                issues = []
                if missing_dirs:
                    issues.append(f"missing directories ({', '.join(missing_dirs)})")
                if unmigrated:
                    issues.append(f"{len(unmigrated)} unmigrated articles")
                checks.append(
                    DoctorCheck(
                        category="wiki_structure",
                        status="warning",
                        message="; ".join(issues) + ".",
                        actionable="Run 'brain79 migrate --apply' to repair wiki structure.",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        category="wiki_structure",
                        status="ok",
                        message=f"Clean directory layout and schema adherence under '{active_s.profile}' profile.",
                    )
                )
    except Exception as e:
        checks.append(
            DoctorCheck(
                category="wiki_structure",
                status="error",
                message=f"Failed to inspect wiki structure: {e}",
                actionable="Verify .brain-79/ permissions and directory layout.",
            )
        )

    # 4. mcp_harnesses
    tier1_targets = [
        p_root / ".mcp.json",
        p_root / ".agents" / "mcp_config.json",
        p_root / ".cursor" / "mcp.json",
    ]
    harness_issues = []
    harness_has_error = False

    for target in tier1_targets:
        rel_target = target.relative_to(p_root).as_posix()
        if not target.is_file():
            harness_issues.append(f"missing {rel_target}")
        else:
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
                srv = data.get("mcpServers", {}).get("brain79", {})
                cmd = str(srv.get("command", ""))
                if cmd != "brain79":
                    harness_issues.append(f"{rel_target} uses non-portable command '{cmd}'")
            except Exception:
                harness_has_error = True
                harness_issues.append(f"{rel_target} contains corrupt JSON")

    # Antigravity plugin checks (.agents/plugins/brain79/)
    agy_plugin_dir = p_root / ".agents" / "plugins" / "brain79"
    agy_plugin_json = agy_plugin_dir / "plugin.json"
    agy_mcp_json = agy_plugin_dir / "mcp_config.json"
    agy_skill_md = agy_plugin_dir / "skills" / "brain79-wiki" / "SKILL.md"

    missing_agy_plugin = False
    if not agy_plugin_json.is_file():
        missing_agy_plugin = True
        harness_issues.append("missing .agents/plugins/brain79/plugin.json")
    else:
        try:
            p_data = json.loads(agy_plugin_json.read_text(encoding="utf-8"))
            if not isinstance(p_data, dict) or not p_data.get("name"):
                harness_issues.append(".agents/plugins/brain79/plugin.json missing valid name")
        except Exception:
            harness_has_error = True
            harness_issues.append(".agents/plugins/brain79/plugin.json contains corrupt JSON")

    if not agy_mcp_json.is_file():
        missing_agy_plugin = True
        harness_issues.append("missing .agents/plugins/brain79/mcp_config.json")
    else:
        try:
            m_data = json.loads(agy_mcp_json.read_text(encoding="utf-8"))
            srv = m_data.get("mcpServers", {}).get("brain79", {})
            cmd = str(srv.get("command", ""))
            args = srv.get("args", [])
            if cmd != "brain79":
                harness_issues.append(f".agents/plugins/brain79/mcp_config.json uses non-portable command '{cmd}'")
            if args != ["--project-root", "."]:
                harness_issues.append(f".agents/plugins/brain79/mcp_config.json uses non-portable arguments '{args}'")
        except Exception:
            harness_has_error = True
            harness_issues.append(".agents/plugins/brain79/mcp_config.json contains corrupt JSON")

    if not agy_skill_md.is_file() or agy_skill_md.stat().st_size == 0:
        missing_agy_plugin = True
        harness_issues.append("missing or empty .agents/plugins/brain79/skills/brain79-wiki/SKILL.md")

    legacy_agents_present = (p_root / ".agents" / "mcp_config.json").is_file()

    if harness_has_error:
        checks.append(
            DoctorCheck(
                category="mcp_harnesses",
                status="error",
                message="; ".join(harness_issues) + ".",
                actionable="Run 'brain79 update-project' to rebuild corrupted MCP configuration files.",
            )
        )
    elif harness_issues:
        action_msg = (
            "Run 'brain79 update-project' or 'brain79 doctor --fix' to register the Antigravity (agy) plugin at .agents/plugins/brain79/."
            if (missing_agy_plugin and legacy_agents_present)
            else "Run 'brain79 update-project' to register portable MCP harnesses."
        )
        checks.append(
            DoctorCheck(
                category="mcp_harnesses",
                status="warning",
                message="; ".join(harness_issues) + ".",
                actionable=action_msg,
            )
        )
    else:
        checks.append(
            DoctorCheck(
                category="mcp_harnesses",
                status="ok",
                message="Universal Tier 1 MCP harnesses configured with portable 'brain79' command.",
            )
        )

    # 5. locks_and_filesystem
    try:
        lock = acquire_wiki_lock(w_root, "doctor_probe", timeout=0.5)
        with lock:
            pass
        inline_locks = list(w_root.rglob("*.lock"))
        drift_lock_file = (w_root / "drift.lock").resolve()
        legacy_locks = [
            f.as_posix()
            for f in inline_locks
            if ".locks" not in f.parts and f.resolve() != drift_lock_file
        ]
        if legacy_locks:
            checks.append(
                DoctorCheck(
                    category="locks_and_filesystem",
                    status="warning",
                    message=f"Detected {len(legacy_locks)} legacy inline lock files.",
                    actionable="Run 'brain79 update-project' to purge legacy inline locks.",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    category="locks_and_filesystem",
                    status="ok",
                    message="Isolated .locks/ directory operational; 0 legacy inline locks.",
                )
            )
    except Exception as e:
        checks.append(
            DoctorCheck(
                category="locks_and_filesystem",
                status="error",
                message=f"Filesystem lock error: {e}",
                actionable="Check permissions in .brain-79/.locks/.",
            )
        )

    # 6. git_hooks
    schema = load_active_schema(w_root)
    git_dir = p_root / ".git"
    if schema.profile == "general" and not git_dir.exists():
        checks.append(
            DoctorCheck(
                category="git_hooks",
                status="ok",
                message="General profile workspace outside Git; git hooks omitted cleanly.",
            )
        )
    elif not git_dir.exists():
        checks.append(
            DoctorCheck(
                category="git_hooks",
                status="info",
                message="No Git repository detected at project root.",
                actionable="Initialize git via 'git init' to enable commit hooks and drift detection.",
            )
        )
    else:
        hook_path = git_dir / "hooks" / "pre-commit"
        if not hook_path.is_file():
            checks.append(
                DoctorCheck(
                    category="git_hooks",
                    status="warning",
                    message="Pre-commit hook is not installed.",
                    actionable="Run 'brain79 update-project' to install .git/hooks/pre-commit.",
                )
            )
        else:
            content = hook_path.read_text(encoding="utf-8")
            is_executable = os.access(hook_path, os.X_OK)
            if "# brain-79 pre-commit hook" in content and is_executable:
                checks.append(
                    DoctorCheck(
                        category="git_hooks",
                        status="ok",
                        message="Executable .git/hooks/pre-commit hook installed.",
                    )
                )
            elif not is_executable:
                checks.append(
                    DoctorCheck(
                        category="git_hooks",
                        status="warning",
                        message="Pre-commit hook file exists but lacks executable permission.",
                        actionable="Run 'chmod +x .git/hooks/pre-commit'.",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        category="git_hooks",
                        status="ok",
                        message="Third-party git hook manager detected; hook preserved.",
                    )
                )

    # 7. handoff_hygiene
    handoffs_dir = w_root / "handoffs"
    if not handoffs_dir.exists():
        checks.append(
            DoctorCheck(
                category="handoff_hygiene",
                status="ok",
                message="Handoff directory clean.",
            )
        )
    else:
        all_handoffs = sorted(handoffs_dir.glob("*.md"))
        count = len(all_handoffs)
        if count == 0:
            checks.append(
                DoctorCheck(
                    category="handoff_hygiene",
                    status="ok",
                    message="No active handoffs; wiki is clean.",
                )
            )
        else:
            latest = all_handoffs[-1]
            freshness = compute_handoff_freshness(latest, wiki_root=w_root)
            if count > 10:
                checks.append(
                    DoctorCheck(
                        category="handoff_hygiene",
                        status="warning",
                        message=f"Accumulated {count} handoffs (latest is {freshness.state}).",
                        actionable="Run 'brain79 handoff-purge --apply' to purge legacy handoffs.",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        category="handoff_hygiene",
                        status="ok",
                        message=f"Latest handoff '{latest.name}' is {freshness.state} ({count} total handoffs).",
                    )
                )

    # 8. derived_state_tracking (R-1.1, R-4.3)
    derived_cache_names = (
        ".navigation_registry.json",
        ".drift_manifest.json",
        ".bootstrap_state.json",
    )
    try:
        wiki_rel = w_root.relative_to(p_root).as_posix()
    except ValueError:
        wiki_rel = ".brain-79"
    drift_lock_rel = f"{wiki_rel}/drift.lock"

    if is_git_workspace(p_root):
        try:
            from brain79.core.git_ops import git_check_ignore, git_ls_files

            tracked_files = set(git_ls_files(p_root, include_others=False, timeout=5.0))
            tracked_derived = [
                f"{wiki_rel}/{name}"
                for name in derived_cache_names
                if f"{wiki_rel}/{name}" in tracked_files
            ]
            drift_lock_ignored = git_check_ignore(p_root, drift_lock_rel, timeout=5.0)

            if tracked_derived:
                rm_cmd = "git rm --cached " + " ".join(tracked_derived)
                checks.append(
                    DoctorCheck(
                        category="derived_state_tracking",
                        status="warning",
                        message=f"Derived JSON cache(s) tracked in Git: {', '.join(tracked_derived)}.",
                        actionable=f"Untrack derived caches with '{rm_cmd}' and run 'brain79 update-project' to sync .brain-79/.gitignore.",
                    )
                )
            elif drift_lock_ignored:
                checks.append(
                    DoctorCheck(
                        category="derived_state_tracking",
                        status="warning",
                        message=f"Tracked drift lockfile '{drift_lock_rel}' is currently git-ignored.",
                        actionable="Run 'brain79 update-project' or 'brain79 doctor --fix' to place '!drift.lock' after '*.lock' in .brain-79/.gitignore.",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        category="derived_state_tracking",
                        status="ok",
                        message="No derived JSON caches tracked in Git; drift.lock is un-ignored.",
                    )
                )
        except Exception as e:
            checks.append(
                DoctorCheck(
                    category="derived_state_tracking",
                    status="info",
                    message=f"Could not inspect Git tracked derived caches: {e}",
                )
            )
    else:
        gi_file = w_root / ".gitignore"
        if gi_file.is_file():
            gi_lines = [ln.strip() for ln in gi_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
            last_star_lock = max((i for i, ln in enumerate(gi_lines) if ln == "*.lock"), default=-1)
            last_neg_drift = max((i for i, ln in enumerate(gi_lines) if ln == "!drift.lock"), default=-1)
            if last_star_lock != -1 and last_neg_drift <= last_star_lock:
                checks.append(
                    DoctorCheck(
                        category="derived_state_tracking",
                        status="warning",
                        message=".brain-79/.gitignore is missing '!drift.lock' after '*.lock'.",
                        actionable="Run 'brain79 update-project' or 'brain79 doctor --fix' to sync .brain-79/.gitignore.",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        category="derived_state_tracking",
                        status="ok",
                        message="Workspace outside Git; .brain-79/.gitignore allows drift.lock.",
                    )
                )
        else:
            checks.append(
                DoctorCheck(
                    category="derived_state_tracking",
                    status="ok",
                    message="Workspace outside Git; derived state tracking check skipped.",
                )
            )

    # 9. git_merge_driver (R-2.3, R-4.3)
    if is_git_workspace(p_root):
        from brain79.core.git_ops import git_config_get_local
        from brain79.core.init_project import (
            DRIFT_LOCK_GITATTRIBUTES_LINE,
            GITATTRIBUTES_LINE,
        )

        ga_file = w_root / ".gitattributes"
        ga_lines = (
            {ln.strip() for ln in ga_file.read_text(encoding="utf-8").splitlines()}
            if ga_file.is_file()
            else set()
        )
        has_index_ga = GITATTRIBUTES_LINE in ga_lines
        has_drift_ga = DRIFT_LOCK_GITATTRIBUTES_LINE in ga_lines
        try:
            configured_index_driver = git_config_get_local(p_root, "merge.brain79-index.driver")
        except Exception:
            configured_index_driver = None
        try:
            configured_drift_driver = git_config_get_local(p_root, "merge.brain79-drift-lock.driver")
        except Exception:
            configured_drift_driver = None

        missing_parts: list[str] = []
        if not has_index_ga:
            missing_parts.append(".brain-79/.gitattributes INDEX.md entry missing")
        if not has_drift_ga:
            missing_parts.append(".brain-79/.gitattributes drift.lock entry missing")
        if not configured_index_driver:
            missing_parts.append("local git merge.brain79-index.driver not configured")
        if not configured_drift_driver:
            missing_parts.append("local git merge.brain79-drift-lock.driver not configured")

        if missing_parts:
            checks.append(
                DoctorCheck(
                    category="git_merge_driver",
                    status="warning",
                    message="; ".join(missing_parts) + ".",
                    actionable="Run 'brain79 update-project' or 'brain79 doctor --fix' to configure Git merge drivers.",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    category="git_merge_driver",
                    status="ok",
                    message="Deterministic INDEX.md and drift.lock Git merge drivers configured.",
                )
            )
    else:
        checks.append(
            DoctorCheck(
                category="git_merge_driver",
                status="ok",
                message="Workspace outside Git; Git merge driver check skipped.",
            )
        )

    # Delegate harness diagnostics through core/harnesses registry (R-4.2)
    from brain79.core.harnesses import diagnose_all_harnesses

    _builtin_harnesses = {"agents_md", "mcp_json", "antigravity", "cursor"}
    for h_name, h_issues in diagnose_all_harnesses(p_root).items():
        if h_name not in _builtin_harnesses and h_issues:
            issue_status: Literal["warning", "error"] = (
                "error" if any("corrupt JSON" in issue for issue in h_issues) else "warning"
            )
            checks.append(
                DoctorCheck(
                    category=f"harness:{h_name}",
                    status=issue_status,
                    message="; ".join(h_issues),
                    actionable="Run 'brain79 update-project' or 'brain79 doctor --fix' to repair harness configuration.",
                )
            )

    # Compute overall status and exit code
    has_error = any(c.status == "error" for c in checks)
    has_warning = any(c.status == "warning" for c in checks)

    overall_status: Literal["ok", "warning", "error"] = "error" if has_error else ("warning" if has_warning else "ok")
    exit_code = 1 if has_error else (2 if has_warning else 0)

    return DoctorReport(
        status=overall_status,
        exit_code=exit_code,
        checks=checks,
        fixed=fixed,
    )
