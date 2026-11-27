from datetime import UTC, datetime
from pathlib import Path
import shutil
import subprocess
from typing import Any

import filelock

from brain79.config import get_wiki_root
from brain79.core.frontmatter import ValidationError
from brain79.core.locks import (
    acquire_wiki_lock,
    atomic_replace_with_retry,
    has_exact_case_path,
    normalize_wiki_rel_path,
)
from brain79.core.validation import validate_article_content


# Directories excluded from article listings (raw sources and locks are not wiki articles)
_EXCLUDED_DIRS = {"_raw", ".locks"}

_RG_PATH: str | None = shutil.which("rg")

_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _safe_resolve(path: str, wiki_root: Path | None = None) -> Path:
    """Resolve a relative wiki path and verify it stays within the wiki root."""
    w_root = (wiki_root or get_wiki_root()).resolve()
    clean_path = normalize_wiki_rel_path(path)

    # Check Windows reserved names and trailing dots/spaces in path components
    for part in Path(clean_path).parts:
        p_obj = Path(part)
        stem = p_obj.stem
        if stem.upper() in _WINDOWS_RESERVED_NAMES or part.upper() in _WINDOWS_RESERVED_NAMES:
            raise ValueError(f"Path '{path}' contains Windows reserved device name '{part}'.")
        if part not in (".", "..") and stem not in (".", ".."):
            if part.endswith(".") or part.endswith(" ") or stem.endswith(".") or stem.endswith(" "):
                raise ValueError(f"Path '{path}' contains forbidden trailing dot or space in '{part}'.")

    target = (w_root / clean_path).resolve()
    if not target.is_relative_to(w_root):
        raise ValueError(f"Path '{path}' resolves outside the wiki directory.")
    return target


def resolve_wiki_path(path: str, wiki_root: Path | None = None) -> Path:
    """Public alias to resolve a relative wiki path safely."""
    return _safe_resolve(path, wiki_root=wiki_root)


def extract_sections_from_markdown(content: str, requested_sections: list[str]) -> str:
    """
    Extract specific ## H2 sections from markdown content while preserving frontmatter and # H1.

    Args:
        content: Raw markdown text (optionally with YAML frontmatter).
        requested_sections: List of section names to extract (case-insensitive substring/equality).

    Returns:
        Projected markdown content containing frontmatter, # H1, and the matched ## H2 sections.
    """
    from brain79.core.frontmatter import parse_frontmatter

    try:
        meta, body = parse_frontmatter(content)
    except Exception:
        meta, body = {}, content
    lines = (body or content).splitlines()

    h1_lines: list[str] = []
    # Key: normalized section title -> list of lines in section (including ## header)
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    in_fence = False
    fence_char: str | None = None

    for line in lines:
        stripped = line.lstrip()
        # Track code fences to avoid splitting on '#' comments or '##' code inside blocks
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = True
                fence_char = stripped[:3]
                if current_title is not None:
                    current_lines.append(line)
                elif not sections:
                    h1_lines.append(line)
                continue

            # Outside code fences, inspect headings
            if line.startswith("# ") and not current_title:
                h1_lines.append(line)
            elif line.startswith("## "):
                if current_title is not None:
                    sections.append((current_title, current_lines))
                current_title = line[3:].strip()
                current_lines = [line]
            else:
                if current_title is not None:
                    current_lines.append(line)
                elif not sections:
                    h1_lines.append(line)
        else:
            # Inside code fence
            if fence_char and stripped.startswith(fence_char):
                in_fence = False
                fence_char = None

            if current_title is not None:
                current_lines.append(line)
            elif not sections:
                h1_lines.append(line)

    if current_title is not None:
        sections.append((current_title, current_lines))

    # Match requested sections
    matched_sections: list[list[str]] = []

    for orig_req in requested_sections:
        req = orig_req.strip().lower()
        if not req:
            continue
        found = False
        for sec_title, sec_lines in sections:
            if req == sec_title.lower() or req in sec_title.lower():
                if sec_lines not in matched_sections:
                    matched_sections.append(sec_lines)
                found = True
        if not found:
            matched_sections.append([f"(No matching sections found for: {orig_req.strip()})"])

    output_parts: list[str] = []

    # Frontmatter
    if meta:
        import yaml

        # Clean YAML serialization
        fm_str = yaml.safe_dump(meta, sort_keys=False).strip()
        output_parts.append(f"---\n{fm_str}\n---")

    # Preamble + H1
    lead_block = "\n".join(h1_lines).strip()
    if lead_block:
        output_parts.append(lead_block)

    # Matched sections
    for sec in matched_sections:
        output_parts.append("\n".join(sec).strip())

    return "\n\n".join(output_parts).strip() + "\n"


