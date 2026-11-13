import os
from pathlib import Path
import re
import sys
from typing import Any

from brain79.core.frontmatter import (
    INACTIVE_STATUSES,
    FrontmatterError,
    ValidationError,
    _normalize_content,
    autofill_deterministic_fields,
    dump_frontmatter,
    generate_frontmatter_template,
    infer_type_for_path,
    normalize_backlink_footer,
    normalize_bullet_colons,
    parse_frontmatter,
    validate_frontmatter,
    validate_location_consistency,
)

# Limits
DEFAULT_INDEX_MAX_LINES = 150
MAX_ARTICLE_LINES = 400
MAX_ARTICLE_BYTES = 20_480  # 20 KB

TEMPORAL_MILESTONE_REGEX = re.compile(
    r"(?<!-)\b(phase|phases|fase|fases|sprint|milestone|etapa)\s+(\d+(\.\d+)?|[ivx]+)\b"
    r"|\b(roadmap\s+ticket)\b"
    r"|\bWIP\b",
    re.IGNORECASE,
)

SHIPPED_SPECIFICATION_REGEX = re.compile(
    r"\b(specification|especificación|especificacion)\b",
    re.IGNORECASE,
)


def get_index_max_lines() -> int:
    env_val = os.environ.get("BRAIN79_INDEX_MAX_LINES")
    if env_val:
        try:
            val = int(env_val)
            if 50 <= val <= 500:
                return val
        except ValueError:
            pass
    return DEFAULT_INDEX_MAX_LINES


# Allowed H2 headers in INDEX.md (ADR-008: Pure automated routing table)
INDEX_ALLOWED_H2 = frozenset({
    "Quick navigation",
})

# V5 strict decision / TD patterns in INDEX.md (Appendix B.1)
DECISION_BULLET_STRICT = re.compile(
    r"(?im)^[-*]\s+(?:Decision|ADR-\d+|Decisión|Decidimos|Acordado|Chose|Rejected alternative):"
)
DECISION_HEADER_STRICT = re.compile(r"(?im)^#{2,3}\s+(?:Decision|ADR|Decisión|Decision Log)\b")
TECHNICAL_DEBT_BULLET_STRICT = re.compile(r"(?im)^[-*]\s+TD-\d+:")
TECHNICAL_DEBT_HEADER_STRICT = re.compile(r"(?im)^#{2,3}\s+Technical [Dd]ebt\b")

_INDEX_DECISION_PATTERNS = [
    DECISION_BULLET_STRICT,
    DECISION_HEADER_STRICT,
    TECHNICAL_DEBT_BULLET_STRICT,
    TECHNICAL_DEBT_HEADER_STRICT,
]


def _mask_code_fences(content: str) -> str:
    """Replace lines inside fenced code blocks with placeholders to avoid false positives."""
    lines = content.split("\n")
    in_fence = False
    fence_char: str | None = None
    masked: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence_char = stripped[:3]
                in_fence = True
            masked.append(line)
        else:
            if fence_char and stripped.startswith(fence_char):
                fence_char = None
                in_fence = False
                masked.append(line)
            else:
                masked.append(" " * len(line))
    return "\n".join(masked)


