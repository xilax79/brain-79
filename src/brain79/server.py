import logging
from typing import Any

from fastmcp import FastMCP

from brain79 import __version__
from brain79.config import get_wiki_root
from brain79.core import context as context_ops
from brain79.core import lint as lint_ops
from brain79.core import wiki as wiki_ops
from brain79.core.frontmatter import ValidationError


# Suppress fastmcp startup banner and INFO logs — MCP hosts interpret
# stderr output as a failure signal during the handshake phase.
logging.getLogger("fastmcp").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)


def _unpack_nested_args(args: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively unpack nested {"args": {...}} dictionaries from proxy callers."""
    if not args or not isinstance(args, dict):
        return {}
    if "args" in args and isinstance(args["args"], dict):
        nested = _unpack_nested_args(args["args"])
        return {**args, **nested}
    return dict(args)


def brain79_orient(
    task: str | None = None,
    paths: list[str] | None = None,
    max_articles: int = 4,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
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

    if args:
        unpacked = _unpack_nested_args(args)
        task = task or unpacked.get("task")
        paths = paths if paths is not None else unpacked.get("paths")
        max_articles = unpacked.get("max_articles", max_articles)

    return orient(task=task, paths=paths, max_articles=max_articles)


def brain79_read(
    path: str = "",
    sections: list[str] | None = None,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    """
    Read a wiki article by its relative path, optionally projecting specific sections.

    Args:
        path: Relative path within .brain-79/ (e.g., "architecture/overview.md")
        sections: Optional list of ## H2 section names to extract (e.g., ["Components", "Data Flow"]).
                  If provided, extracts frontmatter, # H1, and the requested sections.
    """
    if args:
        unpacked = _unpack_nested_args(args)
        path = path or unpacked.get("path", "")
        sections = sections if sections is not None else unpacked.get("sections")

    try:
        return wiki_ops.read_article(path, sections=sections, include_adr_hints=True)
    except (FileNotFoundError, ValueError) as exc:
        return f"Error: {exc}"


def brain79_read_batch(
    requests: list[Any] | None = None,
    paths: list[Any] | None = None,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    """
    Read multiple wiki articles in a single call with optional section projections.

    Args:
        requests: List of path strings or request dicts, each dict with:
                  - "path": Relative path within .brain-79/ (required)
                  - "sections": Optional list of ## H2 section names to project
        paths: Optional list of relative paths within .brain-79/.

    Returns:
        Formatted markdown output containing the read articles and linked ADR notices.
    """
    if args:
        unpacked = _unpack_nested_args(args)
        if requests is None and "requests" in unpacked:
            requests = unpacked.get("requests")
        if paths is None and "paths" in unpacked:
            paths = unpacked.get("paths")

    try:
        results = wiki_ops.read_batch_articles(requests=requests, paths=paths)
        return wiki_ops.format_batch_results(results)
    except Exception as exc:
        return f"Error: {exc}"


def brain79_edit(
    path: str = "",
    edits: list[dict[str, str]] | None = None,
    force_validation_skip: bool = False,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    """
    Apply targeted text replacements to an existing wiki article and validate atomically.

    Args:
        path: Relative path within .brain-79/ (e.g., "INDEX.md")
        edits: List of replacements, each with {"old_text": "...", "new_text": "..."}
        force_validation_skip: If True, bypasses organizational validation
    """
    if args:
        unpacked = _unpack_nested_args(args)
        path = path or unpacked.get("path", "")
        edits = edits if edits is not None else unpacked.get("edits")
        force_validation_skip = force_validation_skip or unpacked.get("force_validation_skip", False)
    edits = edits or []

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


def brain79_search(
    query: str = "",
    tool: str | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    """
    Search wiki articles by keyword (case-insensitive).

    Args:
        query: Search term
    """
    if args:
        unpacked = _unpack_nested_args(args)
        query = query or unpacked.get("query", "")

    results = wiki_ops.search_articles(query)
    if not results:
        return f"No articles found matching '{query}'."

    lines = [f"Found {len(results)} article(s) matching '{query}':\n"]
    for r in results:
        lines.append(f"- {r['path']}")
        if r["excerpt"]:
            lines.append(f"  > {r['excerpt']}")
    return "\n".join(lines)


def brain79_lint(
    tool: str | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    """
    Run a deterministic health check scan on the project wiki (.brain-79/).

    Diagnoses broken local links, namespace violations, structural errors/warnings,
    and orphan articles.
    """
    return lint_ops.lint_wiki()


def brain79_context(
    task: str = "",
    top_n: int = 3,
    paths: list[str] | None = None,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    """
    Retrieve top relevant wiki articles for a task using 3-signal context ranking.

    Args:
        task: Description of task or search query
        top_n: Maximum number of articles to return (default 3)
        paths: Optional list of workspace file paths being inspected/modified
    """
    if args:
        unpacked = _unpack_nested_args(args)
        task = task or unpacked.get("task", "")
        top_n = unpacked.get("top_n", top_n)
        paths = paths if paths is not None else unpacked.get("paths")

    return context_ops.get_context(task=task, top_n=top_n, paths=paths)


def brain79_bootstrap(
    scope: str | None = None,
    force: bool = False,
    auto_map: bool | None = None,
    max_modules: int = 12,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
) -> str:
    """
    Scan the project and return a structured manifest for wiki bootstrapping.

    Args:
        scope: Optional comma-separated list of relative paths to focus on.
        force: If True, re-runs even if bootstrap was already executed.
        auto_map: If True/False, forces or disables auto-mapping; when None (default), enables automatically for software profile wikis.
        max_modules: Maximum number of auto-mapped module proposals to emit (default: 12).
    """
    if args:
        unpacked = _unpack_nested_args(args)
        scope = unpacked.get("scope", scope)
        force = unpacked.get("force", force)
        auto_map = unpacked.get("auto_map", auto_map)
        max_modules = unpacked.get("max_modules", max_modules)
    try:
        from brain79.core.bootstrap import run_bootstrap

        return run_bootstrap(
            scope=scope,
            force=force,
            auto_map=auto_map,
            max_modules=max_modules,
        )
    except (OSError, ValueError) as exc:
        return f"Bootstrap Error: {exc}"


def brain79_session_commit(
    writes: list[dict[str, str]] | None = None,
    edits: list[dict[str, Any]] | None = None,
    handoff: dict[str, Any] | None = None,
    session_summary: str | None = None,
    instructions: str | None = None,
    verified_articles: list[dict[str, str]] | None = None,
    allow_partial_ripple: bool = False,
    force_validation_skip: bool = False,
    tool: str | None = None,
    args: dict[str, Any] | None = None,
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
        handoff: Optional dict with handoff fields (session_type, summary, completed_work, pending_work, boot_instruction)
        session_summary: Optional high-level summary for raw session archiving (_raw/sessions/)
        instructions: Optional user prompt instructions for raw session archiving
        verified_articles: Optional list of internal non-breaking refactors [{"path": "...", "reason": "..."}]
        allow_partial_ripple: Optional boolean to permit committing with partial ripple warnings (default: False)
        force_validation_skip: Whether to bypass frontmatter schema validation

    Returns:
        Structured markdown receipt summarizing the committed transaction.
    """
    from brain79.config import get_wiki_root
    from brain79.core.session_commit import commit_session

    if args:
        unpacked = _unpack_nested_args(args)
        writes = writes if writes is not None else unpacked.get("writes")
        edits = edits if edits is not None else unpacked.get("edits")
        handoff = handoff if handoff is not None else unpacked.get("handoff")
        session_summary = session_summary or unpacked.get("session_summary")
        instructions = instructions or unpacked.get("instructions")
        verified_articles = verified_articles if verified_articles is not None else unpacked.get("verified_articles")
        allow_partial_ripple = allow_partial_ripple or unpacked.get("allow_partial_ripple", False)
        force_validation_skip = force_validation_skip or unpacked.get("force_validation_skip", False)

    payload: dict[str, Any] = {
        "writes": writes or [],
        "edits": edits or [],
        "handoff": handoff,
        "session_summary": session_summary,
        "instructions": instructions,
        "verified_articles": verified_articles or [],
        "allow_partial_ripple": allow_partial_ripple,
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
        if receipt.get("verified_articles"):
            lines.append(f"- **Verified Articles ({len(receipt['verified_articles'])})**: {', '.join(f'`{a}`' for a in receipt['verified_articles'])}")
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


MCP_TOOLS: frozenset[str] = frozenset({
    "brain79_orient",
    "brain79_session_commit",
    "brain79_read",
    "brain79_read_batch",
    "brain79_edit",
    "brain79_context",
    "brain79_search",
    "brain79_lint",
    "brain79_bootstrap",
})

_SERVER_INSTRUCTIONS = (
    "brain79 is a per-project AI memory system exposing 9 focused hot-path MCP tools. "
    "Always call brain79_orient(task?, paths?) at the start of a session for complete cold start orientation "
    "(including INDEX.md, active schema summary, latest handoff, and governing articles). "
    "Use brain79_read, brain79_read_batch, brain79_context, and brain79_search to inspect knowledge, "
    "brain79_bootstrap to scan an empty wiki, brain79_edit for targeted single-article edits, "
    "brain79_session_commit(writes?, edits?, handoff?) to apply article writes, edits, and handoffs atomically, "
    "and brain79_lint() to verify wiki health. "
    "For administrative operations (migrate, doctor, update-project, navigate, handoff-read, handoff-purge, schema), "
    "run the `brain79 <command>` CLI."
)

_TOOL_FUNCS = (
    brain79_orient,
    brain79_session_commit,
    brain79_read,
    brain79_read_batch,
    brain79_edit,
    brain79_context,
    brain79_search,
    brain79_lint,
    brain79_bootstrap,
)


def create_mcp_server() -> FastMCP:
    """Create a configured FastMCP server instance exposing the focused 9-tool surface."""
    server = FastMCP(
        "brain79",
        version=__version__,
        instructions=_SERVER_INSTRUCTIONS,
    )
    for fn in _TOOL_FUNCS:
        server.tool(output_schema=None)(fn)
    return server


mcp = create_mcp_server()