def _extract_linked_adrs_hint(wiki_root: Path, content: str, rel_path: str) -> str | None:
    """Extract active governing ADR references from frontmatter and markdown links.

    Filters out:
    - Self-references (if rel_path itself is an ADR).
    - Superseded, rejected, or legacy ADRs.
    """
    # Never append ADR hint to INDEX.md itself
    if rel_path == "INDEX.md":
        return None

    try:
        from brain79.core.navigation import extract_graph_metadata

        graph_meta = extract_graph_metadata(content, rel_path=rel_path)
    except Exception:
        return None

    from brain79.core.frontmatter import parse_frontmatter

    linked_adrs: list[str] = []
    norm_current = rel_path.replace("\\", "/").strip().lstrip("/")

    for ref in graph_meta.get("related", []) + graph_meta.get("outgoing_links", []):
        ref_norm = ref.replace("\\", "/").strip().lstrip("/")
        if ref_norm.startswith("decisions/") and ref_norm.endswith(".md"):
            # Don't self-link if reading the ADR itself
            if ref_norm == norm_current:
                continue

            # Verify ADR is active (not superseded, rejected, or legacy)
            adr_file = wiki_root / ref_norm
            if adr_file.exists() and adr_file.is_file():
                try:
                    adr_meta, _ = parse_frontmatter(adr_file.read_text(encoding="utf-8"))
                    adr_status = adr_meta.get("status", "").lower()
                    if adr_status in ("superseded", "rejected", "legacy", "deprecated"):
                        continue
                except Exception:
                    pass

            if ref_norm not in linked_adrs:
                linked_adrs.append(ref_norm)

    if not linked_adrs:
        return None

    adr_list_str = ", ".join(linked_adrs)
    return f"\n\n---\n💡 Linked ADRs: {adr_list_str}"


def read_article(
    path: str,
    wiki_root: Path | None = None,
    sections: list[str] | None = None,
    include_adr_hints: bool = False,
) -> str:
    """
    Read an article by its relative path within the wiki.

    Args:
        path: Relative path within wiki root.
        wiki_root: Optional wiki root Path override.
        sections: Optional list of ## H2 section names to project.
        include_adr_hints: If True, appends governing active ADR notice footer.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    target = _safe_resolve(path, wiki_root=w_root)
    if not target.exists():
        raise FileNotFoundError(f"Article not found: {path}")
    if not target.is_file():
        raise ValueError(f"Path is not a file: {path}")

    rel_path_str = target.relative_to(w_root).as_posix()
    try:
        raw_content = target.read_text(encoding="utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            rule="invalid_utf8_encoding",
            path=rel_path_str,
            message=f"File contains invalid UTF-8 bytes: {exc}",
            actionable="Ensure file is encoded in valid UTF-8.",
        )

    if sections:
        content = extract_sections_from_markdown(raw_content, sections)
    else:
        content = raw_content

    # Append ADR hint ONLY if explicitly requested
    if include_adr_hints:
        adr_hint = _extract_linked_adrs_hint(w_root, raw_content, rel_path_str)
        if adr_hint and adr_hint not in content:
            content = content.rstrip() + adr_hint

    return content


_READ_BATCH_USAGE = (
    "Accepted forms: paths=['architecture/overview.md', ...] or "
    "requests=[{'path': 'architecture/overview.md', 'sections': ['Overview']}] "
    "(string elements in requests are also accepted)."
)


def _normalize_batch_item(item: Any, source_name: str) -> tuple[str, list[str] | None]:
    """Validate and normalize a single batch-read element into (rel_path, sections)."""
    if isinstance(item, str):
        norm_path = normalize_wiki_rel_path(item)
        if not norm_path:
            raise ValueError(f"Empty or whitespace-only path in '{source_name}'. {_READ_BATCH_USAGE}")
        return norm_path, None

    if source_name == "requests" and isinstance(item, dict):
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            raise ValueError(
                f"Each dict in 'requests' must contain a string 'path', got {item!r}. {_READ_BATCH_USAGE}"
            )
        norm_path = normalize_wiki_rel_path(raw_path)
        if not norm_path:
            raise ValueError(
                f"Empty or whitespace-only 'path' in 'requests' item {item!r}. {_READ_BATCH_USAGE}"
            )
        raw_sections = item.get("sections")
        if raw_sections is not None:
            if not isinstance(raw_sections, list) or any(
                not isinstance(sec, str) or not sec.strip() for sec in raw_sections
            ):
                raise ValueError(
                    f"'sections' must be a list of non-empty strings, got {raw_sections!r}. {_READ_BATCH_USAGE}"
                )
            norm_sections: list[str] | None = list(raw_sections) if raw_sections else None
        else:
            norm_sections = None
        return norm_path, norm_sections

    expected = "str or dict" if source_name == "requests" else "str"
    raise ValueError(
        f"Invalid element in '{source_name}': expected {expected}, got {type(item).__name__} ({item!r}). "
        f"{_READ_BATCH_USAGE}"
    )


def normalize_batch_requests(
    requests: Any = None,
    paths: Any = None,
) -> list[dict[str, Any]]:
    """Normalize and deduplicate batch-read inputs from requests and/or paths.

    Accepts string paths or request dicts in ``requests`` and/or string paths in
    ``paths``, strips leading ``.brain-79/`` prefixes, and deduplicates by
    ``(normalized_path, tuple(sections) or None)`` in first-seen order
    (``requests`` followed by ``paths``).
    """
    if requests is not None and not isinstance(requests, list):
        raise ValueError(f"'requests' must be a list of request dicts or path strings. {_READ_BATCH_USAGE}")
    if paths is not None and not isinstance(paths, list):
        raise ValueError(f"'paths' must be a list of path strings. {_READ_BATCH_USAGE}")

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...] | None]] = set()

    for source_name, items in (("requests", requests or []), ("paths", paths or [])):
        for item in items:
            norm_path, norm_sections = _normalize_batch_item(item, source_name)
            dedup_key = (norm_path, tuple(norm_sections) if norm_sections else None)
            if dedup_key not in seen:
                seen.add(dedup_key)
                normalized.append({"path": norm_path, "sections": norm_sections})

    if not normalized:
        raise ValueError(
            f"Empty batch: provide at least one path in 'paths' or 'requests'. {_READ_BATCH_USAGE}"
        )

    return normalized


def format_batch_results(results: list[dict[str, Any]]) -> str:
    """Format read_batch_articles results into multi-article markdown output."""
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


def read_batch_articles(
    requests: list[Any] | None = None,
    wiki_root: Path | None = None,
    include_adr_hints: bool = True,
    paths: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Read multiple articles in a single call with optional section projections.

    Args:
        requests: List of path strings or dicts, e.g. [{"path": "features/auth.md", "sections": ["Endpoints"]}].
        wiki_root: Optional wiki root Path override.
        include_adr_hints: Whether to append governing ADR footer hints (default: True for batch presentation).
        paths: Optional list of relative wiki path strings.

    Returns:
        List of dicts: [{"path": str, "content": str | None, "error": str | None}]
    """
    normalized_requests = normalize_batch_requests(requests=requests, paths=paths)
    w_root = (wiki_root or get_wiki_root()).resolve()
    results: list[dict[str, Any]] = []

    for req in normalized_requests:
        path = req["path"]
        secs = req.get("sections")
        try:
            content = read_article(
                path,
                wiki_root=w_root,
                sections=secs,
                include_adr_hints=include_adr_hints,
            )
            results.append({"path": path, "content": content, "error": None})
        except Exception as exc:
            results.append({"path": path, "content": None, "error": str(exc)})

    return results


