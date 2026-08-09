import logging

from fastmcp import FastMCP

from brain79.core import context as context_ops
from brain79.core import handoff as handoff_ops
from brain79.core import wiki as wiki_ops

# Suppress fastmcp startup banner and INFO logs — MCP hosts interpret
# stderr output as a failure signal during the handshake phase.
logging.getLogger("fastmcp").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

mcp = FastMCP(
    "brain79",
    instructions=(
        "brain79 is a per-project AI memory system. "
        "Always call brain79_index() at the start of a session to orient yourself. "
        "Read SCHEMA.md before any wiki curation to understand the rules."
    ),
)


@mcp.tool()
def brain79_index() -> str:
    """
    Return INDEX.md — the project wiki's entry point.
    Always call this first at the start of a session.
    """
    return wiki_ops.get_index()


@mcp.tool()
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


@mcp.tool()
def brain79_write(path: str, content: str) -> str:
    """
    Write or update a wiki article. Creates the file and parent directories if needed.

    Args:
        path: Relative path within .brain-79/ (e.g., "decisions/use-fastmcp.md")
        content: Full markdown content for the article
    """
    try:
        return wiki_ops.write_article(path, content)
    except (ValueError, OSError) as exc:
        return f"Error: {exc}"


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def brain79_ingest(session_summary: str, instructions: str | None = None) -> str:
    """
    Save a session summary to raw sources and return the curation workflow.

    Call this first when the developer asks to update the wiki after a session.
    The session summary is saved as-is to _raw/sessions/ (immutable).
    The agent then curates the wiki using brain79_read / brain79_write.

    Args:
        session_summary: What happened in the session (free text or structured)
        instructions: Optional curation hints from the developer
                      (e.g., "focus on architecture changes, ignore debugging")
    """
    saved_path = wiki_ops.save_raw_session(session_summary, instructions)

    return (
        f"Session saved to: {saved_path}\n\n"
        "Curation workflow:\n"
        "1. brain79_index()            — review current wiki state\n"
        "2. brain79_read('SCHEMA.md')  — recall curation rules\n"
        "3. Identify what changed that has lasting value\n"
        "4. brain79_write(path, content) for each article to create or update\n"
        "5. brain79_write('INDEX.md', ...) if project state changed\n\n"
        "Remember: integrate knowledge, don't append. Curate, don't log."
    )


@mcp.tool()
def brain79_handoff_write(
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
    """
    Write an immutable handoff document for the next session.

    SYSTEM INSTRUCTION:
    1. The wiki ALWAYS wins. If you contradict the wiki, you MUST use wiki_deviation_justification.
    2. Valid types: "feature", "bugfix", "research", "brainstorming".
    3. If there are no pending tasks (pending_work is empty), boot_instruction MUST explicitly indicate "no hay tareas pendientes" (hallucinating next steps is strictly forbidden).
    """
    try:
        return handoff_ops.write_handoff(
            session_type,
            previous_handoff_ref,
            summary,
            completed_work,
            pending_work,
            knowledge_pending_promotion,
            resources,
            gotchas,
            boot_instruction,
            wiki_deviation_justification,
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        return f"Validation Error: {exc}"


@mcp.tool()
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
        return handoff_ops.read_handoff(handoff_ref)
    except (ValueError, FileNotFoundError, OSError) as exc:
        return f"Error reading handoff: {exc}"


@mcp.tool()
def brain79_lint() -> str:
    """
    Run a deterministic health check scan on the project wiki (.brain-79/).

    Diagnoses broken local links, namespace violations, structural errors/warnings,
    and orphan articles.
    """
    return wiki_ops.lint_wiki()


@mcp.tool()
def brain79_context(task: str, top_n: int = 3) -> str:
    """
    Retrieve top relevant wiki articles for a task using TF-IDF ranking.

    Args:
        task: Description of task or search query
        top_n: Maximum number of articles to return (default 3)
    """
    return context_ops.get_context(task, top_n)

