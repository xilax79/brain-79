from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import uuid

from brain79.core.frontmatter import (
    ActiveSchema,
    LOCATION_TO_TYPE,
    load_active_schema,
    normalize_backlink_footer,
    parse_frontmatter,
)
from brain79.core.locks import (
    atomic_replace_with_retry,
    cleanup_legacy_inline_locks,
)

_TYPE_DEFAULTS: dict[str, dict[str, str]] = {
    "decision": {
        "status": "legacy",
        "date": "<file mtime or today>",
        "deciders": "[migrated]",
    },
    "feature": {
        "status": "legacy",
        "version": "unknown",
    },
    "architecture": {
        "stability": "legacy",
    },
    "topic": {
        "status": "legacy",
    },
    "context": {},
    "log": {
        "date": "<file mtime or today>",
    },
    "changelog": {
        "version": "unknown",
        "date": "<file mtime>",
    },
    "handoff": {
        "session_type": "feature",
        "previous_ref": "none",
    },
    "raw_session": {
        "session_id": "migrated-session",
        "session_type": "feature",
    },
    "raw_commit": {
        "commit_sha": "unknown",
    },
}


def _infer_type_from_location(rel_path: Path, schema: ActiveSchema | None = None) -> str | None:
    """Infer frontmatter type from relative file location using active schema."""
    loc_map = schema.location_to_type if schema else LOCATION_TO_TYPE
    for location_prefix, expected_type in loc_map.items():
        if str(rel_path) == location_prefix or str(rel_path).startswith(location_prefix + "/"):
            return expected_type
    return None


def suggest_relocations(wiki_root: Path) -> str:
    """Suggest directory relocations for articles based on frontmatter type or content inference."""
    schema = load_active_schema(wiki_root)
    suggestions: list[str] = ["# Suggested Article Relocations", ""]

    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()
        if rel_str in ("INDEX.md", "SCHEMA.md") or rel.parts[0] in ("_raw", ".locks"):
            continue

        content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        if content.startswith("---\n"):
            try:
                meta, _ = parse_frontmatter(content)
                declared_type = meta.get("type")
                if declared_type:
                    expected_dirs = [d for d, t in schema.location_to_type.items() if t == declared_type]
                    if expected_dirs and not any(
                        rel_str == d or rel_str.startswith(d + "/") for d in expected_dirs
                    ):
                        suggestions.append(
                            f"- Move `{rel_str}` → `{expected_dirs[0]}/{rel.name}` (type='{declared_type}')"
                        )
            except Exception:
                pass
        else:
            inferred = _infer_type_from_location(rel, schema=schema)
            if inferred is None and len(rel.parts) == 1:
                known_dirs = [f"`{d}/`" for d in schema.location_to_type.keys() if d not in ("INDEX.md", "handoffs", "_raw/sessions", "_raw/commits")]
                suggestions.append(
                    f"- Loose file in root `{rel_str}` → consider moving into {', '.join(known_dirs)}"
                )

    if len(suggestions) == 2:
        suggestions.append("No relocations suggested. Article locations match declared types.")

    return "\n".join(suggestions)


