from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import uuid

from brain79.config import get_project_root, get_wiki_root
from brain79.core.drift import (
    WorkspaceIndex,
    compute_applies_to_manifest,
    load_drift_manifest,
    save_drift_manifest,
)
from brain79.core.frontmatter import (
    INACTIVE_STATUSES,
    ActiveSchema,
    LOCATION_TO_TYPE,
    dump_frontmatter,
    load_active_schema,
    normalize_backlink_footer,
    normalize_bullet_colons,
    parse_frontmatter,
    sanitize_summary,
)
from brain79.core.locks import (
    atomic_replace_with_retry,
    cleanup_legacy_inline_locks,
)
from brain79.core.validation import (
    MAX_ARTICLE_BYTES,
    MAX_ARTICLE_LINES,
    check_missing_sections,
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

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError:
            continue
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
    p_root = (wiki_root.parent or get_project_root()).resolve()
    changes: list[str] = []
    skipped: list[str] = []

    ws_index = WorkspaceIndex.build(p_root, wiki_root)
    manifest_data = load_drift_manifest(wiki_root)
    manifest_articles: dict[str, Any] = manifest_data.setdefault("articles", {})
    manifest_purged = False

    # Purge deleted articles from manifest
    for p_art in list(manifest_articles.keys()):
        if not (wiki_root / p_art).is_file():
            del manifest_articles[p_art]
            manifest_purged = True

    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        rel_str = rel.as_posix()

        if rel_str in ("INDEX.md", "SCHEMA.md"):
            skipped.append(f"{rel_str}: protected")
            continue
        if rel.parts and rel.parts[0] in ("_raw", ".locks"):
            skipped.append(f"{rel_str}: in _raw/ or .locks/")
            continue

        try:
            content = md_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError:
            skipped.append(f"{rel_str}: invalid UTF-8 encoding")
            continue
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime, UTC).strftime("%Y-%m-%d")
        inferred_type = _infer_type_from_location(rel, schema=schema)

        if content.startswith("---\n"):
            try:
                meta, body = parse_frontmatter(content)
            except Exception:
                skipped.append(f"{rel_str}: malformed frontmatter")
                continue
        else:
            meta = {}
            body = content

        target_type = (meta.get("type") if meta else None) or inferred_type
        if target_type is None:
            skipped.append(f"{rel_str}: cannot infer type from location")
            continue

        meta = meta or {}

        # Paso A: Campos requeridos por tipo
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

        if target_type not in ("navigation", "handoff", "raw_session", "raw_commit"):
            if "summary" not in meta or not meta["summary"]:
                from brain79.core.navigation import extract_title_and_summary

                _, extracted_s = extract_title_and_summary(body)
                meta["summary"] = sanitize_summary(extracted_s or f"Legacy migrated {target_type}")
            else:
                meta["summary"] = sanitize_summary(str(meta["summary"]))

        # Paso B: Exención semántica de secciones y tamaño (Tier 2)
        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        is_active = status not in INACTIVE_STATUSES and stability not in INACTIVE_STATUSES
        if is_active:
            missing_h2 = check_missing_sections(body, target_type, schema=schema)
            top_dir = rel.parts[0] if len(rel.parts) > 1 else ""
            atomicity_exempt = {"decisions", "changelog", "handoffs", "_raw", ".locks"}
            is_oversized = False
            if top_dir not in atomicity_exempt:
                cand_content = dump_frontmatter(meta, body)
                if (
                    len(cand_content.splitlines()) > MAX_ARTICLE_LINES
                    or len(cand_content.encode("utf-8")) > MAX_ARTICLE_BYTES
                ):
                    is_oversized = True
            if missing_h2 or is_oversized:
                if target_type == "architecture" or "stability" in meta:
                    meta["stability"] = "legacy"
                else:
                    meta["status"] = "legacy"

        # Paso C: Normalización mecánica del cuerpo (Tier 1)
        body = normalize_backlink_footer(body, rel_str)
        body = normalize_bullet_colons(body)

        # Paso D: Sembrado Merkle de applies_to
        applies = meta.get("applies_to")
        manifest_missing = False
        if applies:
            patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
            m_dig, cnt, tgts = compute_applies_to_manifest(
                patterns, p_root, wiki_root, exclude_self_path=rel_str, workspace_index=ws_index
            )
            if m_dig:
                if meta.get("applies_to_digest") != m_dig or meta.get("applies_to_count") != cnt:
                    meta["applies_to_digest"] = m_dig
                    meta["applies_to_count"] = cnt
                if rel_str not in manifest_articles or manifest_articles[rel_str].get("digest") != m_dig:
                    manifest_articles[rel_str] = {"digest": m_dig, "count": cnt, "targets": tgts}
                    manifest_missing = True

        new_content = dump_frontmatter(meta, body)
        content_changed = new_content != content

        if content_changed or manifest_missing:
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
        else:
            skipped.append(f"{rel_str}: up-to-date")

    if not dry_run:
        if changes or manifest_purged:
            save_drift_manifest(wiki_root, manifest_data)
        cleanup_legacy_inline_locks(wiki_root)
        try:
            from brain79.core.navigation import regenerate_index_navigation
            regenerate_index_navigation(wiki_root)
        except Exception:
            pass

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
