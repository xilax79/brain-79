from datetime import UTC, datetime
from pathlib import Path
import time
from typing import Any, Final

from brain79.config import get_wiki_root
from brain79.core import wiki as wiki_ops
from brain79.core.frontmatter import (
    load_active_schema,
    parse_frontmatter,
)
from brain79.core.handoff_freshness import (
    HandoffFreshness,
    compute_code_digest,
    compute_handoff_freshness,
    compute_wiki_digest,
    get_git_branch,
    get_git_head,
)

HANDOFF_ESCALATION_AGE_DAYS: int = 14
HANDOFF_ESCALATION_COMMITS: int = 20

SessionType = str
VALID_SESSION_TYPES = {
    "feature",
    "bugfix",
    "research",
    "brainstorming",
    "architecture",
    "refactor",
    "maintenance",
    "work",
    "general",
    "writing",
    "analysis",
}


def get_valid_session_types(wiki_root: Path | None = None) -> set[str]:
    """Retrieve allowed session types for handoffs based on active schema."""
    try:
        active = load_active_schema(wiki_root or get_wiki_root())
        allowed = active.types.get("handoff", {}).get("enum", {}).get("session_type")
        if allowed:
            return set(allowed)
    except Exception:
        pass
    return VALID_SESSION_TYPES


class HandoffNotFoundError(FileNotFoundError):
    """Base exception for handoff file or directory resolution errors."""


class HandoffsDirNotFoundError(HandoffNotFoundError):
    """Raised when the handoffs/ directory does not exist."""

    def __str__(self) -> str:
        return "Handoffs directory not found."


class NoHandoffsExistError(HandoffNotFoundError):
    """Raised when no handoff files exist in handoffs/."""

    def __str__(self) -> str:
        return "No handoffs saved yet."


def _normalize_list(items: list[str]) -> list[str]:
    """Clean magic strings like 'None' or empty lists hallucinated by the LLM."""
    if not items:
        return []
    cleaned = [i.strip() for i in items if i.strip() and i.strip().lower() != "none"]
    return cleaned


_NOOP_EXACT_VALUES: Final[frozenset[str]] = frozenset({
    "ninguna",
    "ninguno",
    "nada",
    "none",
    "n/a",
    "na",
    "null",
    "sin pendientes",
    "sin tareas",
    "sin tareas pendientes",
    "no pending tasks",
    "no pending work",
    "no open questions",
    "sin preguntas abiertas",
})

_NOOP_SUBSTRING_PATTERNS: Final[tuple[str, ...]] = (
    "atender la próxima tarea",
    "atender la proxima tarea",
    "atender la siguiente solicitud",
    "continuar según la siguiente",
    "continuar segun la siguiente",
    "esperar la siguiente instrucción",
    "esperar la siguiente instruccion",
    "await next user",
    "awaiting next user",
    "wait for next user",
    "wait for user",
    "respond to the next user",
)


def _is_noop_placeholder(text: str) -> bool:
    """Return True if the list item is an empty placeholder or generic 'wait for user' filler."""
    cleaned = text.strip().rstrip(".!").strip().lower()
    if not cleaned or cleaned in _NOOP_EXACT_VALUES:
        return True
    return any(pat in cleaned for pat in _NOOP_SUBSTRING_PATTERNS)


def _has_recent_wiki_writes(wiki_root: Path, window_seconds: float = 1800.0) -> bool:
    """Return True if at least one permanent content article was modified within the current session.

    Session boundary:
    If a previous handoff exists in handoffs/, only articles modified strictly after the latest handoff's
    mtime (and within window_seconds) count as current-session modifications.
    If no previous handoff exists, articles modified within window_seconds count.

    Excludes INDEX.md, SCHEMA.md, _raw/, handoffs/, and .locks/.
    """
    if not wiki_root.is_dir():
        return False

    handoffs_dir = wiki_root / "handoffs"
    cutoff_mtime: float = 0.0
    if handoffs_dir.is_dir():
        handoff_files = sorted(handoffs_dir.glob("handoff-*.md"))
        if handoff_files:
            try:
                cutoff_mtime = handoff_files[-1].stat().st_mtime
            except OSError:
                cutoff_mtime = 0.0

    now = time.time()
    for p in wiki_root.rglob("*.md"):
        parts = p.parts
        if "_raw" in parts or "handoffs" in parts or ".locks" in parts:
            continue
        rel = p.relative_to(wiki_root).as_posix()
        if rel in ("INDEX.md", "SCHEMA.md"):
            continue
        try:
            mtime = p.stat().st_mtime
            if mtime > cutoff_mtime and (now - mtime <= window_seconds):
                return True
        except OSError:
            continue
    return False


