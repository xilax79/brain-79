from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from brain79.config import get_wiki_root
from brain79.core import wiki as wiki_ops

SessionType = Literal["feature", "bugfix", "research", "brainstorming"]
VALID_SESSION_TYPES = {"feature", "bugfix", "research", "brainstorming"}


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


def _resolve_handoff_path(ref: str) -> Path:
    """Resolve a handoff reference ('latest', 'none', '', timestamp, or filename) to a Path."""
    wiki_root = get_wiki_root()
    handoffs_dir = wiki_root / "handoffs"

    cleaned_ref = ref.strip().lower()
    if cleaned_ref in ("", "none", "latest"):
        if not handoffs_dir.exists():
            raise HandoffsDirNotFoundError()
        files = sorted(handoffs_dir.glob("handoff-*.md"))
        if not files:
            raise NoHandoffsExistError()
        return files[-1]

    # Specific ref provided
    raw_ref = ref.strip()
    if raw_ref.endswith(".md"):
        candidate = raw_ref
    elif raw_ref.startswith("handoff-"):
        candidate = f"{raw_ref}.md"
    else:
        candidate = f"handoff-{raw_ref}.md"

    try:
        target = wiki_ops.resolve_wiki_path(f"handoffs/{candidate}")
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


def write_handoff(
    session_type: str,
    previous_handoff_ref: str,
    summary: str,
    completed_work: list[str],
    pending_work: list[str],
    knowledge_pending_promotion: list[str],
    resources: list[str],
    gotchas: list[str],
    boot_instruction: str,
    wiki_deviation_justification: str = "",
) -> str:
    """Generate and save an immutable handoff file validating design rules."""
    # Validation: session_type strip & case-insensitivity
    session_type = session_type.strip().lower()
    if session_type not in VALID_SESSION_TYPES:
        raise ValueError(
            f"Invalid session_type '{session_type}'. Must be one of: {sorted(VALID_SESSION_TYPES)}"
        )

    # Validation: summary non-empty
    summary = summary.strip()
    if not summary:
        raise ValueError("summary cannot be empty.")

    # Validation: lineage reference
    previous_handoff_ref = previous_handoff_ref.strip()
    if previous_handoff_ref and previous_handoff_ref.lower() != "none":
        try:
            _resolve_handoff_path(previous_handoff_ref)
        except HandoffNotFoundError:
            raise FileNotFoundError(
                f"The previous_handoff_ref '{previous_handoff_ref}' does not exist."
            )

    # Normalization
    completed_work = _normalize_list(completed_work)
    pending_work = _normalize_list(pending_work)
    knowledge_pending_promotion = _normalize_list(knowledge_pending_promotion)
    resources = _normalize_list(resources)
    gotchas = _normalize_list(gotchas)

    # Validation: boot_instruction anti-hallucination
    # NOTE: boot_instruction is rendered as plain markdown; not sanitized for HTML.
    boot_instruction = boot_instruction.strip()
    if not boot_instruction:
        raise ValueError("boot_instruction cannot be empty.")

    if not pending_work:
        anti_hallucination_keywords = [
            "no hay tareas",
            "nada pendiente",
            "no hay pendientes",
            "no hay trabajo",
            "no pending",
        ]
        if not any(k in boot_instruction.lower() for k in anti_hallucination_keywords):
            raise ValueError(
                "No pending_work provided, but boot_instruction hallucinates next steps. You must explicitly indicate that there are no pending tasks."
            )

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S-%f")[:-3]
    rel_path = f"handoffs/handoff-{timestamp}.md"

    today_iso = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        "---",
        "type: handoff",
        f"session_type: {session_type}",
        f"previous_ref: {previous_handoff_ref or 'none'}",
        f"last_updated: {today_iso}",
        "schema_version: 1",
        "---",
        "",
        f"# Handoff — {timestamp} (UTC)",
        f"**Tipo de sesión:** {session_type}",
        f"**Referencia anterior:** {previous_handoff_ref or 'none'}\n",
    ]

    if (
        wiki_deviation_justification
        and wiki_deviation_justification.strip().lower() != "none"
    ):
        lines.append("## ⚠️ Desviación de la wiki (Temporal)")
        lines.append(wiki_deviation_justification.strip())
        lines.append("")

    lines.append("## Contexto inmediato")
    lines.append(f"{summary}\n")

    def _add_section(title: str, items: list[str]) -> None:
        if items:
            lines.append(f"## {title}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    _add_section("Trabajo completado", completed_work)
    _add_section("Trabajo pendiente", pending_work)
    _add_section(
        "Conocimiento pendiente de promoción (a wiki)", knowledge_pending_promotion
    )
    _add_section("Recursos", resources)
    _add_section("Gotchas", gotchas)

    lines.append("## Instrucción de arranque")
    lines.append(boot_instruction)

    content = "\n".join(lines)
    wiki_ops.write_article(rel_path, content)

    return rel_path



def read_handoff(ref: str = "latest") -> tuple[str, bool]:
    """
    Read a handoff document.

    Args:
        ref: "latest", "none", or "" (default to latest), or a specific timestamp with or without
             milliseconds or file extension (e.g., "2024-01-01-120000", "2024-01-01-120000-123", or "handoff-2024-01-01-120000.md").
             Timestamp prefixes are supported (e.g., "2024" or "2024-08" returns the latest handoff matching that prefix).

    Returns:
        tuple[str, bool]: (handoff_content, has_promotion_pending)
    """
    target_path = _resolve_handoff_path(ref)
    wiki_root = get_wiki_root()
    rel_path = str(target_path.relative_to(wiki_root))
    content = wiki_ops.read_article(rel_path)

    header = f"=== Handoff: {rel_path} ===\n\n"
    has_promotion_pending = "## Conocimiento pendiente de promoción" in content

    return header + content, has_promotion_pending


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
            lines.append(f"  - {rel}")
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