def migrate_wiki(wiki_root: Path, dry_run: bool = False) -> str:
    """Add frontmatter to legacy articles that lack it, defaulting to status=legacy."""
    from brain79.core.navigation import register_article

    schema = load_active_schema(wiki_root)
    changes: list[str] = []
    skipped: list[str] = []

    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()

        if rel_str in ("INDEX.md", "SCHEMA.md"):
            skipped.append(f"{rel_str}: protected")
            continue
        if rel.parts and rel.parts[0] in ("_raw", ".locks"):
            skipped.append(f"{rel_str}: in _raw/ or .locks/")
            continue

        content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime, UTC).strftime("%Y-%m-%d")
        inferred_type = _infer_type_from_location(rel, schema=schema)

        if content.startswith("---\n"):
            try:
                meta, body = parse_frontmatter(content)
                target_type = (meta.get("type") if meta else None) or inferred_type
                needs_summary_repair = bool(
                    target_type
                    and target_type not in ("navigation", "handoff", "raw_session", "raw_commit")
                    and (not meta or "summary" not in meta or not meta["summary"])
                )

                if meta and "type" in meta and not needs_summary_repair:
                    skipped.append(f"{rel_str}: already has valid frontmatter")
                    if not dry_run:
                        try:
                            from brain79.core.navigation import extract_title_and_summary
                            title, summary = extract_title_and_summary(content)
                            sec = rel.parts[0] if len(rel.parts) > 1 else "root"
                            register_article(wiki_root, rel_str, title, summary, sec)
                        except Exception:
                            pass
                    continue

                # Frontmatter exists but is missing 'type' or needs summary repair
                if target_type is None:
                    skipped.append(f"{rel_str}: has incomplete frontmatter but cannot infer type")
                    continue
                meta = meta or {}
                meta["type"] = target_type
                if "last_updated" not in meta:
                    meta["last_updated"] = today

                defaults = _TYPE_DEFAULTS.get(target_type, {})
                for key, default_template in defaults.items():
                    if key not in meta:
                        if default_template == "<file mtime>":
                            val = file_mtime
                        elif default_template == "<today>":
                            val = today
                        elif default_template == "<file mtime or today>":
                            val = file_mtime or today
                        else:
                            val = default_template
                        meta[key] = val

                if needs_summary_repair:
                    from brain79.core.frontmatter import sanitize_summary
                    from brain79.core.navigation import extract_title_and_summary

                    _, extracted_s = extract_title_and_summary(body)
                    meta["summary"] = sanitize_summary(extracted_s or f"Legacy migrated {target_type}")

                from brain79.core.frontmatter import dump_frontmatter
                new_content = dump_frontmatter(meta, body)
            except Exception:
                skipped.append(f"{rel_str}: malformed frontmatter")
                continue
        else:
            if inferred_type is None:
                skipped.append(f"{rel_str}: cannot infer type from location")
                continue

            lines = ["---", f"type: {inferred_type}", f"last_updated: {today}"]

            defaults = _TYPE_DEFAULTS.get(inferred_type, {})
            for key, default_template in defaults.items():
                if default_template == "<file mtime>":
                    value = file_mtime
                elif default_template == "<today>":
                    value = today
                elif default_template == "<file mtime or today>":
                    value = file_mtime or today
                else:
                    value = default_template
                lines.append(f"{key}: {value}")

            # Auto-populate summary if missing
            try:
                from brain79.core.frontmatter import dump_frontmatter, sanitize_summary
                from brain79.core.navigation import extract_title_and_summary
                _, inferred_summary = extract_title_and_summary(content)
                meta_dict: dict[str, Any] = {"type": inferred_type, "last_updated": today}
                for key, default_template in defaults.items():
                    if default_template == "<file mtime>":
                        val = file_mtime
                    elif default_template == "<today>":
                        val = today
                    elif default_template == "<file mtime or today>":
                        val = file_mtime or today
                    else:
                        val = default_template
                    meta_dict[key] = val
                clean_s = sanitize_summary(inferred_summary) if inferred_summary else f"Legacy migrated {inferred_type}"
                meta_dict["summary"] = clean_s
                body_norm = normalize_backlink_footer(content, rel_str)
                new_content = dump_frontmatter(meta_dict, body_norm)
            except Exception:
                meta_dict = {"type": inferred_type, "last_updated": today, "summary": f"Legacy migrated {inferred_type}"}
                body_norm = normalize_backlink_footer(content, rel_str)
                new_content = dump_frontmatter(meta_dict, body_norm)

        if not dry_run:
            tmp_path = md_file.with_suffix(f".tmp.{uuid.uuid4().hex}")
            try:
                tmp_path.write_text(new_content, encoding="utf-8", newline="\n")
                atomic_replace_with_retry(tmp_path, md_file)
                try:
                    from brain79.core.navigation import extract_title_and_summary
                    title, summary = extract_title_and_summary(new_content)
                    sec = rel.parts[0] if len(rel.parts) > 1 else "root"
                    register_article(wiki_root, rel_str, title, summary, sec)
                except Exception:
                    pass
            except Exception:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise

        changes.append(rel_str)

    if not dry_run:
        cleanup_legacy_inline_locks(wiki_root)

    report_lines = [
        f"# Migration Report ({'DRY RUN' if dry_run else 'APPLIED'})",
        "",
        f"## Changes ({len(changes)})",
    ]
    for change in changes:
        report_lines.append(f"- {change}")
    report_lines.append("")
    report_lines.append(f"## Skipped ({len(skipped)})")
    for skip in skipped:
        report_lines.append(f"- {skip}")
    return "\n".join(report_lines)