def _resolve_handoff_path(ref: str, wiki_root: Path | None = None) -> Path:
    """Resolve a handoff reference ('latest', 'none', '', timestamp, or filename) to a Path."""
    w_root = (wiki_root or get_wiki_root()).resolve()
    handoffs_dir = w_root / "handoffs"

    cleaned_ref = ref.strip().lower()
    if cleaned_ref in ("", "none", "latest"):
        if not handoffs_dir.exists():
            raise HandoffsDirNotFoundError()
        files = sorted(handoffs_dir.glob("handoff-*.md"))
        if not files:
            raise NoHandoffsExistError()

        # Branch-aware resolution (R4)
        cur_branch = get_git_branch(w_root.parent)
        if cur_branch and cur_branch not in ("none", "unknown", "detached"):
            for fpath in reversed(files):
                try:
                    txt = fpath.read_text(encoding="utf-8")
                    fm, _ = parse_frontmatter(txt)
                    if str(fm.get("git_branch", "")).strip() == cur_branch:
                        return fpath
                except Exception:
                    continue
        return files[-1]

    # Specific ref provided
    raw_ref = ref.strip()
    if raw_ref.startswith("handoffs/"):
        raw_ref = raw_ref[len("handoffs/"):]

    if raw_ref.endswith(".md"):
        candidate = raw_ref
    elif raw_ref.startswith("handoff-"):
        candidate = f"{raw_ref}.md"
    else:
        candidate = f"handoff-{raw_ref}.md"

    try:
        target = wiki_ops.resolve_wiki_path(f"handoffs/{candidate}", wiki_root=w_root)
        if target.exists():
            return target
    except ValueError:
        pass

    # Prefix search fallback (e.g., timestamp without ms suffix or YYYY-MM)
    prefix_stem = raw_ref.removesuffix(".md")
    if not prefix_stem.startswith("handoff-"):
        prefix_stem = f"handoff-{prefix_stem}"

    if handoffs_dir.exists():
        matches = sorted(handoffs_dir.glob(f"{prefix_stem}*.md"))
        if matches:
            return matches[-1]

    raise HandoffNotFoundError(f"The handoff reference '{ref}' does not exist.")