def validate_article_content(
    path: str,
    content: str,
    force_skip: bool = False,
    wiki_root: Path | None = None,
    check_workspace_targets: bool = True,
) -> str:
    """Validate article content before writing to disk.

    If validation passes, returns content (potentially with injected metadata if force_skip is True).
    Raises ValidationError if validation fails.
    """
    content = _normalize_content(content)
    rel_path = path.strip("/")

    # Exempt files: SCHEMA.md and anything under _raw/
    if rel_path == "SCHEMA.md" or rel_path.startswith("_raw/"):
        return content

    if force_skip:
        sys.stderr.write(
            "WARNING: Skipping organizational validation. This bypass is logged and visible in brain79 lint.\n"
        )
        if content.startswith("---\n"):
            lines = content.split("\n")
            lines.insert(1, "force_validation_skipped: true")
            return "\n".join(lines)
        else:
            return f"---\nforce_validation_skipped: true\n---\n\n{content}"

    if rel_path == "INDEX.md":
        lines = content.splitlines()
        max_lines = get_index_max_lines()
        if len(lines) > max_lines:
            raise ValidationError(
                rule="index_oversized",
                path=rel_path,
                message=f"INDEX.md has {len(lines)} lines (exceeds limit of {max_lines}).",
                actionable="Extract sections into separate articles in decisions/, features/, architecture/, product/.",
            )

        masked_content = _mask_code_fences(content)
        masked_lines = masked_content.splitlines()

        # Check H2 headers outside code fences
        for line in masked_lines:
            if line.startswith("## "):
                header_title = line[3:].strip()
                if header_title not in INDEX_ALLOWED_H2:
                    raise ValidationError(
                        rule="index_prohibited_header",
                        path=rel_path,
                        message=f"Prohibited header '## {header_title}' in INDEX.md.",
                        actionable=f"INDEX.md H2 headers must be one of: {sorted(INDEX_ALLOWED_H2)}",
                    )

        # Check strict decision patterns in INDEX.md outside code fences
        for pattern in _INDEX_DECISION_PATTERNS:
            if pattern.search(masked_content):
                raise ValidationError(
                    rule="index_prohibited_content",
                    path=rel_path,
                    message="Prohibited decision or technical debt content detected in INDEX.md.",
                    actionable="Move decision declarations and technical debt items to articles in decisions/.",
                )

        # Check optional frontmatter if present
        if content.startswith("---\n"):
            try:
                meta, body = parse_frontmatter(content)
                meta = autofill_deterministic_fields(meta, rel_path, body=body)
                content = dump_frontmatter(meta, body)
                validate_frontmatter(meta, rel_path)
                validate_location_consistency(meta, rel_path)
            except FrontmatterError as e:
                raise ValidationError(
                    rule="frontmatter_malformed",
                    path=rel_path,
                    message=str(e),
                    actionable="Fix frontmatter syntax in INDEX.md.",
                )

        return content

    # Normal articles (not INDEX.md, not SCHEMA.md, not _raw/)
    try:
        meta, body = parse_frontmatter(content)
    except FrontmatterError as e:
        target_t = infer_type_for_path(rel_path)
        tpl = generate_frontmatter_template(target_t) if target_t else ""
        act = "Add YAML frontmatter with `type`, `last_updated`, etc. between `---` delimiters."
        if tpl:
            act += f"\n\nTemplate:\n```yaml\n{tpl}\n```"
        raise ValidationError(
            rule="frontmatter_missing",
            path=rel_path,
            message=str(e),
            actionable=act,
            target_type=target_t,
        )

    from brain79.config import get_wiki_root
    from brain79.core.frontmatter import load_active_schema

    try:
        w_root = (wiki_root or get_wiki_root()).resolve()
        active_s = load_active_schema(w_root)
    except Exception:
        active_s = None

    meta = autofill_deterministic_fields(meta, rel_path, body=body, schema=active_s)
    body = normalize_backlink_footer(body, rel_path)
    body = normalize_bullet_colons(body)
    content = dump_frontmatter(meta, body)
    validate_frontmatter(meta, rel_path, schema=active_s)
    validate_location_consistency(meta, rel_path, schema=active_s)

    top_dir = rel_path.split("/")[0]
    status = str(meta.get("status", "")).lower()
    stability = str(meta.get("stability", "")).lower()
    is_inactive = status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES

    # Check article atomicity and byte size
    atomicity_exempt_dirs = {"decisions", "changelog", "handoffs", "_raw", ".locks"}
    if top_dir not in atomicity_exempt_dirs and not is_inactive:
        new_lines = len(content.splitlines())
        new_bytes = len(content.encode("utf-8"))
        if new_lines > MAX_ARTICLE_LINES or new_bytes > MAX_ARTICLE_BYTES:
            is_monotonic_reduction = False
            target_disk = (w_root / rel_path) if w_root else None
            if target_disk and target_disk.is_file():
                try:
                    old_raw = target_disk.read_text(encoding="utf-8")
                    old_lines = len(old_raw.splitlines())
                    old_bytes = len(old_raw.encode("utf-8"))
                    if (old_lines > MAX_ARTICLE_LINES or old_bytes > MAX_ARTICLE_BYTES) and (new_bytes < old_bytes and new_lines <= old_lines):
                        is_monotonic_reduction = True
                except Exception:
                    pass
            if not is_monotonic_reduction:
                raise ValidationError(
                    rule="article_too_large",
                    path=rel_path,
                    message=f"Article has {new_lines} lines and {new_bytes} bytes (max recommended: {MAX_ARTICLE_LINES} lines / {MAX_ARTICLE_BYTES} bytes).",
                    actionable="Split or distill the article into a concise living manual (< 400 lines and < 20480 bytes).",
                )

    # Check temporal decontamination for living manuals
    living_dirs = ("features", "architecture", "product")
    if top_dir in living_dirs and "roadmap" not in rel_path.lower() and not is_inactive:
        summary = str(meta.get("summary") or "")
        m_summary = TEMPORAL_MILESTONE_REGEX.search(summary)
        if m_summary:
            raise ValidationError(
                rule="temporal_contamination_in_summary",
                path=rel_path,
                message=f"Living manual summary contains temporal project management marker '{m_summary.group(0)}'.",
                actionable="Remove temporal milestone tags from summary. Living manuals must describe software capabilities evergreenly.",
            )

        body_masked = _mask_code_fences(body)
        is_shipped = status == "shipped" or stability == "stable"

        for line_no, raw_line in enumerate(body_masked.splitlines(), start=1):
            line = raw_line.strip()
            if line.startswith("# "):
                title_text = line[2:].strip()
                m_title = TEMPORAL_MILESTONE_REGEX.search(title_text)
                if m_title:
                    raise ValidationError(
                        rule="temporal_contamination_in_title",
                        path=rel_path,
                        message=f"Living manual title contains temporal project management marker '{m_title.group(0)}'.",
                        actionable="Remove temporal milestone tags (e.g. '(Phase X)') from title. Record release delivery in changelog/ instead.",
                    )
                if is_shipped:
                    m_spec = SHIPPED_SPECIFICATION_REGEX.search(title_text)
                    if m_spec:
                        raise ValidationError(
                            rule="shipped_specification_title",
                            path=rel_path,
                            message="Shipped living manual title contains 'specification'.",
                            actionable="Rename title to describe active capability directly (e.g. 'Feature — Subsystem') rather than a specification.",
                        )
            elif line.startswith("## ") or line.startswith("### "):
                heading_text = line.lstrip("#").strip()
                m_heading = TEMPORAL_MILESTONE_REGEX.search(heading_text)
                if m_heading:
                    raise ValidationError(
                        rule="temporal_contamination_in_heading",
                        path=rel_path,
                        message=f"Living manual heading contains temporal project management marker '{m_heading.group(0)}'.",
                        actionable="Remove temporal milestone tags from heading. Keep living manual structure timeless.",
                    )

    if check_workspace_targets and w_root and not (w_root / rel_path).exists():
        check_anti_sprawl_overlap(meta, rel_path, wiki_root=w_root)

    return content


