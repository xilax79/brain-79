"""
Single-call cold start orientation orchestrator and 3-signal context ranker.

Combines:
1. Routing Table (INDEX.md).
2. Active Handoff State (latest handoff summary, pending work, boot instruction, and promo warnings).
3. Governing Knowledge Articles (inlining content of top ranked articles via 3-signal context ranker).
"""

from pathlib import Path
import subprocess
from typing import Any

from brain79.config import get_project_root, get_wiki_root
from brain79.core.context import rank_context_articles
from brain79.core.frontmatter import parse_frontmatter
from brain79.core.handoff import (
    HANDOFF_ESCALATION_AGE_DAYS,
    HANDOFF_ESCALATION_COMMITS,
    _resolve_handoff_path,
    read_handoff,
)
from brain79.core.handoff_freshness import compute_handoff_freshness
from brain79.core.locks import normalize_posix_input
from brain79.core.navigation import extract_title_and_summary
from brain79.core.wiki import get_index, read_article

MAX_ORIENT_INLINE_CHARS = 64_000


def _parse_semver(version_str: str) -> tuple[int, int, int] | None:
    """Parse leading (major, minor, patch) from a semantic version string (including pre-release/dev suffixes)."""
    import re

    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", version_str.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _forward_skew_notice(running_version: str) -> str:
    return (
        f"> ℹ️ **Protocol update available**: Project templates predate brain79 v{running_version}. "
        "Run 'brain79 update-project' to sync AGENTS.md and SCHEMA.md."
    )


def check_protocol_version_skew(project_root: Path, wiki_root: Path) -> str | None:
    """Inspect AGENTS.md delimiter version and SCHEMA.md schema_version for protocol skew."""
    from brain79 import __version__
    from brain79.core.init_project import AGENTS_START_REGEX

    agents_file = project_root / "AGENTS.md"
    if not agents_file.is_file():
        return _forward_skew_notice(__version__)

    try:
        content = agents_file.read_text(encoding="utf-8")
        m_start = AGENTS_START_REGEX.search(content)
        if not m_start:
            return _forward_skew_notice(__version__)
        version_in_block = m_start.group(1)
        if not version_in_block:
            return _forward_skew_notice(__version__)
        running_ver = _parse_semver(__version__)
        block_ver = _parse_semver(version_in_block)
        if running_ver is not None and block_ver is not None:
            if running_ver < block_ver:
                return (
                    f"> ⚠️ **Stale brain79 server/CLI detected**: Running brain79 v{__version__} is older than "
                    f"project protocol templates (v{version_in_block}). "
                    "Restart your MCP client/server or run 'brain79 update' to upgrade."
                )
            if running_ver > block_ver:
                return _forward_skew_notice(__version__)
        elif version_in_block != __version__:
            return _forward_skew_notice(__version__)
    except Exception:
        return _forward_skew_notice(__version__)

    schema_file = wiki_root / "SCHEMA.md"
    if not schema_file.is_file():
        return _forward_skew_notice(__version__)

    try:
        s_meta, _ = parse_frontmatter(schema_file.read_text(encoding="utf-8"))
        schema_version = int(s_meta.get("schema_version", 1))
        if schema_version < 2:
            return _forward_skew_notice(__version__)
    except Exception:
        return _forward_skew_notice(__version__)

    return None