def validate_handoff_params(
    session_type: str,
    previous_handoff_ref: str = "latest",
    summary: str = "",
    completed_work: list[str] | None = None,
    pending_work: list[str] | None = None,
    knowledge_pending_promotion: list[str] | None = None,
    resources: list[str] | None = None,
    gotchas: list[str] | None = None,
    boot_instruction: str = "",
    wiki_deviation_justification: str = "",
    decisions: list[str] | None = None,
    next_steps: list[str] | None = None,
    open_questions: list[str] | None = None,
    boot_instructions: str = "",
    decisions_made: list[str] | None = None,
    session_summary: str = "",
    pending_tasks: list[str] | None = None,
    open_issues: list[str] | None = None,
    resolved_issues: list[str] | None = None,
    files_modified: list[str] | None = None,
    open_loops: list[str] | None = None,
    action_items: list[str] | None = None,
    todo: list[str] | None = None,
    risks_and_blockers: list[str] | None = None,
    blockers: list[str] | None = None,
    risks: list[str] | None = None,
    key_decisions: list[str] | None = None,
    findings: list[str] | None = None,
    _has_session_writes: bool = False,
    wiki_root: Path | None = None,
) -> dict[str, Any]:
    """Validate and normalize handoff parameters without modifying disk.

    Returns:
        Normalized dict of parameters ready for write_handoff.
    Raises:
        ValueError or FileNotFoundError if any parameter violates validation rules.
    """
    session_type = session_type.strip().lower()
    valid_types = get_valid_session_types(wiki_root=wiki_root)
    if session_type not in valid_types:
        raise ValueError(
            f"Invalid session_type '{session_type}'. Must be one of: {sorted(valid_types)}"
        )

    summary = (summary or session_summary or "").strip()
    if not summary:
        raise ValueError("summary cannot be empty.")

    raw_ref = (previous_handoff_ref or "").strip()
    if not raw_ref or raw_ref.lower() in ("none", "initial"):
        normalized_ref = "none"
    elif raw_ref.lower() == "latest":
        try:
            _resolve_handoff_path("latest", wiki_root=wiki_root)
            normalized_ref = "latest"
        except (HandoffNotFoundError, NoHandoffsExistError):
            normalized_ref = "none"
    else:
        try:
            _resolve_handoff_path(raw_ref, wiki_root=wiki_root)
            normalized_ref = raw_ref
        except (HandoffNotFoundError, NoHandoffsExistError):
            raise FileNotFoundError(
                f"The previous_handoff_ref '{raw_ref}' does not exist."
            )

    decisions_in = (
        list(decisions or [])
        + list(decisions_made or [])
        + list(key_decisions or [])
        + list(findings or [])
    )
    raw_completed = list(completed_work or []) + decisions_in + list(resolved_issues or [])
    norm_completed = [x for x in _normalize_list(raw_completed) if not _is_noop_placeholder(x)]

    raw_pending = (
        list(pending_work or [])
        + list(next_steps or [])
        + list(pending_tasks or [])
        + list(open_loops or [])
        + list(action_items or [])
        + list(todo or [])
    )
    norm_pending = [x for x in _normalize_list(raw_pending) if not _is_noop_placeholder(x)]

    raw_gotchas = (
        list(gotchas or [])
        + list(open_questions or [])
        + list(open_issues or [])
        + list(risks_and_blockers or [])
        + list(blockers or [])
        + list(risks or [])
    )
    norm_gotchas = [x for x in _normalize_list(raw_gotchas) if not _is_noop_placeholder(x)]

    norm_promotion = _normalize_list(knowledge_pending_promotion or [])
    norm_resources = _normalize_list(list(resources or []) + list(files_modified or []))

    boot_instruction = (boot_instruction or boot_instructions or "").strip()
    if not boot_instruction:
        raise ValueError("boot_instruction cannot be empty.")

    if not norm_pending and session_type in ("feature", "bugfix"):
        unlisted_work_patterns = (
            "continue implementing",
            "continuar implementando",
            "finish implementing",
            "terminar de implementar",
            "implementing the",
            "implementar el",
        )
        if any(pat in boot_instruction.lower() for pat in unlisted_work_patterns):
            raise ValueError(
                "No pending_work provided, but boot_instruction hallucinates next steps. You must explicitly indicate that there are no pending tasks."
            )

    w_root = (wiki_root or get_wiki_root()).resolve()
    knowledge_session_types = frozenset({"research", "brainstorming", "analysis", "writing"})
    if (w_root / "SCHEMA.md").exists() and session_type in knowledge_session_types:
        has_writes = _has_session_writes or _has_recent_wiki_writes(w_root)

        if not has_writes:
            try:
                schema = load_active_schema(w_root)
                valid_dirs = ", ".join(
                    f"`{d}/`"
                    for d in sorted(schema.location_to_type.keys())
                    if d != "handoffs" and not d.startswith("_raw") and not d.endswith(".md")
                )
            except Exception:
                valid_dirs = "`topics/`, `decisions/`, `features/`, `architecture/`"
            raise ValueError(
                f"Unpersisted '{session_type}' session blocked: no permanent wiki articles were created or updated "
                f"in this session. A '{session_type}' session MUST persist its findings, "
                f"analysis, or conclusions as a permanent wiki article BEFORE or DURING session closure (use "
                f"`brain79_session_commit(writes=[{{'path': '...', 'content': '...'}}], handoff={{...}})`). "
                f"You cannot bypass this with wiki_deviation_justification. Even if the research topic is external, "
                f"domain-general, or non-code, the wiki IS the knowledge base where the user expects this research to be saved. "
                f"Valid target directories: {valid_dirs}."
            )

    return {
        "session_type": session_type,
        "previous_handoff_ref": normalized_ref,
        "summary": summary,
        "completed_work": norm_completed,
        "pending_work": norm_pending,
        "knowledge_pending_promotion": norm_promotion,
        "resources": norm_resources,
        "gotchas": norm_gotchas,
        "boot_instruction": boot_instruction,
        "wiki_deviation_justification": wiki_deviation_justification,
    }


