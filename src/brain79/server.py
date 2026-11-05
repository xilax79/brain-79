import logging
from typing import Any

from fastmcp import FastMCP

from brain79 import __version__
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
    version=__version__,
    instructions=(
        "brain79 is a per-project AI memory system. "
        "Always call brain79_orient(task?, paths?) at the start of a session for complete cold start orientation. "
        "Call brain79_schema() before writing or updating articles to inspect exact frontmatter rules."
    ),
)


@mcp.tool(output_schema=None)
def brain79_orient(
    task: str | None = None,
    paths: list[str] | None = None,
    max_articles: int = 4,
    tool: str | None = None,
) -> str:
    """
    1-call complete cold start orientation.

    Combines INDEX.md routing table, latest handoff state (with promotion warnings),
    and inlined content of top governing articles (via 3-signal path matching, weighted TF-IDF,
    and 1-hop ADR graph expansion).

    Args:
        task: Optional high-level goal or task description.
        paths: Optional list of workspace file paths the agent intends to touch.
        max_articles: Maximum number of governing articles to inline (default: 4).
    """
    from brain79.core.orient import orient

    return orient(task=task, paths=paths, max_articles=max_articles)


@mcp.tool(output_schema=None)
def brain79_index(tool: str | None = None) -> str:
    """
    Return the complete INDEX.md routing table only.
    For session cold start, prefer `brain79_orient` which loads index, active schema summary, latest handoff, and governing articles in a single call.
    """
    return wiki_ops.get_index()


@mcp.tool(output_schema=None)
def brain79_read(
    path: str,
    sections: list[str] | None = None,
    tool: str | None = None,
) -> str:
    """
    Read a wiki article by its relative path, optionally projecting specific sections.

    Args:
        path: Relative path within .brain-79/ (e.g., "architecture/overview.md")
        sections: Optional list of ## H2 section names to extract (e.g., ["Components", "Data Flow"]).
                  If provided, extracts frontmatter, # H1, and the requested sections.
    """
    try:
        return wiki_ops.read_article(path, sections=sections, include_adr_hints=True)
    except (FileNotFoundError, ValueError) as exc:
        return f"Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_read_batch(
    requests: list[dict[str, Any]],
    tool: str | None = None,
) -> str:
    """
    Read multiple wiki articles in a single call with optional section projections.

    Args:
        requests: List of request dicts, each with:
                  - "path": Relative path within .brain-79/ (required)
                  - "sections": Optional list of ## H2 section names to project

    Returns:
        Formatted markdown output containing the read articles and linked ADR notices.
    """
    try:
        results = wiki_ops.read_batch_articles(requests)
        rendered_parts: list[str] = []
        for item in results:
            p = item["path"]
            err = item.get("error")
            content = item.get("content")
            rendered_parts.append(f"## === Article: {p} ===")
            if err:
                rendered_parts.append(f"> ❌ Error: {err}")
            else:
                rendered_parts.append(content or "(empty)")
        return "\n\n".join(rendered_parts)
    except Exception as exc:
        return f"Error reading batch: {exc}"


@mcp.tool(output_schema=None)
def brain79_schema(
    target_type: str | None = None,
    type: str | None = None,
    tool: str | None = None,
) -> str:
    """
    Inspect frontmatter schema requirements and copy-paste templates.

    Respects the project's active profile and custom types declared in .brain-79/SCHEMA.md.

    Args:
        target_type: Optional type to inspect (e.g., "feature", "decision", "topic", "context").
                     If omitted, returns the complete schema reference for the active profile.
        type: Alias for target_type.
    """
    from brain79.config import get_wiki_root
    from brain79.core.frontmatter import get_schema_documentation, load_active_schema

    try:
        active_schema = load_active_schema(get_wiki_root())
    except Exception:
        active_schema = None

    effective_type = type or target_type
    return get_schema_documentation(effective_type, schema=active_schema)