def orient(
    task: str | None = None,
    paths: list[str] | None = None,
    max_articles: int = 4,
    wiki_root: Path | None = None,
    *,
    workspace_index: Any = None,
    git_cache: Any = None,
) -> str:
    """
    Execute 1-call cold start orientation.

    Args:
        task: Optional high-level goal or task description.
        paths: Optional list of workspace file paths the agent intends to touch.
        max_articles: Maximum number of governing articles to inline (default: 4).
        wiki_root: Optional custom wiki root path.
        workspace_index: Optional pre-built WorkspaceIndex to reuse.
        git_cache: Optional pre-built GitSessionCache to reuse.

    Returns:
        Structured markdown combining navigation, handoff state, and governing articles.
    """
    w_root = (wiki_root or get_wiki_root()).resolve()
    if workspace_index is not None:
        p_root = workspace_index.project_root
    else:
        p_root = (w_root.parent if w_root.parent.exists() else get_project_root()).resolve()

    sections: list[str] = [
        "# Brain-79 — Session Cold Start Orientation",
        "",
    ]

    skew_notice = check_protocol_version_skew(p_root, w_root)
    if skew_notice:
        sections.append(skew_notice)
        sections.append("")

    sections.append("## 🗺️ Project Index (Routing Table)")

    # 1. INDEX.md / Routing Table
    try:
        index_content = get_index(wiki_root=w_root)
        sections.append(index_content.strip())
    except Exception as exc:
        sections.append(f"*Could not read INDEX.md: {exc}*")

    # 2. Active Schema Summary
    sections.extend(["", "---", "", "## 📐 Active Schema Summary"])
    try:
        from brain79.core.frontmatter import load_active_schema

        active_schema = load_active_schema(w_root)
        sections.append(f"- **Profile:** `{active_schema.profile}`")
        sections.append(f"- **Enforcement:** `{active_schema.enforcement}`")
        sections.append("- **Managed Directories:**")
        for loc, tname in sorted(active_schema.location_to_type.items()):
            tcfg = active_schema.types.get(tname, {})
            req_fields = ", ".join(f"`{f}`" for f in tcfg.get("required", []))
            extra_note = ""
            if active_schema.profile == "software" and loc in ("architecture", "features"):
                if active_schema.enforcement == "strict":
                    extra_note = "; `applies_to` is strict-required"
                else:
                    extra_note = "; `applies_to` is recommended"
            sections.append(f"  - `{loc}/` → type: `{tname}` (required: {req_fields}{extra_note})")
    except Exception as exc:
        sections.append(f"*Could not load active schema: {exc}*")

    sections.extend(["", "---", ""])

    # Advisory prompt if architectural decision deficit exists
    try:
        from brain79.core.lint_organizational import check_architectural_decision_deficit

        adr_issues = check_architectural_decision_deficit(w_root)
        if adr_issues:
            sections.extend([
                f"> 💡 **Advisory**: {adr_issues[0].message} {adr_issues[0].actionable}",
                "",
            ])
    except Exception:
        pass

    # Operation-scoped WorkspaceIndex and shared GitSessionCache (built once per orient invocation)
    from brain79.core.drift import WorkspaceIndex, detect_all_drift
    from brain79.core.git_ops import GitSessionCache

    if git_cache is None:
        git_cache = getattr(workspace_index, "git_cache", None) or GitSessionCache()
    ws = workspace_index if workspace_index is not None else WorkspaceIndex.build(p_root, w_root, git_cache=git_cache)

    # 3. Latest Handoff
    try:
        target_handoff = _resolve_handoff_path("latest", wiki_root=w_root)
        freshness = compute_handoff_freshness(
            target_handoff,
            wiki_root=w_root,
            workspace_index=ws,
            git_cache=git_cache,
        )
        handoff_content, has_promotion_pending = read_handoff(
            "latest",
            wiki_root=w_root,
            for_orient=True,
            freshness=freshness,
        )
        if has_promotion_pending:
            sections.append(
                "> ⚠️ **Knowledge pending promotion**: the prior session noted critical insights "
                "pending distillation into the permanent wiki. Review and promote when appropriate.\n"
            )
        sections.append(handoff_content.strip())

        # Escalation of aging pending work
        raw_handoff_text = target_handoff.read_text(encoding="utf-8")
        has_pending_work = (
            "## Pending work" in raw_handoff_text
            or "## Trabajo pendiente" in raw_handoff_text
        )
        age_exceeded = freshness.age_seconds >= 86400 * HANDOFF_ESCALATION_AGE_DAYS
        commits_exceeded = (
            freshness.commits_since is not None
            and freshness.commits_since >= HANDOFF_ESCALATION_COMMITS
        )
        if has_pending_work and (age_exceeded or (commits_exceeded and freshness.state != "fresh")):
            sections.append(
                "\n> ⚠️ **Pending work in this handoff is aging**: promote long-lived items "
                "to the roadmap or backlog (architecture/ or topics/), or run `brain79 handoff-purge`."
            )
    except FileNotFoundError:
        sections.extend([
            "## ⏱️ Active handoff state",
            "No prior handoff found (`handoffs/` is empty). Ready for first session.",
        ])
    except Exception as exc:
        sections.extend([
            "## ⏱️ Active handoff state",
            f"*Could not load latest handoff: {exc}*",
        ])

    # 3. Governing Knowledge Articles (3-Signal Ranker)
    if workspace_index is not None:
        p_root = workspace_index.project_root
    else:
        p_root = (w_root.parent if w_root.parent.exists() else get_project_root()).resolve()

    # Unconditional Git working-tree path discovery (even when task=None, paths=None)
    discovered_paths: list[str] = []
    try:
        from brain79.core.git_ops import GitError, git_dirty_paths

        discovered_paths = git_dirty_paths(p_root, exclude_prefix=".brain-79/", timeout=2.0)[:50]
    except (GitError, OSError):
        discovered_paths = []

    effective_paths: list[str] = []
    if paths:
        for p in paths:
            clean_p = normalize_posix_input(p).lstrip("/")
            if clean_p and clean_p not in effective_paths:
                effective_paths.append(clean_p)
    for dp in discovered_paths:
        if dp not in effective_paths:
            effective_paths.append(dp)

    # Unconditional drift detection across entire wiki
    all_drifts = detect_all_drift(
        wiki_root=w_root,
        project_root=p_root,
        workspace_index=ws,
        git_cache=git_cache,
    )

    seen_drifts: set[tuple[str, str, str]] = set()
    drift_alerts: list[str] = []
    for d in all_drifts:
        art_path = d.get("article_path", "")
        ws_file = d.get("workspace_file", d.get("target_file", ""))
        kind = d.get("drift_kind", "modified").upper()
        key = (art_path, ws_file, kind)
        if key not in seen_drifts:
            seen_drifts.add(key)
            tag = "[TRANSITIVE]" if kind == "TRANSITIVE" else "[DIRECT]"
            msg = d.get("message", f"governed file {ws_file} modified")
            drift_alerts.append(
                f"> ⚠️ **Documentation Drift Suspected** ({tag}): Article '{art_path}' governs '{ws_file}' "
                f"({msg}). Verify accuracy before proceeding."
            )

    if drift_alerts:
        sections.extend([
            "",
            "---",
            "",
            "## ⚠️ Documentation Drift Alerts",
            *drift_alerts,
            "",
            "> **Action**: Update drifted articles via `brain79_edit` or `brain79_session_commit`, or pass eligible "
            "internal leaf code refactors in `verified_articles=[{\"path\": \"...\", \"reason\": \"...\"}]` "
            "during `brain79_session_commit`.",
        ])

    if task or effective_paths:
        sections.extend(["", "---", "", "## 📖 Governing Knowledge Articles"])
        effective_max = max(1, max_articles) if max_articles > 0 else 4
        ranked = rank_context_articles(
            task=task,
            paths=effective_paths if effective_paths else None,
            top_n=effective_max,
            wiki_root=w_root,
        )

        if not ranked:
            sections.append("No specific governing articles matched the task or paths.")
        else:
            inlined_count = 0
            surfaced_rels: set[str] = set()
            manifest_articles: list[tuple[str, str, str, str]] = []
            current_chars = sum(len(s) for s in sections)

            for score, article_p, reasons in ranked:
                try:
                    rel_p = article_p.relative_to(w_root).as_posix()
                    if rel_p in ("INDEX.md", "SCHEMA.md"):
                        continue
                    content = read_article(rel_p, wiki_root=w_root)
                    reasons_str = ", ".join(reasons)
                    article_header = f"### === Article: {rel_p} ===\n*Relevance Score: {score:.1f} | Match Signals: {reasons_str}*\n\n"
                    article_block = article_header + content.strip() + "\n\n"

                    if manifest_articles or (current_chars + len(article_block) > MAX_ORIENT_INLINE_CHARS):
                        meta, body = parse_frontmatter(content)
                        summary = str(meta.get("summary") or "").strip()
                        if not summary:
                            _, summary = extract_title_and_summary(content)
                        applies = meta.get("applies_to", [])
                        applies_list = [str(x) for x in applies] if isinstance(applies, list) else ([str(applies)] if applies else [])
                        applies_str = ", ".join(f"`{a}`" for a in applies_list) if applies_list else "*(none)*"

                        h2_headers = [
                            line.removeprefix("## ").strip()
                            for line in body.splitlines()
                            if line.strip().startswith("## ")
                        ]
                        h2_str = ", ".join(h2_headers) if h2_headers else "*(none)*"
                        manifest_articles.append((rel_p, summary, applies_str, h2_str))
                        surfaced_rels.add(rel_p)
                    else:
                        sections.append(f"### === Article: {rel_p} ===")
                        sections.append(f"*Relevance Score: {score:.1f} | Match Signals: {reasons_str}*")
                        sections.append("")
                        sections.append(content.strip())
                        sections.append("")
                        current_chars += len(article_block)
                        inlined_count += 1
                        surfaced_rels.add(rel_p)
                except Exception:
                    continue

            if inlined_count == 0 and not manifest_articles:
                sections.append("No governing articles inlined.")

            if manifest_articles:
                sections.extend([
                    "---",
                    "",
                    "## 🚨 Mandatory Reading Manifest (Must Read Before Editing)",
                    "",
                    "The governing context exceeds the 64,000-character inline budget. The following governing articles "
                    "must be read using `brain79_read_batch(paths=[...])` before modifying code or documentation:",
                    "",
                ])
                for rel_p, summary, applies_str, h2_str in manifest_articles:
                    sections.append(f"- **`{rel_p}`**: {summary}")
                    sections.append(f"  - **Governs (`applies_to`)**: {applies_str}")
                    sections.append(f"  - **Key Sections**: {h2_str}")

            if task and not paths:
                from brain79.core.context import get_wiki_snapshot
                from brain79.core.frontmatter import INACTIVE_STATUSES

                unread_active: list[str] = []
                for snap_p in get_wiki_snapshot(wiki_root=w_root):
                    snap_rel = snap_p.relative_to(w_root).as_posix()
                    if snap_rel in ("INDEX.md", "SCHEMA.md") or snap_rel in surfaced_rels:
                        continue
                    try:
                        snap_text = snap_p.read_text(encoding="utf-8")
                        snap_meta, _ = parse_frontmatter(snap_text) if snap_text.startswith("---\n") else ({}, snap_text)
                        s_status = str((snap_meta or {}).get("status", "")).lower()
                        s_stability = str((snap_meta or {}).get("stability", "")).lower()
                        if s_status in INACTIVE_STATUSES or s_stability in INACTIVE_STATUSES:
                            continue
                    except Exception:
                        pass
                    unread_active.append(snap_rel)

                if unread_active:
                    shown = unread_active[:20]
                    extra = len(unread_active) - len(shown)
                    paths_arg = ", ".join(f'"{p}"' for p in shown)
                    suffix = f" (+{extra} more in INDEX.md)" if extra > 0 else ""
                    sections.extend([
                        "",
                        f"> **Unread active articles ({len(unread_active)} remaining)**: fetch via "
                        f"`brain79_read_batch(paths=[{paths_arg}])`{suffix}.",
                    ])

    return "\n".join(sections)


orient_session = orient

