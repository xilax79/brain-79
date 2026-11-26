import argparse
import json
import sys
import traceback
from typing import Sequence

import filelock

from brain79.cli.io import read_input_field

WHITELIST = {
    "init",
    "update",
    "update-project",
    "doctor",
    "index",
    "read",
    "read-batch",
    "write",
    "edit",
    "write-many",
    "schema",
    "list",
    "search",
    "ingest",
    "handoff-write",
    "handoff-read",
    "lint",
    "context",
    "bootstrap",
    "navigate",
    "migrate",
    "handoff-purge",
    "orient",
    "session-commit",
    "ci-check",
    "stats",
}


def map_exception_to_exit_code(exc: BaseException) -> int:
    """Map python exception to Unix exit code based on domain rules."""
    if isinstance(exc, KeyboardInterrupt):
        return 130
    if isinstance(exc, FileNotFoundError):
        return 2
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return 1
    if isinstance(exc, (PermissionError, filelock.Timeout, OSError)):
        return 3
    return 1


def _positive_int(raw: str) -> int:
    """Parse a strictly positive integer for CLI arguments (argparse exit 2 on failure)."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid positive integer value: {raw!r}") from exc
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return value


def _write_stdout(text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    sys.stdout.write(text)


def dispatch_cmd(cmd: str, sub_args: Sequence[str]) -> int:
    """Parse arguments and execute a specific sub-command."""
    if cmd == "init":
        parser = argparse.ArgumentParser(
            prog="brain79 init",
            description="Initialize a brain-79 memory wiki in the target project.",
        )
        parser.add_argument(
            "--project-root",
            default=None,
            metavar="PATH",
            help="Project root directory (default: current directory)",
        )
        parser.add_argument(
            "--install-git-hooks",
            dest="install_git_hooks",
            action="store_true",
            default=True,
            help="Install .git/hooks/pre-commit if .git exists (default: True)",
        )
        parser.add_argument(
            "--no-git-hooks",
            dest="install_git_hooks",
            action="store_false",
            help="Skip git hook installation",
        )
        parser.add_argument(
            "--no-git",
            dest="auto_git_init",
            action="store_false",
            default=True,
            help="Skip automatic git repository initialization in software profile",
        )
        parser.add_argument(
            "--profile",
            choices=["software", "general"],
            default="software",
            help="Knowledge profile ('software' or 'general', default: software)",
        )
        parser.add_argument(
            "--upgrade",
            action="store_true",
            default=False,
            help="Upgrade project protocol and configurations if wiki already exists",
        )
        parser.add_argument(
            "--include-desktop",
            action="store_true",
            default=False,
            help="Also configure host desktop application configs (Claude Desktop, Windsurf)",
        )
        parser.add_argument(
            "--no-merge-driver",
            dest="install_merge_driver",
            action="store_false",
            default=True,
            help="Skip configuring the deterministic INDEX.md Git merge driver",
        )
        parser.add_argument(
            "--enforcement",
            choices=["strict", "balanced", "advisory"],
            default="strict",
            help="Governance enforcement tier in SCHEMA.md (default: strict)",
        )
        parser.add_argument(
            "--harnesses",
            default="all",
            metavar="LIST",
            help="Comma-separated harnesses to install (default: all; e.g. agents,claude,cursor,copilot,agy,mcp,hooks)",
        )
        parser.add_argument(
            "--install-lifecycle-hooks",
            "--lifecycle-hooks",
            dest="install_lifecycle_hooks",
            action="store_true",
            default=False,
            help="Install opt-in native lifecycle hooks for Claude Code, Antigravity, and Cursor",
        )
        parsed = parser.parse_args(sub_args)
        from pathlib import Path
        from brain79 import config
        from brain79.core.init_project import init_project

        if parsed.project_root:
            target_root = Path(parsed.project_root).resolve()
        elif config._project_root is not None:
            target_root = config._project_root
        else:
            target_root = Path.cwd().resolve()
        selected_harnesses = (
            None
            if parsed.harnesses.strip().lower() == "all"
            else [h.strip() for h in parsed.harnesses.split(",") if h.strip()]
        )
        init_project(
            target_root,
            install_git_hooks_flag=parsed.install_git_hooks,
            profile=parsed.profile,
            auto_git_init=parsed.auto_git_init,
            upgrade=parsed.upgrade,
            include_desktop=parsed.include_desktop,
            harnesses=selected_harnesses,
            install_merge_driver=parsed.install_merge_driver,
            enforcement=parsed.enforcement,
            install_lifecycle_hooks=parsed.install_lifecycle_hooks,
        )
        return 0


    elif cmd == "update":
        parser = argparse.ArgumentParser(
            prog="brain79 update",
            description="Update the installed brain79 CLI tool from upstream Git or local development checkout.",
        )
        parser.add_argument(
            "--branch",
            default=None,
            help="Git branch to install or pull from (default: upstream default branch)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.update import update_project as update_installation

        return update_installation(branch_override=parsed.branch)

    elif cmd == "index":
        parser = argparse.ArgumentParser(
            prog="brain79 index",
            description="Display the project documentation index (INDEX.md).",
        )
        parser.parse_args(sub_args)
        from brain79.core.wiki import get_index

        _write_stdout(get_index())
        return 0

    elif cmd == "read":
        parser = argparse.ArgumentParser(
            prog="brain79 read",
            description="Read an article from the wiki, optionally extracting specific sections.",
        )
        parser.add_argument("path", help="Relative path within .brain-79/")
        parser.add_argument(
            "--sections",
            nargs="*",
            default=None,
            help="Optional list of ## H2 section titles to extract",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.wiki import read_article

        _write_stdout(read_article(parsed.path, sections=parsed.sections))
        return 0

    elif cmd == "read-batch":
        parser = argparse.ArgumentParser(
            prog="brain79 read-batch",
            description="Read multiple wiki articles in a single call, optionally projecting sections.",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--paths",
            nargs="+",
            metavar="PATH",
            help="One or more relative paths within .brain-79/",
        )
        group.add_argument("--file", help="Path to JSON file containing list of read requests or path strings")
        group.add_argument("--stdin", action="store_true", help="Read JSON read requests or path strings from stdin")
        parsed = parser.parse_args(sub_args)

        from brain79.core.wiki import format_batch_results, read_batch_articles

        if parsed.paths is not None:
            results = read_batch_articles(paths=parsed.paths)
        else:
            raw_json = read_input_field(parsed.file, parsed.stdin, "requests")
            requests_data = json.loads(raw_json)
            results = read_batch_articles(requests=requests_data)
        _write_stdout(format_batch_results(results))
        return 0

    elif cmd == "write":
        parser = argparse.ArgumentParser(
            prog="brain79 write",
            description="Create or overwrite a wiki article with schema and frontmatter validation.",
        )
        parser.add_argument("path", help="Relative path within .brain-79/")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--content-file", help="Path to file containing article markdown content")
        group.add_argument(
            "--content-stdin",
            action="store_true",
            help="Read article markdown content from stdin",
        )
        parser.add_argument(
            "--force-validation-skip",
            "--force-skip",
            action="store_true",
            help="Bypass schema validation and tag article with force_validation_skipped",
        )
        parsed = parser.parse_args(sub_args)
        content = read_input_field(parsed.content_file, parsed.content_stdin, "content")
        from brain79.core.wiki import write_article

        write_article(parsed.path, content, force_validation_skip=parsed.force_validation_skip)
        _write_stdout(parsed.path)
        return 0

    elif cmd == "schema":
        parser = argparse.ArgumentParser(
            prog="brain79 schema",
            description="Inspect active schema rules, required frontmatter fields, and document skeletons.",
        )
        parser.add_argument(
            "--type",
            "--target-type",
            default=None,
            dest="target_type",
            help="Optional document type to inspect (e.g., decision, topic, feature, architecture)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.config import get_wiki_root
        from brain79.core.frontmatter import get_schema_documentation, load_active_schema

        try:
            active_schema = load_active_schema(get_wiki_root())
        except Exception:
            active_schema = None

        _write_stdout(get_schema_documentation(parsed.target_type, schema=active_schema))
        return 0

    elif cmd == "edit":
        parser = argparse.ArgumentParser(
            prog="brain79 edit",
            description="Apply targeted text replacements to an existing wiki article.",
        )
        parser.add_argument("path", help="Relative path within .brain-79/")
        parser.add_argument("--old-text", help="Exact text snippet to replace")
        parser.add_argument("--new-text", help="Replacement text snippet")
        parser.add_argument(
            "--edits-file",
            help="Path to JSON file containing list of replacements [{old_text, new_text}]",
        )
        parser.add_argument(
            "--force-validation-skip",
            "--force-skip",
            action="store_true",
            help="Bypass schema validation on resulting content",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.wiki import edit_article

        if parsed.edits_file:
            with open(parsed.edits_file, "r", encoding="utf-8") as f:
                edits = json.load(f)
        elif parsed.old_text is not None and parsed.new_text is not None:
            edits = [{"old_text": parsed.old_text, "new_text": parsed.new_text}]
        else:
            raise ValueError(
                "Must provide either --edits-file or both --old-text and --new-text."
            )

        msg = edit_article(
            parsed.path, edits, force_validation_skip=parsed.force_validation_skip
        )
        _write_stdout(msg)
        return 0

    elif cmd == "write-many":
        parser = argparse.ArgumentParser(
            prog="brain79 write-many",
            description="Write multiple wiki articles in an atomic batch with pre-flight validation.",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--file",
            help="Path to JSON file containing list of articles [{path, content}]",
        )
        group.add_argument(
            "--stdin",
            action="store_true",
            help="Read JSON list of articles from stdin",
        )
        parser.add_argument(
            "--force-validation-skip",
            "--force-skip",
            action="store_true",
            help="Bypass schema validation and tag articles with force_validation_skipped",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.wiki import write_many_articles

        if parsed.file:
            with open(parsed.file, "r", encoding="utf-8") as f:
                articles = json.load(f)
        else:
            articles = json.loads(sys.stdin.read())

        msg = write_many_articles(
            articles, force_validation_skip=parsed.force_validation_skip
        )
        _write_stdout(msg)
        return 0

    elif cmd == "list":
        parser = argparse.ArgumentParser(
            prog="brain79 list",
            description="List wiki articles, optionally filtered by directory section.",
        )
        parser.add_argument("--section", default=None, help="Optional section folder (e.g. decisions, topics, features)")
        parsed = parser.parse_args(sub_args)
        from brain79.core.wiki import list_articles

        articles = list_articles(parsed.section)
        if articles:
            _write_stdout("\n".join(articles))
        else:
            label = f"in '{parsed.section}'" if parsed.section else "in the wiki"
            _write_stdout(f"No articles found {label}.")
        return 0

    elif cmd == "search":
        parser = argparse.ArgumentParser(
            prog="brain79 search",
            description="Search documentation articles by text keywords.",
        )
        parser.add_argument("query", help="Search terms or keywords")
        parsed = parser.parse_args(sub_args)
        from brain79.core.wiki import search_articles

        results = search_articles(parsed.query)
        if not results:
            _write_stdout(f"No articles found matching '{parsed.query}'.")
        else:
            lines = [f"Found {len(results)} article(s) matching '{parsed.query}':\n"]
            for r in results:
                lines.append(f"- {r['path']}")
                if r["excerpt"]:
                    lines.append(f"  > {r['excerpt']}")
            _write_stdout("\n".join(lines))
        return 0

    elif cmd == "ingest":
        parser = argparse.ArgumentParser(
            prog="brain79 ingest",
            description="Save raw notes, transcripts, or logs from a session into _raw/sessions/.",
        )
        sum_group = parser.add_mutually_exclusive_group(required=True)
        sum_group.add_argument(
            "--session-summary-file",
            "--summary-file",
            dest="summary_file",
            help="Path to session summary or transcript file",
        )
        sum_group.add_argument(
            "--session-summary-stdin",
            "--summary-stdin",
            dest="summary_stdin",
            action="store_true",
            help="Read session summary or transcript from stdin",
        )
        inst_group = parser.add_mutually_exclusive_group(required=False)
        inst_group.add_argument(
            "--instructions-file", help="Path to optional instructions file"
        )
        inst_group.add_argument(
            "--instructions-stdin",
            action="store_true",
            help="Read optional instructions from stdin",
        )
        parsed = parser.parse_args(sub_args)
        session_summary = read_input_field(
            parsed.summary_file, parsed.summary_stdin, "session_summary"
        )
        instructions = (
            read_input_field(
                parsed.instructions_file, parsed.instructions_stdin, "instructions"
            )
            or None
        )
        from brain79.core.wiki import save_raw_session

        saved_path = save_raw_session(session_summary, instructions)
        _write_stdout(saved_path)
        return 0

    elif cmd == "handoff-write":
        parser = argparse.ArgumentParser(
            prog="brain79 handoff-write",
            description="Write an immutable session handoff record to preserve context for the next session.",
        )
        parser.add_argument(
            "--session-type",
            required=True,
            help="Session type (e.g., feature, bugfix, research, brainstorming, work, writing, analysis)",
        )
        parser.add_argument(
            "--previous-handoff-ref",
            default="none",
            help="Reference or filename of previous handoff (default: none)",
        )
        sum_group = parser.add_mutually_exclusive_group(required=True)
        sum_group.add_argument("--summary-file", help="Path to handoff summary file")
        sum_group.add_argument(
            "--summary-stdin", action="store_true", help="Read handoff summary from stdin"
        )
        parser.add_argument(
            "--completed-work",
            nargs="*",
            action="extend",
            default=[],
            help="List of completed work items",
        )
        parser.add_argument(
            "--pending-work",
            nargs="*",
            action="extend",
            default=[],
            help="List of pending work items",
        )
        parser.add_argument(
            "--knowledge-pending-promotion",
            nargs="*",
            action="extend",
            default=[],
            help="List of knowledge insights to promote to permanent articles",
        )
        parser.add_argument(
            "--resources",
            nargs="*",
            action="extend",
            default=[],
            help="Relevant file paths or references",
        )
        parser.add_argument(
            "--gotchas",
            nargs="*",
            action="extend",
            default=[],
            help="Known caveats, warnings, or constraints discovered during the session",
        )
        parser.add_argument(
            "--decisions",
            nargs="*",
            action="extend",
            default=[],
            help="List of decisions made (alias merged into completed_work)",
        )
        parser.add_argument(
            "--next-steps",
            nargs="*",
            action="extend",
            default=[],
            help="List of next steps (alias merged into pending_work)",
        )
        parser.add_argument(
            "--open-questions",
            nargs="*",
            action="extend",
            default=[],
            help="List of open questions (alias merged into gotchas)",
        )
        parser.add_argument(
            "--decisions-made",
            nargs="*",
            action="extend",
            default=[],
            help="List of decisions made (alias merged into completed_work)",
        )
        parser.add_argument(
            "--open-issues",
            nargs="*",
            action="extend",
            default=[],
            help="List of open issues (alias merged into gotchas)",
        )
        parser.add_argument(
            "--resolved-issues",
            nargs="*",
            action="extend",
            default=[],
            help="List of resolved issues (alias merged into completed_work)",
        )
        parser.add_argument(
            "--files-modified",
            nargs="*",
            action="extend",
            default=[],
            help="List of modified files (alias merged into resources)",
        )
        parser.add_argument(
            "--open-loops",
            nargs="*",
            action="extend",
            default=[],
            help="List of open loops (alias merged into pending_work)",
        )
        parser.add_argument(
            "--action-items",
            nargs="*",
            action="extend",
            default=[],
            help="List of action items (alias merged into pending_work)",
        )
        parser.add_argument(
            "--todo",
            nargs="*",
            action="extend",
            default=[],
            help="List of todo items (alias merged into pending_work)",
        )
        parser.add_argument(
            "--risks-and-blockers",
            nargs="*",
            action="extend",
            default=[],
            help="List of risks and blockers (alias merged into gotchas)",
        )
        parser.add_argument(
            "--blockers",
            nargs="*",
            action="extend",
            default=[],
            help="List of blockers (alias merged into gotchas)",
        )
        parser.add_argument(
            "--risks",
            nargs="*",
            action="extend",
            default=[],
            help="List of risks (alias merged into gotchas)",
        )
        parser.add_argument(
            "--key-decisions",
            nargs="*",
            action="extend",
            default=[],
            help="List of key decisions (alias merged into completed_work)",
        )
        parser.add_argument(
            "--findings",
            nargs="*",
            action="extend",
            default=[],
            help="List of research findings (alias merged into completed_work)",
        )
        boot_group = parser.add_mutually_exclusive_group(required=True)
        boot_group.add_argument(
            "--boot-instruction-file",
            "--boot-instructions-file",
            help="Path to startup instruction file for next session",
        )
        boot_group.add_argument(
            "--boot-instruction-stdin",
            "--boot-instructions-stdin",
            action="store_true",
            help="Read startup instruction from stdin",
        )
        dev_group = parser.add_mutually_exclusive_group(required=False)
        dev_group.add_argument(
            "--wiki-deviation-justification-file",
            help="Optional justification file if wiki updates deviated from convention",
        )
        dev_group.add_argument(
            "--wiki-deviation-justification-stdin",
            action="store_true",
            help="Read wiki deviation justification from stdin",
        )
        parsed = parser.parse_args(sub_args)

        summary = read_input_field(
            parsed.summary_file, parsed.summary_stdin, "summary"
        )
        boot_instruction = read_input_field(
            parsed.boot_instruction_file,
            parsed.boot_instruction_stdin,
            "boot_instruction",
        )
        wiki_dev = read_input_field(
            parsed.wiki_deviation_justification_file,
            parsed.wiki_deviation_justification_stdin,
            "wiki_deviation_justification",
        )

        from brain79.core.handoff import write_handoff

        rel_path = write_handoff(
            session_type=parsed.session_type,
            previous_handoff_ref=parsed.previous_handoff_ref,
            summary=summary,
            completed_work=parsed.completed_work,
            pending_work=parsed.pending_work,
            knowledge_pending_promotion=parsed.knowledge_pending_promotion,
            resources=parsed.resources,
            gotchas=parsed.gotchas,
            boot_instruction=boot_instruction,
            wiki_deviation_justification=wiki_dev,
            decisions=parsed.decisions,
            next_steps=parsed.next_steps,
            open_questions=parsed.open_questions,
            decisions_made=parsed.decisions_made,
            open_issues=parsed.open_issues,
            resolved_issues=parsed.resolved_issues,
            files_modified=parsed.files_modified,
            open_loops=parsed.open_loops,
            action_items=parsed.action_items,
            todo=parsed.todo,
            risks_and_blockers=parsed.risks_and_blockers,
            blockers=parsed.blockers,
            risks=parsed.risks,
            key_decisions=parsed.key_decisions,
            findings=parsed.findings,
        )
        _write_stdout(rel_path)
        return 0

    elif cmd == "handoff-read":
        parser = argparse.ArgumentParser(
            prog="brain79 handoff-read",
            description="Read a session handoff record to resume context.",
        )
        parser.add_argument(
            "handoff_ref",
            nargs="?",
            default="latest",
            help="Handoff identifier or 'latest' (default: latest)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.handoff import read_handoff

        content, _ = read_handoff(parsed.handoff_ref)
        _write_stdout(content)
        return 0

    elif cmd == "lint":
        parser = argparse.ArgumentParser(
            prog="brain79 lint",
            description="Check wiki health: detect broken links, missing metadata, and structure violations.",
        )
        parser.add_argument(
            "--suggest-extract",
            action="store_true",
            help="Suggest content from INDEX.md that should be extracted into dedicated articles",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with non-zero code on CRITICAL (and on WARNING under strict enforcement)",
        )
        parser.add_argument(
            "--fail-on-warnings",
            action="store_true",
            default=False,
            help="Exit with non-zero code on WARNING under any enforcement tier",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format ('text' for human reading or 'json' for machine parsing)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.config import get_wiki_root
        from brain79.core.lint import lint_wiki
        from brain79.core.lint_organizational import (
            generate_extraction_suggestions,
            lint_organizational,
        )

        wiki_root = get_wiki_root()

        if parsed.suggest_extract:
            _write_stdout(generate_extraction_suggestions(wiki_root))
            return 0

        report = lint_wiki()

        if parsed.format == "json":
            org_issues = lint_organizational(wiki_root)
            issues_data = [
                {
                    "rule": i.rule,
                    "path": i.path,
                    "line": i.line,
                    "severity": i.severity,
                    "message": i.message,
                    "actionable": i.actionable,
                }
                for i in org_issues
            ]
            _write_stdout(json.dumps({"issues": issues_data, "report": report}, indent=2))
        else:
            _write_stdout(report)

        if parsed.strict or parsed.fail_on_warnings:
            from brain79.core.frontmatter import load_active_schema

            tier = load_active_schema(wiki_root).enforcement
            if "[Status: CRITICAL]" in report:
                return 1
            if "[Status: WARNING]" in report and (tier == "strict" or parsed.fail_on_warnings):
                return 1

        return 0

    elif cmd == "context":
        parser = argparse.ArgumentParser(
            prog="brain79 context",
            description="Search for knowledge articles and decisions relevant to a specific task and paths.",
        )
        parser.add_argument("task", help="Task or topic description")
        parser.add_argument(
            "--top-n", type=int, default=3, help="Maximum number of relevant articles to return (default: 3)"
        )
        parser.add_argument(
            "--paths",
            nargs="*",
            default=None,
            help="Workspace file paths being inspected or modified",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.context import get_context

        _write_stdout(
            get_context(
                task=parsed.task,
                top_n=parsed.top_n,
                paths=parsed.paths,
            )
        )
        return 0

    elif cmd == "bootstrap":
        parser = argparse.ArgumentParser(
            prog="brain79 bootstrap",
            description="Analyze an existing project and generate a scan manifest with seed templates.",
        )
        parser.add_argument(
            "--scope", default=None, help="Optional comma-separated relative paths to analyze"
        )
        parser.add_argument(
            "--force", action="store_true", help="Force re-run bootstrap even if already initialized"
        )
        parser.add_argument(
            "--auto-map",
            action="store_true",
            default=False,
            help="Detect module boundaries and emit zero-overlap applies_to governance proposals",
        )
        parser.add_argument(
            "--max-modules",
            type=int,
            default=12,
            help="Maximum number of auto-mapped module proposals to emit (default: 12)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.bootstrap import run_bootstrap

        res = run_bootstrap(
            scope=parsed.scope,
            force=parsed.force,
            auto_map=parsed.auto_map,
            max_modules=parsed.max_modules,
        )
        if res.startswith("[--]"):
            sys.stderr.write(res + "\n")
            return 1
        _write_stdout(res)
        return 0

    elif cmd == "navigate":
        parser = argparse.ArgumentParser(
            prog="brain79 navigate",
            description="Display or regenerate the automated table of contents in INDEX.md.",
        )
        parser.add_argument(
            "--regenerate",
            action="store_true",
            help="Regenerate Quick navigation table in INDEX.md from registry",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Rebuild .navigation_registry.json from Markdown files on disk before rendering",
        )
        parser.add_argument(
            "--merge-driver",
            nargs=3,
            metavar=("BASE", "OURS", "THEIRS"),
            default=None,
            help="Run deterministic 3-way INDEX.md Git merge driver on BASE OURS THEIRS files",
        )
        parsed = parser.parse_args(sub_args)
        if parsed.merge_driver is not None:
            from pathlib import Path
            from brain79.core.navigation import merge_index_files

            base_p, ours_p, theirs_p = (Path(p) for p in parsed.merge_driver)
            if not (base_p.is_file() and ours_p.is_file() and theirs_p.is_file()):
                sys.stderr.write("Error: --merge-driver requires three existing input files (BASE OURS THEIRS).\n")
                return 2
            wiki_root_opt: Path | None = None
            try:
                from brain79.config import get_wiki_root

                candidate_w = get_wiki_root()
                if candidate_w.is_dir():
                    wiki_root_opt = candidate_w
            except Exception:
                wiki_root_opt = None
            return merge_index_files(base_p, ours_p, theirs_p, wiki_root=wiki_root_opt)

        from brain79.config import get_wiki_root
        from brain79.core.navigation import (
            generate_quick_navigation,
            rebuild_navigation_registry,
            regenerate_index_navigation,
        )

        wiki_root = get_wiki_root()
        if parsed.regenerate:
            res = regenerate_index_navigation(wiki_root, rebuild=parsed.rebuild)
            _write_stdout(res)
            return 0
        if parsed.rebuild:
            rebuild_navigation_registry(wiki_root, persist=True)
        _write_stdout(generate_quick_navigation(wiki_root))
        return 0

    elif cmd == "migrate":
        parser = argparse.ArgumentParser(
            prog="brain79 migrate",
            description="Upgrade older documentation files to comply with the active schema.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Preview changes without modifying files (default: True)",
        )
        parser.add_argument(
            "--apply",
            action="store_false",
            dest="dry_run",
            help="Apply changes to files (destructive, requires explicit flag)",
        )
        parser.add_argument(
            "--suggest-relocations",
            action="store_true",
            help="Suggest recommended folder locations based on inferred document type",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.config import get_wiki_root
        from brain79.core.migration import migrate_wiki, suggest_relocations

        wiki_root = get_wiki_root()
        if parsed.suggest_relocations:
            _write_stdout(suggest_relocations(wiki_root))
            return 0
        report = migrate_wiki(wiki_root, dry_run=parsed.dry_run)
        _write_stdout(report)
        return 0

    elif cmd == "orient":
        parser = argparse.ArgumentParser(
            prog="brain79 orient",
            description="Provide orientation for a task: loads index, latest handoff, and relevant articles.",
        )
        parser.add_argument(
            "--task",
            default=None,
            help="Goal, question, or task description",
        )
        parser.add_argument(
            "--paths",
            nargs="*",
            default=None,
            help="Workspace file paths being inspected or modified",
        )
        parser.add_argument(
            "--max-articles",
            type=int,
            default=4,
            help="Maximum number of governing articles to inline (default: 4)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.orient import orient

        report = orient(
            task=parsed.task,
            paths=parsed.paths,
            max_articles=parsed.max_articles,
        )
        _write_stdout(report)
        return 0

    elif cmd == "handoff-purge":
        parser = argparse.ArgumentParser(
            prog="brain79 handoff-purge",
            description="Remove temporary session handoffs while preserving permanent wiki articles.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Preview handoffs that would be deleted without modifying files (default: True)",
        )
        parser.add_argument(
            "--apply",
            action="store_false",
            dest="dry_run",
            help="Actually delete files (destructive, requires explicit flag)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.config import get_wiki_root
        from brain79.core.handoff import purge_handoffs

        wiki_root = get_wiki_root()
        _write_stdout(purge_handoffs(wiki_root, apply=not parsed.dry_run))
        return 0

    elif cmd == "session-commit":
        parser = argparse.ArgumentParser(
            prog="brain79 session-commit",
            description="Finalize a session: commit raw logs, article updates, and handoff in one step.",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--file", help="Path to JSON file containing session commit payload")
        group.add_argument("--stdin", action="store_true", help="Read JSON session commit payload from stdin")
        parser.add_argument(
            "--force-validation-skip",
            action="store_true",
            help="Bypass frontmatter validation during writes/edits",
        )
        parsed = parser.parse_args(sub_args)

        from brain79.config import get_wiki_root
        from brain79.core.session_commit import commit_session

        raw_json = read_input_field(parsed.file, parsed.stdin, "session_commit_payload")
        payload_data = json.loads(raw_json)
        if not isinstance(payload_data, dict):
            raise ValueError("session-commit input must be a JSON object.")

        receipt = commit_session(
            payload_data,
            wiki_root=get_wiki_root(),
            force_validation_skip=parsed.force_validation_skip,
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
        _write_stdout("\n".join(lines))
        return 0

    elif cmd == "update-project":
        parser = argparse.ArgumentParser(
            prog="brain79 update-project",
            description="Non-destructively upgrade project templates, schemas, and multi-harness registrations.",
        )
        parser.add_argument(
            "--project-root",
            default=None,
            metavar="PATH",
            help="Project root directory (default: current directory)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate updates without modifying files on disk",
        )
        parser.add_argument(
            "--commit-transition",
            action="store_true",
            default=False,
            help="Write a fresh maintenance handoff after reconditioning project",
        )
        parser.add_argument(
            "--include-desktop",
            action="store_true",
            default=False,
            help="Also configure host desktop application configs (Claude Desktop, Windsurf)",
        )
        parser.add_argument(
            "--install-lifecycle-hooks",
            "--lifecycle-hooks",
            dest="install_lifecycle_hooks",
            action="store_true",
            default=False,
            help="Install or sync opt-in native lifecycle hooks for Claude Code, Antigravity, and Cursor",
        )
        parsed = parser.parse_args(sub_args)
        from pathlib import Path
        from brain79.config import get_project_root
        from brain79.core.init_project import update_project as run_update_project

        target_root = (
            Path(parsed.project_root).resolve()
            if parsed.project_root
            else get_project_root()
        )
        up_res = run_update_project(
            target_root,
            dry_run=parsed.dry_run,
            commit_transition=parsed.commit_transition,
            include_desktop=parsed.include_desktop,
            install_lifecycle_hooks=parsed.install_lifecycle_hooks,
        )
        lines = [
            f"# Brain-79 Project Upgrade ({'DRY RUN' if up_res.get('dry_run') else 'APPLIED'})",
            f"- **Status**: {up_res.get('status', 'ok')}",
            f"- **AGENTS.md updated**: {up_res.get('manifest_updated')}",
            f"- **SCHEMA.md updated**: {up_res.get('schema_updated')}",
            f"- **MCP configurations**: {', '.join(up_res.get('mcp_configs', [])) if up_res.get('mcp_configs') else 'none'}",
            f"- **Git hook**: {up_res.get('git_hook')}",
        ]
        if up_res.get("lifecycle_hooks"):
            lines.append(f"- **Lifecycle hooks**: {', '.join(up_res['lifecycle_hooks'])}")
        if up_res.get("transition_handoff"):
            lines.append(f"- **Transition handoff**: `{up_res['transition_handoff']}`")
        if up_res.get("migration_report"):
            lines.append("")
            lines.append(str(up_res["migration_report"]))
        _write_stdout("\n".join(lines))
        return 0

    elif cmd == "doctor":
        parser = argparse.ArgumentParser(
            prog="brain79 doctor",
            description="Run 7-point operational diagnostic checks and optionally auto-repair defects.",
        )
        parser.add_argument(
            "--project-root",
            default=None,
            metavar="PATH",
            help="Project root directory (default: current directory)",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            default=False,
            help="Automatically repair discovered defects and skew",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Bypass git safety guard during --fix even if working tree is dirty",
        )
        parser.add_argument(
            "--include-desktop",
            action="store_true",
            default=False,
            help="Include desktop application configurations during --fix",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format: 'text' (default) or 'json'",
        )
        parsed = parser.parse_args(sub_args)
        from pathlib import Path
        from brain79.config import get_project_root, get_wiki_root
        from brain79.core.doctor import run_doctor

        target_root = (
            Path(parsed.project_root).resolve()
            if parsed.project_root
            else get_project_root()
        )
        wiki_root = target_root / ".brain-79" if parsed.project_root else get_wiki_root()
        doc_report = run_doctor(
            project_root=target_root,
            wiki_root=wiki_root,
            fix=parsed.fix,
            force=parsed.force,
            include_desktop=parsed.include_desktop,
            format=parsed.format,
        )
        if parsed.format == "json":
            _write_stdout(json.dumps(doc_report.to_dict(), indent=2))
        else:
            _write_stdout(doc_report.format_text())
        return int(doc_report.exit_code)

    elif cmd == "ci-check":
        parser = argparse.ArgumentParser(
            prog="brain79 ci-check",
            description=(
                "Run read-only CI governance gate (drift, lint, diff impact, ADR surfacing)\n"
                "or execute passive IDE/CLI lifecycle hooks (--lifecycle-hook)."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "--project-root",
            default=None,
            metavar="PATH",
            help="Project root directory (default: current directory)",
        )
        parser.add_argument(
            "--base",
            default=None,
            metavar="REF",
            help="Optional base Git ref for PR diff comparison",
        )
        parser.add_argument(
            "--head",
            default="HEAD",
            metavar="REF",
            help="Head Git ref for PR diff comparison (default: HEAD)",
        )
        parser.add_argument(
            "--enforcement",
            choices=["strict", "balanced", "advisory", "schema"],
            default="strict",
            help="Effective enforcement tier (default: strict)",
        )
        parser.add_argument(
            "--fail-on-warnings",
            action="store_true",
            default=False,
            help="Fail with exit code 1 on warnings under any enforcement tier",
        )
        parser.add_argument(
            "--format",
            choices=["markdown", "text", "json"],
            default="markdown",
            help="Output format on stdout: markdown (default), text, or json",
        )
        parser.add_argument(
            "--summary-file",
            default=None,
            metavar="PATH",
            help="Optional file path to write the Markdown summary",
        )
        parser.add_argument(
            "--write-step-summary",
            action="store_true",
            default=False,
            help="Append the Markdown summary to $GITHUB_STEP_SUMMARY when set",
        )
        parser.add_argument(
            "--lifecycle-hook",
            choices=["session-start", "stop"],
            default=None,
            help="Run passive lifecycle hook handler instead of CI report (always exits 0)",
        )
        parser.add_argument(
            "--client",
            choices=["auto", "claude", "agy", "cursor"],
            default="auto",
            help="Target client protocol for --lifecycle-hook (default: auto)",
        )
        parsed = parser.parse_args(sub_args)
        from pathlib import Path
        from brain79.config import get_explicit_project_root
        from brain79.core.ci_check import run_ci_check, run_lifecycle_hook
        from brain79.core.git_ops import GitError, GitTimeoutError, NotAGitRepoError

        p_root = Path(parsed.project_root).resolve() if parsed.project_root else get_explicit_project_root()

        if parsed.lifecycle_hook is not None:
            hook_result = run_lifecycle_hook(
                parsed.lifecycle_hook,
                client=parsed.client,
                project_root=p_root,
            )
            sys.stdout.write(json.dumps(hook_result, ensure_ascii=True) + "\n")
            sys.stdout.flush()
            return 0

        w_root = (p_root / ".brain-79") if p_root is not None else None
        summary_path = Path(parsed.summary_file) if parsed.summary_file else None
        try:
            ci_report = run_ci_check(
                project_root=p_root,
                wiki_root=w_root,
                base_ref=parsed.base,
                head_ref=parsed.head,
                enforcement=parsed.enforcement,
                fail_on_warnings=parsed.fail_on_warnings,
                summary_file=summary_path,
                write_step_summary=parsed.write_step_summary,
            )
        except GitTimeoutError as exc:
            sys.stderr.write(f"Error: Git operation timed out during ci-check: {exc}\n")
            return 3
        except (ValueError, NotAGitRepoError, GitError) as exc:
            sys.stderr.write(f"Error: Invalid Git reference or repository state: {exc}\n")
            return 2
        except FileNotFoundError as exc:
            sys.stderr.write(f"Error: Summary file path not found: {exc}\n")
            return 2
        except (IsADirectoryError, OSError) as exc:
            sys.stderr.write(f"Error: Filesystem error during ci-check: {exc}\n")
            return 3

        if parsed.format == "json":
            _write_stdout(json.dumps(ci_report.to_dict(), indent=2))
        else:
            _write_stdout(ci_report.markdown_summary)
        return int(ci_report.exit_code)

    elif cmd == "stats":
        parser = argparse.ArgumentParser(
            prog="brain79 stats",
            description="Show read-only context budget, wiki inventory, coverage, and AST guard statistics.",
        )
        parser.add_argument(
            "--format",
            choices=("text", "json"),
            default="text",
            help="Output format: text (default) or json",
        )
        parser.add_argument(
            "--task",
            default=None,
            help="Optional task description passed to orient() budget simulation",
        )
        parser.add_argument(
            "--paths",
            nargs="*",
            default=None,
            help="Optional workspace file paths passed to orient() budget simulation",
        )
        parser.add_argument(
            "--max-articles",
            type=_positive_int,
            default=4,
            help="Maximum number of governing articles to inline in orient() simulation (default: 4)",
        )
        parsed = parser.parse_args(sub_args)

        from brain79.config import get_explicit_project_root
        from brain79.core.stats import compute_stats

        norm_paths: list[str] | None = None
        if parsed.paths is not None:
            norm_paths = [
                tok.strip()
                for raw in parsed.paths
                for tok in raw.split(",")
                if tok.strip()
            ]

        p_root = get_explicit_project_root()
        w_root = (p_root / ".brain-79") if p_root is not None else None
        stats_report = compute_stats(
            project_root=p_root,
            wiki_root=w_root,
            task=parsed.task,
            paths=norm_paths,
            max_articles=parsed.max_articles,
        )
        if parsed.format == "json":
            _write_stdout(json.dumps(stats_report.to_dict(), indent=2))
        else:
            _write_stdout(stats_report.format_text())
        return 0

    raise ValueError(f"Unknown command: {cmd}")



def run_cli(cmd: str, sub_args: Sequence[str], debug: bool = False) -> int:
    """Run CLI subcommand with exception handling and exit code mapping."""
    try:
        return dispatch_cmd(cmd, sub_args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        return code
    except KeyboardInterrupt:
        if debug:
            traceback.print_exc()
        else:
            sys.stderr.write("Operation cancelled by user.\n")
        return 130
    except Exception as exc:
        code = map_exception_to_exit_code(exc)
        if debug:
            traceback.print_exc()
        else:
            if hasattr(exc, "format_user_message"):
                sys.stderr.write(f"Error: {exc.format_user_message()}\n")
            else:
                sys.stderr.write(f"Error: {exc}\n")
        return code