SPRAWL_GUARD_TYPES: frozenset[str] = frozenset({
    "feature",
    "architecture",
    "product",
    "topic",
    "context",
})


def check_anti_sprawl_overlap(
    meta: dict[str, Any],
    path: str,
    wiki_root: Path | None = None,
    workspace_index: Any | None = None,
    overlay_fs: dict[str, str] | None = None,
) -> None:
    """Anti-Sprawl & Target Subsumption Guard on New Article Creation (AC-B2).

    Prevents creating redundant articles that govern code targets already governed by
    an active article of the exact same type, unless explicitly superseded or related.
    """
    declared_type = str(meta.get("type", "")).strip()
    if declared_type not in SPRAWL_GUARD_TYPES:
        return

    if meta.get("allow_overlapping_governance") is True:
        return

    from brain79.core.frontmatter import INACTIVE_STATUSES, PRE_IMPLEMENTATION_STATUSES

    status = str(meta.get("status", "")).lower()
    stability = str(meta.get("stability", "")).lower()
    if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
        return

    applies_val = meta.get("applies_to")
    if not applies_val:
        return

    raw_patterns = (
        [applies_val] if isinstance(applies_val, str) else [str(x) for x in applies_val if x]
    )
    if not raw_patterns:
        return

    from brain79.config import get_wiki_root
    from brain79.core.drift import find_matching_workspace_files
    from brain79.core.locks import normalize_wiki_rel_path, rel_posix

    try:
        w_root = (wiki_root or get_wiki_root()).resolve()
    except Exception:
        return

    p_root = w_root.parent

    # Dynamically extract known wiki directories from active schema
    try:
        from brain79.core.frontmatter import load_active_schema
        active_schema = load_active_schema(w_root)
        known_dirs = {prefix.split("/")[0] for prefix in active_schema.location_to_type.keys()}
    except Exception:
        known_dirs = {"decisions", "features", "architecture", "product", "topics", "context", "log", "changelog"}
    known_dirs.add(".brain-79")

    def _resolve_targets(pats: list[str]) -> set[str]:
        code_pats = [
            p.strip().lstrip("/")
            for p in pats
            if not any(
                p.strip().lstrip("/").startswith(f"{d}/") or p.strip().lstrip("/") == d
                for d in known_dirs
            )
        ]
        if not code_pats:
            return set()
        matched: set[str] = set()
        if workspace_index is not None and hasattr(workspace_index, "find_matching_files"):
            matched = set(workspace_index.find_matching_files(code_pats))
        elif p_root.exists():
            for p in find_matching_workspace_files(code_pats, p_root):
                try:
                    matched.add(rel_posix(p, p_root))
                except ValueError:
                    pass
        return matched if matched else set(code_pats)

    t_new = _resolve_targets(raw_patterns)
    if not t_new:
        return

    # Supersedes and related declarations on new article (normalized for .brain-79/ prefixes)
    supersedes_raw = meta.get("supersedes")
    supersedes_list = (
        [supersedes_raw] if isinstance(supersedes_raw, str) else [str(x) for x in (supersedes_raw or []) if x]
    )
    supersedes_norm = {
        normalize_wiki_rel_path(p).removesuffix(".md") for p in supersedes_list
    } | {normalize_wiki_rel_path(p) for p in supersedes_list}

    related_raw = meta.get("related")
    related_list = (
        [related_raw] if isinstance(related_raw, str) else [str(x) for x in (related_raw or []) if x]
    )
    related_norm = {
        normalize_wiki_rel_path(p).removesuffix(".md") for p in related_list
    } | {normalize_wiki_rel_path(p) for p in related_list}

    rel_path_clean = normalize_wiki_rel_path(path)

    # Collect existing and overlay candidate articles
    candidates: list[tuple[str, dict[str, Any]]] = []

    if overlay_fs:
        for ov_path, ov_content in overlay_fs.items():
            norm_ov = normalize_wiki_rel_path(ov_path)
            if norm_ov == rel_path_clean or norm_ov in ("INDEX.md", "SCHEMA.md"):
                continue
            if norm_ov.startswith("_raw/") or norm_ov.startswith(".locks/"):
                continue
            try:
                from brain79.core.frontmatter import parse_frontmatter
                meta_ov, _ = parse_frontmatter(ov_content)
                if meta_ov:
                    candidates.append((norm_ov, meta_ov))
            except Exception:
                continue

    overlay_paths = {c[0] for c in candidates}

    for md_file in sorted(w_root.rglob("*.md")):
        rel_e = md_file.relative_to(w_root).as_posix()
        if rel_e == rel_path_clean or rel_e in ("INDEX.md", "SCHEMA.md"):
            continue
        if rel_e.startswith("_raw/") or rel_e.startswith(".locks/"):
            continue
        if rel_e in overlay_paths:
            continue

        try:
            from brain79.core.frontmatter import parse_frontmatter
            content_e = md_file.read_text(encoding="utf-8")
            meta_e, _ = parse_frontmatter(content_e)
            if meta_e:
                candidates.append((rel_e, meta_e))
        except Exception:
            continue

    non_active = INACTIVE_STATUSES | PRE_IMPLEMENTATION_STATUSES

    # Scan candidate articles of the same type
    for rel_e, meta_e in candidates:
        if str(meta_e.get("type", "")).strip() != declared_type:
            continue

        status_e = str(meta_e.get("status", "")).lower()
        stability_e = str(meta_e.get("stability", "")).lower()
        if status_e in non_active or stability_e in non_active:
            continue

        applies_e = meta_e.get("applies_to")
        if not applies_e:
            continue

        raw_patterns_e = (
            [applies_e] if isinstance(applies_e, str) else [str(x) for x in applies_e if x]
        )
        t_e = _resolve_targets(raw_patterns_e)
        if not t_e:
            continue

        intersection = t_new & t_e
        if not intersection:
            continue

        rel_e_clean = rel_e.removesuffix(".md")
        is_superseded = rel_e in supersedes_norm or rel_e_clean in supersedes_norm
        is_related = rel_e in related_norm or rel_e_clean in related_norm

        # Case 1 — Full Target Subsumption (T_new subset of T_E)
        if t_new.issubset(t_e):
            if is_superseded:
                continue
            overlapping_str = ", ".join(sorted(list(intersection))[:5])
            if len(intersection) > 5:
                overlapping_str += f" and {len(intersection) - 5} more"
            raise ValidationError(
                rule="duplicate_governance_target",
                path=rel_path_clean,
                message=f"Anti-sprawl guard: existing active article '{rel_e}' of type '{declared_type}' already governs {overlapping_str}.",
                actionable=f"Use brain79_edit to update '{rel_e}' organically instead of creating a duplicate article, or declare 'supersedes: {rel_e}'.",
            )

        # Case 2 — Partial Target Overlap (Jaccard >= 0.65)
        union = t_new | t_e
        jaccard = len(intersection) / len(union)
        if jaccard >= 0.65:
            if is_superseded or is_related:
                continue
            overlapping_str = ", ".join(sorted(list(intersection))[:5])
            if len(intersection) > 5:
                overlapping_str += f" and {len(intersection) - 5} more"
            raise ValidationError(
                rule="duplicate_governance_target",
                path=rel_path_clean,
                message=f"Anti-sprawl guard: existing active article '{rel_e}' of type '{declared_type}' overlaps {len(intersection)} code targets ({int(jaccard * 100)}% Jaccard index: {overlapping_str}).",
                actionable=f"Use brain79_edit to update '{rel_e}' organically, or declare 'supersedes: {rel_e}' or link '{rel_e}' in 'related'.",
            )


