from datetime import UTC, datetime
from pathlib import Path
import shutil
import subprocess
from typing import Any

import filelock

from brain79.config import get_wiki_root
from brain79.core.frontmatter import ValidationError
from brain79.core.validation import validate_article_content


# Directories excluded from article listings (raw sources are not wiki articles)
_EXCLUDED_DIRS = {"_raw"}



_RG_PATH: str | None = shutil.which("rg")


def _safe_resolve(path: str, wiki_root: Path | None = None) -> Path:
    """Resolve a relative wiki path and verify it stays within the wiki root."""
    w_root = (wiki_root or get_wiki_root()).resolve()
    target = (w_root / path).resolve()
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

    raw_content = target.read_text(encoding="utf-8")
    rel_path_str = str(target.relative_to(w_root))

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


def read_batch_articles(
    requests: list[dict[str, Any]],
    wiki_root: Path | None = None,
    include_adr_hints: bool = True,
) -> list[dict[str, Any]]:
    """
    Read multiple articles in a single call with optional section projections.

    Args:
        requests: List of dicts, e.g. [{"path": "features/auth.md", "sections": ["Endpoints"]}]
        wiki_root: Optional wiki root Path override.
        include_adr_hints: Whether to append governing ADR footer hints (default: True for batch presentation).

    Returns:
        List of dicts: [{"path": str, "content": str | None, "error": str | None}]
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    results: list[dict[str, Any]] = []

    for req in requests:
        path = req.get("path")
        if not path:
            results.append({"path": "", "content": None, "error": "Missing 'path' in request."})
            continue

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

    rel_path_str = str(target.relative_to(w_root))
    content = validate_article_content(
        rel_path_str, content, force_skip=force_validation_skip, wiki_root=w_root
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(".md.lock")
    lock = filelock.FileLock(str(lock_path), timeout=timeout)

    try:
        with lock:
            tmp_path = target.with_suffix(".md.tmp")
            try:
                tmp_path.write_text(content, encoding="utf-8")
                tmp_path.replace(target)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
    except filelock.Timeout:
        raise OSError(
            f"El archivo {path} está bloqueado por otro proceso. Reintenta en unos segundos."
        )

    # Best-effort navigation registration & synchronization (P1.1, P0.5)
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

            rel_p = target.relative_to(w_root)
            title, summary = extract_title_and_summary(content)
            graph_meta = extract_graph_metadata(content, rel_path=str(rel_p))
            section = rel_p.parts[0] if len(rel_p.parts) > 1 else "root"
            register_article(
                w_root,
                str(rel_p),
                title,
                summary,
                section,
                graph_meta=graph_meta,
            )
            if not _skip_nav_regen:
                try:
                    regenerate_index_navigation(w_root)
                except Exception:
                    pass
        elif rel_path_str == "INDEX.md" and "## Quick navigation" in content:
            if not _skip_nav_regen:
                from brain79.core.navigation import regenerate_index_navigation

                try:
                    regenerate_index_navigation(w_root)
                except Exception:
                    pass
    except Exception:
        pass

    return f"Written: {path}"


def check_file_health(wiki_root: Path, rel_path: str, content: str) -> list[str]:
    """Run lightweight per-file health checks returning warnings (if any)."""
    warnings: list[str] = []

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
    from urllib.parse import unquote
    raw_targets = _extract_raw_link_targets(content)
    article_path = wiki_root / rel_path
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
            target_file = (wiki_root / path_part.lstrip("/")).resolve()
        else:
            target_file = (article_path.parent / path_part).resolve()
        try:
            target_rel = target_file.relative_to(wiki_root)
            if not target_file.exists():
                warnings.append(f"Broken local link: '{raw_target}' -> '{target_rel}' does not exist.")
        except ValueError:
            warnings.append(f"Link points outside wiki: '{raw_target}'.")

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
        except Exception:
            pass

    return warnings


def edit_article(
    path: str,
    edits: list[dict[str, str]],
    timeout: float = 5.0,
    force_validation_skip: bool = False,
) -> str:
    """Apply one or more text replacements to an article, validate, and write atomically."""
    if not edits:
        raise ValueError("edits list cannot be empty.")

    target = _safe_resolve(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Article not found: {path}")

    content = target.read_text(encoding="utf-8")

    for idx, edit in enumerate(edits):
        old_text = edit.get("old_text")
        new_text = edit.get("new_text")
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
        path, content, timeout=timeout, force_validation_skip=force_validation_skip
    )


def write_many_articles(
    articles: list[dict[str, str]],
    timeout: float = 5.0,
    force_validation_skip: bool = False,
) -> str:
    """Validate all articles in batch first; if all valid, write them atomically."""
    if not articles:
        raise ValueError("articles list cannot be empty.")

    wiki_root = get_wiki_root().resolve()
    validated_contents: list[tuple[str, str]] = []
    validation_errors: list[str] = []

    # 1. Validation pass (all-or-nothing)
    for idx, item in enumerate(articles):
        p = item.get("path")
        c = item.get("content")
        if not p or c is None:
            raise ValueError(f"Article #{idx + 1} must have 'path' and 'content'.")

        target = _safe_resolve(p)
        if target.suffix != ".md":
            raise ValueError(f"write_many_articles requires .md paths, got {p}")

        rel_path_str = str(target.relative_to(wiki_root))
        try:
            val_c = validate_article_content(rel_path_str, c, force_skip=force_validation_skip)
            validated_contents.append((p, val_c))
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

    # 2. Write pass
    written: list[str] = []
    for p, val_c in validated_contents:
        write_article(
            p,
            val_c,
            timeout=timeout,
            force_validation_skip=force_validation_skip,
            _skip_nav_regen=True,
        )
        written.append(p)

    # 3. Single navigation regeneration at the end of the batch
    try:
        from brain79.core.navigation import regenerate_index_navigation

        regenerate_index_navigation(wiki_root)
    except Exception:
        pass

    return f"Batch write succeeded: {len(written)} article(s) written: {', '.join(written)} · lint OK"


def list_articles(section: str | None = None) -> list[str]:
    """List all markdown articles (excluding _raw/) optionally filtered by section."""
    wiki_root = get_wiki_root()
    if not wiki_root.exists():
        return []

    if section and (
        section in _EXCLUDED_DIRS
        or any(part in _EXCLUDED_DIRS for part in Path(section).parts)
    ):
        return []

    root = wiki_root / section if section else wiki_root
    if not root.exists():
        return []

    articles: list[str] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(wiki_root)
        if not any(part in _EXCLUDED_DIRS for part in rel.parts):
            articles.append(str(rel))

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

        rel_str = str(rel)
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
        results.append({"path": str(rel), "excerpt": excerpt[:200]})

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