def write_handoff(
    session_type: str,
    previous_handoff_ref: str = "latest",
    summary: str = "",
    completed_work: list[str] | None = None,
    pending_work: list[str] | None = None,
    knowledge_pending_promotion: list[str] | None = None,
    resources: list[str] | None = None,
    gotchas: list[str] | None = None,
    boot_instruction: str = "",
    wiki_deviation_justification: str = "",
    decisions: list[str] | None = None,
    next_steps: list[str] | None = None,
    open_questions: list[str] | None = None,
    boot_instructions: str = "",
    decisions_made: list[str] | None = None,
    session_summary: str = "",
    pending_tasks: list[str] | None = None,
    open_issues: list[str] | None = None,
    resolved_issues: list[str] | None = None,
    files_modified: list[str] | None = None,
    open_loops: list[str] | None = None,
    action_items: list[str] | None = None,
    todo: list[str] | None = None,
    risks_and_blockers: list[str] | None = None,
    blockers: list[str] | None = None,
    risks: list[str] | None = None,
    key_decisions: list[str] | None = None,
    findings: list[str] | None = None,
    _has_session_writes: bool = False,
    wiki_root: Path | None = None,
) -> str:
    """Generate and save an immutable handoff file validating design rules."""
    params = validate_handoff_params(
        session_type=session_type,
        previous_handoff_ref=previous_handoff_ref,
        summary=summary,
        completed_work=completed_work,
        pending_work=pending_work,
        knowledge_pending_promotion=knowledge_pending_promotion,
        resources=resources,
        gotchas=gotchas,
        boot_instruction=boot_instruction,
        wiki_deviation_justification=wiki_deviation_justification,
        decisions=decisions,
        next_steps=next_steps,
        open_questions=open_questions,
        boot_instructions=boot_instructions,
        decisions_made=decisions_made,
        session_summary=session_summary,
        pending_tasks=pending_tasks,
        open_issues=open_issues,
        resolved_issues=resolved_issues,
        files_modified=files_modified,
        open_loops=open_loops,
        action_items=action_items,
        todo=todo,
        risks_and_blockers=risks_and_blockers,
        blockers=blockers,
        risks=risks,
        key_decisions=key_decisions,
        findings=findings,
        _has_session_writes=_has_session_writes,
        wiki_root=wiki_root,
    )

    session_type = params["session_type"]
    previous_handoff_ref = params["previous_handoff_ref"]
    summary = params["summary"]
    completed_work = params["completed_work"]
    pending_work = params["pending_work"]
    knowledge_pending_promotion = params["knowledge_pending_promotion"]
    resources = params["resources"]
    gotchas = params["gotchas"]
    boot_instruction = params["boot_instruction"]
    wiki_deviation_justification = params["wiki_deviation_justification"]

    w_root = (wiki_root or get_wiki_root()).resolve()
    project_root = w_root.parent

    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    git_branch = get_git_branch(project_root)
    git_head = get_git_head(project_root)
    wiki_digest = compute_wiki_digest(w_root)
    code_digest = compute_code_digest(project_root)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S-%f")[:-3]
    rel_path = f"handoffs/handoff-{timestamp}.md"

    today_iso = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        "---",
        "type: handoff",
        f"session_type: {session_type}",
        f"previous_ref: {previous_handoff_ref or 'none'}",
        f"created_at: {created_at}",
        f"last_updated: {today_iso}",
        f"git_branch: {git_branch}",
        f"git_head: {git_head}",
        f"wiki_digest: {wiki_digest}",
        f"code_digest: {code_digest}",
        "schema_version: 1",
        "---",
        "",
        f"# Handoff — {timestamp} (UTC)",
        f"**Session type**: {session_type}",
        f"**Previous ref**: {previous_handoff_ref or 'none'}\n",
    ]

    if (
        wiki_deviation_justification
        and wiki_deviation_justification.strip().lower() != "none"
    ):
        lines.append("## ⚠️ Wiki deviation (temporary)")
        lines.append(wiki_deviation_justification.strip())
        lines.append("")

    lines.append("## Immediate context")
    lines.append(f"{summary}\n")

    def _add_section(title: str, items: list[str]) -> None:
        if items:
            lines.append(f"## {title}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    _add_section("Completed work", completed_work)
    _add_section("Pending work", pending_work)
    _add_section(
        "Knowledge pending promotion", knowledge_pending_promotion
    )
    _add_section("Resources", resources)
    _add_section("Gotchas", gotchas)

    lines.append("## Boot instruction")
    lines.append(boot_instruction)

    content = "\n".join(lines)
    wiki_ops.write_article(rel_path, content, wiki_root=w_root)

    return rel_path



def _format_age(seconds: float) -> str:
    """Format age in seconds into a human-readable compact string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"


def read_handoff(
    ref: str = "latest",
    wiki_root: Path | None = None,
    for_orient: bool = False,
    freshness: HandoffFreshness | None = None,
) -> tuple[str, bool]:
    """Read a handoff document and apply authority decay banners.

    Args:
        ref: "latest", "none", or "" (default to latest), or a specific timestamp with or without
             milliseconds or file extension.
        wiki_root: Optional custom wiki root path.
        for_orient: If True, applies orient-specific projection (e.g. omits boot instruction
                    for foreign branch handoffs).
        freshness: Optional pre-computed HandoffFreshness object to avoid redundant calculations.

    Returns:
        tuple[str, bool]: (rendered_content, has_promotion_pending)
    """
    target_path = _resolve_handoff_path(ref, wiki_root=wiki_root)
    w_root = (wiki_root or get_wiki_root()).resolve()
    rel_path = target_path.relative_to(w_root).as_posix()
    content = wiki_ops.read_article(rel_path, wiki_root=w_root)

    if freshness is None:
        freshness = compute_handoff_freshness(target_path, wiki_root=w_root)
    age_str = _format_age(freshness.age_seconds)

    # Detect promotion pending (support both English and legacy Spanish)
    has_promotion_pending = (
        "## Knowledge pending promotion" in content
        or "## Conocimiento pendiente de promoción" in content
    )

    # Build Header and Banner based on Freshness State
    if freshness.state == "fresh":
        banner = (
            f"## ⏱️ Active handoff state\n\n"
            f"> Fresh: written {age_str} ago on '{freshness.handoff_branch}'; no wiki or code changes since.\n\n"
        )
        rendered_content = banner + content

    elif freshness.state in ("stale", "unverified"):
        reasons_str = ", ".join(freshness.reasons) if freshness.reasons else "workspace state changed"
        commits_str = f"{freshness.commits_since} commit(s)" if freshness.commits_since is not None else "unknown commits"
        code_str = "yes" if freshness.code_changed is True else ("no" if freshness.code_changed is False else "unknown")
        if not freshness.changed_wiki_articles:
            articles_str = "none"
        elif len(freshness.changed_wiki_articles) <= 10:
            articles_str = ", ".join(freshness.changed_wiki_articles)
        else:
            articles_str = f"{', '.join(freshness.changed_wiki_articles[:10])} (and {len(freshness.changed_wiki_articles) - 10} more)"

        banner = (
            f"## ⏱️ Last handoff (stale: verify before acting)\n\n"
            f"> ⚠️ **Stale handoff**: written {age_str} ago on '{freshness.handoff_branch}'.\n"
            f"> Reasons: {reasons_str}.\n"
            f"> Changes since handoff: {commits_str}, code changed: {code_str}, changed wiki articles: {articles_str}.\n\n"
        )

        adjusted = content
        adjusted = adjusted.replace("## Boot instruction\n", "## Boot instruction (historical: verify against current state)\n")
        adjusted = adjusted.replace("## Instrucción de arranque\n", "## Instrucción de arranque (historical: verify against current state)\n")
        rendered_content = banner + adjusted

    elif freshness.state == "foreign_branch":
        banner = (
            f"## ⏱️ Last handoff (from branch '{freshness.handoff_branch}', current branch '{freshness.current_branch}')\n\n"
            f"> ⚠️ **Foreign branch handoff**: recorded on branch '{freshness.handoff_branch}' while active branch is '{freshness.current_branch}'.\n\n"
        )
        if for_orient:
            lines = content.splitlines()
            extracted_lines: list[str] = []
            capturing_context = False
            for line in lines:
                if line.startswith("## Immediate context") or line.startswith("## Contexto inmediato"):
                    capturing_context = True
                    extracted_lines.append(line)
                elif line.startswith("## ") and capturing_context:
                    break
                elif capturing_context:
                    extracted_lines.append(line)
                elif line.startswith("# Handoff —") or line.startswith("**Session type") or line.startswith("**Tipo de sesión") or line.startswith("**Previous ref") or line.startswith("**Referencia anterior"):
                    extracted_lines.append(line)

            extracted_str = "\n".join(extracted_lines).strip()
            hint = "\n\n> ℹ️ Call `brain79_handoff_read(...)` to inspect the complete cross-branch handoff."
            rendered_content = banner + extracted_str + hint
        else:
            rendered_content = banner + content

    else:
        rendered_content = f"=== Handoff: {rel_path} ===\n\n" + content

    return rendered_content, has_promotion_pending


def purge_handoffs(wiki_root: Path, apply: bool = False) -> str:
    """Empty the handoffs directory completely and unregister them from the navigation registry.

    Deletes ALL files inside `.brain-79/handoffs/` (handoffs, stale locks, .gitkeep,
    anything else). Leaves the directory itself in place but empty.

    Args:
        wiki_root: Path to .brain-79/.
        apply: If False (default), only preview what would be deleted.
               If True, actually delete the files and unregister navigation.

    Returns:
        Markdown-formatted report.

    Safety:
        - Deletes EVERYTHING inside `handoffs/` (leaves the directory itself)
        - Does NOT touch `_raw/`, other wiki articles, or any other directory
        - Does NOT scan articles for markdown links referencing handoffs
          (the linter detects those; the agent fixes them)
    """
    handoffs_dir = wiki_root / "handoffs"

    if not handoffs_dir.exists():
        return f"# Handoff Purge ({'APPLIED' if apply else 'DRY RUN'})\n\nNo handoffs directory found. Nothing to do."

    all_files = sorted(
        f for f in handoffs_dir.iterdir()
        if f.is_file() and f.name != ".gitkeep"
    )

    if not all_files:
        return f"# Handoff Purge ({'APPLIED' if apply else 'DRY RUN'})\n\nHandoffs directory is already empty."

    total_bytes = sum(f.stat().st_size for f in all_files)
    file_count = len(all_files)

    if not apply:
        lines = [
            "# Handoff Purge (DRY RUN)",
            "",
            f"Would delete {file_count} files ({total_bytes} bytes) and leave handoffs/ empty:",
        ]
        for f in all_files:
            rel = f.relative_to(wiki_root)
            lines.append(f"  - {rel.as_posix()}")
        lines.append("")
        lines.append("Would unregister handoff entries from `.navigation_registry.json`.")
        lines.append("")
        lines.append("Run with --apply (CLI) or apply=True (MCP) to actually delete.")
        return "\n".join(lines)

    # Apply: delete all files in handoffs/
    deleted: list[Path] = []
    deleted_bytes = 0
    for f in all_files:
        try:
            file_size = f.stat().st_size
            f.unlink()
            deleted.append(f)
            deleted_bytes += file_size
        except OSError:
            pass  # skip files we can't delete (permission, locked, etc.)

    # Clean up corresponding centralized lock files in .locks/
    locks_dir = wiki_root / ".locks"
    if locks_dir.exists():
        for lock_file in locks_dir.glob("handoffs__*.lock"):
            try:
                lock_file.unlink()
            except OSError:
                pass

    # Unregister from navigation registry
    unregistered_count = 0
    try:
        from brain79.core.navigation import (
            _get_lock,
            _save_registry_unlocked,
            load_registry,
        )

        lock = _get_lock(wiki_root)
        with lock:
            registry = load_registry(wiki_root)
            handoff_paths = {f"handoffs/{f.name}" for f in deleted}
            articles = registry.get("articles", [])
            before = len(articles)
            registry["articles"] = [
                a for a in articles if a.get("path") not in handoff_paths
            ]
            after = len(registry["articles"])
            unregistered_count = before - after
            if unregistered_count > 0:
                _save_registry_unlocked(wiki_root, registry)
    except Exception:
        pass  # best-effort; if registry fails, files are still deleted

    lines = [
        "# Handoff Purge (APPLIED)",
        "",
        f"Deleted {len(deleted)} files ({deleted_bytes} bytes). Handoffs directory is now empty.",
        f"Unregistered {unregistered_count} navigation entries.",
    ]
    return "\n".join(lines)