def extract_h2_headers(content: str) -> list[str]:
    """Extract all ## H2 heading titles from markdown content, masking code blocks."""
    masked = _mask_code_fences(content)
    headers: list[str] = []
    for line in masked.splitlines():
        if line.startswith("## "):
            headers.append(line[3:].strip())
    return headers


def check_missing_sections(
    content: str,
    target_type: str,
    schema: Any | None = None,
) -> list[str]:
    """Check if content is missing any required H2 sections for the target type.

    Supports synonyms/alternatives when a required section is defined as a list of acceptable titles.
    Decisions strictly require standard ADR sections.
    Inactive articles (superseded, deprecated, rejected, archived, legacy) are exempted.
    Matches headings using exact match or boundary phrases (avoiding partial substring accidents).
    """
    from brain79.core.frontmatter import load_active_schema, parse_frontmatter

    # Exemption for inactive statuses
    try:
        from brain79.core.frontmatter import INACTIVE_STATUSES, parse_frontmatter
        meta, _ = parse_frontmatter(content)
        status = str(meta.get("status", "")).lower()
        stability = str(meta.get("stability", "")).lower()
        if status in INACTIVE_STATUSES or stability in INACTIVE_STATUSES:
            return []
    except Exception:
        pass

    active = schema or load_active_schema()
    type_cfg = active.types.get(target_type, {})
    req_sections = type_cfg.get("required_sections", [])
    if not req_sections:
        return []

    present_headers = extract_h2_headers(content)
    normalized_headers = [h.strip().lower() for h in present_headers]

    # Any valid H2 section is structurally sound for topic and context across profiles
    if target_type in ("topic", "context"):
        if present_headers:
            return []

    missing: list[str] = []
    for req in req_sections:
        if isinstance(req, str):
            req_name = req
            candidates = [req.lower()]
        else:
            req_name = req[0]
            candidates = [c.lower() for c in req]

        matched = False
        for c in candidates:
            for nh in normalized_headers:
                # 1. Exact match (e.g. "status" == "status", "overview" == "overview")
                if nh == c:
                    matched = True
                    break
                # 2. Strict prefix/suffix match (e.g. "adr status", "decision consequences", "system overview")
                if nh.startswith(c + " ") or nh.endswith(" " + c):
                    matched = True
                    break
                # 3. Word boundary regex match for multi-word phrases (e.g. "general description", "executive summary")
                if " " in c and re.search(rf"\b{re.escape(c)}\b", nh):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            missing.append(req_name)

    return missing