def write_article(
    path: str,
    content: str,
    timeout: float = 5.0,
    force_validation_skip: bool = False,
    _skip_nav_regen: bool = False,
    wiki_root: Path | None = None,
) -> str:
    """
    Write or update an article atomically with file locking. Creates parent directories as needed.

    Note: The .md.lock file remains on disk between writes (standard filelock behavior on Unix).
    It is excluded by .gitignore and article search patterns (*.md).
    For manual cleanup: find .brain-79 -name '*.lock' -delete.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    target = _safe_resolve(path, wiki_root=w_root)

    if target.suffix != ".md":
        raise ValueError(f"write_article requires .md paths, got {path}")

    clean_path = normalize_wiki_rel_path(path)
    if target.exists() and not has_exact_case_path(w_root, clean_path):
        raise ValidationError(
            rule="case_collision",
            path=clean_path,
            message=f"Case collision: requested path '{clean_path}' differs in character casing from existing file on disk.",
            actionable="Use the exact case of the existing article or rename it explicitly.",
        )

    rel_path_str = target.relative_to(w_root).as_posix()
    from brain79.core.drift import load_drift_lock

    load_drift_lock(w_root)

    content = validate_article_content(
        rel_path_str,
        content,
        force_skip=force_validation_skip,
        check_workspace_targets=False,
        wiki_root=w_root,
    )

    is_special = (
        rel_path_str in ("INDEX.md", "SCHEMA.md")
        or rel_path_str.startswith("_raw/")
        or rel_path_str.startswith("handoffs/")
    )

    downgraded_warnings: list[str] = []

    # Pre-flight unanchored governance parity check (also surfaces warning under force_validation_skip=True)
    if not _skip_nav_regen and not is_special:
        from brain79.core.frontmatter import load_active_schema, parse_frontmatter
        from brain79.core.lint_organizational import (
            is_unanchored_governance_article,
            unanchored_governance_actionable,
            unanchored_governance_message,
        )

        active_schema = load_active_schema(w_root)
        try:
            pre_meta, _ = parse_frontmatter(content)
        except Exception:
            pre_meta = {}
        if is_unanchored_governance_article(pre_meta, active_schema, rel_path=rel_path_str):
            doc_type = str(pre_meta.get("type", "")).strip().lower()
            if force_validation_skip or active_schema.enforcement in ("balanced", "advisory"):
                downgraded_warnings.append(
                    f"[unanchored_governance_article] {unanchored_governance_message(rel_path_str, doc_type)}"
                )
            else:
                raise ValidationError(
                    rule="unanchored_governance_article",
                    path=rel_path_str,
                    message=unanchored_governance_message(rel_path_str, doc_type),
                    actionable=unanchored_governance_actionable(rel_path_str),
                )

    drift_lock_updates: dict[str, dict[str, Any]] | None = None
    drift_lock_removals: set[str] | None = None

    if not _skip_nav_regen and not is_special and force_validation_skip:
        drift_lock_removals = {rel_path_str}

    # Single-file target check, anti-sprawl, and drift.lock entry staging
    if not _skip_nav_regen and not is_special and not force_validation_skip:
        from brain79.config import get_project_root
        from brain79.core.drift import (
            WorkspaceIndex,
            compute_applies_to_manifest,
        )
        from brain79.core.frontmatter import (
            INACTIVE_STATUSES,
            PRE_IMPLEMENTATION_STATUSES,
            load_active_schema,
            parse_frontmatter,
        )
        from brain79.core.validation import check_anti_sprawl_overlap

        enforcement = load_active_schema(w_root).enforcement
        p_root = (w_root.parent or get_project_root()).resolve()
        ws_index = WorkspaceIndex.build(p_root, w_root, overlay_fs={rel_path_str: content})
        meta, _ = parse_frontmatter(content)

        # Anti-sprawl check on new articles (strict/balanced=BLOCK, advisory=WARN)
        if not target.exists():
            try:
                check_anti_sprawl_overlap(meta, rel_path_str, wiki_root=w_root, workspace_index=ws_index)
            except ValidationError as exc:
                if enforcement == "advisory" and exc.rule in ("anti_sprawl_overlap_violation", "duplicate_governance_target"):
                    downgraded_warnings.append(f"[{exc.rule}] {exc.message}")
                else:
                    raise

        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES
        is_strictly_active = status not in non_active and stability not in non_active

        applies = meta.get("applies_to")
        if is_strictly_active and applies:
            patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
            for pat in patterns:
                matches = ws_index.find_matching_files([pat])
                if not matches:
                    if enforcement in ("balanced", "advisory"):
                        downgraded_warnings.append(
                            f"[applies_to_target_missing] applies_to pattern '{pat}' does not match any file in workspace index."
                        )
                    else:
                        raise ValidationError(
                            rule="applies_to_target_missing",
                            path=rel_path_str,
                            message=f"applies_to pattern '{pat}' does not match any file in workspace index.",
                            actionable="Verify that governed target files exist or declare pre-implementation status (e.g. planned/draft).",
                        )

            master_digest, count, targets_map = compute_applies_to_manifest(
                patterns,
                p_root,
                w_root,
                exclude_self_path=rel_path_str,
                workspace_index=ws_index,
            )
            if master_digest and targets_map:
                drift_lock_updates = {
                    rel_path_str: {
                        "digest": master_digest,
                        "count": count,
                        "targets": targets_map,
                    }
                }
            else:
                drift_lock_removals = {rel_path_str}
        else:
            drift_lock_removals = {rel_path_str}

    target.parent.mkdir(parents=True, exist_ok=True)
    lock = acquire_wiki_lock(w_root, rel_path_str, timeout=timeout)

    try:
        with lock:
            from brain79.core.locks import create_temp_path

            orig_bytes: bytes | None = target.read_bytes() if target.is_file() else None
            tmp_path = create_temp_path(target, suffix=".md.tmp")
            try:
                tmp_path.write_text(content, encoding="utf-8", newline="\n")
                atomic_replace_with_retry(tmp_path, target)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

            if not _skip_nav_regen and not force_validation_skip and not is_special:
                try:
                    from brain79.core.navigation import (
                        extract_graph_metadata,
                        extract_title_and_summary,
                        register_article,
                    )

                    rel_p = target.relative_to(w_root)
                    rel_posix_str = rel_p.as_posix()
                    title, summary = extract_title_and_summary(content)
                    graph_meta = extract_graph_metadata(content, rel_path=rel_posix_str)
                    section = rel_p.parts[0] if len(rel_p.parts) > 1 else "root"
                    register_article(
                        w_root,
                        rel_posix_str,
                        title,
                        summary,
                        section,
                        graph_meta=graph_meta,
                    )
                except Exception:
                    pass

            if not _skip_nav_regen and (drift_lock_updates or drift_lock_removals):
                from brain79.core.drift import update_drift_lock_entries

                try:
                    update_drift_lock_entries(
                        w_root,
                        updates=drift_lock_updates,
                        removals=drift_lock_removals,
                    )
                except BaseException:
                    if orig_bytes is None:
                        target.unlink(missing_ok=True)
                    else:
                        rb_tmp = create_temp_path(target, suffix=".md.rollback")
                        try:
                            rb_tmp.write_bytes(orig_bytes)
                            atomic_replace_with_retry(rb_tmp, target)
                        finally:
                            rb_tmp.unlink(missing_ok=True)
                    raise
    except filelock.Timeout:
        raise OSError(
            f"El archivo {path} está bloqueado por otro proceso. Reintenta en unos segundos."
        )

    # Best-effort navigation registration and index synchronization
    try:
        if (
            not force_validation_skip
            and rel_path_str != "INDEX.md"
            and rel_path_str != "SCHEMA.md"
            and not rel_path_str.startswith("_raw/")
            and not rel_path_str.startswith("handoffs/")
        ):
            from brain79.core.navigation import (
                extract_graph_metadata,
                extract_title_and_summary,
                regenerate_index_navigation,
                register_article,
            )

            if _skip_nav_regen:
                rel_p = target.relative_to(w_root)
                rel_posix_str = rel_p.as_posix()
                title, summary = extract_title_and_summary(content)
                graph_meta = extract_graph_metadata(content, rel_path=rel_posix_str)
                section = rel_p.parts[0] if len(rel_p.parts) > 1 else "root"
                register_article(
                    w_root,
                    rel_posix_str,
                    title,
                    summary,
                    section,
                    graph_meta=graph_meta,
                )
            if not _skip_nav_regen:
                try:
                    regenerate_index_navigation(w_root)
                except ValidationError as nav_exc:
                    if nav_exc.rule == "corrupt_drift_lock":
                        raise
                except Exception:
                    pass
        elif rel_path_str == "INDEX.md" and "## Quick navigation" in content:
            if not _skip_nav_regen:
                from brain79.core.navigation import regenerate_index_navigation

                try:
                    regenerate_index_navigation(w_root)
                except ValidationError as nav_exc:
                    if nav_exc.rule == "corrupt_drift_lock":
                        raise
                except Exception:
                    pass
    except ValidationError as nav_exc:
        if nav_exc.rule == "corrupt_drift_lock":
            raise
    except Exception:
        pass

    if downgraded_warnings:
        warn_block = "\n".join(f"- Warning: {w}" for w in downgraded_warnings)
        return f"Written: {rel_path_str}\n{warn_block}"
    return f"Written: {rel_path_str}"


def check_file_health(wiki_root: Path, rel_path: str, content: str) -> list[str]:
    """Run lightweight per-file health checks returning warnings (if any)."""
    warnings: list[str] = []

    # Normalize rel_path to be strictly relative to wiki_root without leading .brain-79/ prefixes
    w_root = wiki_root.resolve()
    try:
        rel_path = _safe_resolve(rel_path, wiki_root=w_root).relative_to(w_root).as_posix()
    except Exception:
        rel_path = normalize_wiki_rel_path(rel_path)

    # Exempt paths
    if rel_path in ("SCHEMA.md",) or rel_path.startswith("_raw/") or rel_path.startswith("handoffs/"):
        return warnings

    # 1. H1 Header check
    from brain79.core.lint import _extract_raw_link_targets, _has_h1_header
    if not _has_h1_header(content):
        warnings.append(f"Missing H1 header in '{rel_path}'.")

    # 2. Decision & Technical Debt leakage in non-decision documents
    if not rel_path.startswith("decisions/") and rel_path != "INDEX.md":
        from brain79.core.frontmatter import load_active_schema
        from brain79.core.validation import (
            DECISION_BULLET_STRICT,
            DECISION_HEADER_STRICT,
            TECHNICAL_DEBT_BULLET_STRICT,
            TECHNICAL_DEBT_HEADER_STRICT,
            _mask_code_fences,
        )
        masked = _mask_code_fences(content)
        if DECISION_HEADER_STRICT.search(masked) or DECISION_BULLET_STRICT.search(masked):
            warnings.append(
                f"Structural decision leakage detected in non-decision article '{rel_path}'. Move decisions to decisions/."
            )

        active_schema = load_active_schema(wiki_root)
        if active_schema.supports_technical_debt_leakage:
            if TECHNICAL_DEBT_HEADER_STRICT.search(masked) or TECHNICAL_DEBT_BULLET_STRICT.search(masked):
                warnings.append(
                    f"Technical debt leakage detected in '{rel_path}'. Move to decisions/ or features/."
                )

    # 3. Broken local links in this article
    import posixpath
    from urllib.parse import unquote
    raw_targets = _extract_raw_link_targets(content)
    article_parent_rel = Path(rel_path).parent.as_posix()
    for raw_target in raw_targets:
        if (
            raw_target.startswith(
                ("http://", "https://", "mailto:", "ftp://", "file://", "//", "tel:", "data:")
            )
            or "://" in raw_target
        ):
            continue
        path_part = unquote(raw_target.split("#", 1)[0])
        if not path_part:
            continue
        if path_part.startswith("/"):
            norm_target_rel = posixpath.normpath(path_part.lstrip("/"))
        else:
            if article_parent_rel == ".":
                norm_target_rel = posixpath.normpath(path_part)
            else:
                norm_target_rel = posixpath.normpath(posixpath.join(article_parent_rel, path_part))

        if norm_target_rel.startswith("../") or norm_target_rel == "..":
            warnings.append(f"Link points outside wiki: '{raw_target}'.")
            continue

        target_file = wiki_root / norm_target_rel
        if not target_file.is_file() or not has_exact_case_path(wiki_root, norm_target_rel):
            warnings.append(f"Broken local link: '{raw_target}' -> '{norm_target_rel}' does not exist.")

    # 4. Required structural sections check
    if rel_path != "INDEX.md":
        from brain79.core.frontmatter import infer_type_for_path, load_active_schema, parse_frontmatter
        from brain79.core.validation import check_missing_sections

        try:
            active_schema = load_active_schema(wiki_root)
            meta, _ = parse_frontmatter(content)
            doc_type = meta.get("type") or infer_type_for_path(rel_path, schema=active_schema)
            if doc_type:
                missing_secs = check_missing_sections(content, doc_type, schema=active_schema)
                for sec in missing_secs:
                    warnings.append(
                        f"Missing required section '## {sec}' in '{rel_path}' for type '{doc_type}'."
                    )

            from brain79.core.lint_organizational import (
                is_unanchored_governance_article,
                unanchored_governance_message,
            )

            if is_unanchored_governance_article(meta, active_schema, rel_path=rel_path):
                norm_type = str(meta.get("type", "")).strip().lower()
                warnings.append(
                    f"[unanchored_governance_article] {unanchored_governance_message(rel_path, norm_type)}"
                )
        except Exception:
            pass

    return warnings


def edit_article(
    path: str,
    edits: list[dict[str, str]],
    timeout: float = 5.0,
    force_validation_skip: bool = False,
    wiki_root: Path | None = None,
) -> str:
    """Apply one or more text replacements to an article, validate, and write atomically."""
    if not edits:
        raise ValueError("edits list cannot be empty.")

    w_root = (wiki_root or get_wiki_root()).resolve()
    target = _safe_resolve(path, wiki_root=w_root)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Article not found: {path}")

    rel_str = target.relative_to(w_root).as_posix()
    try:
        content = target.read_text(encoding="utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            rule="invalid_utf8_encoding",
            path=rel_str,
            message=f"File contains invalid UTF-8 bytes: {exc}",
            actionable="Ensure file is encoded in valid UTF-8.",
        )

    for idx, edit in enumerate(edits):
        old_text = edit.get("old_text") if edit.get("old_text") is not None else edit.get("oldText")
        new_text = edit.get("new_text") if edit.get("new_text") is not None else edit.get("newText")
        if old_text is None or new_text is None:
            raise ValueError(f"Edit #{idx + 1} must contain 'old_text' and 'new_text'.")
        if not old_text:
            raise ValueError(f"Edit #{idx + 1} 'old_text' cannot be empty.")

        count = content.count(old_text)
        if count == 0:
            snippet = old_text[:60] + "..." if len(old_text) > 60 else old_text
            raise ValueError(f"Edit #{idx + 1} failed: 'old_text' not found: {snippet!r}")
        if count > 1:
            snippet = old_text[:60] + "..." if len(old_text) > 60 else old_text
            raise ValueError(f"Edit #{idx + 1} ambiguous: 'old_text' matches {count} times: {snippet!r}")

        content = content.replace(old_text, new_text, 1)

    return write_article(
        path,
        content,
        timeout=timeout,
        force_validation_skip=force_validation_skip,
        wiki_root=wiki_root,
    )


def write_many_articles(
    articles: list[dict[str, str]],
    timeout: float = 5.0,
    force_validation_skip: bool = False,
    wiki_root: Path | None = None,
) -> str:
    """Validate all articles in batch first; if all valid, write them atomically."""
    import json
    from brain79.config import get_project_root
    from brain79.core.drift import (
        DRIFT_LOCK_FILENAME,
        DRIFT_LOCK_VERSION,
        WorkspaceIndex,
        compute_applies_to_manifest,
        load_drift_lock,
        save_drift_lock,
    )
    from brain79.core.frontmatter import INACTIVE_STATUSES, PRE_IMPLEMENTATION_STATUSES, parse_frontmatter
    from brain79.core.locks import create_temp_path

    if not articles:
        raise ValueError("articles list cannot be empty.")

    w_root = (wiki_root or get_wiki_root()).resolve()
    load_drift_lock(w_root)
    p_root = (w_root.parent or get_project_root()).resolve()
    validated_contents: list[tuple[str, str]] = []
    validation_errors: list[str] = []

    # 1. Validation pass (all-or-nothing schema check)
    for idx, item in enumerate(articles):
        p = item.get("path")
        c = item.get("content")
        if not p or c is None:
            raise ValueError(f"Article #{idx + 1} must have 'path' and 'content'.")

        target = _safe_resolve(p, wiki_root=w_root)
        if target.suffix != ".md":
            raise ValueError(f"write_many_articles requires .md paths, got {p}")

        clean_path = normalize_wiki_rel_path(p)
        if target.exists() and not has_exact_case_path(w_root, clean_path):
            raise ValidationError(
                rule="case_collision",
                path=clean_path,
                message=f"Case collision: requested path '{clean_path}' differs in character casing from existing file on disk.",
                actionable="Use the exact case of the existing article or rename it explicitly.",
            )

        rel_path_str = target.relative_to(w_root).as_posix()
        try:
            val_c = validate_article_content(
                rel_path_str,
                c,
                force_skip=force_validation_skip,
                check_workspace_targets=False,
                wiki_root=w_root,
            )
            validated_contents.append((rel_path_str, val_c))
        except ValidationError as exc:
            validation_errors.append(f"[{p}]\n{exc.format_user_message()}")
        except Exception as exc:
            validation_errors.append(f"[{p}] {exc}")

    if validation_errors:
        raise ValidationError(
            rule="batch_validation_failed",
            path="batch",
            message=f"Batch validation failed for {len(validation_errors)} article(s):\n\n"
            + "\n\n".join(validation_errors),
            actionable="Fix all validation errors listed above before re-submitting batch.",
        )

    # 2. Transaction lock + target check & digest stamping pass
    tx_lock = acquire_wiki_lock(w_root, "_transaction.lock", timeout=timeout)
    with tx_lock:
        virtual_fs = {rel_p: val_c for rel_p, val_c in validated_contents}
        ws_index = WorkspaceIndex.build(p_root, w_root, overlay_fs=virtual_fs)

        # Validate applies_to_target_missing and anti-sprawl overlap
        from brain79.core.frontmatter import load_active_schema
        from brain79.core.lint_organizational import (
            build_unanchored_batch_error,
            is_unanchored_governance_article,
            unanchored_governance_message,
        )
        from brain79.core.validation import check_anti_sprawl_overlap

        active_schema = load_active_schema(w_root)
        enforcement = active_schema.enforcement
        batch_downgraded_warnings: list[str] = []

        unanchored_offenders: list[tuple[str, str]] = []
        for rel_p, val_c in validated_contents:
            try:
                meta, _ = parse_frontmatter(val_c)
            except Exception:
                continue
            if is_unanchored_governance_article(meta, active_schema, rel_path=rel_p):
                doc_type = str(meta.get("type", "")).strip().lower()
                if force_validation_skip or enforcement in ("balanced", "advisory"):
                    batch_downgraded_warnings.append(
                        f"[unanchored_governance_article] ({rel_p}) {unanchored_governance_message(rel_p, doc_type)}"
                    )
                else:
                    unanchored_offenders.append((rel_p, doc_type))

        if unanchored_offenders:
            raise build_unanchored_batch_error(unanchored_offenders)
        for rel_p, val_c in validated_contents:
            try:
                meta, body = parse_frontmatter(val_c)
                status = str(meta.get("status", "")).lower()
                stability = str(meta.get("stability", "")).lower()
                non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES

                if not (w_root / rel_p).is_file():
                    try:
                        check_anti_sprawl_overlap(
                            meta, rel_p, wiki_root=w_root, workspace_index=ws_index, overlay_fs=virtual_fs
                        )
                    except ValidationError as exc:
                        if enforcement == "advisory" and exc.rule in ("anti_sprawl_overlap_violation", "duplicate_governance_target"):
                            batch_downgraded_warnings.append(f"[{exc.rule}] ({rel_p}) {exc.message}")
                        else:
                            raise

                if status not in non_active and stability not in non_active:
                    applies = meta.get("applies_to")
                    if applies:
                        patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
                        for pat in patterns:
                            matches = ws_index.find_matching_files([pat])
                            if not matches:
                                if enforcement in ("balanced", "advisory"):
                                    batch_downgraded_warnings.append(
                                        f"[applies_to_target_missing] ({rel_p}) applies_to pattern '{pat}' does not match any file in workspace index."
                                    )
                                else:
                                    raise ValidationError(
                                        rule="applies_to_target_missing",
                                        path=rel_p,
                                        message=f"applies_to pattern '{pat}' does not match any file in workspace index.",
                                        actionable="Verify that governed target files exist or declare pre-implementation status (e.g. planned/draft).",
                                    )
            except ValidationError:
                raise
            except Exception:
                pass

        # Stage drift.lock entries in memory (2 iterations for fixed-point convergence) without stamping .md frontmatter
        lock_data = load_drift_lock(w_root) or {"version": DRIFT_LOCK_VERSION, "articles": {}}
        lock_staging = json.loads(json.dumps(lock_data))
        lock_staging.setdefault("articles", {})
        non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES

        for _ in range(2):
            for rel_p in list(virtual_fs.keys()):
                val_c = virtual_fs[rel_p]
                try:
                    meta, _ = parse_frontmatter(val_c)
                    st = str(meta.get("status", "")).lower()
                    sp = str(meta.get("stability", "")).lower()
                    is_active = st not in non_active and sp not in non_active
                    applies = meta.get("applies_to")
                    is_special_p = (
                        rel_p in ("INDEX.md", "SCHEMA.md")
                        or rel_p.startswith("_raw/")
                        or rel_p.startswith("handoffs/")
                    )
                    if not force_validation_skip and not is_special_p and is_active and applies:
                        patterns = [str(x) for x in applies] if isinstance(applies, list) else [str(applies)]
                        master_digest, count, targets = compute_applies_to_manifest(
                            patterns,
                            p_root,
                            w_root,
                            exclude_self_path=rel_p,
                            overlay_fs=virtual_fs,
                            workspace_index=ws_index,
                        )
                        if master_digest and targets:
                            lock_staging["articles"][rel_p] = {
                                "digest": master_digest,
                                "count": count,
                                "targets": targets,
                            }
                        else:
                            lock_staging["articles"].pop(rel_p, None)
                    else:
                        lock_staging["articles"].pop(rel_p, None)
                except Exception:
                    lock_staging["articles"].pop(rel_p, None)

        final_contents: list[tuple[str, str]] = [(rel_p, virtual_fs[rel_p]) for rel_p, _ in validated_contents]

        drift_lock_file = w_root / DRIFT_LOCK_FILENAME
        orig_lock_bytes: bytes | None = drift_lock_file.read_bytes() if drift_lock_file.is_file() else None
        orig_md_bytes: dict[str, bytes | None] = {
            rel_p: (w_root / rel_p).read_bytes() if (w_root / rel_p).is_file() else None
            for rel_p, _ in final_contents
        }

        written: list[str] = []
        try:
            save_drift_lock(w_root, lock_staging)

            # 3. Write pass
            for rel_p, val_c in final_contents:
                write_article(
                    rel_p,
                    val_c,
                    timeout=timeout,
                    force_validation_skip=force_validation_skip,
                    _skip_nav_regen=True,
                    wiki_root=w_root,
                )
                written.append(rel_p)

            # 4. Navigation regeneration
            try:
                from brain79.core.navigation import regenerate_index_navigation

                regenerate_index_navigation(w_root)
            except ValidationError as nav_exc:
                if nav_exc.rule == "corrupt_drift_lock":
                    raise
            except Exception:
                pass
        except BaseException:
            for rel_p, orig_b in orig_md_bytes.items():
                md_target = w_root / rel_p
                if orig_b is None:
                    md_target.unlink(missing_ok=True)
                else:
                    rb_tmp = create_temp_path(md_target, suffix=".md.rollback")
                    try:
                        rb_tmp.write_bytes(orig_b)
                        atomic_replace_with_retry(rb_tmp, md_target)
                    finally:
                        rb_tmp.unlink(missing_ok=True)

            if orig_lock_bytes is None:
                drift_lock_file.unlink(missing_ok=True)
            else:
                rb_lock_tmp = create_temp_path(drift_lock_file, suffix=".lock.rollback")
                try:
                    rb_lock_tmp.write_bytes(orig_lock_bytes)
                    atomic_replace_with_retry(rb_lock_tmp, drift_lock_file)
                finally:
                    rb_lock_tmp.unlink(missing_ok=True)
            raise

    if batch_downgraded_warnings:
        base_msg = f"Batch write succeeded: {len(written)} article(s) written: {', '.join(written)} · INDEX.md auto-synced"
        warn_block = "\n".join(f"- Warning: {w}" for w in batch_downgraded_warnings)
        return f"{base_msg}\n{warn_block}"
    return f"Batch write succeeded: {len(written)} article(s) written: {', '.join(written)} · INDEX.md auto-synced · lint OK"


def list_articles(
    section: str | None = None,
    wiki_root: Path | None = None,
) -> list[str]:
    """List all markdown articles (excluding _raw/) optionally filtered by section."""
    w_root = (wiki_root or get_wiki_root()).resolve()
    if not w_root.exists():
        return []

    if section and (
        section in _EXCLUDED_DIRS
        or any(part in _EXCLUDED_DIRS for part in Path(section).parts)
    ):
        return []

    root = w_root / section if section else w_root
    if not root.exists():
        return []

    articles: list[str] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(w_root)
        if not any(part in _EXCLUDED_DIRS for part in rel.parts):
            articles.append(rel.as_posix())

    return articles


def get_index(wiki_root: Path | None = None) -> str:
    """Return the content of INDEX.md."""
    try:
        return read_article("INDEX.md", wiki_root=wiki_root)
    except FileNotFoundError:
        return (
            "INDEX.md not found.\n"
            "Run `brain79 init --project-root <path>` to initialize the wiki."
        )


def _search_ripgrep(query: str) -> list[dict[str, str]]:
    wiki_root = get_wiki_root()
    cmd = [
        _RG_PATH or "rg",
        "-i",
        "-F",
        "-n",
        "--null",
        "-g",
        "*.md",
        "-g",
        "!_raw/**",
        "-g",
        "!.locks/**",
        "--no-follow",
        query,
        str(wiki_root),
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if res.returncode >= 2:
        raise ValueError(f"ripgrep failed with return code {res.returncode}")

    results: list[dict[str, str]] = []
    seen_files: set[str] = set()

    for line in res.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\0", 1)
        if len(parts) != 2:
            continue
        filepath_str, rest = parts
        try:
            rel = Path(filepath_str).relative_to(wiki_root)
        except ValueError:
            continue

        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue

        rel_str = rel.as_posix()
        if rel_str in seen_files:
            continue
        seen_files.add(rel_str)

        content_parts = rest.split(":", 1)
        excerpt = content_parts[1].strip() if len(content_parts) == 2 else rest.strip()
        results.append({"path": rel_str, "excerpt": excerpt[:200]})

    return results


def _search_python(query: str) -> list[dict[str, str]]:
    wiki_root = get_wiki_root()
    query_lower = query.lower()
    results: list[dict[str, str]] = []

    for p in sorted(wiki_root.rglob("*.md")):
        rel = p.relative_to(wiki_root)
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue

        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue

        if query_lower not in content.lower():
            continue

        excerpt = next(
            (
                line.strip()
                for line in content.splitlines()
                if query_lower in line.lower()
            ),
            "",
        )
        results.append({"path": rel.as_posix(), "excerpt": excerpt[:200]})

    return results


def search_articles(query: str) -> list[dict[str, str]]:
    """Search wiki articles by keyword (case-insensitive). Returns path + excerpt."""
    wiki_root = get_wiki_root()
    if not wiki_root.exists():
        return []

    if not query or not query.strip():
        return []

    if _RG_PATH:
        try:
            return _search_ripgrep(query)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return _search_python(query)

    return _search_python(query)


def save_raw_session(
    session_summary: str,
    instructions: str | None = None,
    wiki_root: Path | None = None,
) -> str:
    """Save a raw session summary to _raw/sessions/ and return the saved path."""
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%d-%H%M%S-%f")[:-3]
    today = now.strftime("%Y-%m-%d")
    session_id = f"session-{timestamp}"
    rel_path = f"_raw/sessions/{session_id}.md"

    frontmatter_lines = [
        "---",
        "type: raw_session",
        f"session_id: {session_id}",
        "session_type: feature",
        f"last_updated: {today}",
        "---",
        "",
        f"# Session — {timestamp}",
        "",
    ]
    if instructions:
        frontmatter_lines.append(f"> **Curation instructions:** {instructions}\n")
    frontmatter_lines.append(session_summary)

    write_article(rel_path, "\n".join(frontmatter_lines), wiki_root=wiki_root)
    return rel_path
