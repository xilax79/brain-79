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
            "--profile",
            choices=["software", "general"],
            default="software",
            help="Knowledge profile ('software' or 'general', default: software)",
        )
        parsed = parser.parse_args(sub_args)
        from pathlib import Path
        from brain79.config import get_project_root
        from brain79.core.init_project import init_project

        target_root = (
            Path(parsed.project_root).resolve()
            if parsed.project_root
            else get_project_root()
        )
        init_project(
            target_root,
            install_git_hooks_flag=parsed.install_git_hooks,
            profile=parsed.profile,
        )
        return 0


    elif cmd == "update":
        parser = argparse.ArgumentParser(
            prog="brain79 update",
            description="Update project templates and schema to match the current brain-79 version.",
        )
        parser.add_argument(
            "--branch",
            default=None,
            help="Template branch override (auto-detected by default)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.update import update_project

        return update_project(branch_override=parsed.branch)

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
        group.add_argument("--file", help="Path to JSON file containing list of read requests")
        group.add_argument("--stdin", action="store_true", help="Read JSON read requests from stdin")
        parsed = parser.parse_args(sub_args)

        from brain79.core.wiki import read_batch_articles

        raw_json = read_input_field(parsed.file, parsed.stdin, "requests")
        requests_data = json.loads(raw_json)
        if not isinstance(requests_data, list):
            raise ValueError("read-batch input must be a JSON array of request objects.")

        results = read_batch_articles(requests_data)
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
        _write_stdout("\n\n".join(rendered_parts))
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
            help="Exit with non-zero code if any critical errors or warnings exist",
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

        if parsed.strict and ("[Status: CRITICAL]" in report or "[Status: WARNING]" in report):
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
        parsed = parser.parse_args(sub_args)
        from brain79.core.bootstrap import run_bootstrap

        res = run_bootstrap(scope=parsed.scope, force=parsed.force)
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
        parsed = parser.parse_args(sub_args)
        from brain79.config import get_wiki_root
        from brain79.core.navigation import (
            generate_quick_navigation,
            regenerate_index_navigation,
        )

        wiki_root = get_wiki_root()
        if parsed.regenerate:
            res = regenerate_index_navigation(wiki_root)
            _write_stdout(res)
            return 0
        else:
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
        if receipt.get("handoff_path"):
            lines.append(f"- **Session Handoff**: `{receipt['handoff_path']}`")
        lines.append(f"- **Inline Health**: `{receipt.get('health_status', 'ok')}`")
        if receipt.get("warnings"):
            lines.append("\n### Warnings:")
            for w in receipt["warnings"]:
                lines.append(f"- ⚠️ {w}")
        _write_stdout("\n".join(lines))
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

