import logging

from fastmcp import FastMCP

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
    except ValueError as exc:
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
