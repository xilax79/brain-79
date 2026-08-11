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
    "write",
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
        parser = argparse.ArgumentParser(prog="brain79 init")
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
        parsed = parser.parse_args(sub_args)
        from pathlib import Path
        from brain79.config import get_project_root
        from brain79.core.init_project import init_project

        target_root = (
            Path(parsed.project_root).resolve()
            if parsed.project_root
            else get_project_root()
        )
        init_project(target_root, install_git_hooks_flag=parsed.install_git_hooks)
        return 0


    elif cmd == "update":
        parser = argparse.ArgumentParser(prog="brain79 update")
        parser.add_argument(
            "--branch",
            default=None,
            help="Default branch (auto-detected or manually overridden)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.update import update_project

        return update_project(branch_override=parsed.branch)

    elif cmd == "index":
        parser = argparse.ArgumentParser(prog="brain79 index")
        parser.parse_args(sub_args)
        from brain79.core.wiki import get_index

        _write_stdout(get_index())
        return 0

    elif cmd == "read":
        parser = argparse.ArgumentParser(prog="brain79 read")
        parser.add_argument("path", help="Relative path within .brain-79/")
        parsed = parser.parse_args(sub_args)
        from brain79.core.wiki import read_article

        _write_stdout(read_article(parsed.path))
        return 0

    elif cmd == "write":
        parser = argparse.ArgumentParser(prog="brain79 write")
        parser.add_argument("path", help="Relative path within .brain-79/")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--content-file", help="Path to file containing content")
        group.add_argument(
            "--content-stdin",
            action="store_true",
            help="Read content from stdin",
        )
        parser.add_argument(
            "--force-validation-skip",
            "--force-skip",
            action="store_true",
            help="Bypass organizational validation and inject force_validation_skipped metadata",
        )
        parsed = parser.parse_args(sub_args)
        content = read_input_field(parsed.content_file, parsed.content_stdin, "content")
        from brain79.core.wiki import write_article

        write_article(parsed.path, content, force_validation_skip=parsed.force_validation_skip)
        _write_stdout(parsed.path)
        return 0

    elif cmd == "list":
        parser = argparse.ArgumentParser(prog="brain79 list")
        parser.add_argument("--section", default=None, help="Optional section filter")
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
        parser = argparse.ArgumentParser(prog="brain79 search")
        parser.add_argument("query", help="Search query")
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
        parser = argparse.ArgumentParser(prog="brain79 ingest")
        sum_group = parser.add_mutually_exclusive_group(required=True)
        sum_group.add_argument(
            "--session-summary-file",
            "--summary-file",
            dest="summary_file",
            help="Path to session summary file",
        )
        sum_group.add_argument(
            "--session-summary-stdin",
            "--summary-stdin",
            dest="summary_stdin",
            action="store_true",
            help="Read session summary from stdin",
        )
        inst_group = parser.add_mutually_exclusive_group(required=False)
        inst_group.add_argument(
            "--instructions-file", help="Path to instructions file"
        )
        inst_group.add_argument(
            "--instructions-stdin",
            action="store_true",
            help="Read instructions from stdin",
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
        parser = argparse.ArgumentParser(prog="brain79 handoff-write")
        parser.add_argument(
            "--session-type",
            required=True,
            choices=["feature", "bugfix", "research", "brainstorming"],
            help="Session type",
        )
        parser.add_argument(
            "--previous-handoff-ref",
            default="none",
            help="Previous handoff reference",
        )
        sum_group = parser.add_mutually_exclusive_group(required=True)
        sum_group.add_argument("--summary-file", help="Path to summary file")
        sum_group.add_argument(
            "--summary-stdin", action="store_true", help="Read summary from stdin"
        )
        parser.add_argument(
            "--completed-work",
            nargs="*",
            action="extend",
            default=[],
            help="Completed work items",
        )
        parser.add_argument(
            "--pending-work",
            nargs="*",
            action="extend",
            default=[],
            help="Pending work items",
        )
        parser.add_argument(
            "--knowledge-pending-promotion",
            nargs="*",
            action="extend",
            default=[],
            help="Knowledge pending promotion",
        )
        parser.add_argument(
            "--resources",
            nargs="*",
            action="extend",
            default=[],
            help="Resource items",
        )
        parser.add_argument(
            "--gotchas",
            nargs="*",
            action="extend",
            default=[],
            help="Gotcha items",
        )
        boot_group = parser.add_mutually_exclusive_group(required=True)
        boot_group.add_argument(
            "--boot-instruction-file", help="Path to boot instruction file"
        )
        boot_group.add_argument(
            "--boot-instruction-stdin",
            action="store_true",
            help="Read boot instruction from stdin",
        )
        dev_group = parser.add_mutually_exclusive_group(required=False)
        dev_group.add_argument(
            "--wiki-deviation-justification-file",
            help="Path to wiki deviation justification file",
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
        )
        _write_stdout(rel_path)
        return 0

    elif cmd == "handoff-read":
        parser = argparse.ArgumentParser(prog="brain79 handoff-read")
        parser.add_argument(
            "handoff_ref",
            nargs="?",
            default="latest",
            help="Handoff reference (default: latest)",
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.handoff import read_handoff

        content, _ = read_handoff(parsed.handoff_ref)
        _write_stdout(content)
        return 0

    elif cmd == "lint":
        parser = argparse.ArgumentParser(prog="brain79 lint")
        parser.add_argument(
            "--suggest-extract",
            action="store_true",
            help="Show actionable extraction suggestions for INDEX.md",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with non-zero code if any errors or warnings exist",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format (text or json)",
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
        parser = argparse.ArgumentParser(prog="brain79 context")
        parser.add_argument("task", help="Task description")
        parser.add_argument(
            "--top-n", type=int, default=3, help="Maximum number of articles to return"
        )
        parsed = parser.parse_args(sub_args)
        from brain79.core.context import get_context

        _write_stdout(get_context(parsed.task, parsed.top_n))
        return 0

    elif cmd == "bootstrap":
        parser = argparse.ArgumentParser(prog="brain79 bootstrap")
        parser.add_argument(
            "--scope", default=None, help="Optional comma-separated relative paths"
        )
        parser.add_argument(
            "--force", action="store_true", help="Force re-run bootstrap"
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
        parser = argparse.ArgumentParser(prog="brain79 navigate")
        parser.add_argument(
            "--regenerate",
            action="store_true",
            help="Regenerate INDEX.md Quick navigation from registry",
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
        parser = argparse.ArgumentParser(prog="brain79 migrate")
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
            help="Suggest where files should be moved based on type inference",
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
            sys.stderr.write(f"Error: {exc}\n")
        return code