@mcp.tool(output_schema=None)
def brain79_write(
    path: str,
    content: str,
    force_validation_skip: bool = False,
    tool: str | None = None,
) -> str:
    """
    Write or update a wiki article. Creates the file and parent directories if needed.

    Args:
        path: Relative path within .brain-79/ (e.g., "decisions/use-fastmcp.md")
        content: Full markdown content for the article
        force_validation_skip: If True, bypasses organizational validation
    """
    try:
        clean_path = wiki_ops.normalize_wiki_rel_path(path)
        msg = wiki_ops.write_article(
            clean_path, content, force_validation_skip=force_validation_skip
        )
        health = wiki_ops.check_file_health(get_wiki_root(), clean_path, content)
        if health:
            return f"{msg} · INDEX.md auto-synced\nLint warnings:\n" + "\n".join(f"- {w}" for w in health)
        return f"{msg} · INDEX.md auto-synced · lint OK"
    except ValidationError as exc:
        return f"Error: {exc.format_user_message()}"
    except (ValueError, OSError) as exc:
        return f"Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_edit(
    path: str,
    edits: list[dict[str, str]],
    force_validation_skip: bool = False,
    tool: str | None = None,
) -> str:
    """
    Apply targeted text replacements to an existing wiki article and validate atomically.

    Args:
        path: Relative path within .brain-79/ (e.g., "INDEX.md")
        edits: List of replacements, each with {"old_text": "...", "new_text": "..."}
        force_validation_skip: If True, bypasses organizational validation
    """
    try:
        clean_path = wiki_ops.normalize_wiki_rel_path(path)
        msg = wiki_ops.edit_article(
            clean_path, edits, force_validation_skip=force_validation_skip
        )
        updated_content = wiki_ops.read_article(clean_path)
        health = wiki_ops.check_file_health(get_wiki_root(), clean_path, updated_content)
        if health:
            return f"{msg} · INDEX.md auto-synced\nLint warnings:\n" + "\n".join(f"- {w}" for w in health)
        return f"{msg} · INDEX.md auto-synced · lint OK"
    except ValidationError as exc:
        return f"Error: {exc.format_user_message()}"
    except (FileNotFoundError, ValueError, OSError) as exc:
        return f"Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_write_many(
    articles: list[dict[str, str]],
    force_validation_skip: bool = False,
    tool: str | None = None,
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
def brain79_list(
    section: str | None = None,
    tool: str | None = None,
) -> str:
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
def brain79_search(
    query: str,
    tool: str | None = None,
) -> str:
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
def brain79_ingest(
    session_summary: str,
    instructions: str | None = None,
    tool: str | None = None,
) -> str:
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
    tool: str | None = None,
) -> str:
    """
    Write an immutable handoff document for the next session.

    ON-DEMAND POLICY:
    Call this ONLY when explicitly requested by the user (e.g. 'save handoff', 'wrap up session', 'haz handoff')
    or when terminating an autonomous headless sub-agent process. Do NOT call automatically after every conversational turn.

    RECOMMENDED 1-CALL SESSION WRAP-UP:
    If this session produced research findings, analyses, or new wiki articles, prefer calling
    `brain79_session_commit(writes=[...], handoff={...})` in a single atomic transaction.

    PARAMETER ALIASES:
    - `decisions` / `decisions_made`: automatically merged into `completed_work`.
    - `next_steps` / `pending_tasks`: automatically merged into `pending_work` (generic filler like 'wait for user' is filtered out).
    - `open_questions`: automatically merged into `gotchas` (placeholders like 'None' or 'Ninguna' are filtered out).
    - `session_summary`: accepted as fallback for `summary`.
    - `boot_instructions`: accepted as alias for `boot_instruction`.

    SYSTEM INSTRUCTION:
    1. The wiki ALWAYS wins. If you contradict the wiki, you MUST use wiki_deviation_justification.
    2. Valid session types: "feature", "bugfix", "research", "brainstorming", "writing", "analysis".
    3. boot_instruction must provide clear orientation for resuming work in the next session (cannot be empty).
    4. Unpersisted research sessions will be blocked unless wiki articles are persisted or wiki_deviation_justification is provided.
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
        )
        return f"Handoff successfully saved at: {rel_path}"
    except (ValueError, FileNotFoundError, OSError) as exc:
        return f"Validation Error: {exc}"


@mcp.tool(output_schema=None)
def brain79_handoff_read(
    handoff_ref: str = "latest",
    tool: str | None = None,
) -> str:
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
def brain79_handoff_purge(
    apply: bool = False,
    tool: str | None = None,
) -> str:
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
def brain79_lint(tool: str | None = None) -> str:
    """
    Run a deterministic health check scan on the project wiki (.brain-79/).

    Diagnoses broken local links, namespace violations, structural errors/warnings,
    and orphan articles.
    """
    return lint_ops.lint_wiki()


@mcp.tool(output_schema=None)
def brain79_context(
    task: str,
    top_n: int = 3,
    paths: list[str] | None = None,
    tool: str | None = None,
) -> str:
    """
    Retrieve top relevant wiki articles for a task using 3-signal context ranking.

    Args:
        task: Description of task or search query
        top_n: Maximum number of articles to return (default 3)
        paths: Optional list of workspace file paths being inspected/modified
    """
    return context_ops.get_context(task=task, top_n=top_n, paths=paths)


@mcp.tool(output_schema=None)
def brain79_bootstrap(
    scope: str | None = None,
    force: bool = False,
    tool: str | None = None,
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
def brain79_navigate(
    regenerate: bool = False,
    tool: str | None = None,
) -> str:
    """
    Manage INDEX.md navigation.

    Note: brain79_write, brain79_edit, brain79_write_many, and brain79_session_commit automatically
    sync INDEX.md. Only call brain79_navigate(regenerate=True) after manual filesystem edits outside MCP.

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
def brain79_session_commit(
    writes: list[dict[str, str]] | None = None,
    edits: list[dict[str, Any]] | None = None,
    handoff: dict[str, Any] | None = None,
    session_summary: str | None = None,
    instructions: str | None = None,
    force_validation_skip: bool = False,
    tool: str | None = None,
) -> str:
    """
    1-call atomic end-of-session finalization transaction.

    ON-DEMAND HANDOFF POLICY:
    Pass the `handoff` argument ONLY when explicitly requested by the user (e.g. 'wrap up session', 'save handoff',
    'haz handoff') or when terminating an autonomous headless sub-agent process. During normal interactive
    turns, omit `handoff` and commit only writes/edits/raw logs.

    Executes the entire end-of-session wrap-up in a single all-or-nothing call:
    1. Pre-flight validation of all writes, in-memory simulated edits, and handoff rules.
       If ANY validation check fails, zero files on disk are modified.
    2. Atomic execution: saves raw session log (if session_summary provided), writes articles,
       applies edits, saves immutable handoff (if handoff provided), and syncs navigation registry and INDEX.md once.
    3. Runs inline health checks on all touched articles and returns a unified receipt.

    Args:
        writes: Optional list of articles to create/overwrite [{"path": "...", "content": "..."}]
        edits: Optional list of targeted text replacements [{"path": "...", "edits": [{"old_text": "...", "new_text": "..."}]}]
        handoff: Optional dict matching brain79_handoff_write parameters (session_type, summary, completed_work, pending_work, boot_instruction)
        session_summary: Optional high-level summary for raw session archiving (_raw/sessions/)
        instructions: Optional user prompt instructions for raw session archiving
        force_validation_skip: Whether to bypass frontmatter schema validation

    Returns:
        Structured markdown receipt summarizing the committed transaction.
    """
    from brain79.config import get_wiki_root
    from brain79.core.session_commit import commit_session

    payload: dict[str, Any] = {
        "writes": writes or [],
        "edits": edits or [],
        "handoff": handoff,
        "session_summary": session_summary,
        "instructions": instructions,
    }

    try:
        receipt = commit_session(
            payload,
            wiki_root=get_wiki_root(),
            force_validation_skip=force_validation_skip,
        )
        lines = ["# Brain-79 — Session Commit Receipt", ""]
        lines.append("- **Status**: ✅ Transaction Committed Successfully")
        if receipt.get("session_raw_path"):
            lines.append(f"- **Raw Session Log**: `{receipt['session_raw_path']}`")
        if receipt.get("written_articles"):
            lines.append(f"- **Written Articles ({len(receipt['written_articles'])})**: {', '.join(f'`{a}`' for a in receipt['written_articles'])}")
        if receipt.get("edited_articles"):
            lines.append(f"- **Edited Articles ({len(receipt['edited_articles'])})**: {', '.join(f'`{a}`' for a in receipt['edited_articles'])}")
        if receipt.get("handoff_path"):
            lines.append(f"- **Session Handoff**: `{receipt['handoff_path']}`")
        lines.append(f"- **Inline Health**: `{receipt.get('health_status', 'ok')}`")
        if receipt.get("warnings"):
            lines.append("\n### Warnings:")
            for w in receipt["warnings"]:
                lines.append(f"- ⚠️ {w}")
        return "\n".join(lines)
    except ValidationError as exc:
        return f"Commit Validation Failed:\n{exc.format_user_message()}"
    except Exception as exc:
        return f"Commit Aborted: {exc}"


@mcp.tool(output_schema=None)
def brain79_migrate(
    dry_run: bool = True,
    tool: str | None = None,
) -> str:
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
