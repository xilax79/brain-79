import logging
from typing import Literal

from fastmcp import FastMCP

from brain79.config import get_wiki_root
from brain79.core import context as context_ops
from brain79.core import handoff as handoff_ops
from brain79.core import lint as lint_ops
from brain79.core import wiki as wiki_ops
from brain79.core.frontmatter import ValidationError


# Suppress fastmcp startup banner and INFO logs — MCP hosts interpret
# stderr output as a failure signal during the handshake phase.
logging.getLogger("fastmcp").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

mcp = FastMCP(
    "brain79",
    instructions=(
        "brain79 is a per-project AI memory system. "
        "Always call brain79_index() at the start of a session to orient yourself. "
        "Call brain79_schema() before writing or updating articles to inspect exact frontmatter rules."
    ),
)


@mcp.tool(output_schema=None)
def brain79_index() -> str:
    """
    Return INDEX.md — the project wiki's entry point.
    Always call this first at the start of a session.
    """
    return wiki_ops.get_index()


@mcp.tool(output_schema=None)
def brain79_read(path: str) -> str:
    """
    Read a wiki article by its relative path.

    Args:
        path: Relative path within .brain-79/ (e.g., "architecture/overview.md")
    """
    try:
        return wiki_ops.read_article(path)
    except (FileNotFoundError, ValueError) as exc:
        return f"Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_schema(target_type: str | None = None) -> str:
    """
    Inspect frontmatter schema requirements and copy-paste templates.

    Args:
        target_type: Optional type to inspect (e.g., "feature", "decision", "architecture").
                     If omitted, returns the complete schema reference for all types.
    """
    from brain79.core.frontmatter import get_schema_documentation

    return get_schema_documentation(target_type)


@mcp.tool(output_schema=None)
def brain79_write(
    path: str, content: str, force_validation_skip: bool = False
) -> str:
    """
    Write or update a wiki article. Creates the file and parent directories if needed.

    Args:
        path: Relative path within .brain-79/ (e.g., "decisions/use-fastmcp.md")
        content: Full markdown content for the article
        force_validation_skip: If True, bypasses organizational validation
    """
    try:
        msg = wiki_ops.write_article(
            path, content, force_validation_skip=force_validation_skip
        )
        health = wiki_ops.check_file_health(get_wiki_root(), path, content)
        if health:
            return f"{msg}\nLint warnings:\n" + "\n".join(f"- {w}" for w in health)
        return f"{msg} · lint OK"
    except ValidationError as exc:
        return f"Error: {exc.format_user_message()}"
    except (ValueError, OSError) as exc:
        return f"Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_edit(
    path: str,
    edits: list[dict[str, str]],
    force_validation_skip: bool = False,
) -> str:
    """
    Apply targeted text replacements to an existing wiki article and validate atomically.

    Args:
        path: Relative path within .brain-79/ (e.g., "INDEX.md")
        edits: List of replacements, each with {"old_text": "...", "new_text": "..."}
        force_validation_skip: If True, bypasses organizational validation
    """
    try:
        msg = wiki_ops.edit_article(
            path, edits, force_validation_skip=force_validation_skip
        )
        updated_content = wiki_ops.read_article(path)
        health = wiki_ops.check_file_health(get_wiki_root(), path, updated_content)
        if health:
            return f"{msg}\nLint warnings:\n" + "\n".join(f"- {w}" for w in health)
        return f"{msg} · lint OK"
    except ValidationError as exc:
        return f"Error: {exc.format_user_message()}"
    except (FileNotFoundError, ValueError, OSError) as exc:
        return f"Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_write_many(
    articles: list[dict[str, str]],
    force_validation_skip: bool = False,
) -> str:
    """
    Validate and atomically write multiple wiki articles in a single batch call.

    All articles are validated before any files are written (all-or-nothing).

    Args:
        articles: List of articles, each with {"path": "...", "content": "..."}
        force_validation_skip: If True, bypasses organizational validation
    """
    try:
        return wiki_ops.write_many_articles(
            articles, force_validation_skip=force_validation_skip
        )
    except ValidationError as exc:
        return f"Error: {exc.format_user_message()}"
    except (ValueError, OSError) as exc:
        return f"Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_list(section: str | None = None) -> str:
    """
    List all wiki articles, optionally filtered by section directory.

    Args:
        section: Optional section to filter by (e.g., "architecture", "features")
    """
    articles = wiki_ops.list_articles(section)
    if not articles:
        label = f"in '{section}'" if section else "in the wiki"
        return f"No articles found {label}."
    return "\n".join(articles)


@mcp.tool(output_schema=None)
def brain79_search(query: str) -> str:
    """
    Search wiki articles by keyword (case-insensitive).

    Args:
        query: Search term
    """
    results = wiki_ops.search_articles(query)
    if not results:
        return f"No articles found matching '{query}'."

    lines = [f"Found {len(results)} article(s) matching '{query}':\n"]
    for r in results:
        lines.append(f"- {r['path']}")
        if r["excerpt"]:
            lines.append(f"  > {r['excerpt']}")
    return "\n".join(lines)


@mcp.tool(output_schema=None)
def brain79_ingest(session_summary: str, instructions: str | None = None) -> str:
    """
    Save a session summary to raw sources and return state-aware curation guide.

    Call this first when the developer asks to update the wiki after a session.
    The session summary is saved as-is to _raw/sessions/ (immutable).
    The agent then curates the wiki using state-aware guidance.

    Args:
        session_summary: What happened in the session (free text or structured)
        instructions: Optional curation hints from the developer
                      (e.g., "focus on architecture changes, ignore debugging")
    """
    saved_path = wiki_ops.save_raw_session(session_summary, instructions)
    from brain79.core.curate import prepare_curation_guide

    guide = prepare_curation_guide(get_wiki_root(), session_summary)
    return f"Session saved to: {saved_path}\n\n{guide}"


@mcp.tool(output_schema=None)
def brain79_handoff_write(
    session_type: Literal["feature", "bugfix", "research", "brainstorming"],
    previous_handoff_ref: str = "latest",
    summary: str = "",
    completed_work: list[str] | None = None,
    pending_work: list[str] | None = None,
    knowledge_pending_promotion: list[str] | None = None,
    resources: list[str] | None = None,
    gotchas: list[str] | None = None,
    boot_instruction: str = "",
    wiki_deviation_justification: str = "",
) -> str:
    """
    Write an immutable handoff document for the next session.

    SYSTEM INSTRUCTION:
    1. The wiki ALWAYS wins. If you contradict the wiki, you MUST use wiki_deviation_justification.
    2. Valid session types: "feature", "bugfix", "research", "brainstorming".
    3. If there are no pending tasks (pending_work is empty), boot_instruction MUST explicitly indicate that there are no pending tasks (e.g. "no hay tareas pendientes" or "no pending tasks").
    """
    try:
        rel_path = handoff_ops.write_handoff(
            session_type=session_type,
            previous_handoff_ref=previous_handoff_ref,
            summary=summary,
            completed_work=completed_work or [],
            pending_work=pending_work or [],
            knowledge_pending_promotion=knowledge_pending_promotion or [],
            resources=resources or [],
            gotchas=gotchas or [],
            boot_instruction=boot_instruction,
            wiki_deviation_justification=wiki_deviation_justification,
        )
        return f"Handoff successfully saved at: {rel_path}"
    except (ValueError, FileNotFoundError, OSError) as exc:
        return f"Validation Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_handoff_read(handoff_ref: str = "latest") -> str:
    """
    Read a handoff document.

    Args:
        handoff_ref: "latest" (default), "none", or "" to get the latest handoff,
                     or a specific timestamp with or without milliseconds or file extension
                     (e.g., "2024-01-01-120000", "2024-01-01-120000-123", or "handoff-2024-01-01-120000.md").
                     Timestamp prefixes are supported (e.g., "2024" or "2024-08" returns the latest handoff matching that prefix).

    If the handoff contains "knowledge_pending_promotion", the response will
    include a warning instructing you to call brain79_ingest immediately.
    """
    try:
        content, has_promotion = handoff_ops.read_handoff(handoff_ref)
        if has_promotion:
            content += (
                "\n\n> ⚠️ **ATENCIÓN:** Este handoff contiene elementos en "
                "'Conocimiento pendiente de promoción'. Tu responsabilidad inmediata "
                "es consolidarlos en la memoria a largo plazo usando `brain79_ingest`."
            )
        return content
    except (handoff_ops.HandoffsDirNotFoundError, handoff_ops.NoHandoffsExistError) as exc:
        return str(exc)
    except (ValueError, FileNotFoundError, OSError) as exc:
        return f"Error reading handoff: {exc}"


@mcp.tool(output_schema=None)
def brain79_handoff_purge(apply: bool = False) -> str:
    """
    Wipe all handoff files and unregister them from the navigation registry.

    Handoffs are supertemporal transitional artifacts. This command is the
    explicit exception to handoff immutability, intended for cleanup of
    legacy wikis or operational resets.

    Args:
        apply: If False (default), only preview what would be deleted.
               If True, actually delete the files.

    Returns:
        Markdown-formatted report listing files affected.
    """
    try:
        from brain79.core.handoff import purge_handoffs

        return purge_handoffs(get_wiki_root(), apply=apply)
    except (OSError, ValueError) as exc:
        return f"Handoff Purge Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_lint() -> str:
    """
    Run a deterministic health check scan on the project wiki (.brain-79/).

    Diagnoses broken local links, namespace violations, structural errors/warnings,
    and orphan articles.
    """
    return lint_ops.lint_wiki()


@mcp.tool(output_schema=None)
def brain79_context(task: str, top_n: int = 3) -> str:
    """
    Retrieve top relevant wiki articles for a task using TF-IDF ranking.

    Args:
        task: Description of task or search query
        top_n: Maximum number of articles to return (default 3)
    """
    return context_ops.get_context(task, top_n)


@mcp.tool(output_schema=None)
def brain79_bootstrap(
    scope: str | None = None,
    force: bool = False,
) -> str:
    """
    Scan the project and return a structured manifest for wiki bootstrapping.

    Args:
        scope: Optional comma-separated list of relative paths to focus on.
        force: If True, re-runs even if bootstrap was already executed.
    """
    try:
        from brain79.core.bootstrap import run_bootstrap

        return run_bootstrap(scope=scope, force=force)
    except (OSError, ValueError) as exc:
        return f"Bootstrap Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_navigate(regenerate: bool = False) -> str:
    """
    Manage INDEX.md navigation.

    Args:
        regenerate: If True, regenerates INDEX.md Quick navigation section from registry.
    """
    try:
        from brain79.core.navigation import (
            generate_quick_navigation,
            regenerate_index_navigation,
        )

        wiki_root = get_wiki_root()
        if regenerate:
            return regenerate_index_navigation(wiki_root)
        else:
            return generate_quick_navigation(wiki_root)
    except (OSError, ValueError, FileNotFoundError) as exc:
        return f"Navigation Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_migrate(dry_run: bool = True) -> str:
    """
    Add frontmatter to legacy wiki articles.

    Args:
        dry_run: If True, only preview changes without modifying files. Default True for safety.
    """
    try:
        from brain79.core.migration import migrate_wiki

        return migrate_wiki(get_wiki_root(), dry_run=dry_run)
    except (OSError, ValueError) as exc:
        return f"Migration Error: {exc}"
